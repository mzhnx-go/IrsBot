import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { AgentService } from "@/client"

export interface ToolCall {
  name: string
  phase: "start" | "end"
  /** 工具入参（后端序列化为字符串并截断） */
  input?: string
  /** 工具结果（end 阶段带回） */
  output?: string
}

export interface ChatMessage {
  id: string
  /** 数据库消息 ID（history 恢复或 done 事件回填；本地乐观新增时为空） */
  dbId?: string
  role: "user" | "assistant"
  content: string
  toolCalls?: ToolCall[]
  streaming?: boolean
  /** 本轮被用户中断，回复是半成品 */
  stopped?: boolean
  /** 后端生成失败的中文化错误提示气泡 */
  error?: boolean
}

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed"

// 重连退避：指数增长封顶，超过上限判定为彻底断开
const MAX_RECONNECT = 6

// 模块级：useCustomToast 每次渲染返回新函数，不能进 WS effect 的依赖
// （否则 effect 反复重建 → 重连风暴）。全中文文案，不复用其英文标题。
const errorToast = (description: string) => {
  toast.error(description)
}

export function useAgentChat(conversationId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [connState, setConnState] = useState<ConnectionState>("connecting")
  const [isStreaming, setIsStreaming] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)

  const isConnected = connState === "open"

  useEffect(() => {
    // 给"最后一条 assistant 消息"追加文字；没有就新建一条
    const appendAssistantChunk = (chunk: string) => {
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last?.role !== "assistant") {
          // 新建一条 AI 消息
          return [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: chunk,
              streaming: true,
            },
          ]
        }
        // 在后面续字
        return [
          ...prev.slice(0, -1),
          { ...last, content: last.content + chunk },
        ]
      })
    }

    // ─── 建连 ───
    // WebSocket 地址必须**动态**从当前页面推导，不能烤进构建产物：
    //   ws  : 页面是 https 时用 wss（否则浏览器拦截混合内容），否则 ws
    //   host: 直接用 location.host → 谁在托管页面就连谁（同源）
    //
    // ⚠️ 不要写成 import.meta.env.VITE_API_URL.replace(/^http/, "ws")：
    //    VITE_API_URL 改为相对路径（如 "/api"）后，字符串里没有 "http"，
    //    正则替换**静默失效** → 得到 "/api/api/v1/..." 这种非法 ws 地址，
    //    表现为"WebSocket 连不上"但看不出原因。
    const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl =
      `${wsProtocol}//${location.host}` +
      `/api/v1/agent/chat/ws/${conversationId}` +
      `?token=${localStorage.getItem("access_token")}`

    // 连接与自动重连：非主动关闭（切换会话/卸载）导致的断开，
    // 按指数退避重连；后端重连后会重新推 history，前端据此对齐真实落库状态。
    let closedIntentionally = false
    let attempt = 0
    let reconnectTimer: number | undefined
    let ws: WebSocket

    const connect = () => {
      setConnState(attempt === 0 ? "connecting" : "reconnecting")
      ws = new WebSocket(wsUrl)
      wsRef.current = ws

      // 只让"当前连接"更新状态。
      // StrictMode 下 effect 会跑两次：旧连接 close 的 onclose 是异步触发的，
      // 若不判断，会把新连接刚建立的 isConnected=true 覆盖成 false
      ws.onopen = () => {
        if (wsRef.current !== ws) return
        attempt = 0
        setConnState("open")
      }

      ws.onmessage = (event) => {
        if (wsRef.current !== ws) return
        const msg = JSON.parse(event.data)

        if (msg.type === "history") {
          // 建连后后端推送的历史消息，据此恢复已有对话（刷新不丢）
          setMessages(
            (
              msg.messages as Array<{
                id?: string
                role: "user" | "assistant"
                content: string
                tool_calls?: ToolCall[]
                stopped?: boolean
              }>
            ).map((h) => ({
              id: h.id ?? crypto.randomUUID(),
              dbId: h.id,
              role: h.role,
              content: h.content,
              toolCalls: h.tool_calls,
              stopped: h.stopped,
              streaming: false,
            })),
          )
        } else if (msg.type === "text_chunk") {
          // AI 回复流式生成中，往最后一条 assistant 消息追加文字
          appendAssistantChunk(msg.content)
        } else if (msg.type === "tool_call") {
          // 与后端 merge_tool_trace 同口径：start 追加一条，
          // end 回填到同名最近一条未完成的 start，面板只留一行。
          // 注意：工具通常先于任何 text_chunk 触发，此时还没有 assistant
          // 消息，要先建一条空占位，否则事件会被直接丢掉、面板不出现。
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            const hasAssistant = last?.role === "assistant"
            const base = hasAssistant ? prev.slice(0, -1) : prev
            const target: ChatMessage = hasAssistant
              ? last
              : {
                  id: crypto.randomUUID(),
                  role: "assistant",
                  content: "",
                  streaming: true,
                }
            const calls = [...(target.toolCalls ?? [])]
            if (msg.phase === "start") {
              calls.push({
                name: msg.name,
                phase: "start",
                input: msg.input,
              })
            } else {
              let idx = -1
              for (let i = calls.length - 1; i >= 0; i--) {
                if (calls[i].name === msg.name && calls[i].phase === "start") {
                  idx = i
                  break
                }
              }
              if (idx >= 0)
                calls[idx] = {
                  ...calls[idx],
                  phase: "end",
                  output: msg.output,
                }
              else
                calls.push({
                  name: msg.name,
                  phase: "end",
                  output: msg.output,
                })
            }
            return [...base, { ...target, toolCalls: calls }]
          })
        } else if (msg.type === "done") {
          // 本轮回复结束；后端回传落库消息 ID，回填给本地乐观消息，
          // 之后删除/编辑重发/重新生成才能按 ID 调 REST
          setIsStreaming(false)
          setMessages((prev) => {
            let lastUser = -1
            let lastAssistant = -1
            prev.forEach((m, i) => {
              if (m.role === "user") lastUser = i
              if (m.role === "assistant") lastAssistant = i
            })
            return prev.map((m, i) => {
              let next = m
              if (m.streaming) next = { ...next, streaming: false }
              if (i === lastUser && msg.user_message_id)
                next = { ...next, dbId: msg.user_message_id }
              if (i === lastAssistant && msg.assistant_message_id)
                next = { ...next, dbId: msg.assistant_message_id }
              if (i === lastAssistant && msg.interrupted)
                next = { ...next, stopped: true }
              return next
            })
          })
        } else if (msg.type === "error") {
          // 后端生成异常：中文化提示以红字气泡固定展示（不是一闪而过的 toast）
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: msg.message || "回复生成失败，请稍后重试。",
              error: true,
            },
          ])
        }
      }

      ws.onclose = (event) => {
        if (wsRef.current !== ws || closedIntentionally) return
        setIsStreaming(false)
        // 4404 = 会话不存在/无权限：重连也没用，直接终态
        if (event.code === 4404) {
          setConnState("closed")
          return
        }
        if (attempt >= MAX_RECONNECT) {
          setConnState("closed")
          errorToast("连接已断开，请刷新页面重试")
          return
        }
        // 指数退避：1s / 2s / 4s …… 上限 ~13s
        const delay = Math.min(1000 * 2 ** attempt, 13000) + Math.random() * 400
        attempt += 1
        setConnState("reconnecting")
        reconnectTimer = window.setTimeout(connect, delay)
      }
    }

    connect()

    // ─── 清理：切换会话/卸载时关连接（不再自动重连） ───
    return () => {
      closedIntentionally = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [conversationId])

  const sendMessage = useCallback((content: string) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content },
    ])
    setIsStreaming(true)

    ws.send(JSON.stringify({ type: "message", content }))
  }, [])

  /** 中断当前生成：通知后端 cancel 本轮任务。
   *  真正的收尾（isStreaming 置假、部分回复落库）由后端随后的 done 事件驱动，
   *  这里不本地置状态，避免与 done 竞态导致半成品消息丢失 ID。 */
  const interrupt = useCallback(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: "interrupt" }))
  }, [])

  /** 截断本地状态：删掉 dbId 对应消息及其后的所有消息 */
  const truncateLocal = useCallback((dbId: string, inclusive: boolean) => {
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.dbId === dbId)
      if (idx < 0) return prev
      return idx === 0 && inclusive
        ? []
        : prev.slice(0, inclusive ? idx : idx + 1)
    })
  }, [])

  /** 删除单条消息 */
  const deleteMessage = useCallback(
    async (dbId: string) => {
      try {
        await AgentService.deleteConversationMessage({
          conversationId,
          messageId: dbId,
        })
        setMessages((prev) => prev.filter((m) => m.dbId !== dbId))
      } catch {
        errorToast("删除消息失败，请重试")
      }
    },
    [conversationId],
  )

  /** 重新生成：截掉最后一条用户消息及其后回复，重新发送同一问题 */
  const regenerate = useCallback(async () => {
    let target: ChatMessage | undefined
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        target = messages[i]
        break
      }
    }
    if (!target?.dbId || isStreaming) return
    try {
      await AgentService.truncateConversationMessages({
        conversationId,
        requestBody: { message_id: target.dbId, inclusive: true },
      })
      truncateLocal(target.dbId, true)
      sendMessage(target.content)
    } catch {
      errorToast("重新生成失败，请重试")
    }
  }, [messages, isStreaming, conversationId, truncateLocal, sendMessage])

  /** 编辑重发：改用户消息内容并删掉其后的所有消息，重新发送 */
  const editAndResend = useCallback(
    async (dbId: string, newContent: string) => {
      if (isStreaming) return
      try {
        await AgentService.truncateConversationMessages({
          conversationId,
          requestBody: { message_id: dbId, inclusive: true },
        })
        truncateLocal(dbId, true)
        sendMessage(newContent)
      } catch {
        errorToast("编辑重发失败，请重试")
      }
    },
    [isStreaming, conversationId, truncateLocal, sendMessage],
  )

  return {
    messages,
    isConnected,
    connState,
    isStreaming,
    sendMessage,
    interrupt,
    deleteMessage,
    regenerate,
    editAndResend,
  }
}

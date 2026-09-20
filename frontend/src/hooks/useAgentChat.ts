import { useCallback, useEffect, useRef, useState } from "react"

import { AgentService } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"

export interface ToolCall {
  name: string
  phase: "start" | "end"
}

export interface ChatMessage {
  id: string
  /** 数据库消息 ID（history 恢复或 done 事件回填；本地乐观新增时为空） */
  dbId?: string
  role: "user" | "assistant"
  content: string
  toolCalls?: ToolCall[]
  streaming?: boolean
}

export function useAgentChat(conversationId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const { showErrorToast } = useCustomToast()

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

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    // 只让"当前连接"更新状态。
    // StrictMode 下 effect 会跑两次：旧连接 close 的 onclose 是异步触发的，
    // 若不判断，会把新连接刚建立的 isConnected=true 覆盖成 false
    ws.onopen = () => {
      if (wsRef.current === ws) setIsConnected(true)
    }

    ws.onmessage = (event) => {
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
            }>
          ).map((h) => ({
            id: h.id ?? crypto.randomUUID(),
            dbId: h.id,
            role: h.role,
            content: h.content,
            toolCalls: h.tool_calls,
            streaming: false,
          })),
        )
      } else if (msg.type === "text_chunk") {
        // AI 回复流式生成中，往最后一条 assistant 消息追加文字
        appendAssistantChunk(msg.content)
      } else if (msg.type === "tool_call") {
        // 记录工具调用状态（start/end），追加到最后一条 assistant 消息
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last?.role !== "assistant") return prev
          return [
            ...prev.slice(0, -1),
            {
              ...last,
              toolCalls: [
                ...(last.toolCalls ?? []),
                { name: msg.name, phase: msg.phase },
              ],
            },
          ]
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
            return next
          })
        })
      }
    }

    ws.onclose = () => {
      if (wsRef.current === ws) setIsConnected(false)
    }

    // ─── 清理：切换会话/卸载时关连接 ───
    return () => {
      ws.close()
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
        showErrorToast("删除消息失败，请重试")
      }
    },
    [conversationId, showErrorToast],
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
      showErrorToast("重新生成失败，请重试")
    }
  }, [
    messages,
    isStreaming,
    conversationId,
    truncateLocal,
    sendMessage,
    showErrorToast,
  ])

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
        showErrorToast("编辑重发失败，请重试")
      }
    },
    [isStreaming, conversationId, truncateLocal, sendMessage, showErrorToast],
  )

  return {
    messages,
    isConnected,
    isStreaming,
    sendMessage,
    deleteMessage,
    regenerate,
    editAndResend,
  }
}

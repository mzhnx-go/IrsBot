import { useCallback, useEffect, useRef, useState } from "react"

export interface ToolCall {
  name: string
  phase: "start" | "end"
}

export interface ChatMessage {
  id: string
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
              role: "user" | "assistant"
              content: string
              tool_calls?: ToolCall[]
            }>
          ).map((h) => ({
            id: crypto.randomUUID(),
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
        // 本轮回复结束
        setIsStreaming(false)
        setMessages((prev) =>
          prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
        )
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

  // 给"最后一条 assistant 消息"追加文字；没有就新建一条
  // （定义在 useEffect 内部：它只服务于消息事件，也避免依赖数组警告）
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

  return { messages, isConnected, isStreaming, sendMessage }
}

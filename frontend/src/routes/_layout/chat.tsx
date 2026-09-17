import { createFileRoute } from "@tanstack/react-router"
import { ArrowUp } from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"

import { type ChatMessage, useAgentChat } from "@/hooks/useAgentChat"

export const Route = createFileRoute("/_layout/chat")({
  component: ChatPage,
})

/** 外层组件：负责创建会话（拿到真实 UUID），就绪后才挂载聊天室 */
function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false

    // 调后端 POST /agent/conversations，创建会话拿到真实 UUID
    const createConversation = async () => {
      try {
        // 用同源相对路径（与 main.tsx 的 OpenAPI.BASE = "" 保持一致）。
        // ⚠️ 不要把 VITE_API_URL 改成 "/api" 后再拼这里 —— 会得到
        //    "/api/api/v1/agent/conversations"（路径重复）。
        const res = await fetch("/api/v1/agent/conversations", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
          body: JSON.stringify({ title: "新对话" }),
        })
        if (!res.ok) {
          throw new Error(`创建会话失败（HTTP ${res.status}）`)
        }
        const data = await res.json()
        if (!cancelled) setConversationId(data.id)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      }
    }

    createConversation()
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return <div className="py-40 text-center text-destructive">{error}</div>
  }

  // 会话还没创建好，不能渲染聊天室（否则 WS 连到一个空 ID 上）
  if (!conversationId) {
    return (
      <div className="py-40 text-center text-muted-foreground">
        正在创建会话…
      </div>
    )
  }

  // 会话 ID 就绪 → 挂载聊天室。条件挂载组件是 React 合法模式
  return <ChatRoom conversationId={conversationId} />
}

/** 内层组件：conversationId 一定有效，useAgentChat 在这里调用 */
function ChatRoom({ conversationId }: { conversationId: string }) {
  const { messages, isConnected, isStreaming, sendMessage } =
    useAgentChat(conversationId)
  const [input, setInput] = useState("")

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const content = input.trim()
    if (!content || isStreaming) return
    sendMessage(content)
    setInput("")
  }

  return (
    <div className="flex min-h-[calc(100svh-4rem)] flex-col">
      <div className="mx-auto w-full max-w-3xl flex-1">
        {messages.length === 0 ? (
          <div className="py-40 text-center">
            <h1 className="text-2xl font-semibold">有什么可以帮你？</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {isConnected ? "连接就绪，输入消息开始对话" : "正在连接服务器…"}
            </p>
          </div>
        ) : (
          <div className="space-y-4 py-8">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
          </div>
        )}
      </div>

      {/* 底部输入框（仿千问）：多行长输入区 + 强调蓝圆形发送按钮
        动效：聚焦框 shadow 过渡 150ms；发送按钮 hover/按压微缩放 150ms；均有 reduced-motion 降级 */}
      <form
        onSubmit={handleSubmit}
        className="sticky bottom-4 mx-auto w-full max-w-3xl"
      >
        <div className="flex items-end gap-2 rounded-2xl border border-input bg-background px-4 py-2 shadow-sm transition-shadow duration-[150ms] ease-out focus-within:border-[var(--chat-accent)] focus-within:shadow-[0_0_0_3px_rgba(22,93,255,0.15)]">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={isStreaming ? "AI 回复中…" : "输入消息…"}
            rows={1}
            disabled={!isConnected}
            onKeyDown={(e) => {
              // Enter 发送，Shift+Enter 换行
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
            className="max-h-40 min-h-6 w-full resize-none bg-transparent py-1.5 text-sm leading-6 text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
          />
          <button
            type="submit"
            aria-label="发送"
            disabled={!input.trim() || isStreaming || !isConnected}
            className="flex size-8 shrink-0 items-center justify-center self-end rounded-full text-white transition-all duration-[150ms] ease-out hover:scale-[1.05] active:scale-90 motion-reduce:transform-none disabled:pointer-events-none disabled:scale-100 disabled:bg-muted disabled:text-muted-foreground"
            style={{
              // 可发送时用概念图强调蓝（token）；否则交给 disabled 灰态
              background:
                input.trim() && !isStreaming && isConnected
                  ? "var(--chat-accent)"
                  : undefined,
            }}
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </form>
    </div>
  )
}

/** 消息气泡：用户靠右、AI 靠左 */
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        }`}
      >
        {message.content}
        {/* 流式生成中的闪烁光标 */}
        {message.streaming && <span className="animate-pulse">▍</span>}
      </div>
    </div>
  )
}

export default ChatPage

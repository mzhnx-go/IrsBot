import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { ArrowUp } from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"

import { AgentService } from "@/client"
import { type ChatMessage, useAgentChat } from "@/hooks/useAgentChat"

export const Route = createFileRoute("/_layout/chat")({
  // 会话 ID 走 URL search param（/chat?c=<uuid>）：
  // - 侧边栏点会话 → 带 c 进入，直接恢复该会话
  // - 不带 c 进入 → effect 自动建新会话，再 replace 回写参数（不产生历史记录）
  validateSearch: (search: Record<string, unknown>) => ({
    c: typeof search.c === "string" && search.c ? search.c : undefined,
  }),
  component: ChatPage,
})

/** 外层组件：保证 URL 里有一个有效会话 ID，就绪后才挂载聊天室 */
function ChatPage() {
  const { c: conversationId } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState("")

  useEffect(() => {
    if (conversationId) return
    let cancelled = false

    // 没有会话 ID → 创建新会话并 replace 回写 ?c=（失败给错误态）
    AgentService.createConversation({
      requestBody: { title: "新对话" },
    })
      .then((conv) => {
        if (cancelled) return
        queryClient.invalidateQueries({ queryKey: ["conversations"] })
        navigate({
          to: "/chat",
          search: { c: conv.id },
          replace: true,
        })
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
        }
      })

    return () => {
      cancelled = true
    }
  }, [conversationId, navigate, queryClient])

  if (error) {
    return <div className="py-40 text-center text-destructive">{error}</div>
  }

  // 会话还没就绪，不能渲染聊天室（否则 WS 连到一个空 ID 上）
  if (!conversationId) {
    return (
      <div className="py-40 text-center text-muted-foreground">
        正在创建会话…
      </div>
    )
  }

  // key=conversationId：切换会话时整个聊天室（含 WS 连接）重建
  return <ChatRoom key={conversationId} conversationId={conversationId} />
}

/** 内层组件：conversationId 一定有效，useAgentChat 在这里调用 */
function ChatRoom({ conversationId }: { conversationId: string }) {
  const { messages, isConnected, isStreaming, sendMessage } =
    useAgentChat(conversationId)
  const [input, setInput] = useState("")
  const queryClient = useQueryClient()

  // 一轮对话结束（done）→ 刷新侧边栏列表：
  // 首条消息可能刚生成了新标题，且该会话的 updated_at 已变，应浮到最前
  useEffect(() => {
    if (!isStreaming) {
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    }
  }, [isStreaming, queryClient])

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
        className={
          isUser
            ? "max-w-[80%] rounded-2xl rounded-br-sm bg-[var(--chat-accent)] px-4 py-2.5 text-sm leading-6 text-white"
            : "max-w-[80%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2.5 text-sm leading-6 text-foreground"
        }
      >
        {/* 工具调用状态行（AI 消息且有工具调用时显示） */}
        {message.toolCalls?.map((tc, i) => (
          <p key={i} className="mb-1 text-xs text-muted-foreground">
            [{tc.phase === "start" ? "调用" : "完成"}] {tc.name}
          </p>
        ))}
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  )
}

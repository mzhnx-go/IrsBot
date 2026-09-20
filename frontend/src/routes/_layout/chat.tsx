import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { ArrowUp, Loader2, Square } from "lucide-react"
import { type FormEvent, useEffect, useRef, useState } from "react"
import { AgentService } from "@/client"
import ChatOnboarding from "@/components/Chat/ChatOnboarding"
import MessageItem from "@/components/Chat/MessageItem"
import PersonaPicker from "@/components/Chat/PersonaPicker"
import { useAgentChat } from "@/hooks/useAgentChat"

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
  const {
    messages,
    isConnected,
    connState,
    isStreaming,
    sendMessage,
    interrupt,
    deleteMessage,
    regenerate,
    editAndResend,
  } = useAgentChat(conversationId)
  const [input, setInput] = useState("")
  // 已点停止、等待后端收尾 done（done 到达后 isStreaming 置假自动复位）
  const [stopping, setStopping] = useState(false)
  const queryClient = useQueryClient()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isStreaming) setStopping(false)
  }, [isStreaming])

  // 新消息/流式增量时贴底；用户已上滑阅读历史时不打断
  // biome-ignore lint/correctness/useExhaustiveDependencies: messages 仅作"有新内容"触发器，读取的是 DOM 滚动几何
  useEffect(() => {
    const el = document.documentElement
    const nearBottom =
      el.scrollHeight - window.scrollY - window.innerHeight < 160
    if (nearBottom) bottomRef.current?.scrollIntoView({ block: "end" })
  }, [messages])

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
        {/* 会话人设选择器：右上角小控件，切换即绑定/解绑 */}
        <div className="flex justify-end pt-2">
          <PersonaPicker conversationId={conversationId} />
        </div>
        {/* 连接状态横幅：重连过程与终态都要让用户看得见（中文化） */}
        {messages.length > 0 &&
          connState !== "open" &&
          connState !== "connecting" && (
            <div
              role="status"
              className={`sticky top-3 z-10 mx-auto mt-4 flex w-fit items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs shadow-sm backdrop-blur ${
                connState === "closed"
                  ? "border-destructive/30 bg-destructive/10 text-destructive"
                  : "border-border bg-background/90 text-muted-foreground"
              }`}
            >
              {connState === "reconnecting" ? (
                <>
                  <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" />
                  连接已断开，正在自动重连…
                </>
              ) : (
                <>
                  连接已断开，发送已暂停
                  <button
                    type="button"
                    onClick={() => window.location.reload()}
                    className="rounded-full border border-current px-2 py-0.5 transition-opacity duration-100 hover:opacity-70"
                  >
                    刷新重试
                  </button>
                </>
              )}
            </div>
          )}
        {messages.length === 0 ? (
          <div className="flex flex-col gap-6 px-4 py-24 text-center md:py-32">
            {/* 没有任何模型源时先指路（配置闭环），有则隐藏 */}
            <ChatOnboarding />
            <div>
              <h1 className="text-xl font-semibold md:text-2xl">
                有什么可以帮你？
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                {connState === "open"
                  ? "连接就绪，输入消息开始对话"
                  : connState === "reconnecting"
                    ? "连接已断开，正在自动重连…"
                    : connState === "closed"
                      ? "连接已断开，请刷新页面重试"
                      : "正在连接服务器…"}
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4 py-8">
            {messages.map((m, i) => (
              <MessageItem
                key={m.id}
                message={m}
                isLast={i === messages.length - 1}
                disabled={isStreaming}
                onDelete={deleteMessage}
                onRegenerate={regenerate}
                onEditResend={editAndResend}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* 底部输入框（仿千问）：多行长输入区 + 强调蓝圆形发送按钮
        动效：聚焦框 shadow 过渡 150ms；发送按钮 hover/按压微缩放 150ms；均有 reduced-motion 降级 */}
      <form
        onSubmit={handleSubmit}
        // 底部留白叠加 iOS 安全区（home 指示条不遮住输入框）
        className="sticky bottom-4 mx-auto w-full max-w-3xl pb-[env(safe-area-inset-bottom)]"
      >
        <div className="flex items-end gap-2 rounded-2xl border border-input bg-background px-4 py-2 shadow-sm transition-shadow duration-[150ms] ease-out focus-within:border-[var(--chat-accent)] focus-within:shadow-[0_0_0_3px_rgba(22,93,255,0.15)]">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              isStreaming
                ? "AI 回复中…"
                : connState === "reconnecting"
                  ? "正在重连，请稍候…"
                  : connState === "closed"
                    ? "连接已断开，请刷新页面重试"
                    : "输入消息…"
            }
            rows={1}
            disabled={!isConnected}
            // 手机键盘右下角显示「发送」而非换行
            enterKeyHint="send"
            onKeyDown={(e) => {
              // Enter 发送，Shift+Enter 换行
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
            className="max-h-40 min-h-6 w-full resize-none bg-transparent py-1.5 text-sm leading-6 text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
          />
          {isStreaming ? (
            /* 流式中：发送按钮变身为停止按钮；点击发 interrupt，
               等后端收尾 done 后 isStreaming 自动置假复位 */
            <button
              type="button"
              aria-label="停止生成"
              onClick={() => {
                setStopping(true)
                interrupt()
              }}
              className="flex size-8 shrink-0 items-center justify-center self-end rounded-full bg-[var(--chat-accent)] text-white transition-transform duration-[150ms] ease-out hover:scale-[1.05] active:scale-90 motion-reduce:transform-none"
            >
              {stopping ? (
                <Loader2 className="size-4 animate-spin motion-reduce:animate-none" />
              ) : (
                <Square className="size-3 fill-current" />
              )}
            </button>
          ) : (
            <button
              type="submit"
              aria-label="发送"
              disabled={!input.trim() || !isConnected}
              className="flex size-8 shrink-0 items-center justify-center self-end rounded-full text-white transition-all duration-[150ms] ease-out hover:scale-[1.05] active:scale-90 motion-reduce:transform-none disabled:pointer-events-none disabled:scale-100 disabled:bg-muted disabled:text-muted-foreground"
              style={{
                // 可发送时用概念图强调蓝（token）；否则交给 disabled 灰态
                background:
                  input.trim() && isConnected
                    ? "var(--chat-accent)"
                    : undefined,
              }}
            >
              <ArrowUp className="size-4" />
            </button>
          )}
        </div>
      </form>
    </div>
  )
}

import {
  ArrowUp,
  Check,
  Copy,
  Pencil,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react"
import { type ReactNode, useState } from "react"
import { MessageAttachments } from "@/components/Chat/AttachmentChips"
import MarkdownContent from "@/components/Chat/MarkdownContent"
import Sources from "@/components/Chat/Sources"
import ToolCalls from "@/components/Chat/ToolCalls"
import type { ChatMessage } from "@/hooks/useAgentChat"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"

interface MessageItemProps {
  message: ChatMessage
  /** 最后一条消息才允许重新生成 */
  isLast: boolean
  /** 流式生成中禁用一切操作 */
  disabled: boolean
  onDelete: (dbId: string) => void
  onRegenerate: () => void
  onEditResend: (dbId: string, newContent: string) => void
}

const ActionButton = ({
  label,
  onClick,
  children,
}: {
  label: string
  onClick: () => void
  children: ReactNode
}) => (
  <button
    type="button"
    title={label}
    aria-label={label}
    onClick={onClick}
    className="rounded-md p-1.5 text-muted-foreground transition-colors duration-100 hover:bg-muted hover:text-foreground active:scale-95"
  >
    {children}
  </button>
)

const MessageItem = ({
  message,
  isLast,
  disabled,
  onDelete,
  onRegenerate,
  onEditResend,
}: MessageItemProps) => {
  const isUser = message.role === "user"
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(message.content)
  const [, copy] = useCopyToClipboard()

  const canAct = !!message.dbId && !disabled && !message.streaming

  const handleCopy = () => {
    copy(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleSaveEdit = () => {
    const content = draft.trim()
    if (!content || !message.dbId) return
    setEditing(false)
    onEditResend(message.dbId, content)
  }

  if (editing) {
    return (
      <div className="flex justify-end">
        <div className="w-full max-w-[80%] rounded-2xl border border-input bg-background p-3 shadow-sm">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={Math.min(8, Math.max(2, draft.split("\n").length + 1))}
            // biome-ignore lint/a11y/noAutofocus: 点击编辑后应立即进入可输入态
            autoFocus
            className="w-full resize-none bg-transparent text-sm leading-6 outline-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSaveEdit()
              }
              if (e.key === "Escape") setEditing(false)
            }}
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="flex items-center gap-1 rounded-full border px-3 py-1 text-xs text-muted-foreground transition-colors duration-100 hover:text-foreground"
            >
              <X className="size-3" /> 取消
            </button>
            <button
              type="button"
              onClick={handleSaveEdit}
              disabled={!draft.trim()}
              className="flex items-center gap-1 rounded-full bg-[var(--chat-accent)] px-3 py-1 text-xs text-white transition-transform duration-100 active:scale-95 disabled:opacity-50"
            >
              <ArrowUp className="size-3" /> 保存并重新发送
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      className={
        isUser
          ? "group flex flex-col items-end"
          : "group flex flex-col items-start"
      }
    >
      <div
        className={
          isUser
            ? "max-w-[80%] rounded-2xl rounded-br-sm bg-[var(--chat-accent)] px-4 py-2.5 text-sm leading-6 text-white"
            : message.error
              ? "max-w-[85%] rounded-2xl rounded-bl-sm border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm leading-6 text-destructive"
              : "max-w-[85%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2.5 text-foreground"
        }
      >
        {/* 工具调用折叠面板（AI 消息且有工具调用时显示） */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolCalls calls={message.toolCalls} />
        )}
        {/* 用户消息携带的附件（文件名 chip；图片字节不内联展示） */}
        {isUser && message.attachments && message.attachments.length > 0 && (
          <MessageAttachments items={message.attachments} />
        )}
        {isUser || message.error ? (
          // 只发附件没打字时正文为空，空段落会在气泡里留一段空白
          message.content ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : null
        ) : (
          <MarkdownContent
            content={message.content}
            streaming={message.streaming}
          />
        )}
      </div>

      {/* RAG 检索来源：气泡下方可折叠列表 */}
      {!isUser && message.citations && message.citations.length > 0 && (
        <div className="mt-1.5 w-full max-w-[85%]">
          <Sources citations={message.citations} />
        </div>
      )}

      {/* 被中断的半成品回复：明确标注，避免误以为回复完整 */}
      {!isUser && message.stopped && (
        <p className="mt-1 text-xs text-muted-foreground">已停止生成</p>
      )}

      {/* 悬停操作条：触屏无 hover，常驻显示 */}
      <div
        className={`mt-1 flex gap-0.5 transition-opacity duration-150 ${
          canAct
            ? "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100"
            : "hidden"
        }`}
      >
        <ActionButton label={copied ? "已复制" : "复制"} onClick={handleCopy}>
          {copied ? (
            <Check className="size-3.5" />
          ) : (
            <Copy className="size-3.5" />
          )}
        </ActionButton>
        {isUser && (
          <ActionButton
            label="编辑重发"
            onClick={() => {
              setDraft(message.content)
              setEditing(true)
            }}
          >
            <Pencil className="size-3.5" />
          </ActionButton>
        )}
        {isLast && !isUser && (
          <ActionButton label="重新生成" onClick={onRegenerate}>
            <RefreshCw className="size-3.5" />
          </ActionButton>
        )}
        <ActionButton label="删除" onClick={() => onDelete(message.dbId!)}>
          <Trash2 className="size-3.5" />
        </ActionButton>
      </div>
    </div>
  )
}

export default MessageItem

import {
  AlertCircle,
  FileText,
  Image as ImageIcon,
  Loader2,
  X,
} from "lucide-react"

import type { MessageAttachment } from "@/hooks/useAgentChat"
import type { PendingAttachment } from "@/hooks/useChatAttachments"

const formatBytes = (bytes: number) => {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * 输入框上方的待发送附件条。
 *
 * 三种状态各说各话：上传中显示转圈（此时不能发送）、失败标红并给原因、
 * 成功显示解析结果（文档"已解析 N 字"、图片给缩略图）。
 */
export function AttachmentChips({
  items,
  onRemove,
}: {
  items: PendingAttachment[]
  onRemove: (key: string) => void
}) {
  if (items.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap gap-2" data-testid="attachment-chips">
      {items.map((item) => (
        <div
          key={item.key}
          data-testid="attachment-chip"
          className={`group flex items-center gap-2 rounded-xl border px-2.5 py-1.5 text-xs ${
            item.status === "error"
              ? "border-destructive/40 bg-destructive/5 text-destructive"
              : "border-border bg-background text-foreground"
          }`}
        >
          {item.status === "uploading" ? (
            <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground motion-reduce:animate-none" />
          ) : item.status === "error" ? (
            <AlertCircle className="size-3.5 shrink-0" />
          ) : item.previewUrl ? (
            <img
              src={item.previewUrl}
              alt={item.filename}
              className="size-6 shrink-0 rounded object-cover"
            />
          ) : (
            <FileText className="size-3.5 shrink-0 text-muted-foreground" />
          )}

          <div className="flex min-w-0 flex-col">
            <span className="max-w-40 truncate">{item.filename}</span>
            <span className="text-[10px] text-muted-foreground">
              {item.status === "uploading"
                ? "上传中…"
                : item.status === "error"
                  ? (item.error ?? "上传失败")
                  : item.kind === "image"
                    ? `${formatBytes(item.size)} · 图片`
                    : `已解析 ${item.extractedChars ?? 0} 字${
                        item.truncated ? "（已截断）" : ""
                      }`}
            </span>
          </div>

          <button
            type="button"
            aria-label={`移除 ${item.filename}`}
            onClick={() => onRemove(item.key)}
            className="shrink-0 rounded-full p-0.5 text-muted-foreground transition-colors duration-100 hover:bg-muted hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        </div>
      ))}
    </div>
  )
}

/**
 * 已发送消息里的附件展示（气泡内只读）。
 *
 * 只渲染文件名 chip 而不内联图片：图片字节需要带鉴权才能取，
 * 为一张缩略图开口子不划算——真正要看图的是模型（S5 多模态直传）。
 */
export function MessageAttachments({
  items,
  tone = "inverted",
}: {
  items: MessageAttachment[]
  /** inverted：深色气泡内（用户消息），用半透明白字 */
  tone?: "inverted" | "default"
}) {
  if (items.length === 0) return null

  const chipClass =
    tone === "inverted"
      ? "border-white/30 bg-white/10 text-white"
      : "border-border bg-background text-foreground"

  return (
    <div className="mb-1.5 flex flex-wrap gap-1.5">
      {items.map((a) => (
        <span
          key={a.id}
          data-testid="message-attachment"
          title={`${a.filename} · ${formatBytes(a.size)}`}
          className={`flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${chipClass}`}
        >
          {a.kind === "image" ? (
            <ImageIcon className="size-3" />
          ) : (
            <FileText className="size-3" />
          )}
          <span className="max-w-40 truncate">{a.filename}</span>
        </span>
      ))}
    </div>
  )
}

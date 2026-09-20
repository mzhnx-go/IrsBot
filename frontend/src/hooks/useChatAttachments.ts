import { useCallback, useState } from "react"
import { toast } from "sonner"

import { AgentService, type Body_agent_upload_attachment } from "@/client"
import type { MessageAttachment } from "@/hooks/useAgentChat"

/** 待发送附件：上传/解析过程中的状态也在这里，发送时只取 status==="ready" 的 */
export interface PendingAttachment {
  /** 本地定位用 key（上传失败后也靠它删） */
  key: string
  filename: string
  size: number
  status: "uploading" | "ready" | "error"
  /** 上传成功后后端返回的 att_id */
  id?: string
  kind?: string
  extractedChars?: number | null
  truncated?: boolean
  /** 图片本地预览地址（objectURL，移除时必须 revoke） */
  previewUrl?: string
  error?: string
}

/** 文档白名单与后端 DocumentParser.SUPPORTED_EXTENSIONS 对齐 */
const DOC_EXTENSIONS = [".pdf", ".txt", ".md", ".docx"]
/** 图片白名单：后端按魔数复核，这里只是提前给反馈 */
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]

const DOC_MAX_BYTES = 20 * 1024 * 1024
const IMAGE_MAX_BYTES = 10 * 1024 * 1024
/** 与后端 attachments.MAX_PER_MESSAGE 一致 */
const MAX_PER_MESSAGE = 10

const extOf = (name: string) => {
  const i = name.lastIndexOf(".")
  return i < 0 ? "" : name.slice(i).toLowerCase()
}

const isDoc = (name: string) => DOC_EXTENSIONS.includes(extOf(name))
const isImage = (name: string) => IMAGE_EXTENSIONS.includes(extOf(name))

/** 前端预检：拦掉一眼就不合规的文件，省一次往返也省一次后端落盘 */
function precheck(file: File): string | null {
  if (!isDoc(file.name) && !isImage(file.name)) {
    return `不支持 ${extOf(file.name) || "该"} 格式，仅支持 ${DOC_EXTENSIONS.join("/")} 与图片`
  }
  const limit = isDoc(file.name) ? DOC_MAX_BYTES : IMAGE_MAX_BYTES
  if (file.size > limit) {
    return `文件超过 ${limit / 1024 / 1024}MB 上限`
  }
  return null
}

/**
 * 管理"这一轮待发送的附件"。
 *
 * 附件是**本轮有效**：上传即落盘、随消息发送，不进知识库也不跨轮复用。
 * 上传状态与消息发送解耦——用户可以边等解析边打字。
 */
export function useChatAttachments(conversationId: string) {
  const [pending, setPending] = useState<PendingAttachment[]>([])

  const remove = useCallback((key: string) => {
    setPending((prev) => {
      const target = prev.find((p) => p.key === key)
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl)
      return prev.filter((p) => p.key !== key)
    })
  }, [])

  const clear = useCallback(() => {
    setPending((prev) => {
      for (const p of prev) {
        if (p.previewUrl) URL.revokeObjectURL(p.previewUrl)
      }
      return []
    })
  }, [])

  const addFiles = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return

      // 先按当前条数判断是否超量：一次塞太多既无用也是后端拒绝的输入
      const room = MAX_PER_MESSAGE - pending.length
      if (room <= 0) {
        toast.error(`单条消息最多携带 ${MAX_PER_MESSAGE} 个附件`)
        return
      }
      const accepted = files.slice(0, room)
      if (accepted.length < files.length) {
        toast.error(
          `单条消息最多携带 ${MAX_PER_MESSAGE} 个附件，已忽略多余文件`,
        )
      }

      const prepared: PendingAttachment[] = []
      for (const file of accepted) {
        const problem = precheck(file)
        if (problem) {
          toast.error(`${file.name}：${problem}`)
          continue
        }
        prepared.push({
          key: crypto.randomUUID(),
          filename: file.name,
          size: file.size,
          status: "uploading",
          previewUrl: isImage(file.name)
            ? URL.createObjectURL(file)
            : undefined,
        })
      }
      if (prepared.length === 0) return
      setPending((prev) => [...prev, ...prepared])

      // 逐个上传：一个失败不影响其它，用户能只删掉坏的那个
      await Promise.all(
        accepted.map(async (file, i) => {
          const entry = prepared[i]
          if (!entry) return
          try {
            const res = await AgentService.uploadAttachment({
              // 传普通对象而非 FormData 实例：客户端 getFormData() 用
              // Object.entries() 自己组装 multipart（FormData 实例遍历为空）
              formData: {
                conversation_id: conversationId,
                file,
              } as unknown as Body_agent_upload_attachment,
            })
            setPending((prev) =>
              prev.map((p) =>
                p.key === entry.key
                  ? {
                      ...p,
                      status: "ready",
                      id: res.id,
                      kind: res.kind,
                      extractedChars: res.extracted_chars,
                      truncated: res.truncated,
                    }
                  : p,
              ),
            )
          } catch (e) {
            const detail = await readErrorDetail(e)
            setPending((prev) =>
              prev.map((p) =>
                p.key === entry.key
                  ? { ...p, status: "error", error: detail }
                  : p,
              ),
            )
          }
        }),
      )
    },
    [conversationId, pending.length],
  )

  /** 待发送的附件元数据（顺序与 pending 一致）；有上传中/失败时返回 null */
  const readyAttachments = useCallback((): MessageAttachment[] | null => {
    if (pending.some((p) => p.status !== "ready")) return null
    return pending.map((p) => ({
      id: p.id!,
      kind: p.kind!,
      filename: p.filename,
      size: p.size,
    }))
  }, [pending])

  return { pending, addFiles, remove, clear, readyAttachments }
}

/** 从 ApiError 里挖出后端的中文 detail（拿不到就退回通用文案） */
async function readErrorDetail(e: unknown): Promise<string> {
  const body = (e as { body?: { detail?: unknown } })?.body
  const detail = body?.detail
  if (typeof detail === "string" && detail) return detail
  if (e instanceof Error && e.message) return e.message
  return "上传失败，请重试"
}

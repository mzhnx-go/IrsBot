import { Link } from "@tanstack/react-router"
import { ArrowLeft, FileText, RotateCcw, Trash2 } from "lucide-react"
import { useState } from "react"

import type { TrashDocumentOut } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useKbTrash } from "@/hooks/useKnowledgeBase"

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const formatDate = (iso: string) =>
  new Date(iso).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })

/** 距到期还有几天（不足一天按 1 天算，避免显示成「0 天后删除」） */
const daysLeft = (expiresAt: string) =>
  Math.max(
    1,
    Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 86_400_000),
  )

const TrashRow = ({
  doc,
  onRestore,
  onPurge,
  restoring,
  purging,
}: {
  doc: TrashDocumentOut
  onRestore: (docId: string) => void
  onPurge: (docId: string) => void
  restoring: boolean
  purging: boolean
}) => {
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <div className="flex items-center justify-between rounded-lg border px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <FileText className="size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{doc.filename}</p>
          <p className="text-xs text-muted-foreground">
            {doc.kb_name} · {formatSize(doc.file_size)} · {doc.chunks_count} 个分块
          </p>
          <p className="text-xs text-muted-foreground">
            删除于 {formatDate(doc.deleted_at)} · {daysLeft(doc.expires_at)} 天后自动清除
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge variant="outline" className="text-muted-foreground">
          回收站
        </Badge>
        <Button
          variant="outline"
          size="sm"
          disabled={restoring || purging}
          onClick={() => onRestore(doc.id)}
        >
          <RotateCcw />
          恢复
        </Button>
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <Button
            variant="ghost"
            size="icon"
            className="text-destructive"
            disabled={restoring || purging}
            onClick={() => setConfirmOpen(true)}
          >
            <Trash2 />
          </Button>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>彻底删除</DialogTitle>
              <DialogDescription>
                确定彻底删除「{doc.filename}
                」吗？磁盘文件与向量数据将一并清除，该操作不可撤销。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline">取消</Button>
              </DialogClose>
              <Button
                variant="destructive"
                onClick={() => {
                  onPurge(doc.id)
                  setConfirmOpen(false)
                }}
              >
                彻底删除
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}

const KnowledgeBaseTrash = () => {
  const { trashQuery, restoreDoc, purgeDoc } = useKbTrash()

  if (trashQuery.isPending) {
    return null
  }

  const docs = trashQuery.data ?? []

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <Link
          to="/knowledge-base"
          className="flex w-fit items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          返回知识库列表
        </Link>
        <div>
          <h2 className="text-lg font-semibold">回收站</h2>
          <p className="text-sm text-muted-foreground">
            删除的文档会留在这里，恢复后重新向量化；超过保留期的文档会自动清除。
          </p>
        </div>
      </div>

      {docs.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          回收站是空的。
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {docs.map((doc) => (
            <TrashRow
              key={doc.id}
              doc={doc}
              restoring={restoreDoc.isPending && restoreDoc.variables === doc.id}
              purging={purgeDoc.isPending && purgeDoc.variables === doc.id}
              onRestore={(docId) => restoreDoc.mutate(docId)}
              onPurge={(docId) => purgeDoc.mutate(docId)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default KnowledgeBaseTrash
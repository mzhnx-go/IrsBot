import { Link } from "@tanstack/react-router"
import { ArrowLeft, FileText, Search, Trash2, Upload } from "lucide-react"
import { useRef, useState } from "react"

import type { DocumentOut } from "@/client"
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
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { useKbDetail } from "@/hooks/useKnowledgeBase"

/** 文档解析状态 → 展示文案与配色（对应后端 status 的四个取值） */
const STATUS_META: Record<string, { label: string; className: string }> = {
  pending: { label: "待处理", className: "text-muted-foreground" },
  processing: {
    label: "解析中",
    className: "text-amber-600 dark:text-amber-500",
  },
  done: {
    label: "已入库",
    className: "text-emerald-600 dark:text-emerald-500",
  },
  error: { label: "失败", className: "text-destructive" },
}

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const DocumentRow = ({
  doc,
  onDelete,
  deleting,
}: {
  doc: DocumentOut
  onDelete: (docId: string) => void
  deleting: boolean
}) => {
  const meta = STATUS_META[doc.status] ?? {
    label: doc.status,
    className: "text-muted-foreground",
  }
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <div className="flex items-center justify-between rounded-lg border px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <FileText className="size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{doc.filename}</p>
          <p className="text-xs text-muted-foreground">
            {formatSize(doc.file_size)} · {doc.chunks_count} 个分块
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge variant="outline" className={meta.className}>
          {meta.label}
        </Badge>
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="text-destructive"
              disabled={deleting}
            >
              <Trash2 />
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>删除文档</DialogTitle>
              <DialogDescription>
                确定删除「{doc.filename}
                」吗？文档会移入回收站并从检索中立即移除，可在保留期内恢复。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline">取消</Button>
              </DialogClose>
              <Button
                variant="destructive"
                disabled={deleting}
                onClick={() => {
                  onDelete(doc.id)
                  setConfirmOpen(false)
                }}
              >
                删除
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}

const KnowledgeBaseDetail = ({ kbId }: { kbId: string }) => {
  const { kbQuery, docsQuery, uploadDoc, deleteDoc, queryKb } =
    useKbDetail(kbId)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState("")

  if (kbQuery.isPending) {
    return null
  }

  const kb = kbQuery.data
  const docs = docsQuery.data ?? []
  const results = queryKb.data?.results ?? []

  return (
    <div className="flex flex-col gap-6">
      {/* 头部：返回 + 库名 + 描述 */}
      <div className="flex flex-col gap-3">
        <Link
          to="/knowledge-base"
          className="flex w-fit items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          返回知识库列表
        </Link>
        <div>
          <h2 className="text-lg font-semibold">{kb?.name}</h2>
          {kb?.description && (
            <p className="text-sm text-muted-foreground">{kb.description}</p>
          )}
        </div>
      </div>

      {/* 文档区 */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">文档</h3>
          <Button
            variant="outline"
            size="sm"
            disabled={uploadDoc.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload />
            上传文档
          </Button>
          {/* 隐藏的原生 file input：样式无法定制，交给上面的按钮触发 */}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".md,.markdown,.txt,.pdf,.docx"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) {
                uploadDoc.mutate(file)
              }
              // 清空 value：否则连续选同一个文件不会触发 change
              e.target.value = ""
            }}
          />
        </div>

        {docs.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            还没有文档。上传 .md / .txt / .pdf 后会自动解析入库。
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {docs.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                deleting={deleteDoc.isPending && deleteDoc.variables === doc.id}
                onDelete={(docId) => deleteDoc.mutate(docId)}
              />
            ))}
          </div>
        )}
      </section>

      {/* 检索测试区 */}
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-medium">检索测试</h3>
        <div className="flex gap-2">
          <Input
            placeholder="输入一个问题，看看能召回哪些内容"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && query.trim()) {
                queryKb.mutate(query.trim())
              }
            }}
          />
          <LoadingButton
            loading={queryKb.isPending}
            disabled={!query.trim()}
            onClick={() => queryKb.mutate(query.trim())}
          >
            <Search />
            检索
          </LoadingButton>
        </div>

        {results.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            尚无检索结果。上传文档后可在此验证召回效果。
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {results.map((chunk, i) => (
              <div
                key={`${chunk.source ?? "unknown"}-${i}`}
                className="rounded-lg border p-4"
              >
                <p className="mb-2 text-xs text-muted-foreground">
                  [{i + 1}] 来源：{chunk.source ?? "未知"}
                </p>
                <p className="text-sm whitespace-pre-wrap">{chunk.content}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default KnowledgeBaseDetail

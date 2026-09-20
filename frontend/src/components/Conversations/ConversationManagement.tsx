import { useQuery } from "@tanstack/react-query"
import {
  Download,
  Eye,
  MoreHorizontal,
  Pencil,
  Power,
  Search,
  Trash2,
} from "lucide-react"
import { useMemo, useState } from "react"

import {
  AgentService,
  type ConversationResponse,
  type MessageOut,
} from "@/client"
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { ConversationExportFormat } from "@/hooks/useConversations"
import useConversations from "@/hooks/useConversations"
import usePersonas from "@/hooks/usePersonas"

const EXPORT_FORMATS: { format: ConversationExportFormat; label: string }[] = [
  { format: "md", label: "Markdown (.md)" },
  { format: "txt", label: "纯文本 (.txt)" },
  { format: "json", label: "JSON (.json)" },
  { format: "docx", label: "Word (.docx)" },
  { format: "pdf", label: "PDF (.pdf)" },
]

const formatTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString() : "-"

/** 历史查看对话框：只读渲染消息，工具调用折叠展示入参 */
const HistoryDialog = ({
  conversation,
  open,
  onOpenChange,
}: {
  conversation: ConversationResponse | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) => {
  const messagesQuery = useQuery({
    queryKey: ["conversation-messages", conversation?.id],
    queryFn: () =>
      AgentService.listConversationMessages({
        conversationId: conversation?.id ?? "",
        limit: 500,
      }),
    enabled: open && !!conversation,
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{conversation?.title ?? "历史消息"}</DialogTitle>
          <DialogDescription>只读快照，不在此处编辑。</DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto">
          {messagesQuery.isPending ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              加载中…
            </p>
          ) : (messagesQuery.data ?? []).length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              该会话还没有消息。
            </p>
          ) : (
            <div className="flex flex-col gap-3 py-2">
              {(messagesQuery.data ?? []).map((m: MessageOut) => (
                <div key={m.id} className="rounded-lg border p-3">
                  <div className="mb-1 flex items-center justify-between">
                    <Badge variant="secondary">{m.role}</Badge>
                    <span className="text-xs text-muted-foreground">
                      {formatTime(m.created_at)}
                    </span>
                  </div>
                  {m.content && (
                    <p className="text-sm break-words whitespace-pre-wrap">
                      {m.content}
                    </p>
                  )}
                  {(m.tool_calls ?? []).map((tc, i) => {
                    // 展示用轨迹 {name,phase,input,output}；旧数据兼容 {name,args}
                    const input = tc.input ?? tc.args ?? ""
                    return (
                      <details
                        key={String(tc.id ?? i)}
                        className="mt-2 text-xs"
                      >
                        <summary className="cursor-pointer text-muted-foreground">
                          工具调用：{String(tc.name ?? "unknown")}
                        </summary>
                        <pre className="mt-1 max-h-48 overflow-auto rounded bg-muted p-2">
                          {typeof input === "string"
                            ? input
                            : JSON.stringify(input, null, 2)}
                        </pre>
                        {tc.output != null && (
                          <pre className="mt-1 max-h-48 overflow-auto rounded bg-muted/60 p-2">
                            {typeof tc.output === "string"
                              ? tc.output
                              : JSON.stringify(tc.output, null, 2)}
                          </pre>
                        )}
                      </details>
                    )
                  })}
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** 重命名对话框（受控） */
const RenameDialog = ({
  conversation,
  open,
  onOpenChange,
}: {
  conversation: ConversationResponse | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) => {
  const { renameConversation } = useConversations()
  const [title, setTitle] = useState("")

  const submit = () => {
    if (!conversation || !title.trim()) return
    renameConversation.mutate(
      { conversationId: conversation.id, title: title.trim() },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (o && conversation) setTitle(conversation.title)
        onOpenChange(o)
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>重命名会话</DialogTitle>
        </DialogHeader>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="新的会话标题"
          className="my-2"
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <LoadingButton
            onClick={submit}
            loading={renameConversation.isPending}
            disabled={!title.trim()}
          >
            保存
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const ConversationManagement = () => {
  const { setConversationStatus, deleteConversation, exportConversation } =
    useConversations()
  const { personasQuery } = usePersonas()
  const [search, setSearch] = useState("")
  const [historyTarget, setHistoryTarget] =
    useState<ConversationResponse | null>(null)
  const [renameTarget, setRenameTarget] = useState<ConversationResponse | null>(
    null,
  )
  const [deleteTarget, setDeleteTarget] = useState<ConversationResponse | null>(
    null,
  )

  // 管理页独立取大页容量；key 前缀仍是 ["conversations"]，
  // 与侧边栏共享同一套失效广播
  const { data } = useQuery({
    queryKey: ["conversations", { limit: 200 }],
    queryFn: () => AgentService.listConversations({ limit: 200 }),
  })

  const personaNames = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of personasQuery.data ?? []) map.set(p.id, p.name)
    return map
  }, [personasQuery.data])

  const rows = (data ?? []).filter((c) =>
    c.title.toLowerCase().includes(search.trim().toLowerCase()),
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">会话管理</h2>
          <p className="text-sm text-muted-foreground">
            查看历史、导出、重命名、停用或删除会话。停用后该会话不能再发送消息。
          </p>
        </div>
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="按标题搜索…"
            className="pl-8"
          />
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {data?.length
            ? "没有匹配的会话。"
            : "还没有会话，去聊天页发起第一个对话吧。"}
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>标题</TableHead>
              <TableHead>人设</TableHead>
              <TableHead>更新时间</TableHead>
              <TableHead>状态</TableHead>
              <TableHead className="w-16 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="max-w-64 truncate font-medium">
                  {c.title}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {c.persona_id
                    ? (personaNames.get(c.persona_id) ?? "（已删除）")
                    : "-"}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatTime(c.updated_at)}
                </TableCell>
                <TableCell>
                  {c.is_enabled ? (
                    <Badge variant="outline">启用</Badge>
                  ) : (
                    <Badge variant="destructive">已停用</Badge>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="查看历史"
                      onClick={() => setHistoryTarget(c)}
                    >
                      <Eye className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={c.is_enabled ? "停用" : "启用"}
                      disabled={setConversationStatus.isPending}
                      onClick={() =>
                        setConversationStatus.mutate({
                          conversationId: c.id,
                          isEnabled: !c.is_enabled,
                        })
                      }
                    >
                      <Power
                        className={
                          c.is_enabled
                            ? "size-4 text-emerald-600"
                            : "size-4 text-muted-foreground"
                        }
                      />
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label="更多">
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setRenameTarget(c)}>
                          <Pencil />
                          重命名
                        </DropdownMenuItem>
                        {EXPORT_FORMATS.map((f) => (
                          <DropdownMenuItem
                            key={f.format}
                            onClick={() =>
                              exportConversation.mutate({
                                conversationId: c.id,
                                format: f.format,
                              })
                            }
                          >
                            <Download />
                            导出 {f.label}
                          </DropdownMenuItem>
                        ))}
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => setDeleteTarget(c)}
                        >
                          <Trash2 />
                          删除
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <HistoryDialog
        conversation={historyTarget}
        open={historyTarget !== null}
        onOpenChange={(o) => {
          if (!o) setHistoryTarget(null)
        }}
      />
      <RenameDialog
        conversation={renameTarget}
        open={renameTarget !== null}
        onOpenChange={(o) => {
          if (!o) setRenameTarget(null)
        }}
      />
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(o) => {
          if (!o) setDeleteTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>删除会话</DialogTitle>
            <DialogDescription>
              确定删除「{deleteTarget?.title}
              」吗？该会话下的所有消息会一并删除，不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <DialogClose asChild>
              <Button variant="outline">取消</Button>
            </DialogClose>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleteTarget) deleteConversation.mutate(deleteTarget.id)
                setDeleteTarget(null)
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default ConversationManagement

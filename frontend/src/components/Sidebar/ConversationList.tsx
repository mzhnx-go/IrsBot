import { useNavigate, useRouterState } from "@tanstack/react-router"
import {
  Download,
  ListChecks,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react"
import { useState } from "react"
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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import useConversations from "@/hooks/useConversations"

/**
 * 侧边栏「最近对话」列表：
 * - 顶部「新对话」按钮
 * - 会话项：单行截断，选中项浅灰底；hover 浮出「…」菜单
 * - 「…」→ 重命名 / 批量管理 / 导出（占位）/ 删除（均带确认或表单）
 *
 * 视觉只动颜色和透明度（150ms ease-out），不做位移/缩放 —— 列表是
 * 高频浏览区域，动效必须几乎不可感知。
 */
export function ConversationList() {
  const { conversationsQuery, deleteConversation, renameConversation } =
    useConversations()
  const navigate = useNavigate()
  const { isMobile, setOpenMobile } = useSidebar()

  // 当前打开的会话 ID（/chat?c=<id>），用于高亮与删除后跳转
  const search = useRouterState({
    select: (s) => s.location.search as { c?: string },
  })
  const activeId = search.c

  const conversations = conversationsQuery.data ?? []

  // ── 各弹窗状态（互相独立，同一时刻最多开一个） ──
  // 待删除（单个）
  const [pendingDelete, setPendingDelete] = useState<{
    id: string
    title: string
  } | null>(null)
  // 重命名（存 id + 当前输入值）
  const [renaming, setRenaming] = useState<{
    id: string
    title: string
  } | null>(null)
  // 批量管理主面板
  const [batchOpen, setBatchOpen] = useState(false)
  // 批量面板里勾选中的会话 id
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  // 批量删除二次确认
  const [batchConfirm, setBatchConfirm] = useState(false)

  const handleSelect = (id: string) => {
    if (isMobile) setOpenMobile(false)
    navigate({ to: "/chat", search: { c: id } })
  }

  const handleNewChat = () => {
    if (isMobile) setOpenMobile(false)
    // 不带 c 进入 /chat：页面effect会自动创建新会话并 replace 回写参数
    navigate({ to: "/chat", search: { c: undefined } })
  }

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return
    const wasActive = pendingDelete.id === activeId
    const id = pendingDelete.id
    setPendingDelete(null)
    await deleteConversation.mutateAsync(id)
    // 删的是当前打开的会话 → 回到 /chat 让页面创建新会话
    if (wasActive) {
      navigate({ to: "/chat", search: { c: undefined } })
    }
  }

  const handleConfirmRename = async () => {
    if (!renaming) return
    const title = renaming.title.trim()
    if (!title) return
    const { id } = renaming
    setRenaming(null)
    await renameConversation.mutateAsync({ conversationId: id, title })
  }

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleBatchDelete = async () => {
    setBatchConfirm(false)
    const ids = [...selectedIds]
    const deletingActive = ids.includes(activeId ?? "")
    setBatchOpen(false)
    setSelectedIds(new Set())
    for (const id of ids) {
      await deleteConversation.mutateAsync(id)
    }
    if (deletingActive) {
      navigate({ to: "/chat", search: { c: undefined } })
    }
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>最近对话</SidebarGroupLabel>
      <SidebarGroupContent>
        {/* 新对话按钮 */}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={handleNewChat} tooltip="新对话">
              <Plus />
              <span>新对话</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>

        {/* 会话列表 */}
        <SidebarMenu className="mt-1">
          {conversationsQuery.isPending ? null : conversations.length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted-foreground">
              暂无历史对话
            </p>
          ) : (
            conversations.map((conv) => {
              const isActive = conv.id === activeId
              const isDeleting =
                deleteConversation.isPending &&
                deleteConversation.variables === conv.id

              return (
                <SidebarMenuItem key={conv.id}>
                  <SidebarMenuButton
                    isActive={isActive}
                    tooltip={conv.title}
                    disabled={isDeleting}
                    onClick={() => handleSelect(conv.id)}
                  >
                    <span className="truncate">{conv.title}</span>
                  </SidebarMenuButton>

                  {/* 「…」菜单：hover 或选中时浮出（showOnHover 由 sidebar 组件内置） */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <SidebarMenuAction showOnHover disabled={isDeleting}>
                        <MoreHorizontal />
                        <span className="sr-only">更多操作</span>
                      </SidebarMenuAction>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent side="right" align="start">
                      <DropdownMenuItem
                        onClick={() =>
                          setRenaming({ id: conv.id, title: conv.title })
                        }
                      >
                        <Pencil />
                        <span>重命名</span>
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => {
                          setSelectedIds(new Set())
                          setBatchOpen(true)
                        }}
                      >
                        <ListChecks />
                        <span>批量管理</span>
                      </DropdownMenuItem>
                      {/* 导出对话：入口占位，Word/PDF/TXT/Json 后续实现 */}
                      <DropdownMenuItem disabled>
                        <Download />
                        <span>导出对话</span>
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={() =>
                          setPendingDelete({ id: conv.id, title: conv.title })
                        }
                      >
                        <Trash2 className="text-destructive" />
                        <span className="text-destructive">删除对话</span>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </SidebarMenuItem>
              )
            })
          )}
        </SidebarMenu>
      </SidebarGroupContent>

      {/* 删除二次确认（单个） */}
      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除对话</DialogTitle>
            <DialogDescription>
              确定删除「{pendingDelete?.title}
              」？对话内的所有消息将一并删除，且不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="ghost">取消</Button>
            </DialogClose>
            <Button variant="destructive" onClick={handleConfirmDelete}>
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 重命名弹窗（带输入框，回车提交） */}
      <Dialog
        open={renaming !== null}
        onOpenChange={(open) => !open && setRenaming(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名对话</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            value={renaming?.title ?? ""}
            onChange={(e) =>
              setRenaming((prev) =>
                prev ? { ...prev, title: e.target.value } : prev,
              )
            }
            onKeyDown={(e) => {
              if (e.key === "Enter") handleConfirmRename()
            }}
            placeholder="输入新的对话名称"
          />
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="ghost">取消</Button>
            </DialogClose>
            <Button
              onClick={handleConfirmRename}
              disabled={!renaming?.title.trim()}
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 批量管理面板（：列表 + 复选框 + 全选 + 底部操作栏） */}
      <Dialog open={batchOpen} onOpenChange={setBatchOpen}>
        <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>对话批量管理</span>
              {/* 用原生 input[type=checkbox]：label 可正确关联（a11y）、自带键盘支持；
                  Radix Checkbox 渲染成 button，label 关联不到表单控件反而报错 */}
              <label className="flex cursor-pointer items-center gap-2 text-sm font-normal text-muted-foreground">
                全选
                <input
                  type="checkbox"
                  className="size-4 cursor-pointer"
                  style={{ accentColor: "var(--primary)" }}
                  checked={
                    conversations.length > 0 &&
                    selectedIds.size === conversations.length
                  }
                  onChange={(e) =>
                    setSelectedIds(
                      e.target.checked
                        ? new Set(conversations.map((c) => c.id))
                        : new Set(),
                    )
                  }
                />
              </label>
            </DialogTitle>
          </DialogHeader>

          {/* 可滚动会话清单 */}
          <div className="-mx-1 flex-1 overflow-y-auto px-1">
            {conversations.map((conv) => (
              <label
                key={conv.id}
                className="flex cursor-pointer items-center justify-between gap-3 rounded-md px-2 py-2.5 text-sm transition-colors duration-150 ease-out hover:bg-muted"
              >
                <span className="truncate">{conv.title}</span>
                {/* 点击/键盘统一走 checkbox 原生行为，label 自动关联 */}
                <input
                  type="checkbox"
                  className="size-4 shrink-0 cursor-pointer"
                  style={{ accentColor: "var(--primary)" }}
                  checked={selectedIds.has(conv.id)}
                  onChange={() => toggleSelected(conv.id)}
                />
              </label>
            ))}
          </div>

          <DialogFooter className="items-center sm:justify-between">
            <span className="text-xs text-muted-foreground">
              已选 {selectedIds.size}/{conversations.length}
            </span>
            <div className="flex gap-2">
              <DialogClose asChild>
                <Button variant="ghost">取消</Button>
              </DialogClose>
              <Button
                variant="destructive"
                disabled={selectedIds.size === 0}
                onClick={() => setBatchConfirm(true)}
              >
                删除
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 批量删除二次确认 */}
      <Dialog open={batchConfirm} onOpenChange={setBatchConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>批量删除对话</DialogTitle>
            <DialogDescription>
              确定删除选中的 {selectedIds.size}
              个对话？对话内的所有消息将一并删除，且不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="ghost">取消</Button>
            </DialogClose>
            <Button variant="destructive" onClick={handleBatchDelete}>
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SidebarGroup>
  )
}

export default ConversationList

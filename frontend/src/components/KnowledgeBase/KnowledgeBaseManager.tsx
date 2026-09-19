import { zodResolver } from "@hookform/resolvers/zod"
import { Link } from "@tanstack/react-router"
import { FolderOpen, Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import type { KBOut } from "@/client"
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
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useKnowledgeBase from "@/hooks/useKnowledgeBase"

const formSchema = z.object({
  name: z.string().min(1, { message: "名称必填" }),
  description: z.string().optional(),
})

type FormData = z.infer<typeof formSchema>

const AddKbDialog = () => {
  const [isOpen, setIsOpen] = useState(false)
  const { createKb } = useKnowledgeBase()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: {
      name: "",
      description: "",
    },
  })

  const onSubmit = (data: FormData) => {
    createKb.mutate(
      {
        name: data.name,
        description: data.description || undefined,
      },
      {
        onSuccess: () => {
          form.reset()
          setIsOpen(false)
        },
      },
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2" />
          新建知识库
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建知识库</DialogTitle>
          <DialogDescription>
            创建后可向其中上传文档，AI 对话时将检索库内内容作为上下文。
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className="grid gap-4 py-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      名称 <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input
                        placeholder="如：产品手册"
                        type="text"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>描述（可选）</FormLabel>
                    <FormControl>
                      <textarea
                        placeholder="这个知识库存什么内容"
                        className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={createKb.isPending}>
                  取消
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={createKb.isPending}>
                保存
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

interface KbRowProps {
  kb: KBOut
  onDelete: (id: string) => void
}

const KbRow = ({ kb, onDelete }: KbRowProps) => {
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <div className="flex items-center justify-between rounded-lg border p-4">
      <div className="min-w-0">
        <Link
          to="/knowledge-base/$kbId"
          params={{ kbId: kb.id }}
          className="flex w-fit items-center gap-2 hover:underline"
        >
          <FolderOpen className="size-4 shrink-0 text-muted-foreground" />
          <span className="font-medium">{kb.name}</span>
          <Badge variant="outline">{kb.document_count} 个文档</Badge>
        </Link>
        {kb.description && (
          <p className="truncate text-sm text-muted-foreground">
            {kb.description}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm" className="text-destructive">
              <Trash2 />
              删除
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>删除知识库</DialogTitle>
              <DialogDescription>
                确定删除「{kb.name}
                」吗？库内全部文档（含回收站中的）与向量数据将一并删除，该操作不可撤销。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline">取消</Button>
              </DialogClose>
              <Button
                variant="destructive"
                onClick={() => {
                  onDelete(kb.id)
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

const KnowledgeBaseManager = () => {
  const { kbListQuery, deleteKb } = useKnowledgeBase()

  if (kbListQuery.isPending) {
    return null
  }

  const kbs = kbListQuery.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">知识库</h2>
          <p className="text-sm text-muted-foreground">
            管理知识库。AI 对话时可基于库内文档回答问题。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link to="/knowledge-base/trash">
              <Trash2 />
              回收站
            </Link>
          </Button>
          <AddKbDialog />
        </div>
      </div>

      {kbs.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          还没有知识库。点击右上角「新建知识库」创建一个。
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {kbs.map((kb) => (
            <KbRow key={kb.id} kb={kb} onDelete={(id) => deleteKb.mutate(id)} />
          ))}
        </div>
      )}
    </div>
  )
}

export default KnowledgeBaseManager

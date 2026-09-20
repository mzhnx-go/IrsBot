import { zodResolver } from "@hookform/resolvers/zod"
import { Drama, Pencil, Plus, Power, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import type { PersonaResponse } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import usePersonas from "@/hooks/usePersonas"

const formSchema = z.object({
  name: z.string().min(1, { message: "名称必填" }),
  prompt: z.string().min(1, { message: "人设提示词必填" }),
  avatar: z.string().max(8).optional(),
  is_active: z.boolean(),
})

type FormData = z.infer<typeof formSchema>

const EMPTY: FormData = { name: "", prompt: "", avatar: "", is_active: true }

interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** null = 新建模式，非 null = 编辑该人设 */
  editing: PersonaResponse | null
}

const PersonaFormDialog = ({ open, onOpenChange, editing }: DialogProps) => {
  const { createPersona, updatePersona } = usePersonas()
  const isEdit = editing !== null

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: EMPTY,
  })

  // 打开对话框时同步表单内容（新建=清空，编辑=回填该人设）
  useEffect(() => {
    if (!open) return
    if (editing) {
      form.reset({
        name: editing.name,
        prompt: editing.prompt,
        avatar: editing.avatar ?? "",
        is_active: editing.is_active,
      })
    } else {
      form.reset(EMPTY)
    }
  }, [open, editing, form])

  const onSubmit = (data: FormData) => {
    const body = {
      name: data.name,
      prompt: data.prompt,
      avatar: data.avatar || undefined,
      is_active: data.is_active,
    }
    const opts = {
      onSuccess: () => onOpenChange(false),
    }
    if (isEdit) {
      updatePersona.mutate({ personaId: editing.id, body }, opts)
    } else {
      createPersona.mutate(body, opts)
    }
  }

  const pending = createPersona.isPending || updatePersona.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {!isEdit && (
        <DialogTrigger asChild>
          <Button>
            <Plus className="mr-2" />
            新增人设
          </Button>
        </DialogTrigger>
      )}
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑人设" : "新增人设"}</DialogTitle>
          <DialogDescription>
            人设提示词会追加到平台默认系统提示词之后，不覆盖平台规则。
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-[1fr_6rem] gap-4">
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
                          placeholder="如：锐评毒舌"
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
                  name="avatar"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>头像</FormLabel>
                      <FormControl>
                        <Input placeholder="😀" type="text" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="prompt"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      人设提示词 <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="描述这个角色的语气、立场与风格，例如：你是一位辛辣犀利的影评人……"
                        rows={6}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      对话绑定该人设后，AI 会按此角色风格回复。
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-2">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={(v) => field.onChange(Boolean(v))}
                      />
                    </FormControl>
                    <FormLabel className="!mt-0">启用</FormLabel>
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={pending}>
                  取消
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={pending}>
                保存
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

interface PersonaRowProps {
  persona: PersonaResponse
  onEdit: () => void
  onToggle: () => void
  onDelete: () => void
  toggling: boolean
}

const PersonaRow = ({
  persona,
  onEdit,
  onToggle,
  onDelete,
  toggling,
}: PersonaRowProps) => {
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border p-4">
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-lg">
          {persona.avatar || <Drama className="size-4 text-muted-foreground" />}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium">{persona.name}</span>
            {!persona.is_active && <Badge variant="outline">已停用</Badge>}
          </div>
          <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
            {persona.prompt}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={onToggle}
          disabled={toggling}
        >
          <Power />
          {persona.is_active ? "停用" : "启用"}
        </Button>
        <Button variant="outline" size="sm" onClick={onEdit}>
          <Pencil />
          编辑
        </Button>
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm" className="text-destructive">
              <Trash2 />
              删除
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>删除人设</DialogTitle>
              <DialogDescription>
                确定删除「{persona.name}
                」吗？已绑定该人设的会话会自动解绑，此操作不可撤销。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline">取消</Button>
              </DialogClose>
              <Button
                variant="destructive"
                onClick={() => {
                  onDelete()
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

const PersonaSettings = () => {
  const { personasQuery, updatePersona, deletePersona } = usePersonas()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<PersonaResponse | null>(null)

  if (personasQuery.isPending) {
    return null
  }

  const personas = personasQuery.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">人设</h2>
          <p className="text-sm text-muted-foreground">
            为 AI 定义角色风格，在对话中绑定后按人设回复。
          </p>
        </div>
        <PersonaFormDialog
          open={dialogOpen}
          onOpenChange={(o) => {
            setDialogOpen(o)
            if (!o) setEditing(null)
          }}
          editing={editing}
        />
      </div>

      {personas.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          还没有人设。点击右上角「新增人设」创建第一个角色。
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {personas.map((p) => (
            <PersonaRow
              key={p.id}
              persona={p}
              toggling={updatePersona.variables?.personaId === p.id}
              onEdit={() => {
                setEditing(p)
                setDialogOpen(true)
              }}
              onToggle={() =>
                updatePersona.mutate({
                  personaId: p.id,
                  body: { is_active: !p.is_active },
                })
              }
              onDelete={() => deletePersona.mutate(p.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default PersonaSettings

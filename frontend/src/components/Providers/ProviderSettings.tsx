import { zodResolver } from "@hookform/resolvers/zod"
import { Plus, Star, Trash2 } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import type { ProviderOut } from "@/client"
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
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { PasswordInput } from "@/components/ui/password-input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useProviders from "@/hooks/useProviders"

const formSchema = z.object({
  name: z.string().min(1, { message: "名称必填" }),
  provider_type: z.enum(["openai", "anthropic", "gemini"]),
  api_key: z.string().min(1, { message: "API Key 必填" }),
  model_name: z.string().min(1, { message: "模型名必填" }),
  base_url: z.string().optional(),
  is_default: z.boolean(),
})

type FormData = z.infer<typeof formSchema>

const TYPE_LABELS: Record<string, string> = {
  openai: "OpenAI 兼容",
  anthropic: "Anthropic",
  gemini: "Gemini",
}

const AddProviderDialog = ({
  initialOpen = false,
}: {
  initialOpen?: boolean
}) => {
  const [isOpen, setIsOpen] = useState(initialOpen)
  const { createProvider } = useProviders()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: {
      name: "",
      provider_type: "openai",
      api_key: "",
      model_name: "",
      base_url: "",
      is_default: false,
    },
  })

  const onSubmit = (data: FormData) => {
    createProvider.mutate(
      {
        name: data.name,
        provider_type: data.provider_type,
        api_key: data.api_key,
        model_name: data.model_name,
        base_url: data.base_url || undefined,
        is_default: data.is_default,
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
          新增模型源
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新增模型源</DialogTitle>
          <DialogDescription>
            添加一套模型 API 配置。API Key 会加密后存储，且不会再显示。
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
                        placeholder="如：通义千问"
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
                name="provider_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>类型</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="选择类型" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="openai">OpenAI 兼容</SelectItem>
                        <SelectItem value="anthropic">Anthropic</SelectItem>
                        <SelectItem value="gemini">Gemini</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      API Key <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <PasswordInput placeholder="sk-..." {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="model_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      模型名 <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input
                        placeholder="如：qwen-plus"
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
                name="base_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>API 地址（可选）</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="如：https://dashscope.aliyuncs.com/compatible-mode/v1"
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
                name="is_default"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-2">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={(v) => field.onChange(Boolean(v))}
                      />
                    </FormControl>
                    <FormLabel className="!mt-0">设为默认模型源</FormLabel>
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={createProvider.isPending}>
                  取消
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={createProvider.isPending}>
                保存
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

interface ProviderRowProps {
  provider: ProviderOut
  onSetDefault: (id: string) => void
  onDelete: (id: string) => void
}

const ProviderRow = ({
  provider,
  onSetDefault,
  onDelete,
}: ProviderRowProps) => {
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <div className="flex items-center justify-between rounded-lg border p-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium">{provider.name}</span>
          {provider.is_default && <Badge>默认</Badge>}
          {!provider.is_active && <Badge variant="outline">已停用</Badge>}
        </div>
        <p className="truncate text-sm text-muted-foreground">
          {TYPE_LABELS[provider.provider_type] ?? provider.provider_type}
          {" · "}
          {provider.model_name}
          {provider.base_url ? ` · ${provider.base_url}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={provider.is_default}
          onClick={() => onSetDefault(provider.id)}
        >
          <Star />
          设为默认
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
              <DialogTitle>删除模型源</DialogTitle>
              <DialogDescription>
                确定删除「{provider.name}」吗？该操作不可撤销。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline">取消</Button>
              </DialogClose>
              <Button
                variant="destructive"
                onClick={() => {
                  onDelete(provider.id)
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

const ProviderSettings = ({
  autoOpenNew = false,
}: {
  autoOpenNew?: boolean
}) => {
  const { providersQuery, updateProvider, deleteProvider } = useProviders()

  if (providersQuery.isPending) {
    return null
  }

  const providers = providersQuery.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">模型源</h2>
          <p className="text-sm text-muted-foreground">
            管理多套模型 API 配置，AI 对话使用标记为「默认」的模型源。
          </p>
        </div>
        <AddProviderDialog initialOpen={autoOpenNew} />
      </div>

      {providers.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          还没有模型源。点击右上角「新增模型源」添加一套配置。
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {providers.map((p) => (
            <ProviderRow
              key={p.id}
              provider={p}
              onSetDefault={(id) =>
                updateProvider.mutate({
                  providerId: id,
                  body: { is_default: true },
                })
              }
              onDelete={(id) => deleteProvider.mutate(id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default ProviderSettings

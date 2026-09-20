import {
  ArrowDownUp,
  Braces,
  Mic,
  MessagesSquare,
  Plus,
  Trash2,
  Volume2,
  Wallet,
} from "lucide-react"
import { useState } from "react"

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
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import useProviderBalance from "@/hooks/useProviderBalance"
import useProviders from "@/hooks/useProviders"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"

// ── 能力 Tab 栏（AstrBot 风格）────────────────────────────────
// 「对话」是现有能力；其余四类供应商为前端占位，后端能力待实现。
// TODO(待实现)：语音转文字 / 文字转语音 / 嵌入 / 重排序供应商的
// 数据模型、CRUD 端点与 Agent 集成。届时 Tab 放开为 enabled。
const CAPABILITY_TABS = [
  { key: "chat", label: "对话", icon: MessagesSquare, enabled: true },
  { key: "stt", label: "语音转文字", icon: Mic, enabled: false },
  { key: "tts", label: "文字转语音", icon: Volume2, enabled: false },
  { key: "embedding", label: "嵌入", icon: Braces, enabled: false },
  { key: "rerank", label: "重排序", icon: ArrowDownUp, enabled: false },
] as const

const formSchema = z.object({
  name: z.string().min(1, { message: "名称必填" }),
  provider_type: z.enum(["openai", "anthropic", "gemini"]),
  api_key: z.string().min(1, { message: "API Key 必填" }),
  model_name: z.string().min(1, { message: "模型名必填" }),
  base_url: z.string().optional(),
  is_default: z.boolean(),
  // 三态：auto=自动（服务端按模型名推断）/ yes / no
  supports_vision: z.enum(["auto", "yes", "no"]),
})

type FormData = z.infer<typeof formSchema>

const TYPE_LABELS: Record<string, string> = {
  openai: "OpenAI 兼容",
  anthropic: "Anthropic",
  gemini: "Gemini",
}

/** 三态 ↔ API 的 bool | null 互转（表单用字符串，接口用布尔/空） */
const VISION_TO_FORM = (v: boolean | null | undefined) =>
  v === true ? "yes" : v === false ? "no" : "auto"

const VISION_FROM_FORM = (v: "auto" | "yes" | "no") =>
  v === "auto" ? null : v === "yes"

// ── 新增模型源弹窗（既有功能，原样保留）──────────────────────

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
      supports_vision: "auto",
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
        supports_vision: VISION_FROM_FORM(data.supports_vision),
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
        <Button variant="ghost" size="sm" className="text-primary">
          <Plus className="mr-1" />
          新增
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
                name="supports_vision"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>视觉能力</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="选择视觉能力" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="auto">
                          自动判断（按模型名）
                        </SelectItem>
                        <SelectItem value="yes">支持视觉</SelectItem>
                        <SelectItem value="no">不支持视觉</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      传图片时据此决定：支持则把图片直接发给模型，否则提示当前
                      模型看不了图。
                    </p>
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

// ── 左列表卡片 ────────────────────────────────────────────────

interface ProviderListItemProps {
  provider: ProviderOut
  selected: boolean
  onSelect: () => void
  onDelete: () => void
}

const ProviderListItem = ({
  provider,
  selected,
  onSelect,
  onDelete,
}: ProviderListItemProps) => {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const { balanceQuery } = useProviderBalance(provider.id)

  const balanceText = (() => {
    if (balanceQuery.isFetching) return "查询中…"
    if (balanceQuery.error) return "查询失败，请稍后重试"
    const balance = balanceQuery.data
    if (!balance) return null
    if (!balance.supported) {
      return balance.detail ?? "该服务商不支持余额查询"
    }
    if (balance.error) return balance.error
    const symbol = balance.currency === "CNY" ? "¥" : "$"
    const money =
      balance.remaining == null
        ? "未知"
        : `${symbol}${balance.remaining.toFixed(2)}`
    return `剩余额度 ${money}${balance.detail ? `（${balance.detail}）` : ""}`
  })()

  return (
    <div
      data-testid="provider-row"
      data-provider-name={provider.name}
      onClick={onSelect}
      className={cn(
        "group cursor-pointer rounded-lg border p-3 transition-colors",
        selected ? "border-primary bg-primary/5" : "hover:bg-muted/60",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium">{provider.name}</span>
            {provider.is_default && <Badge>默认</Badge>}
            {!provider.is_active && <Badge variant="outline">已停用</Badge>}
          </div>
          <p className="truncate text-sm text-muted-foreground">
            {provider.base_url ??
              TYPE_LABELS[provider.provider_type] ??
              provider.provider_type}
          </p>
        </div>
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive"
              aria-label={`删除 ${provider.name}`}
              onClick={(e) => e.stopPropagation()}
            >
              <Trash2 />
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>删除模型源</DialogTitle>
              <DialogDescription>
                确定删除「{provider.name}
                」吗？该操作不可撤销。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline">取消</Button>
              </DialogClose>
              <Button
                variant="destructive"
                onClick={(e) => {
                  e.stopPropagation()
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
      {/* 查余额：e2e 按 provider-row 行内定位按钮与结果，必须留在卡片里 */}
      <div className="mt-2 flex items-center justify-between gap-2">
        <Button
          variant="outline"
          size="sm"
          className="h-7"
          data-testid="provider-balance-button"
          disabled={balanceQuery.isFetching}
          onClick={(e) => {
            e.stopPropagation()
            balanceQuery.refetch()
          }}
        >
          <Wallet />
          {balanceQuery.isFetching ? "查询中" : "查余额"}
        </Button>
        {balanceText && (
          <p
            data-testid="provider-balance-result"
            className="truncate text-xs text-muted-foreground"
          >
            {balanceText}
          </p>
        )}
      </div>
    </div>
  )
}

// ── 右详情面板：设置区 ────────────────────────────────────────

/** 详情表单行：左侧标签+说明，右侧控件（AstrBot 排版） */
function SettingRow({
  label,
  description,
  children,
}: {
  label: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div className="grid grid-cols-[220px_1fr] items-center gap-4 border-b py-3 last:border-b-0">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {description && (
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        )}
      </div>
      <div>{children}</div>
    </div>
  )
}

interface ProviderDetailProps {
  provider: ProviderOut
}

/** key={provider.id} 重挂载：切换选中项时表单回到该供应商的当前值 */
const ProviderDetail = ({ provider }: ProviderDetailProps) => {
  const { updateProvider } = useProviders()

  const [name, setName] = useState(provider.name)
  // API Key：后端从不回传明文——留空 = 不修改，输入新值才进 PATCH
  const [apiKey, setApiKey] = useState("")
  const [modelName, setModelName] = useState(provider.model_name)
  const [baseUrl, setBaseUrl] = useState(provider.base_url ?? "")
  const [isDefault, setIsDefault] = useState(provider.is_default)
  const [supportsVision, setSupportsVision] = useState<
    "auto" | "yes" | "no"
  >(VISION_TO_FORM(provider.supports_vision))

  const handleSave = () => {
    if (!name.trim() || !modelName.trim()) return
    updateProvider.mutate({
      providerId: provider.id,
      body: {
        name: name.trim(),
        model_name: modelName.trim(),
        base_url: baseUrl.trim() || undefined,
        is_default: isDefault,
        supports_vision: VISION_FROM_FORM(supportsVision),
        // 留空不提交，避免把占位串当新 Key 覆盖掉密文
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      },
    })
  }

  return (
    <div
      data-testid="provider-detail"
      data-provider-name={provider.name}
      className="flex h-full flex-col"
    >
      {/* 详情头部：名称 + 地址 + 保存配置 */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="truncate text-xl font-semibold">{provider.name}</h3>
          <p className="truncate text-sm text-muted-foreground">
            {provider.base_url ??
              TYPE_LABELS[provider.provider_type] ??
              provider.provider_type}
          </p>
        </div>
        <LoadingButton
          size="sm"
          loading={updateProvider.isPending}
          onClick={handleSave}
          data-testid="provider-save"
          disabled={!name.trim() || !modelName.trim()}
        >
          保存配置
        </LoadingButton>
      </div>

      {/* 设置 */}
      <h4 className="mt-6 text-base font-semibold">设置</h4>
      <div>
        <SettingRow label="名称" description="模型源显示名称">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </SettingRow>
        <SettingRow
          label="类型"
          description="创建后不可修改（后端约定）"
        >
          <Input
            value={TYPE_LABELS[provider.provider_type] ?? provider.provider_type}
            disabled
          />
        </SettingRow>
        <SettingRow
          label="API Key"
          description="已加密存储。留空表示不修改；输入新值则覆盖"
        >
          <div className="flex items-center gap-2">
            <PasswordInput
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="••••••••••••••••"
            />
            {/* TODO(待实现)：多 Key 轮换（后端需 ProviderKey 表与轮询策略） */}
            <Button
              variant="outline"
              size="sm"
              className="shrink-0"
              disabled
              title="待实现"
            >
              添加更多
            </Button>
          </div>
        </SettingRow>
        <SettingRow label="API 地址" description="自定义 API 端点 URL（可选）">
          <Input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://…/v1"
          />
        </SettingRow>
        <SettingRow label="默认模型名" description="对话默认使用的模型">
          <Input
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
          />
        </SettingRow>
        <SettingRow label="设为默认" description="对话使用标记为默认的模型源">
          <Switch
            checked={isDefault}
            onCheckedChange={setIsDefault}
            data-testid="provider-default-switch"
          />
        </SettingRow>
        <SettingRow
          label="视觉能力"
          description="传图片时：支持则直接发给模型，否则提示看不了图"
        >
          <Select
            value={supportsVision}
            onValueChange={(v) =>
              setSupportsVision(v as "auto" | "yes" | "no")
            }
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">自动判断（按模型名）</SelectItem>
              <SelectItem value="yes">支持视觉</SelectItem>
              <SelectItem value="no">不支持视觉</SelectItem>
            </SelectContent>
          </Select>
        </SettingRow>
      </div>

      {/* 高级配置（前端占位，功能待实现）：
          需要后端在 ProviderConfig 增加对应列并提供 PATCH 语义后才能启用，
          参照 AstrBot：超时时间 / 代理地址 / 自定义请求头 */}
      <h4 className="mt-6 flex items-center gap-2 text-base font-semibold">
        高级配置…
        <Badge variant="outline" className="font-normal text-muted-foreground">
          待实现
        </Badge>
      </h4>
      <div>
        <SettingRow label="超时时间" description="超时时间，单位为秒。">
          <Input disabled placeholder="120" title="待实现" />
        </SettingRow>
        <SettingRow
          label="代理地址"
          description="HTTP/HTTPS 代理地址，仅对该提供商的 API 请求生效。"
        >
          <Input
            disabled
            placeholder="http://127.0.0.1:7890"
            title="待实现"
          />
        </SettingRow>
        <SettingRow
          label="自定义请求头"
          description="键值对将合并到该提供商的 HTTP 请求头中，值必须为字符串。"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm text-muted-foreground">暂无项目</span>
            <Button
              variant="outline"
              size="sm"
              disabled
              title="待实现"
            >
              修改
            </Button>
          </div>
        </SettingRow>
      </div>

      {/* 模型区（前端占位，功能待实现）：
          「获取模型列表」需后端透传上游 GET /models 并落库；
          「自定义模型」需模型管理表（每供应商多模型 + 默认模型选择）。
          当前默认模型名在上方「设置」区维护 */}
      <h4 className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-base font-semibold">模型</p>
          <p className="text-xs text-muted-foreground">可用模型 0</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            disabled
            placeholder="搜索模型或 ID"
            title="待实现"
            className="h-8 w-40 rounded-md border border-input bg-transparent px-2 text-sm placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
          />
          <Button variant="outline" size="sm" disabled title="待实现">
            获取模型列表
          </Button>
          <Button variant="outline" size="sm" disabled title="待实现">
            自定义模型
          </Button>
        </div>
      </h4>
    </div>
  )
}

// ── 页面主体：能力 Tab + 主从两栏 ─────────────────────────────

const ProviderSettings = ({
  autoOpenNew = false,
}: {
  autoOpenNew?: boolean
}) => {
  const { providersQuery, deleteProvider } = useProviders()
  // 未选中任何项时右侧显示空态（与 AstrBot 一致），不自动选中
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (providersQuery.isPending) {
    return null
  }

  const providers = providersQuery.data ?? []
  const selected = providers.find((p) => p.id === selectedId) ?? null

  return (
    <div className="flex flex-col gap-4">
      {/* 能力 Tab 栏 */}
      <div className="flex flex-wrap items-center gap-2">
        {CAPABILITY_TABS.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              type="button"
              disabled={!tab.enabled}
              title={tab.enabled ? undefined : "待实现"}
              data-testid={`provider-tab-${tab.key}`}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition-colors",
                tab.key === "chat"
                  ? "bg-muted font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted/60",
                !tab.enabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
              )}
            >
              <Icon className="size-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* 主从两栏 */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[340px_1fr]">
        {/* 左：模型源列表 */}
        <div className="rounded-xl border p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">模型源</h2>
            <AddProviderDialog initialOpen={autoOpenNew} />
          </div>
          {providers.length === 0 ? (
            <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
              还没有模型源，点击右上角「新增」添加
            </p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {providers.map((p) => (
                <ProviderListItem
                  key={p.id}
                  provider={p}
                  selected={p.id === selectedId}
                  onSelect={() => setSelectedId(p.id)}
                  onDelete={() => {
                    if (selectedId === p.id) setSelectedId(null)
                    deleteProvider.mutate(p.id)
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* 右：详情面板 */}
        <div className="rounded-xl border p-6">
          {selected ? (
            <ProviderDetail key={selected.id} provider={selected} />
          ) : (
            <div
              data-testid="provider-empty"
              className="flex h-full min-h-72 flex-col items-center justify-center gap-2 text-muted-foreground"
            >
              <p className="text-4xl">🖱️</p>
              <p className="text-sm">请选择一个模型源</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ProviderSettings

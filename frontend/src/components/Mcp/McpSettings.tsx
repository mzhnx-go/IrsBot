import { zodResolver } from "@hookform/resolvers/zod"
import { ChevronDown, Pencil, Plug, Plus, Trash2, Wrench } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"
import type { MCPServerResponse } from "@/client"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useMcpServers from "@/hooks/useMcpServers"

const TRANSPORT_LABELS: Record<string, string> = {
  sse: "SSE",
  stdio: "stdio（本地命令）",
  streamable_http: "Streamable HTTP",
}

/** 工具条目来自 MCP list_tools：{name, description, inputSchema} */
function toolName(tool: Record<string, unknown>): string {
  return typeof tool.name === "string" ? tool.name : "未知工具"
}

function toolDesc(tool: Record<string, unknown>): string {
  return typeof tool.description === "string" ? tool.description : ""
}

const formSchema = z
  .object({
    name: z.string().min(1, { message: "名称必填" }),
    transport_type: z.enum(["sse", "stdio", "streamable_http"]),
    url: z.string().optional(),
    command: z.string().optional(),
    args: z.string().optional(),
    env_vars: z.string().optional(),
    is_active: z.boolean(),
  })
  .superRefine((data, ctx) => {
    if (data.transport_type === "stdio") {
      if (!data.command?.trim()) {
        ctx.addIssue({
          code: "custom",
          path: ["command"],
          message: "stdio 传输必须填启动命令",
        })
      }
    } else if (!data.url?.trim()) {
      ctx.addIssue({
        code: "custom",
        path: ["url"],
        message: "该传输方式必须填服务地址",
      })
    }
  })

type FormData = z.infer<typeof formSchema>

/** "A=1\nB=2" 多行文本 → env 字典；空行忽略 */
function parseEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split("\n")) {
    const t = line.trim()
    if (!t) continue
    const i = t.indexOf("=")
    if (i > 0) out[t.slice(0, i)] = t.slice(i + 1)
  }
  return out
}

const envToText = (env: Record<string, unknown>): string =>
  Object.entries(env)
    .map(([k, v]) => `${k}=${String(v)}`)
    .join("\n")

interface ServerFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 传入表示编辑，null 为新增 */
  server: MCPServerResponse | null
}

const ServerFormDialog = ({
  open,
  onOpenChange,
  server,
}: ServerFormDialogProps) => {
  const { createServer, updateServer } = useMcpServers()
  const isEdit = server !== null

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: {
      name: "",
      transport_type: "streamable_http",
      url: "",
      command: "",
      args: "",
      env_vars: "",
      is_active: true,
    },
  })

  // 打开时同步初值（编辑回填 / 新增重置）
  useEffect(() => {
    if (!open) return
    form.reset(
      server
        ? {
            name: server.name,
            transport_type: server.transport_type as FormData["transport_type"],
            url: server.url ?? "",
            command: server.command ?? "",
            args: server.args.join(" "),
            env_vars: envToText(server.env_vars ?? {}),
            is_active: server.is_active,
          }
        : {
            name: "",
            transport_type: "streamable_http",
            url: "",
            command: "",
            args: "",
            env_vars: "",
            is_active: true,
          },
    )
  }, [open, server, form])

  const transport = form.watch("transport_type")

  const onSubmit = (data: FormData) => {
    const payload = {
      name: data.name,
      transport_type: data.transport_type,
      url: data.transport_type === "stdio" ? null : data.url || null,
      command: data.transport_type === "stdio" ? data.command || null : null,
      args:
        data.transport_type === "stdio"
          ? (data.args?.trim().split(/\s+/).filter(Boolean) ?? [])
          : [],
      env_vars: parseEnv(data.env_vars ?? ""),
      is_active: data.is_active,
    }
    const onDone = () => onOpenChange(false)
    if (isEdit) {
      updateServer.mutate(
        { serverId: server.id, body: payload },
        { onSuccess: onDone },
      )
    } else {
      createServer.mutate(payload, { onSuccess: onDone })
    }
  }

  const pending = createServer.isPending || updateServer.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "编辑 MCP 服务" : "新增 MCP 服务"}
          </DialogTitle>
          <DialogDescription>
            MCP（Model Context Protocol）服务为 AI 提供外部工具。
            保存后可用「测试连接」验证并拉取工具列表。
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
                        placeholder="如：文件系统"
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
                name="transport_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>传输方式</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="选择传输方式" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="streamable_http">
                          Streamable HTTP
                        </SelectItem>
                        <SelectItem value="sse">SSE</SelectItem>
                        <SelectItem value="stdio">stdio（本地命令）</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {transport === "stdio" ? (
                <>
                  <FormField
                    control={form.control}
                    name="command"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          启动命令 <span className="text-destructive">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="如：npx" type="text" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="args"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>命令参数（空格分隔）</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="如：-y @modelcontextprotocol/server-filesystem /tmp"
                            type="text"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </>
              ) : (
                <FormField
                  control={form.control}
                  name="url"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        服务地址 <span className="text-destructive">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input
                          placeholder="如：https://mcp.example.com/http"
                          type="text"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              <FormField
                control={form.control}
                name="env_vars"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>环境变量（每行 KEY=VALUE，可选）</FormLabel>
                    <FormControl>
                      <textarea
                        rows={3}
                        placeholder={"API_KEY=xxx\nTOKEN=yyy"}
                        className="w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 font-mono text-sm shadow-sm outline-none focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring"
                        {...field}
                      />
                    </FormControl>
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
                    <FormLabel className="!mt-0">
                      启用（AI 对话可调用其工具）
                    </FormLabel>
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

const McpRow = ({ server }: { server: MCPServerResponse }) => {
  const { deleteServer, updateServer, connectServer } = useMcpServers()
  const [editOpen, setEditOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)

  const endpoint =
    server.transport_type === "stdio"
      ? [server.command, ...(server.args ?? [])].filter(Boolean).join(" ")
      : (server.url ?? "")

  const connecting =
    connectServer.isPending && connectServer.variables === server.id

  const handleConnect = () => {
    connectServer.mutate(server.id, {
      onSuccess: (res) => {
        if (res.success) {
          toast.success(res.message || "连接成功")
          setToolsOpen(true)
        } else {
          toast.error(res.message || "连接失败")
        }
      },
    })
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{server.name}</span>
            <Badge variant="secondary">
              {TRANSPORT_LABELS[server.transport_type] ?? server.transport_type}
            </Badge>
            {!server.is_active && <Badge variant="outline">已停用</Badge>}
          </div>
          <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
            {endpoint || "—"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={connecting}
            onClick={handleConnect}
          >
            <Plug className={connecting ? "animate-pulse" : undefined} />
            {connecting ? "连接中…" : "测试连接"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              updateServer.mutate({
                serverId: server.id,
                body: { is_active: !server.is_active },
              })
            }
          >
            {server.is_active ? "停用" : "启用"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label="编辑"
            onClick={() => setEditOpen(true)}
          >
            <Pencil />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label="删除"
            className="text-destructive"
            onClick={() => setConfirmOpen(true)}
          >
            <Trash2 />
          </Button>
        </div>
      </div>

      {/* 工具预览：connect 成功后后端缓存在 tools 列 */}
      {server.tools?.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setToolsOpen((v) => !v)}
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors duration-100 hover:text-foreground"
          >
            <Wrench className="size-3" />
            {server.tools.length} 个工具
            <ChevronDown
              className={`size-3 transition-transform duration-200 motion-reduce:transition-none ${
                toolsOpen ? "rotate-180" : ""
              }`}
            />
          </button>
          {/* 折叠动画：grid-rows 0fr→1fr，只动布局不引发布局抖动 */}
          <div
            className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${
              toolsOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
            }`}
          >
            <div className="overflow-hidden">
              <ul className="mt-1.5 flex flex-col gap-1">
                {server.tools.map((t, i) => (
                  <li
                    key={i}
                    className="rounded-md bg-muted/50 px-2.5 py-1.5 text-xs"
                  >
                    <span className="font-mono font-medium">{toolName(t)}</span>
                    {toolDesc(t) && (
                      <span className="ml-2 text-muted-foreground">
                        {toolDesc(t)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      <ServerFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        server={server}
      />

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>删除 MCP 服务</DialogTitle>
            <DialogDescription>
              确定删除「{server.name}」吗？该操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <DialogClose asChild>
              <Button variant="outline">取消</Button>
            </DialogClose>
            <Button
              variant="destructive"
              onClick={() => {
                deleteServer.mutate(server.id)
                setConfirmOpen(false)
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

const McpSettings = () => {
  const { mcpQuery } = useMcpServers()
  const [addOpen, setAddOpen] = useState(false)

  if (mcpQuery.isPending) {
    return null
  }

  const servers = mcpQuery.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">MCP 服务</h2>
          <p className="text-sm text-muted-foreground">
            接入外部 MCP（Model Context Protocol）服务，为 AI 对话扩展工具。
          </p>
        </div>
        <Button onClick={() => setAddOpen(true)}>
          <Plus className="mr-2" />
          新增 MCP 服务
        </Button>
      </div>

      {servers.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          还没有 MCP 服务。点击右上角「新增 MCP 服务」接入外部工具。
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {servers.map((s) => (
            <McpRow key={s.id} server={s} />
          ))}
        </div>
      )}

      <ServerFormDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        server={null}
      />
    </div>
  )
}

export default McpSettings

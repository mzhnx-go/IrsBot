import { AlertTriangle } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import useToolPermissions from "@/hooks/useToolPermissions"

/**
 * 工具权限开关（超管专属，位于设置页）。
 *
 * 这里只决定 Agent **能看到**哪些危险工具：关闭后工具不会进入本轮
 * 工具集，即使模型凭记忆调用也会收到「工具不存在」。shell 关闭同时
 * 影响不了 file 工具，两个开关各自独立；file_write 另受
 * FILE_WRITE_ROOTS 路径白名单约束（开关只是第一道门）。
 */
const ToolPermissionsSettings = () => {
  const { toolPermissionsQuery, updateToolPermissions } = useToolPermissions()

  if (toolPermissionsQuery.isPending) {
    return <p className="text-muted-foreground py-4 text-sm">加载中…</p>
  }

  // 读不到就不渲染：超管页的附加信息，不值得用错误态盖住主内容
  if (toolPermissionsQuery.isError || !toolPermissionsQuery.data) {
    return null
  }

  const settings = toolPermissionsQuery.data
  const busy = updateToolPermissions.isPending

  // 只提交被改动的字段：后端会用当前值合并未提供的字段，
  // 避免快速连续切换时用过期缓存互相覆盖
  const apply = (patch: {
    shell_enabled?: boolean
    file_write_enabled?: boolean
  }) => updateToolPermissions.mutate(patch)

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>工具权限</CardTitle>
        <CardDescription>
          决定 Agent 是否可以使用高破坏力工具。保存后立即生效（下一轮对话起），
          无需重启。默认全部关闭。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {(!settings.shell_enabled || !settings.file_write_enabled) && (
          <Alert>
            <AlertTriangle />
            <AlertTitle>风险提示</AlertTitle>
            <AlertDescription>
              开启后模型可执行任意命令 / 写服务器文件。仅在你信任的使用环境
              （本机、内网）中开启。
            </AlertDescription>
          </Alert>
        )}

        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="font-medium">shell_execute（命令执行）</span>
            <span className="text-sm text-muted-foreground">
              允许 Agent 在服务器执行 shell 命令。
              {!settings.shell_enabled && settings.env_shell_enabled && (
                <span className="text-foreground">
                  {" "}
                  `.env` 中 ENABLE_SHELL=true 已被此处覆盖。
                </span>
              )}
            </span>
          </div>
          <Switch
            checked={settings.shell_enabled}
            disabled={busy}
            onCheckedChange={(checked) => apply({ shell_enabled: checked })}
            aria-label="启用 shell_execute"
            data-testid="tool-permission-shell"
          />
        </div>

        <Separator />

        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="font-medium">
              file_read / file_write（服务器文件读写）
            </span>
            <span className="text-sm text-muted-foreground">
              允许 Agent 读取和写入服务器文件；写入仍受 FILE_WRITE_ROOTS
              路径白名单限制。
              {!settings.file_write_enabled &&
                settings.env_file_write_enabled && (
                  <span className="text-foreground">
                    {" "}
                    `.env` 中 ENABLE_FILE_WRITE=true 已被此处覆盖。
                  </span>
                )}
            </span>
          </div>
          <Switch
            checked={settings.file_write_enabled}
            disabled={busy}
            onCheckedChange={(checked) =>
              apply({ file_write_enabled: checked })
            }
            aria-label="启用文件读写工具"
            data-testid="tool-permission-file"
          />
        </div>
      </CardContent>
    </Card>
  )
}

export default ToolPermissionsSettings

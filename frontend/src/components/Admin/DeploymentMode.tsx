import { useState } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import useDeploymentSettings from "@/hooks/useDeploymentSettings"

/**
 * 部署模式开关（单用户 / 多租户）—— 超管专属，放在 /admin 页。
 *
 * 这个控件背后只有**一个**配置：匿名自助注册是否开放。
 * 「单用户 / 多租户」是它的展示标签，因为「超管始终可建号、归属隔离始终生效」
 * 在两种模式下没有差别，再拆一个开关只会多出两个产出相同结果的档位。
 *
 * 开启「多租户」会弹二次确认：这一步等于**对任何能访问此服务的人开放注册**，
 * 而注册进来的账号会消耗部署者自己的 API Key。
 */
const DeploymentMode = () => {
  const { deploymentSettingsQuery, updateDeploymentSettings } =
    useDeploymentSettings()
  const [confirmOpen, setConfirmOpen] = useState(false)

  if (deploymentSettingsQuery.isPending) {
    return <p className="text-muted-foreground py-4 text-sm">加载中…</p>
  }

  // 读不到就不渲染：这是超管页的附加信息，不值得用错误态盖住主内容
  if (deploymentSettingsQuery.isError || !deploymentSettingsQuery.data) {
    return null
  }

  const settings = deploymentSettingsQuery.data
  const isMultiTenant = settings.open_registration
  const busy = updateDeploymentSettings.isPending

  const apply = (openRegistration: boolean) =>
    updateDeploymentSettings.mutate({ open_registration: openRegistration })

  return (
    <>
      <Card data-testid="deployment-mode-card">
        <CardHeader>
          <CardTitle>部署模式</CardTitle>
          <CardDescription>
            决定是否允许任何人自助注册账号。管理员建号、数据归属隔离在两种模式下
            <strong className="font-medium text-foreground">完全一致</strong>
            ，不受此开关影响。
          </CardDescription>
        </CardHeader>

        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Button
              variant={isMultiTenant ? "outline" : "default"}
              onClick={() => apply(false)}
              disabled={busy || !isMultiTenant}
              data-testid="deployment-mode-single-user"
            >
              单用户模式
            </Button>
            <Button
              variant={isMultiTenant ? "default" : "outline"}
              onClick={() => setConfirmOpen(true)}
              disabled={busy || isMultiTenant}
              data-testid="deployment-mode-multi-tenant"
            >
              多租户模式
            </Button>
          </div>

          <p className="text-sm text-muted-foreground">
            {isMultiTenant
              ? "当前：任何访问者都能在登录页注册账号。"
              : "当前：只接受管理员创建的账号，登录页不显示注册入口。"}
          </p>

          {settings.user_count > 1 && (
            <p className="text-sm text-muted-foreground">
              系统内已有 {settings.user_count} 个账号； 关闭自助注册
              <strong>不会</strong>删除或停用它们，它们仍可正常登录。
            </p>
          )}

          {settings.env_open_registration !== settings.open_registration && (
            <Alert>
              <AlertDescription>
                `.env` 里的 USERS_OPEN_REGISTRATION=
                {String(settings.env_open_registration)}
                已被此处的设置覆盖 —— 之后修改 `.env` 不再生效，请在此页调整。
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>开启多租户模式？</DialogTitle>
            <DialogDescription className="flex flex-col gap-2">
              <span>
                开启后，
                <strong className="font-medium text-foreground">
                  任何能访问此服务的人都可以注册账号
                </strong>
                ，并使用你配置的模型源（消耗你的 API Key）。
              </span>
              <span>
                请确认服务未暴露到公网，或你确实希望他人使用。开启后可随时切回
                单用户模式。
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              取消
            </Button>
            <Button
              onClick={() => {
                setConfirmOpen(false)
                apply(true)
              }}
              data-testid="deployment-mode-confirm"
            >
              确认开启
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default DeploymentMode

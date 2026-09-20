import { createFileRoute } from "@tanstack/react-router"
import type { ComponentType } from "react"

import ChangePassword from "@/components/UserSettings/ChangePassword"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import SystemPromptSettings from "@/components/UserSettings/SystemPromptSettings"
import ToolPermissionsSettings from "@/components/UserSettings/ToolPermissionsSettings"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"

type SettingsTab = {
  value: string
  title: string
  component: ComponentType
  superuserOnly?: boolean
}

const tabsConfig: SettingsTab[] = [
  { value: "my-profile", title: "我的资料", component: UserInformation },
  { value: "password", title: "密码", component: ChangePassword },
  {
    value: "system-prompt",
    title: "系统提示词",
    component: SystemPromptSettings,
  },
  {
    value: "tool-permissions",
    title: "工具权限",
    component: ToolPermissionsSettings,
    superuserOnly: true,
  },
  { value: "danger-zone", title: "危险操作", component: DeleteAccount },
]

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  head: () => ({
    meta: [
      {
        title: "设置 - IrsBot",
      },
    ],
  }),
})

function UserSettings() {
  const { user: currentUser } = useAuth()

  if (!currentUser) {
    return null
  }

  const tabs = tabsConfig.filter(
    (tab) => !tab.superuserOnly || currentUser.is_superuser,
  )

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">用户设置</h1>
        <p className="text-muted-foreground">管理账号设置与偏好</p>
      </div>

      <Tabs defaultValue="my-profile">
        <TabsList>
          {tabs.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.title}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            <tab.component />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}

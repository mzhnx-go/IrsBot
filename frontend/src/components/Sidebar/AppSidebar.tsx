import {
  Home,
  Library,
  MessageSquare,
  PanelLeftClose,
  Settings,
  Users
} from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

// ⚠️ 原 `{ icon: Briefcase, title: "Items", path: "/items" }` 已随 D1.4 删除
//    （模板残留的示例待办功能，IrsBot 不使用）。
const baseItems: Item[] = [
  { icon: Home, title: "Dashboard", path: "/" },
  { icon: MessageSquare, title: "聊天", path: "/chat" },
  { icon: Library, title: "知识库", path: "/knowledge-base" },
  { icon: Settings, title: "设置", path: "/settings" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const items = currentUser?.is_superuser
    ? [...baseItems, { icon: Users, title: "Admin", path: "/admin" }]
    : baseItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="flex flex-row items-center justify-between gap-2 px-4 py-3 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
        <Logo variant="responsive" />
        {/* 收起侧边栏按钮（仿千问）：窄侧栏模式下隐藏 */}
        <SidebarTrigger className="text-muted-foreground group-data-[collapsible=icon]:hidden">
          <PanelLeftClose className="h-4 w-4" />
        </SidebarTrigger>
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar

import {
  BarChart3,
  BookOpen,
  Drama,
  Home,
  Library,
  MessagesSquare,
  PanelLeftClose,
  Plug,
  Settings,
  Sparkles,
  Users,
} from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import ConversationList from "@/components/Sidebar/ConversationList"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type ItemGroup, Main } from "./Main"
import { User } from "./User"

// 信息架构重组（Phase 15.3a）：按「工作台 / 资源 / 系统」三段分组，
// 使用频率高的对话类入口放最上，资源管理居中，低频的系统配置垫底。
// 「聊天」入口已移除：下方 ConversationList 的「新对话」+「最近对话」才是
// 进聊天的真实路径，一个 /chat 不需要三个入口。
const navGroups: ItemGroup[] = [
  {
    label: "工作台",
    items: [
      { icon: Home, title: "Dashboard", path: "/" },
      { icon: MessagesSquare, title: "会话管理", path: "/conversations" },
    ],
  },
  {
    label: "资源",
    items: [
      { icon: Library, title: "知识库", path: "/knowledge-base" },
      { icon: Plug, title: "MCP 服务", path: "/mcp" },
      { icon: BookOpen, title: "技能", path: "/skills" },
      { icon: Drama, title: "人设", path: "/personas" },
    ],
  },
  {
    label: "系统",
    items: [
      { icon: Sparkles, title: "模型源", path: "/providers" },
      { icon: BarChart3, title: "统计", path: "/stats" },
      { icon: Settings, title: "设置", path: "/settings" },
      { icon: Users, title: "Admin", path: "/admin", superuserOnly: true },
    ],
  },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const groups: ItemGroup[] = navGroups.map((group) => ({
    ...group,
    items: group.items.filter(
      (item) => !item.superuserOnly || Boolean(currentUser?.is_superuser),
    ),
  }))

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
        <Main groups={groups} />
        {/* 历史对话（Phase 15.1）：仅在有会话数据的聊天场景展示 */}
        <ConversationList />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar

import AppSidebar from "@/components/Sidebar/AppSidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { isLoggedIn } from "@/hooks/useAuth";
import {
  createFileRoute,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router";
import { PanelLeftOpen } from "lucide-react";
import { useEffect, useState } from "react"; // 引入必要的 React Hooks

export const Route = createFileRoute("/_layout")({
  component: Layout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
  },
})

function Layout() {
  // 聊天页全屏沉浸：隐藏顶栏和页脚
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const isChatPage = pathname === "/chat"

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <ChatExpandTrigger />
        <main className={isChatPage ? "flex-1" : "flex-1 p-6 md:p-8"}>
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

/**
 * 侧边栏收起后在左上角悬浮一个展开按钮（全页面通用）
 * 使用 useEffect 监听状态变化，延迟触发淡入动画，避免与侧边栏滑动动画冲突。
 */
function ChatExpandTrigger() {
  const { state } = useSidebar()
  // 独立控制按钮的淡入状态
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (state === "collapsed") {
      // 侧边栏收起动画通常为 200ms，这里延迟 200ms 后再让按钮淡入
      const timer = setTimeout(() => {
        setIsVisible(true)
      }, 200)

      // 清理定时器，防止内存泄漏或状态错乱
      return () => clearTimeout(timer)
    }
    // 展开时，立即隐藏按钮（无退出动画，符合你的需求）
    setIsVisible(false)
  }, [state])

  return (
    <SidebarTrigger
      // 始终渲染组件，通过 opacity 和 pointer-events 控制视觉显隐和点击穿透
      className={`chat-expand-trigger fixed left-[3.5rem] top-3 z-20 text-muted-foreground transition-opacity duration-150 ease-out ${
        isVisible ? "opacity-100" : "opacity-0 pointer-events-none"
      }`}
    >
      <PanelLeftOpen className="h-4 w-4" />
    </SidebarTrigger>
  )
}

export default Layout

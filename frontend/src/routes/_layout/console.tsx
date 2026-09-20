import { createFileRoute, redirect } from "@tanstack/react-router"

import LogConsole from "@/components/Console/LogConsole"
import { UsersService } from "@/client"

export const Route = createFileRoute("/_layout/console")({
  component: Console,
  beforeLoad: async () => {
    const user = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: "控制台 - IrsBot",
      },
    ],
  }),
})

function Console() {
  return (
    <div className="flex h-full flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">控制台</h1>
        <p className="text-muted-foreground">
          实时查看后端运行日志（仅保留最近 2000 条，重启即清空；持久化请用
          docker compose logs）
        </p>
      </div>
      <div className="min-h-0 flex-1">
        <LogConsole />
      </div>
    </div>
  )
}

import { createFileRoute } from "@tanstack/react-router"

import ProviderSettings from "@/components/Providers/ProviderSettings"

export const Route = createFileRoute("/_layout/providers")({
  // ?new=1：从聊天空状态引导跳转过来时，自动展开「新增模型源」弹窗
  validateSearch: (search: Record<string, unknown>) => ({
    new: search.new === 1 || search.new === "1" ? 1 : undefined,
  }),
  component: ProvidersPage,
  head: () => ({
    meta: [
      {
        title: "模型源 - IrsBot",
      },
    ],
  }),
})

function ProvidersPage() {
  const { new: isNew } = Route.useSearch()
  return <ProviderSettings autoOpenNew={Boolean(isNew)} />
}

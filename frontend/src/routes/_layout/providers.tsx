import { createFileRoute } from "@tanstack/react-router"

import ProviderSettings from "@/components/Providers/ProviderSettings"

export const Route = createFileRoute("/_layout/providers")({
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
  return <ProviderSettings />
}

import { createFileRoute } from "@tanstack/react-router"

import StatsDashboard from "@/components/Stats/StatsDashboard"

export const Route = createFileRoute("/_layout/stats")({
  component: StatsPage,
  head: () => ({
    meta: [
      {
        title: "统计 - IrsBot",
      },
    ],
  }),
})

function StatsPage() {
  return <StatsDashboard />
}

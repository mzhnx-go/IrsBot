import { createFileRoute } from "@tanstack/react-router"

import McpSettings from "@/components/Mcp/McpSettings"

export const Route = createFileRoute("/_layout/mcp")({
  component: McpPage,
  head: () => ({
    meta: [
      {
        title: "MCP 服务 - IrsBot",
      },
    ],
  }),
})

function McpPage() {
  return <McpSettings />
}

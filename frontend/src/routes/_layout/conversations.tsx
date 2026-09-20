import { createFileRoute } from "@tanstack/react-router"

import ConversationManagement from "@/components/Conversations/ConversationManagement"

export const Route = createFileRoute("/_layout/conversations")({
  component: ConversationsPage,
  head: () => ({
    meta: [
      {
        title: "会话管理 - IrsBot",
      },
    ],
  }),
})

function ConversationsPage() {
  return <ConversationManagement />
}

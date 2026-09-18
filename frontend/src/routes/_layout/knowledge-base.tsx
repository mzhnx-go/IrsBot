import { createFileRoute } from "@tanstack/react-router"

import KnowledgeBaseManager from "@/components/KnowledgeBase/KnowledgeBaseManager"

export const Route = createFileRoute("/_layout/knowledge-base")({
  component: KnowledgeBasePage,
})

function KnowledgeBasePage() {
  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8">
      <KnowledgeBaseManager />
    </div>
  )
}

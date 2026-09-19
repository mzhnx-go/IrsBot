import { createFileRoute } from "@tanstack/react-router"

import KnowledgeBaseDetail from "@/components/KnowledgeBase/KnowledgeBaseDetail"

export const Route = createFileRoute("/_layout/knowledge-base/$kbId")({
  component: KnowledgeBaseDetailPage,
})

function KnowledgeBaseDetailPage() {
  const { kbId } = Route.useParams()

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8">
      <KnowledgeBaseDetail kbId={kbId} />
    </div>
  )
}

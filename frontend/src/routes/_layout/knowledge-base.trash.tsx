import { createFileRoute } from "@tanstack/react-router"

import KnowledgeBaseTrash from "@/components/KnowledgeBase/KnowledgeBaseTrash"

/** /knowledge-base/trash —— 回收站（静态段优先于 $kbId，不会被当成知识库 id） */
export const Route = createFileRoute("/_layout/knowledge-base/trash")({
  component: KnowledgeBaseTrashPage,
})

function KnowledgeBaseTrashPage() {
  return <KnowledgeBaseTrash />
}
import { createFileRoute } from "@tanstack/react-router"

import KnowledgeBaseManager from "@/components/KnowledgeBase/KnowledgeBaseManager"

/** /knowledge-base 精确匹配（index 路由）——知识库列表页 */
export const Route = createFileRoute("/_layout/knowledge-base/")({
  component: KnowledgeBaseListPage,
})

function KnowledgeBaseListPage() {
  return <KnowledgeBaseManager />
}
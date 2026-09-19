import { createFileRoute, Outlet } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/knowledge-base")({
  component: KnowledgeBaseLayout,
})

/**
 * 父路由只做布局壳：必须渲染 <Outlet />，否则子路由（/knowledge-base/$kbId
 * 详情页）没有渲染插槽，详情 URL 会一直显示父组件的内容。
 */
function KnowledgeBaseLayout() {
  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8">
      <Outlet />
    </div>
  )
}

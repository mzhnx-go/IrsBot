import { expect, test } from "@playwright/test"

/**
 * Phase 15 各配置台/对话页面的冒烟测试（15.3b：每页至少 1 条）。
 *
 * 全部走默认 storageState（超管会话）：这些页面本身即"超管配好环境后
 * 的日常入口"，普通用户的可见性差异在 onboarding.spec.ts 里单独锁。
 */

const pages: { path: string; heading: string }[] = [
  { path: "/chat", heading: "有什么可以帮你？" },
  { path: "/knowledge-base", heading: "知识库" },
  { path: "/providers", heading: "模型源" },
  { path: "/mcp", heading: "MCP 服务" },
  { path: "/skills", heading: "技能" },
  { path: "/personas", heading: "人设" },
  { path: "/conversations", heading: "会话管理" },
  { path: "/stats", heading: "统计" },
]

for (const { path, heading } of pages) {
  test(`${path} 页面可访问且渲染核心标题`, async ({ page }) => {
    await page.goto(path)
    await expect(page.getByRole("heading", { name: heading })).toBeVisible()
  })
}

test("/conversations 搜索框可用", async ({ page }) => {
  await page.goto("/conversations")
  const search = page.getByPlaceholder("按标题搜索…")
  await expect(search).toBeVisible()
  await expect(search).toBeEditable()
})

test("/stats 指标卡渲染", async ({ page }) => {
  await page.goto("/stats")
  for (const label of ["运行次数", "Token 用量", "平均耗时", "工具调用"]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible()
  }
})

test("/settings 工具权限标签（超管可见且开关渲染）", async ({ page }) => {
  await page.goto("/settings")
  await page.getByRole("tab", { name: "工具权限" }).click()
  await expect(page.getByTestId("tool-permission-shell")).toBeVisible()
  await expect(page.getByTestId("tool-permission-file")).toBeVisible()
})

test("侧边栏信息架构：三个分组标签齐全", async ({ page }) => {
  await page.goto("/")
  // 注意：shadcn 的 <aside> 嵌在布局容器里，不会映射成 complementary 角色，
  // 所以用 data-sidebar 属性圈定范围
  const sidebar = page.locator('[data-sidebar="sidebar"]').first()
  for (const label of ["工作台", "资源", "系统"]) {
    await expect(sidebar.getByText(label, { exact: true })).toBeVisible()
  }
  await expect(sidebar.getByText("Admin", { exact: true })).toBeVisible()
})

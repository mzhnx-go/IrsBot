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
    // 指标卡标签与明细表列名可能同名（如「工具调用」），取第一个即可
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
  }
})

test("/providers 每张卡片都有查余额按钮", async ({ page }) => {
  await page.goto("/providers")
  const rows = page.getByTestId("provider-row")
  await expect(rows.first()).toBeVisible()
  // 卡片数与按钮数必须一一对应：漏渲染的卡片会让用户以为"这条不支持"
  await expect(page.getByTestId("provider-balance-button")).toHaveCount(
    await rows.count(),
  )
})

test("/providers 查余额：不支持的厂商给出明确提示", async ({ page }) => {
  await page.goto("/providers")
  // 按行定位、不靠顺序：用户随时会加自己的模型源，第一条不一定是种子源。
  // 种子的 default 源指向 dashscope（.env 的 OPENAI_BASE_URL），该厂商无余额
  // 接口 → 后端走本地提示分支、不发上游请求，因此本用例离线可稳定复现。
  const row = page
    .getByTestId("provider-row")
    .filter({ hasText: "dashscope.aliyuncs.com" })
  await expect(row).toHaveCount(1)
  await row.getByTestId("provider-balance-button").click()
  await expect(row.getByTestId("provider-balance-result")).toContainText(
    "阿里云",
  )
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

test("侧边栏：「聊天」入口已移除，「新对话」在「最近对话」之上", async ({
  page,
}) => {
  await page.goto("/")
  const sidebar = page.locator('[data-sidebar="sidebar"]').first()

  // 进聊天的真实路径是「新对话」+「最近对话」，不再保留独立的「聊天」入口
  await expect(sidebar.getByText("聊天", { exact: true })).toHaveCount(0)

  // 用归属关系（DOM 纵向位置）而非文案顺序断言：
  // 种子库里存在标题就叫「新对话」的会话，纯文案定位会撞上
  const newChat = sidebar.getByTestId("new-chat-button")
  const label = sidebar.getByText("最近对话", { exact: true })
  await expect(newChat).toBeVisible()
  await expect(label).toBeVisible()

  const newChatBox = await newChat.boundingBox()
  const labelBox = await label.boundingBox()
  expect(newChatBox).not.toBeNull()
  expect(labelBox).not.toBeNull()
  expect(newChatBox!.y).toBeLessThan(labelBox!.y)
})

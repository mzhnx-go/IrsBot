import { expect, test } from "@playwright/test"
import { randomEmail, randomPassword } from "./utils/random"
import { createUser } from "./utils/privateApi"
import { logInUser } from "./utils/user"

// 控制台页（/console）：superuser 专属的实时日志视图。
// 前置：backend 已挂日志环形缓冲（GET /api/v1/logs），dist 为含 /console 的新构建。

test.describe("Console page (superuser)", () => {
  test("页面可见且渲染日志条目", async ({ page }) => {
    await page.goto("/console")
    await expect(page.getByRole("heading", { name: "控制台" })).toBeVisible()
    // 后端启动至今必有日志，等首轮轮询（2s）拿到数据
    await expect(page.getByTestId("console-log-entry").first()).toBeVisible({
      timeout: 10_000,
    })
    await expect(page.getByTestId("console-connection")).toContainText(
      "实时刷新中",
    )
  })

  test("侧边栏出现「控制台」入口（superuser 可见）", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByRole("link", { name: "控制台" })).toBeVisible()
  })

  test("暂停/继续切换生效", async ({ page }) => {
    await page.goto("/console")
    await expect(page.getByTestId("console-log-entry").first()).toBeVisible({
      timeout: 10_000,
    })

    await page.getByTestId("console-toggle").click()
    await expect(page.getByTestId("console-connection")).toContainText("已暂停")
    await page.getByTestId("console-toggle").click()
    await expect(page.getByTestId("console-connection")).toContainText(
      "实时刷新中",
    )
  })

  test("关键字过滤命中指定标记", async ({ page }) => {
    await page.goto("/console")
    await expect(page.getByTestId("console-log-entry").first()).toBeVisible({
      timeout: 10_000,
    })

    // 输入一个必然不存在的关键字 → 视图清空并显示空态
    await page.getByTestId("console-search").fill("console-e2e-no-such-marker")
    await expect(page.getByTestId("console-log-entry")).toHaveCount(0)
    await expect(page.getByText(/暂无符合条件的日志/)).toBeVisible()

    await page.getByTestId("console-search").fill("")
    await expect(page.getByTestId("console-log-entry").first()).toBeVisible()
  })

  test("清屏后视图为空、计数归零", async ({ page }) => {
    await page.goto("/console")
    await expect(page.getByTestId("console-log-entry").first()).toBeVisible({
      timeout: 10_000,
    })

    await page.getByTestId("console-clear").click()
    await expect(page.getByTestId("console-log-entry")).toHaveCount(0)
    await expect(page.getByTestId("console-count")).toContainText("0 / 0 条")
  })
})

test.describe("Console page (normal user)", () => {
  // 清掉 setup 注入的 superuser 会话，否则 /login 会被已登录态重定向走
  test.use({ storageState: { cookies: [], origins: [] } })

  test("普通用户访问 /console 被重定向回首页", async ({ page }) => {
    const email = randomEmail()
    const password = randomPassword()
    await createUser({ email, password })

    await logInUser(page, email, password)
    await page.goto("/console")
    await expect(page).not.toHaveURL(/\/console/)
    await expect(page).toHaveURL(/\/$/)
  })
})

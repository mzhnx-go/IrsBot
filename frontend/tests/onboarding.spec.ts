import { expect, test } from "@playwright/test"
import { createUser } from "./utils/privateApi"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser } from "./utils/user"

/**
 * 配置闭环引导（15.2g）+ 普通用户可见性（15.2f）—— 需要一个**没有模型源**
 * 的新账号才能验证引导卡；Provider 按用户归属，新建账号天然是零配置状态。
 */
test.describe("首进引导与权限可见性", () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  let email: string
  let password: string

  test.beforeAll(async () => {
    email = randomEmail()
    password = randomPassword()
    await createUser({ email, password })
  })

  test("聊天空状态显示模型源引导，一键直达新增弹窗", async ({ page }) => {
    await logInUser(page, email, password)
    await page.goto("/chat")

    await expect(page.getByText("先配置一个模型源")).toBeVisible()

    await page.getByTestId("onboarding-go-providers").click()
    await expect(page).toHaveURL(/\/providers\?new=1/)
    await expect(
      page.getByRole("heading", { name: "新增模型源" }),
    ).toBeVisible()
  })

  test("普通用户设置页不显示「工具权限」标签", async ({ page }) => {
    await logInUser(page, email, password)
    await page.goto("/settings")

    await expect(page.getByRole("tab", { name: "工具权限" })).toHaveCount(0)
    // 其余标签正常，确认不是整页没渲染导致的假阴性
    await expect(page.getByRole("tab", { name: "我的资料" })).toBeVisible()
  })
})

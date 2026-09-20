import { expect, type Page } from "@playwright/test"

// ⚠️ signUpNewUser 辅助已删除：注册默认关闭（单用户模式），
//    测试建统一律走 privateApi.createUser，不再经由注册页。

export async function logInUser(page: Page, email: string, password: string) {
  await page.goto("/login")

  await page.getByTestId("email-input").fill(email)
  await page.getByTestId("password-input").fill(password)
  await page.getByRole("button", { name: "登录" }).click()
  await page.waitForURL("/")
  await expect(page.getByText("欢迎回来，很高兴又见到你！")).toBeVisible()
}

export async function logOutUser(page: Page) {
  await page.getByTestId("user-menu").click()
  await page.getByRole("menuitem", { name: "退出登录" }).click()
  await page.goto("/login")
}

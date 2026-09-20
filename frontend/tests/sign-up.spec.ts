import { expect, type Page, test } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "./config.ts"
import { randomEmail, randomPassword } from "./utils/random"

test.use({ storageState: { cookies: [], origins: [] } })

const fillForm = async (
  page: Page,
  full_name: string,
  email: string,
  password: string,
  confirm_password: string,
) => {
  await page.getByTestId("full-name-input").fill(full_name)
  await page.getByTestId("email-input").fill(email)
  await page.getByTestId("password-input").fill(password)
  await page.getByTestId("confirm-password-input").fill(confirm_password)
}

const verifyInput = async (page: Page, testId: string) => {
  const input = page.getByTestId(testId)
  await expect(input).toBeVisible()
  await expect(input).toHaveText("")
  await expect(input).toBeEditable()
}

test("Inputs are visible, empty and editable", async ({ page }) => {
  await page.goto("/signup")

  await verifyInput(page, "full-name-input")
  await verifyInput(page, "email-input")
  await verifyInput(page, "password-input")
  await verifyInput(page, "confirm-password-input")
})

test("Sign Up button is visible", async ({ page }) => {
  await page.goto("/signup")

  await expect(page.getByRole("button", { name: "注册" })).toBeVisible()
})

test("Log In link is visible", async ({ page }) => {
  await page.goto("/signup")

  await expect(page.getByRole("link", { name: "登录" })).toBeVisible()
})

test("Sign up with valid name, email, and password", async ({ page }) => {
  const full_name = "Test User"
  const email = randomEmail()
  const password = randomPassword()

  await page.goto("/signup")
  await fillForm(page, full_name, email, password, password)
  await page.getByRole("button", { name: "注册" }).click()
})

test("Sign up with invalid email", async ({ page }) => {
  await page.goto("/signup")

  await fillForm(
    page,
    "Playwright Test",
    "invalid-email",
    "changethis",
    "changethis",
  )
  await page.getByRole("button", { name: "注册" }).click()

  await expect(page.getByText("邮箱格式不正确")).toBeVisible()
})

// 默认部署是单用户模式（注册关闭）。本用例验证**开放注册下**的重复邮箱报错，
// 所以在 describe 级别临时打开、afterAll 恢复原值 —— 即使用例中途超时，
// 恢复也一定执行（此前放在用例体内 + finally，超时后 context 已关闭导致恢复失败）。
test.describe("开放注册场景", () => {
  let authHeaders: Record<string, string>
  let original: boolean

  test.beforeAll(async ({ request }) => {
    const login = await request.post("/api/v1/login/access-token", {
      form: { username: firstSuperuser, password: firstSuperuserPassword },
    })
    expect(login.ok()).toBeTruthy()
    const token = (await login.json()).access_token as string
    authHeaders = { Authorization: `Bearer ${token}` }

    const before = await request.get("/api/v1/settings/deployment", {
      headers: authHeaders,
    })
    original = (await before.json()).open_registration as boolean

    await request.patch("/api/v1/settings/deployment", {
      headers: authHeaders,
      data: { open_registration: true },
    })
  })

  test.afterAll(async ({ request }) => {
    if (!original) {
      const login = await request.post("/api/v1/login/access-token", {
        form: { username: firstSuperuser, password: firstSuperuserPassword },
      })
      const token = (await login.json()).access_token as string
      await request.patch("/api/v1/settings/deployment", {
        headers: { Authorization: `Bearer ${token}` },
        data: { open_registration: false },
      })
    }
  })

  test("Sign up with existing email", async ({ page }) => {
    test.setTimeout(60000)
    const fullName = "Test User"
    const email = randomEmail()
    const password = randomPassword()

    await page.goto("/signup")
    await fillForm(page, fullName, email, password, password)
    await page.getByRole("button", { name: "注册" }).click()
    // 注册成功不自动登录：跳转 /login 让用户手动登录
    await page.waitForURL("/login")

    await page.goto("/signup")
    await fillForm(page, fullName, email, password, password)
    await page.getByRole("button", { name: "注册" }).click()

    await expect(
      page.getByText("The user with this email already exists in the system"),
    ).toBeVisible()
  })
})

test("Sign up with weak password", async ({ page }) => {
  const fullName = "Test User"
  const email = randomEmail()
  const password = "weak"

  await page.goto("/signup")

  await fillForm(page, fullName, email, password, password)
  await page.getByRole("button", { name: "注册" }).click()

  await expect(page.getByText("密码长度至少为 8 个字符")).toBeVisible()
})

test("Sign up with mismatched passwords", async ({ page }) => {
  const fullName = "Test User"
  const email = randomEmail()
  const password = randomPassword()
  const password2 = randomPassword()

  await page.goto("/signup")

  await fillForm(page, fullName, email, password, password2)
  await page.getByRole("button", { name: "注册" }).click()

  await expect(page.getByText("两次输入的密码不一致")).toBeVisible()
})

test("Sign up with missing full name", async ({ page }) => {
  const fullName = ""
  const email = randomEmail()
  const password = randomPassword()

  await page.goto("/signup")

  await fillForm(page, fullName, email, password, password)
  await page.getByRole("button", { name: "注册" }).click()

  await expect(page.getByText("请输入姓名")).toBeVisible()
})

test("Sign up with missing email", async ({ page }) => {
  const fullName = "Test User"
  const email = ""
  const password = randomPassword()

  await page.goto("/signup")

  await fillForm(page, fullName, email, password, password)
  await page.getByRole("button", { name: "注册" }).click()

  await expect(page.getByText("邮箱格式不正确")).toBeVisible()
})

test("Sign up with missing password", async ({ page }) => {
  const fullName = ""
  const email = randomEmail()
  const password = ""

  await page.goto("/signup")

  await fillForm(page, fullName, email, password, password)
  await page.getByRole("button", { name: "注册" }).click()

  await expect(page.getByText("请输入密码")).toBeVisible()
})

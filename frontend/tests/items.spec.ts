import { expect, test } from "@playwright/test"
import { createUser } from "./utils/privateApi"
import {
  randomEmail,
  randomItemDescription,
  randomItemTitle,
  randomPassword,
} from "./utils/random"
import { logInUser } from "./utils/user"

test("Items page is accessible and shows correct title", async ({ page }) => {
  await page.goto("/items")
  await expect(page.getByRole("heading", { name: "物品" })).toBeVisible()
  await expect(page.getByText("创建并管理你的物品")).toBeVisible()
})

test("Add Item button is visible", async ({ page }) => {
  await page.goto("/items")
  await expect(page.getByRole("button", { name: "新增物品" })).toBeVisible()
})

test.describe("Items management", () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  let email: string
  const password = randomPassword()

  test.beforeAll(async () => {
    email = randomEmail()
    await createUser({ email, password })
  })

  test.beforeEach(async ({ page }) => {
    await logInUser(page, email, password)
    await page.goto("/items")
  })

  test("Create a new item successfully", async ({ page }) => {
    const title = randomItemTitle()
    const description = randomItemDescription()

    await page.getByRole("button", { name: "新增物品" }).click()
    await page.getByLabel("标题").fill(title)
    await page.getByLabel("描述").fill(description)
    await page.getByRole("button", { name: "保存" }).click()

    await expect(page.getByText("物品创建成功")).toBeVisible()
    await expect(page.getByText(title)).toBeVisible()
  })

  test("Create item with only required fields", async ({ page }) => {
    const title = randomItemTitle()

    await page.getByRole("button", { name: "新增物品" }).click()
    await page.getByLabel("标题").fill(title)
    await page.getByRole("button", { name: "保存" }).click()

    await expect(page.getByText("物品创建成功")).toBeVisible()
    await expect(page.getByText(title)).toBeVisible()
  })

  test("Cancel item creation", async ({ page }) => {
    await page.getByRole("button", { name: "新增物品" }).click()
    await page.getByLabel("标题").fill("Test Item")
    await page.getByRole("button", { name: "取消" }).click()

    await expect(page.getByRole("dialog")).not.toBeVisible()
  })

  test("Title is required", async ({ page }) => {
    await page.getByRole("button", { name: "新增物品" }).click()
    await page.getByLabel("标题").fill("")
    await page.getByLabel("标题").blur()

    await expect(page.getByText("标题必填")).toBeVisible()
  })

  test.describe("Edit and Delete", () => {
    let itemTitle: string

    test.beforeEach(async ({ page }) => {
      itemTitle = randomItemTitle()

      await page.getByRole("button", { name: "新增物品" }).click()
      await page.getByLabel("标题").fill(itemTitle)
      await page.getByRole("button", { name: "保存" }).click()
      await expect(page.getByText("物品创建成功")).toBeVisible()
      await expect(page.getByRole("dialog")).not.toBeVisible()
    })

    test("Edit an item successfully", async ({ page }) => {
      const itemRow = page.getByRole("row").filter({ hasText: itemTitle })
      await itemRow.getByRole("button").last().click()
      await page.getByRole("menuitem", { name: "编辑物品" }).click()

      const updatedTitle = randomItemTitle()
      await page.getByLabel("标题").fill(updatedTitle)
      await page.getByRole("button", { name: "保存" }).click()

      await expect(page.getByText("物品更新成功")).toBeVisible()
      await expect(page.getByText(updatedTitle)).toBeVisible()
    })

    test("Delete an item successfully", async ({ page }) => {
      const itemRow = page.getByRole("row").filter({ hasText: itemTitle })
      await itemRow.getByRole("button").last().click()
      await page.getByRole("menuitem", { name: "删除物品" }).click()

      await page.getByRole("button", { name: "删除" }).click()

      await expect(page.getByText("物品删除成功")).toBeVisible()
      await expect(page.getByText(itemTitle)).not.toBeVisible()
    })
  })
})

test.describe("Items empty state", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Shows empty state message when no items exist", async ({ page }) => {
    const email = randomEmail()
    const password = randomPassword()
    await createUser({ email, password })
    await logInUser(page, email, password)

    await page.goto("/items")

    await expect(page.getByText("还没有任何物品")).toBeVisible()
    await expect(page.getByText("添加一个新物品开始使用")).toBeVisible()
  })
})

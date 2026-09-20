import { expect, test } from "@playwright/test"

/**
 * 聊天输入框附件能力 e2e（Phase 16 / S8）。
 *
 * 覆盖「用户可见的菜单与上传结果」，不碰真实模型调用（那是 S4-S6 的容器验收）：
 * - 菜单三项齐全且**没有**「共享屏幕和应用」
 * - 上传文档 → chip 出现并显示解析结果
 * - 截屏提问 → 抓帧变成图片 chip（getDisplayMedia 用 canvas.captureStream 打桩，
 *   否则无头浏览器弹不出选屏器，用例无法自动化）
 */

test("输入框「＋」菜单：三项齐全，不含共享屏幕", async ({ page }) => {
  await page.goto("/chat")
  await page.getByTestId("attachment-menu-button").click()

  await expect(page.getByTestId("attachment-menu-document")).toBeVisible()
  await expect(page.getByTestId("attachment-menu-image")).toBeVisible()
  await expect(page.getByTestId("attachment-menu-screenshot")).toBeVisible()
  // 用户明确不要共享屏幕：它不该出现在菜单里
  await expect(page.getByText("共享屏幕", { exact: false })).toHaveCount(0)
})

test("上传文档后出现附件 chip 并显示解析结果", async ({ page }) => {
  await page.goto("/chat")
  await page
    .getByTestId("attachment-input-document")
    .setInputFiles({
      name: "年报摘录.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("净利润 12345 万，同比增长 8%。"),
    })

  const chip = page.getByTestId("attachment-chip")
  await expect(chip).toHaveCount(1)
  await expect(chip).toContainText("年报摘录.txt")
  // 文档解析完成会显示字数，而不是停在「上传中…」
  await expect(chip).toContainText("已解析")
})

test("截屏提问：抓帧后进入附件 chip", async ({ page }) => {
  // 打桩 getDisplayMedia：无头浏览器里没有真实选屏器，用 canvas 造一条视频轨
  await page.addInitScript(() => {
    const canvas = document.createElement("canvas")
    canvas.width = 320
    canvas.height = 240
    const ctx = canvas.getContext("2d")
    if (ctx) {
      ctx.fillStyle = "#ffffff"
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = "#000000"
      ctx.font = "20px sans-serif"
      ctx.fillText("E2E-SCREEN", 20, 120)
    }
    const stream = canvas.captureStream(5)
    Object.defineProperty(navigator.mediaDevices, "getDisplayMedia", {
      configurable: true,
      value: async () => stream,
    })
  })

  await page.goto("/chat")
  await page.getByTestId("attachment-menu-button").click()
  await page.getByTestId("attachment-menu-screenshot").click()

  const chip = page.getByTestId("attachment-chip")
  await expect(chip).toHaveCount(1)
  await expect(chip).toContainText("截图-")
  await expect(chip).toContainText("图片")
})

import { expect, test } from "@playwright/test"

// 模型源能力 Tab（P5）的实机闭环：五个 Tab 全部可用、模型源按能力分栏、
// 新建的源只出现在自己那一栏。
//
// 用例打在 8000 的实机 dist 上（默认 superuser storageState）。
// 自清理：新建的源用固定名称，用例末尾从界面删除；断言只针对这个源，
// 不碰种子里的 default / Agnes。

const CAP_NAME = "e2e-embedding-src"
const CAP_MODEL = "BAAI/bge-m3"
const CAP_KEY = "sk-e2e-capability-key"

const TAB_KEYS = ["chat", "stt", "tts", "embedding", "rerank"] as const

/** 各能力的空态文案：用来判断「这一栏的数据已经到位」。 */
const EMPTY_TEXT: Record<(typeof TAB_KEYS)[number], string> = {
  chat: "还没有对话模型源",
  stt: "还没有语音转文字模型源",
  tts: "还没有文字转语音模型源",
  embedding: "还没有嵌入模型源",
  rerank: "还没有重排序模型源",
}

/** 幂等清理：若上次失败运行留下了同名源，先删掉。 */
async function removeLeftover(page: import("@playwright/test").Page) {
  for (const key of TAB_KEYS) {
    const row = page.getByTestId("provider-row").filter({ hasText: CAP_NAME })
    await page.getByTestId(`provider-tab-${key}`).click()
    // 切栏会按能力重新拉一次列表；count() 不等待，必须先把数据等出来，
    // 否则会误判为「这一栏没有目标行」而跳过清理。
    // 数据到位的标志：出现了任一行，或出现了这一栏的空态。
    await expect(
      page
        .getByTestId("provider-row")
        .first()
        .or(page.getByText(EMPTY_TEXT[key])),
    ).toBeVisible()
    if ((await row.count()) === 0) continue
    await row.getByRole("button", { name: `删除 ${CAP_NAME}` }).click()
    await page.getByRole("button", { name: "删除", exact: true }).click()
    await expect(row).toHaveCount(0)
  }
}

test.describe("模型源能力 Tab（P5）", () => {
  test("五个 Tab 均可用；新建源只落在自己那一栏", async ({ page }) => {
    await page.goto("/providers")

    // ── 五个 Tab 都在且不再是禁用占位（P5 之前后四个是 disabled）──
    for (const key of TAB_KEYS) {
      const tab = page.getByTestId(`provider-tab-${key}`)
      await expect(tab).toBeVisible()
      await expect(tab).toBeEnabled()
    }
    await expect(page.getByTestId("provider-tab-chat")).toHaveAttribute(
      "aria-pressed",
      "true",
    )

    await removeLeftover(page)

    // ── 嵌入 Tab：种子里没有嵌入源 → 空态带能力名 ──
    await page.getByTestId("provider-tab-embedding").click()
    await expect(page.getByTestId("provider-tab-embedding")).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    await expect(page.getByText("还没有嵌入模型源")).toBeVisible()

    // ── 在嵌入 Tab 新建，并设为「嵌入」的默认源 ──
    await page.getByRole("button", { name: "新增" }).click()
    const dialog = page
      .getByRole("dialog")
      .filter({ hasText: "新增嵌入模型源" })
    await expect(dialog).toBeVisible()
    // 非对话能力：不该出现「视觉能力」这一行
    await expect(dialog.getByText("视觉能力")).toHaveCount(0)

    await dialog.getByLabel("名称").fill(CAP_NAME)
    await dialog.getByLabel("API Key").fill(CAP_KEY)
    await dialog.getByLabel("模型名").fill(CAP_MODEL)
    await dialog.getByLabel("设为默认嵌入模型源").check()
    await dialog.getByRole("button", { name: "保存" }).click()

    const embRow = page.getByTestId("provider-row").filter({ hasText: CAP_NAME })
    await expect(embRow).toHaveCount(1)
    // 行内只显示名称/地址；这里先确认它成了嵌入栏的「默认」
    await expect(embRow.getByText("默认")).toBeVisible()

    // ── 切到对话 Tab：新建的嵌入源不串台，且对话的默认源没被抢走 ──
    await page.getByTestId("provider-tab-chat").click()
    await expect(
      page.getByTestId("provider-row").filter({ hasText: CAP_NAME }),
    ).toHaveCount(0)
    // 对话栏仍有且仅有一条默认（默认的互斥范围是 (user_id, capability)）
    await expect(
      page.getByTestId("provider-row").filter({ hasText: "默认" }),
    ).toHaveCount(1)

    // ── 切回嵌入 Tab：详情文案按能力变化，模型名确实落库了 ──
    await page.getByTestId("provider-tab-embedding").click()
    await page
      .getByTestId("provider-row")
      .filter({ hasText: CAP_NAME })
      .click()
    const detail = page.getByTestId("provider-detail")
    await expect(detail).toBeVisible()
    await expect(detail.getByText("嵌入使用的默认模型")).toBeVisible()
    // 「默认模型名」这一行确实存的是嵌入栏填的值
    const modelRow = detail.locator(".grid").filter({ hasText: "默认模型名" })
    await expect(modelRow.getByRole("textbox")).toHaveValue(CAP_MODEL)
    await expect(detail.getByText("视觉能力")).toHaveCount(0)

    // ── 自清理 ──
    await page
      .getByTestId("provider-row")
      .filter({ hasText: CAP_NAME })
      .getByRole("button", { name: `删除 ${CAP_NAME}` })
      .click()
    await page.getByRole("button", { name: "删除", exact: true }).click()
    await expect(
      page.getByTestId("provider-row").filter({ hasText: CAP_NAME }),
    ).toHaveCount(0)
  })

  test("对话 Tab 的存量模型源行为不变（种子仍在、可展开详情）", async ({
    page,
  }) => {
    await page.goto("/providers")
    const row = page.getByTestId("provider-row").first()
    await expect(row).toBeVisible()
    await row.click()
    await expect(page.getByTestId("provider-detail")).toBeVisible()
    // 对话源仍保留视觉能力行（存量行为）
    await expect(page.getByTestId("provider-detail").getByText("视觉能力")).toBeVisible()
  })
})

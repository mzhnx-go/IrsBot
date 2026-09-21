import { expect, test } from "@playwright/test"

// 多 API Key（P8）「添加更多」面板的实机闭环：批量粘贴 → 打码清单 → 启停 → 删除。
//
// 这是 P8 唯一没有自动化覆盖的一段（后端轮换/去重/越权已有 test_provider_keys.py）。
// 用例打在 8000 的实机 dist 上，走默认 storageState（超管会话）。
//
// 自清理：标记 Key 用固定明文（掩码可预期），进面板先删残留、跑完再删干净，
// 绝不碰 Agnes 上已有的真实 Key 行（断言围绕「基线行数 ± 2」而不是绝对行数）。

const AGNES_BASE_URL = "apihub.agnes-ai.com"
const KEY_A = "sk-e2e-mask-AAAA1111"
const KEY_B = "sk-e2e-mask-BBBB2222"
// 与后端 _mask_key 一致：前 4 后 4，中间星号
const MASK_A = "sk-e****1111"
const MASK_B = "sk-e****2222"

test.describe("模型源多 API Key 面板（P8）", () => {
  test("批量粘贴 → 打码 → 启停 → 删除，闭环且自清理", async ({ page }) => {
    await page.goto("/providers")

    // 按行定位、不靠顺序：用户随时会加自己的模型源
    const row = page
      .getByTestId("provider-row")
      .filter({ hasText: AGNES_BASE_URL })
    await expect(row).toHaveCount(1)
    await row.click()

    const detail = page.getByTestId("provider-detail")
    await expect(detail).toBeVisible()

    // ── 展开面板 ──
    const toggle = detail.getByTestId("provider-keys-toggle")
    await expect(toggle).toHaveText("添加更多")
    await toggle.click()
    await expect(toggle).toHaveText("收起密钥")

    const panel = detail.getByTestId("provider-keys-panel")
    await expect(panel).toBeVisible()

    // ── 幂等：清掉上一次失败运行可能留下的标记 Key ──
    for (const mask of [MASK_A, MASK_B]) {
      const stale = panel.getByRole("button", { name: `删除 ${mask}` })
      if ((await stale.count()) > 0) {
        await stale.click()
        await expect(stale).toHaveCount(0)
      }
    }

    const baseline = await panel.locator("li").count()

    // ── 批量粘贴两把 ──
    await panel.locator("textarea").fill(`${KEY_A}\n${KEY_B}`)
    await panel.getByRole("button", { name: /^添加（2）/ }).click()

    await expect(panel.locator("li")).toHaveCount(baseline + 2)
    await expect(panel.getByText(MASK_A, { exact: true })).toHaveCount(1)
    await expect(panel.getByText(MASK_B, { exact: true })).toHaveCount(1)

    // 只出掩码：明文既不该留在清单里，输入框也应已清空
    await expect(panel).not.toContainText(KEY_A)
    await expect(panel.locator("textarea")).toHaveValue("")

    // ── 启停（停用后必须落库，刷新仍在） ──
    const switchA = panel.getByRole("switch", { name: `启停 ${MASK_A}` })
    await expect(switchA).toBeChecked()
    await switchA.click()
    await expect(switchA).not.toBeChecked()

    await page.reload()
    await row.click()
    const panel2 = page.getByTestId("provider-detail").getByTestId("provider-keys-panel")
    await page.getByTestId("provider-detail").getByTestId("provider-keys-toggle").click()
    await expect(panel2).toBeVisible()

    const switchA2 = panel2.getByRole("switch", { name: `启停 ${MASK_A}` })
    await expect(switchA2).not.toBeChecked()
    await switchA2.click()
    await expect(switchA2).toBeChecked()

    // ── 删除：行数回到基线，标记 Key 全部消失 ──
    await panel2.getByRole("button", { name: `删除 ${MASK_A}` }).click()
    await expect(panel2.getByRole("button", { name: `删除 ${MASK_A}` })).toHaveCount(0)
    await panel2.getByRole("button", { name: `删除 ${MASK_B}` }).click()
    await expect(panel2.getByRole("button", { name: `删除 ${MASK_B}` })).toHaveCount(0)

    await expect(panel2.locator("li")).toHaveCount(baseline)
  })
})

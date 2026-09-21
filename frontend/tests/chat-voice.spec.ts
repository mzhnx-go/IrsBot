import { expect, type Page, test } from "@playwright/test"

/**
 * 语音能力 e2e（P9b 语音转文字 / P9c 文字转语音）。
 *
 * 验证的是「按钮 → 录音 → 真实 HTTP → 真实后端 → 上游错误回流成中文提示」
 * 这条完整链路，**不是**真实语音识别效果：
 * - `getUserMedia` / `MediaRecorder` 用 initScript 打桩（无头浏览器没有麦克风，
 *   也没有选麦克风的弹窗），但产出的 Blob 会真的走 multipart 传到 8000；
 * - 上游指向一个「黑洞」源（base_url 指到后端自己的非音频路径 → 404），
 *   这样既不花真实 STT/TTS 的钱，又能证明**后端确实拿着配置好的源在发请求**
 *   ——如果它没去用配置源，就会回 400「尚未配置…」而不是上游失败。
 *
 * 未覆盖（本机没有可用的 STT/TTS 上游，无法自动化）：
 * 真实语音的转写质量、真实音频的播放。见 plan/PROGRESS.md 的 P9b/P9c 留档。
 */

const STT_SRC = "e2e-voice-stt"
const TTS_SRC = "e2e-voice-tts"
//: 指到后端自己的 /api/v1 下：`/audio/transcriptions` 与 `/audio/speech`
//: 在这里并不存在 → 上游 404 → 后端翻成 502。链路通即可，不求上游成功。
const BLACKHOLE_BASE = "http://127.0.0.1:8000/api/v1"

/** 打桩媒体录音：造一条假音频轨与一个立刻产字节的 MediaRecorder。 */
async function stubRecorder(page: Page) {
  await page.addInitScript(() => {
    class FakeRecorder {
      state = "inactive"
      mimeType = "audio/webm"
      ondataavailable: ((e: { data: Blob }) => void) | null = null
      onstop: (() => void) | null = null

      start() {
        this.state = "recording"
        setTimeout(() => {
          this.ondataavailable?.({
            data: new Blob(["e2e-fake-audio"], { type: "audio/webm" }),
          })
        }, 0)
      }

      stop() {
        this.state = "inactive"
        setTimeout(() => this.onstop?.(), 0)
      }
    }
    // @ts-expect-error 故意替换浏览器实现，只保留 hook 依赖的接口形状
    window.MediaRecorder = FakeRecorder
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      configurable: true,
      value: async () => ({ getTracks: () => [] }),
    })
  })
}

/** 用 localStorage 里的令牌直接打后端（e2e 只有这个身份）。 */
async function api(
  page: Page,
  path: string,
  init?: { method?: string; data?: unknown; headers?: Record<string, string> },
) {
  const token = await page.evaluate(() => localStorage.getItem("access_token"))
  const base = "http://127.0.0.1:8000/api/v1"
  return page.request.fetch(`${base}${path}`, {
    method: init?.method ?? "GET",
    headers: {
      Authorization: `Bearer ${token ?? ""}`,
      ...(init?.headers ?? {}),
    },
    // 传对象而非字符串：Playwright 会按 JSON 序列化并带上 Content-Type，
    // 手写字符串的话没有 Content-Type，FastAPI 会把它当字符串校验（422）
    data: init?.data,
  })
}

/** 建一个黑洞源并设默认；返回 id 供清理。 */
async function seedSource(page: Page, name: string, capability: string) {
  const res = await api(page, "/providers", {
    method: "POST",
    data: {
      name,
      provider_type: "openai",
      capability,
      api_key: "sk-e2e-voice",
      model_name: capability === "stt" ? "whisper-1" : "tts-1",
      base_url: BLACKHOLE_BASE,
      is_default: true,
    },
  })
  expect(res.status(), await res.text()).toBe(200)
  return (await res.json()).id as string
}

async function dropSource(page: Page, id: string) {
  const res = await api(page, `/providers/${id}`, { method: "DELETE" })
  expect([200, 404]).toContain(res.status())
}

test("语音输入：录音 → 上传识别，走的是「语音转文字」默认源", async ({
  page,
}) => {
  await stubRecorder(page)
  await page.goto("/chat")

  const seeded = await seedSource(page, STT_SRC, "stt")
  try {
    const mic = page.getByTestId("chat-mic-button")
    await expect(mic).toBeEnabled()
    await expect(mic).toHaveAttribute("aria-label", "语音输入")
    await expect(mic).toHaveAttribute("data-status", "idle")

    // ── 开始录音：按钮转为「结束录音」，并出现录音提示 ──
    await mic.click()
    await expect(mic).toHaveAttribute("data-status", "recording")
    await expect(mic).toHaveAttribute("aria-label", "结束录音")
    await expect(page.getByTestId("chat-recording-hint")).toBeVisible()

    // ── 结束录音：自动上传识别 ──
    await mic.click()

    // 上游是黑洞 → 502 且回显上游原因；这条断言同时证明
    // 「后端确实用了我们配的 stt 源」（没配的话会是 400 尚未配置）
    await expect(page.getByText(/语音识别失败/)).toBeVisible({ timeout: 20000 })
    // 状态复位：识别结束、不是录音中
    await expect(mic).toHaveAttribute("data-status", "idle", {
      timeout: 20000,
    })
    await expect(page.getByTestId("chat-recording-hint")).toHaveCount(0)
    // 识别失败不该污染输入框
    await expect(page.locator("form textarea")).toHaveValue("")
  } finally {
    await dropSource(page, seeded)
  }
})

test("文字转语音：合成走的是「文字转语音」默认源，未配置时报明确错误", async ({
  page,
}) => {
  await page.goto("/chat")
  const body = { text: "你好，我是 IrsBot" }

  const seeded = await seedSource(page, TTS_SRC, "tts")
  try {
    const ok = await api(page, "/agent/audio/speech", {
      method: "POST",
      data: body,
    })
    expect(ok.status()).toBe(502)
    expect((await ok.json()).detail).toContain("语音合成失败")
  } finally {
    await dropSource(page, seeded)
  }

  // 源删掉后：明确的配置指引，而不是 500 或静默失败
  const missing = await api(page, "/agent/audio/speech", {
    method: "POST",
    data: body,
  })
  expect(missing.status()).toBe(400)
  expect((await missing.json()).detail).toBe(
    "尚未配置文字转语音模型源，请先到「模型源」页添加并设为默认",
  )
})

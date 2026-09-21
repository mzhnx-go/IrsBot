import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { OpenAPI } from "@/client"
import { useAudioRecorder } from "@/hooks/useAudioRecorder"

/** 从后端错误体里挖出中文 detail（拿不到就退回通用文案）。 */
const readApiDetail = async (res: Response, fallback: string) => {
  try {
    const body = await res.json()
    if (body?.detail) return String(body.detail)
  } catch {
    // 响应不是 JSON（网关错误页等），保持默认文案
  }
  return `${fallback}（HTTP ${res.status}）`
}

/** 生成的 SDK 按 JSON 解析，音频字节会被当字符串解码 → 这里直接走 fetch 取 Blob。 */
const synthesize = async (text: string): Promise<Blob> => {
  const res = await fetch(`${OpenAPI.BASE}/api/v1/agent/audio/speech`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${localStorage.getItem("access_token") ?? ""}`,
    },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) {
    throw new Error(await readApiDetail(res, "语音合成失败"))
  }
  const blob = await res.blob()
  if (blob.size === 0) throw new Error("语音合成返回了空音频")
  return blob
}

/**
 * 把 Markdown 洗成适合朗读的纯文本。
 *
 * 直接念原始 Markdown 会把「星号井号反引号」一起读出来，代码块更会念成一串
 * 乱码；所以代码块整体略过，其余标记剥掉只留文字。
 */
export const toSpeechText = (markdown: string) =>
  markdown
    .replace(/```[\s\S]*?```/g, " 代码块已省略。")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s{0,3}>\s?/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/(\*\*|__|\*|_|~~)/g, "")
    .replace(/\n{2,}/g, "\n")
    .trim()

/**
 * 语音输入：录音 → 上传识别 → 返回文本（由调用方决定填进哪里）。
 *
 * 识别不写进输入框是刻意的：语音识别必然有错字，让用户看一眼再发送，
 * 比"说出来就发出去"稳妥得多。
 */
export const useTranscribe = () => {
  const recorder = useAudioRecorder()
  const [isTranscribing, setIsTranscribing] = useState(false)
  /** 让 e2e/无障碍能看出当前处于录音还是识别中 */
  const status = isTranscribing
    ? "transcribing"
    : recorder.isRecording
      ? "recording"
      : "idle"

  const toggle = useCallback(async (): Promise<string | null> => {
    if (isTranscribing) return null

    if (!recorder.isRecording) {
      try {
        await recorder.start()
      } catch {
        // 拒绝授权 / 无麦克风设备：给一句中文提示，输入框保持原样
        toast.error("无法开始录音：麦克风权限被拒绝或不可用")
      }
      return null
    }

    const blob = await recorder.stop()
    if (!blob) return null

    setIsTranscribing(true)
    try {
      const form = new FormData()
      form.append("file", blob, "recording.webm")
      const res = await fetch(
        `${OpenAPI.BASE}/api/v1/agent/audio/transcriptions`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("access_token") ?? ""}`,
          },
          body: form,
        },
      )
      if (!res.ok) {
        throw new Error(await readApiDetail(res, "语音识别失败"))
      }
      const body = await res.json()
      const text = typeof body?.text === "string" ? body.text.trim() : ""
      if (!text) {
        toast.info("没有识别到内容，请再说一次")
        return null
      }
      return text
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "语音识别失败")
      return null
    } finally {
      setIsTranscribing(false)
    }
  }, [isTranscribing, recorder])

  return {
    isRecording: recorder.isRecording,
    isSupported: recorder.isSupported,
    isTranscribing,
    status,
    toggle,
  }
}

/**
 * 朗读回复：整段合成后播放（不做流式，见计划书 P9c）。
 *
 * 同一时刻只播一条：点另一条会先停掉当前音频；再点正在播的那条 = 停止。
 */
export const useSpeak = () => {
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const urlRef = useRef<string | null>(null)

  const teardown = useCallback(() => {
    audioRef.current?.pause()
    audioRef.current = null
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
    setPlayingId(null)
  }, [])

  // 卸载时停播：否则切会话/切页后音频还在后台响
  useEffect(() => () => teardown(), [teardown])

  const speak = useCallback(
    async (id: string, markdown: string) => {
      if (playingId === id) {
        teardown()
        return
      }
      teardown()

      const text = toSpeechText(markdown)
      if (!text) {
        toast.info("这条回复没有可朗读的内容")
        return
      }

      setLoadingId(id)
      try {
        const blob = await synthesize(text)
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audioRef.current = audio
        urlRef.current = url
        audio.onended = () => teardown()
        audio.onerror = () => {
          toast.error("音频播放失败")
          teardown()
        }
        setPlayingId(id)
        await audio.play()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "朗读失败")
        teardown()
      } finally {
        setLoadingId(null)
      }
    },
    [playingId, teardown],
  )

  return { speak, playingId, loadingId }
}

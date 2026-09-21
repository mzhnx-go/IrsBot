import { useCallback, useEffect, useRef, useState } from "react"

/**
 * 录音能力探测：`getUserMedia` 与 `MediaRecorder` 都得在。
 *
 * 两者都要求安全上下文——127.0.0.1 算安全上下文，局域网 IP / http 域名不算，
 * 这时按钮应显示为不可用并给出原因，而不是点了没反应。
 */
const recorderSupported = () =>
  typeof navigator !== "undefined" &&
  typeof navigator.mediaDevices?.getUserMedia === "function" &&
  typeof window !== "undefined" &&
  typeof window.MediaRecorder !== "undefined"

/**
 * 麦克风录音：start() 开始，stop() 返回录到的音频 Blob。
 *
 * 为什么 stop() 用 Promise 而不是回调：`MediaRecorder.stop()` 只是请求停止，
 * 数据要等 `onstop` 才齐。调用方（上传识别）必须拿到完整的 Blob 才能发请求，
 * 用 Promise 把这层异步收在 hook 内部，调用处就是一句 `await stop()`。
 *
 * 麦克风是敏感权限：**任何退出路径都要停掉 track**（卸载、取消、出错），
 * 否则标签页会一直亮着"正在录音"的指示。
 */
export const useAudioRecorder = () => {
  const [isRecording, setIsRecording] = useState(false)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const pendingRef = useRef<((blob: Blob | null) => void) | null>(null)

  /** 停掉麦克风并复位内部引用；不碰 isRecording（调用方各自负责 UI 状态）。 */
  const release = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => {
      track.stop()
    })
    streamRef.current = null
    recorderRef.current = null
    chunksRef.current = []
  }, [])

  // 卸载兜底：切会话/刷新时不能把麦克风留在打开状态
  useEffect(
    () => () => {
      const recorder = recorderRef.current
      if (recorder && recorder.state === "recording") {
        recorder.stop()
      }
      pendingRef.current?.(null)
      pendingRef.current = null
      release()
    },
    [release],
  )

  const start = useCallback(async () => {
    if (!recorderSupported()) {
      throw new Error("当前浏览器或访问方式不支持录音（需 HTTPS 或 127.0.0.1）")
    }
    // 授权失败（用户拒绝 / 没有设备）会在这里抛，由调用方翻译成中文提示
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream)
    chunksRef.current = []

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }
    recorder.onstop = () => {
      // mimeType 由浏览器决定（Chrome 是 audio/webm;codecs=opus），原样带上，
      // 上游普遍按内容嗅探；空录音（用户秒停）返回 null 让调用方跳过上传。
      const blob = new Blob(chunksRef.current, {
        type: recorder.mimeType || "audio/webm",
      })
      const resolve = pendingRef.current
      pendingRef.current = null
      release()
      setIsRecording(false)
      resolve?.(blob.size > 0 ? blob : null)
    }

    recorderRef.current = recorder
    streamRef.current = stream
    recorder.start()
    setIsRecording(true)
  }, [release])

  const stop = useCallback(
    () =>
      new Promise<Blob | null>((resolve) => {
        const recorder = recorderRef.current
        if (!recorder || recorder.state === "inactive") {
          resolve(null)
          return
        }
        pendingRef.current = resolve
        recorder.stop()
      }),
    [],
  )

  return { isRecording, isSupported: recorderSupported(), start, stop }
}

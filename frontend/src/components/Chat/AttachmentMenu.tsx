import { Camera, FileText, Image as ImageIcon, Plus } from "lucide-react"
import { useRef } from "react"
import { toast } from "sonner"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface AttachmentMenuProps {
  /** 选中的文件交给上层上传（本组件不关心上传过程） */
  onPick: (files: File[]) => void
  disabled?: boolean
}

const DOC_ACCEPT = ".pdf,.txt,.md,.docx"
const IMAGE_ACCEPT = ".png,.jpg,.jpeg,.gif,.webp"

/** 屏幕捕获要安全上下文：127.0.0.1 属于 secure context，局域网 IP 访问时浏览器会拒绝。 */
const canCaptureScreen = () =>
  typeof navigator !== "undefined" &&
  typeof navigator.mediaDevices?.getDisplayMedia === "function"

/**
 * 抓一帧屏幕并封装成图片 File；失败（拒绝授权/无捕获源）抛错由调用方提示。
 *
 * 关键点：授权一旦拿到，**画完一帧立刻 stop 掉所有 track** ——
 * 标签页不应留下「正在共享」的指示，本项目不做持续共享。
 */
const captureScreenshot = async (): Promise<File> => {
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
  })
  try {
    const video = document.createElement("video")
    video.srcObject = stream
    video.muted = true
    video.playsInline = true
    await video.play()
    // 等一帧：play() 返回时首帧未必已就绪，立刻 drawImage 会得到全黑
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

    const canvas = document.createElement("canvas")
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext("2d")
    if (!ctx || canvas.width === 0 || canvas.height === 0) {
      throw new Error("屏幕帧尺寸无效")
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((b) => resolve(b), "image/png"),
    )
    if (!blob) throw new Error("截图编码失败")
    return new File([blob], `截图-${Date.now()}.png`, { type: "image/png" })
  } finally {
    stream.getTracks().forEach((track) => {
      track.stop()
    })
  }
}

/**
 * 输入框左侧的 `＋` 按钮：上传文档 / 上传图片 / 截屏提问。
 *
 * 文件选择用隐藏的原生 input 而非菜单项直接承载——`accept` 过滤与
 * "同一文件连选两次也要触发"（input.value 必须清空）只有原生 input 能做对。
 */
const AttachmentMenu = ({ onPick, disabled }: AttachmentMenuProps) => {
  const docInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const screenSupported = canCaptureScreen()

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    // 清空 value：否则第二次选同一个文件不会触发 change
    e.target.value = ""
    if (files.length) onPick(files)
  }

  const handleScreenshot = async () => {
    try {
      onPick([await captureScreenshot()])
    } catch {
      // 用户在授权弹窗点了取消 / 明确拒绝：给一句中文提示，输入框保持原样
      toast.error("未能截屏：屏幕捕获被拒绝或已取消")
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label="添加附件"
            data-testid="attachment-menu-button"
            disabled={disabled}
            className="flex size-8 shrink-0 items-center justify-center self-end rounded-full text-muted-foreground transition-colors duration-100 hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="size-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top">
          <DropdownMenuItem
            data-testid="attachment-menu-document"
            onSelect={() => docInputRef.current?.click()}
          >
            <FileText className="size-4" />
            上传文档
          </DropdownMenuItem>
          <DropdownMenuItem
            data-testid="attachment-menu-image"
            onSelect={() => imageInputRef.current?.click()}
          >
            <ImageIcon className="size-4" />
            上传图片
          </DropdownMenuItem>
          <DropdownMenuItem
            data-testid="attachment-menu-screenshot"
            disabled={!screenSupported}
            title={
              screenSupported
                ? undefined
                : "当前浏览器或访问方式不支持屏幕捕获（需 HTTPS 或 127.0.0.1）"
            }
            onSelect={() => void handleScreenshot()}
          >
            <Camera className="size-4" />
            截屏提问
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <input
        ref={docInputRef}
        type="file"
        accept={DOC_ACCEPT}
        multiple
        hidden
        data-testid="attachment-input-document"
        onChange={handleChange}
      />
      <input
        ref={imageInputRef}
        type="file"
        accept={IMAGE_ACCEPT}
        multiple
        hidden
        data-testid="attachment-input-image"
        onChange={handleChange}
      />
    </>
  )
}

export default AttachmentMenu

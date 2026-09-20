import { FileText, Image as ImageIcon, Plus } from "lucide-react"
import { useRef } from "react"

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

/**
 * 输入框左侧的 `＋` 按钮：上传文档 / 上传图片。
 *
 * 文件选择用隐藏的原生 input 而非菜单项直接承载——`accept` 过滤与
 * "同一文件连选两次也要触发"（input.value 必须清空）只有原生 input 能做对。
 */
const AttachmentMenu = ({ onPick, disabled }: AttachmentMenuProps) => {
  const docInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    // 清空 value：否则第二次选同一个文件不会触发 change
    e.target.value = ""
    if (files.length) onPick(files)
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

import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import useSystemPrompt from "@/hooks/useSystemPrompt"

const MAX_LENGTH = 10000

const SystemPromptSettings = () => {
  const { systemPromptQuery, updateSystemPrompt } = useSystemPrompt()
  const [value, setValue] = useState("")

  // 查询数据到达后同步进本地编辑框（只在初始加载时执行一次）
  useEffect(() => {
    if (systemPromptQuery.data) {
      setValue(systemPromptQuery.data.system_prompt ?? "")
    }
  }, [systemPromptQuery.data])

  const isCustom = systemPromptQuery.data?.is_custom ?? false

  if (systemPromptQuery.isPending) {
    return <p className="text-muted-foreground py-4">加载中…</p>
  }

  return (
    <div className="max-w-2xl flex flex-col gap-4">
      <div>
        <h3 className="text-lg font-semibold">系统提示词</h3>
        <p className="text-sm text-muted-foreground">
          当前生效：
          {isCustom ? (
            <span className="text-foreground">自定义提示词</span>
          ) : (
            <span>默认提示词</span>
          )}
          。对所有会话全局生效，保存后立即生效，无需重启。
        </p>
      </div>

      <textarea
        className="min-h-48 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        placeholder={isCustom ? "" : "留空使用默认提示词；填写后保存即自定义"}
        maxLength={MAX_LENGTH}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        data-testid="system-prompt-textarea"
      />
      <p className="text-xs text-muted-foreground">
        {value.length} / {MAX_LENGTH} 字符
      </p>

      <div className="flex gap-3">
        <Button
          onClick={() => updateSystemPrompt.mutate({ system_prompt: value })}
          disabled={updateSystemPrompt.isPending}
          data-testid="system-prompt-save"
        >
          保存
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            setValue("")
            updateSystemPrompt.mutate({ system_prompt: "" })
          }}
          disabled={updateSystemPrompt.isPending}
          data-testid="system-prompt-clear"
        >
          清空（恢复默认行为）
        </Button>
      </div>
    </div>
  )
}

export default SystemPromptSettings

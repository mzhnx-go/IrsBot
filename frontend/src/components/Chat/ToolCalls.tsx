import { Check, ChevronRight, Loader2, Wrench } from "lucide-react"
import { useEffect, useState } from "react"

import type { ToolCall } from "@/hooks/useAgentChat"

const Section = ({ label, text }: { label: string; text: string }) => {
  if (!text) return null
  return (
    <div className="mt-1.5">
      <p className="mb-0.5 text-[11px] font-medium text-muted-foreground">
        {label}
      </p>
      <pre className="max-h-40 overflow-auto rounded-md bg-background/60 border border-border/50 p-2 font-mono text-[11px] leading-5 whitespace-pre-wrap break-all">
        {text}
      </pre>
    </div>
  )
}

const ToolCallRow = ({ tc }: { tc: ToolCall }) => {
  const running = tc.phase === "start"
  const [open, setOpen] = useState(false)

  // 执行中自动展开让用户看到入参；结束后自动收起，不挤占正文空间
  useEffect(() => {
    setOpen(running)
  }, [running])

  return (
    <div className="rounded-lg border border-border/60 bg-background/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors duration-100 hover:text-foreground"
      >
        <Wrench className="size-3.5 shrink-0" />
        <span className="font-mono">{tc.name}</span>
        <span className="ml-auto flex items-center gap-1">
          {running ? (
            <>
              <Loader2 className="size-3.5 animate-spin" />
              执行中
            </>
          ) : (
            <>
              <Check className="size-3.5 text-green-600 dark:text-green-500" />
              完成
            </>
          )}
          <ChevronRight
            className={`size-3.5 transition-transform duration-200 ease-out motion-reduce:transition-none ${open ? "rotate-90" : ""}`}
          />
        </span>
      </button>
      {/* 折叠动画：grid-rows 0fr↔1fr（内容不参与布局计算，兼容任意高度） */}
      <div
        className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div className="overflow-hidden">
          <div className="px-2.5 pb-2">
            <Section label="入参" text={tc.input ?? ""} />
            <Section label="结果" text={tc.output ?? ""} />
          </div>
        </div>
      </div>
    </div>
  )
}

const ToolCalls = ({ calls }: { calls: ToolCall[] }) => {
  return (
    <div className="mb-2 flex flex-col gap-1.5">
      {calls.map((tc, i) => (
        <ToolCallRow key={i} tc={tc} />
      ))}
    </div>
  )
}

export default ToolCalls

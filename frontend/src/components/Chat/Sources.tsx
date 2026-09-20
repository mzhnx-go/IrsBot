import { ChevronRight, FileText } from "lucide-react"
import { useState } from "react"

import type { Citation } from "@/hooks/useAgentChat"

/** 相关度展示：rerank 分数是 0~1 语义相关度（百分比），
 *  RRF 融合分只有 ~0.0x 量级，展示原始值更诚实 */
const scoreLabel = (score?: number) => {
  if (typeof score !== "number") return null
  if (score >= 0.1) return `${Math.round(score * 100)}%`
  return score.toFixed(3)
}

// uploads/kb/<uuid>/<filename> → 只留文件名，路径前缀对读者无意义
const baseName = (source: string) => {
  const parts = source.split("/")
  return parts[parts.length - 1] || source
}

const SourceRow = ({ c }: { c: Citation }) => {
  const label = scoreLabel(c.score)
  return (
    <li className="flex flex-col gap-0.5 border-t border-border/50 py-1.5 first:border-t-0">
      <div className="flex items-center gap-1.5 text-xs">
        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate" title={c.source}>
          {baseName(c.source)}
        </span>
        <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {c.kb}
        </span>
        {label && (
          <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
            {label}
          </span>
        )}
      </div>
      <p className="line-clamp-2 pl-5 text-[11px] leading-4 text-muted-foreground">
        {c.snippet}
      </p>
    </li>
  )
}

const Sources = ({ citations }: { citations: Citation[] }) => {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-2 rounded-lg border border-border/60 bg-background/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors duration-100 hover:text-foreground"
      >
        <FileText className="size-3.5 shrink-0" />
        参考 {citations.length} 个来源
        <ChevronRight
          className={`ml-auto size-3.5 transition-transform duration-200 ease-out motion-reduce:transition-none ${open ? "rotate-90" : ""}`}
        />
      </button>
      {/* 折叠动画：grid-rows 0fr↔1fr，与工具调用面板同款 */}
      <div
        className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div className="overflow-hidden">
          <ul className="px-2.5 pb-2">
            {citations.map((c, i) => (
              <SourceRow key={i} c={c} />
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

export default Sources

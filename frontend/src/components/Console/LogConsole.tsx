import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Check, Maximize2, Minimize2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import useLogStream from "@/hooks/useLogStream"
import { cn } from "@/lib/utils"
import {
  Pause,
  Play,
  Trash2,
} from "lucide-react"

// 与后端 logging 级别对齐；CRITICAL 单列（AstrBot 也单列一档）
const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const
type Level = (typeof LEVELS)[number]

// 级别 → 行文本颜色（终端观感）
const LEVEL_STYLES: Record<string, string> = {
  DEBUG: "text-zinc-400",
  INFO: "text-sky-300",
  WARNING: "text-yellow-300",
  ERROR: "text-red-400",
  CRITICAL: "text-red-300",
}

// 级别 → 筛选徽标配色（选中态）
const LEVEL_BADGE: Record<string, string> = {
  DEBUG: "bg-zinc-800 text-zinc-300 border-zinc-600",
  INFO: "bg-sky-950 text-sky-300 border-sky-700",
  WARNING: "bg-yellow-950 text-yellow-300 border-yellow-700",
  ERROR: "bg-red-950 text-red-300 border-red-700",
  CRITICAL: "bg-red-950 text-red-200 border-red-600",
}

// 时间戳：日志条目里显示到秒；日期交给行首 hover title
function formatTs(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour12: false })
}

function formatTsFull(ts: number) {
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false })
}

export default function LogConsole() {
  const [paused, setPaused] = useState(false)
  const [levels, setLevels] = useState<Set<Level>>(new Set(LEVELS))
  const [keyword, setKeyword] = useState("")
  // 可选信息内容：访问日志（默认排除——多为压测式轮询噪声）、来源定位、自动滚动
  const [showAccess, setShowAccess] = useState(false)
  const [showSource, setShowSource] = useState(true)
  const [autoScroll, setAutoScroll] = useState(true)
  const [fullscreen, setFullscreen] = useState(false)
  const { entries, connected, clear } = useLogStream(!paused)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickBottomRef = useRef(true)

  // 用户上滚即视为"想留在原处"；自动滚动开关打开时才跟随新日志
  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    stickBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (el && autoScroll && stickBottomRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [entries, autoScroll])

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return entries.filter((e) => {
      if (!levels.has(e.level as Level)) return false
      // 「排除访问日志」只针对 uvicorn.access（其余 logger 不受影响）
      if (!showAccess && e.logger === "uvicorn.access") return false
      if (
        kw !== "" &&
        !e.message.toLowerCase().includes(kw) &&
        !e.logger.toLowerCase().includes(kw)
      ) {
        return false
      }
      return true
    })
  }, [entries, levels, keyword, showAccess])

  const toggleLevel = (level: Level) => {
    setLevels((prev) => {
      const next = new Set(prev)
      if (next.has(level)) {
        next.delete(level)
      } else {
        next.add(level)
      }
      return next
    })
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-3",
        fullscreen && "fixed inset-0 z-50 bg-background p-4",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {/* 级别筛选徽标（AstrBot 风格：✓ 徽标，点选切换） */}
        <div className="flex flex-wrap items-center gap-1.5">
          {LEVELS.map((level) => {
            const active = levels.has(level)
            return (
              <button
                key={level}
                type="button"
                data-testid={`console-level-${level}`}
                onClick={() => toggleLevel(level)}
                className={cn(
                  "flex items-center gap-1 rounded-full border px-2.5 py-1 font-mono text-xs transition-colors",
                  active
                    ? LEVEL_BADGE[level]
                    : "border-zinc-800 bg-transparent text-zinc-600 opacity-60",
                )}
              >
                {active && <Check className="size-3" />}
                {level}
              </button>
            )
          })}
        </div>
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索日志…"
          data-testid="console-search"
          className="h-8 w-48 rounded-md border border-input bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring"
        />
        <div className="ml-auto flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <label
            className="flex cursor-pointer items-center gap-1.5"
            title="uvicorn 访问日志多为轮询噪声，默认排除"
          >
            <Switch checked={showAccess} onCheckedChange={setShowAccess} />
            访问日志
          </label>
          <label
            className="flex cursor-pointer items-center gap-1.5"
            title="显示来源（父目录.文件名:行号）"
          >
            <Switch checked={showSource} onCheckedChange={setShowSource} />
            来源
          </label>
          <label className="flex cursor-pointer items-center gap-1.5">
            <Switch checked={autoScroll} onCheckedChange={setAutoScroll} />
            自动滚动
          </label>
          <button
            type="button"
            data-testid="console-toggle"
            onClick={() => setPaused((p) => !p)}
            className="flex items-center gap-1 rounded-md border px-2 py-1 transition-colors hover:bg-muted"
          >
            {paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
            {paused ? "继续" : "暂停"}
          </button>
          <button
            type="button"
            data-testid="console-clear"
            onClick={clear}
            className="flex items-center gap-1 rounded-md border px-2 py-1 transition-colors hover:bg-muted"
          >
            <Trash2 className="size-3.5" />
            清屏
          </button>
          <button
            type="button"
            data-testid="console-fullscreen"
            onClick={() => setFullscreen((f) => !f)}
            className="flex items-center rounded-md border px-2 py-1 transition-colors hover:bg-muted"
            title={fullscreen ? "退出全屏" : "全屏"}
          >
            {fullscreen ? (
              <Minimize2 className="size-3.5" />
            ) : (
              <Maximize2 className="size-3.5" />
            )}
          </button>
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        data-testid="console-log-view"
        className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed"
      >
        {filtered.length === 0 ? (
          <p className="text-zinc-600">
            暂无符合条件的日志（等待后端输出，或调整级别/关键字/访问日志过滤）
          </p>
        ) : (
          filtered.map((e) => (
            <div
              key={e.id}
              data-testid="console-log-entry"
              title={formatTsFull(e.ts)}
              className="flex gap-2 whitespace-pre-wrap break-all py-0.5"
            >
              <span className="shrink-0 text-zinc-600">{formatTs(e.ts)}</span>
              <span
                className={cn(
                  "w-[68px] shrink-0 font-semibold",
                  LEVEL_STYLES[e.level] ?? "text-zinc-400",
                )}
              >
                {e.level}
              </span>
              <span className="shrink-0 text-purple-400">[{e.logger}]</span>
              {showSource && e.source && (
                <span className="shrink-0 text-teal-500">[{e.source}]</span>
              )}
              <span className="text-zinc-200">{e.message}</span>
            </div>
          ))
        )}
      </div>

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <Badge variant="outline" data-testid="console-connection">
          {connected && !paused ? "实时刷新中" : paused ? "已暂停" : "连接中断，重试中…"}
        </Badge>
        <span data-testid="console-count">
          {filtered.length} / {entries.length} 条
        </span>
        <span>每 2 秒增量拉取；访问日志默认排除，可按需开启</span>
      </div>
    </div>
  )
}

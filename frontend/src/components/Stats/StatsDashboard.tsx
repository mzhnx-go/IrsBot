import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { AgentService } from "@/client"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const RANGE_OPTIONS = [
  { value: "7", label: "近 7 天" },
  { value: "14", label: "近 14 天" },
  { value: "30", label: "近 30 天" },
  { value: "90", label: "近 90 天" },
]

const STATUS_LABEL: Record<
  string,
  {
    label: string
    variant: "default" | "secondary" | "destructive" | "outline"
  }
> = {
  completed: { label: "完成", variant: "secondary" },
  failed: { label: "失败", variant: "destructive" },
  interrupted: { label: "已中断", variant: "outline" },
  running: { label: "运行中", variant: "default" },
}

const formatDuration = (ms: number | null | undefined) => {
  if (ms == null) return "-"
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

const StatCard = ({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: string
}) => (
  <div className="rounded-lg border p-4">
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
  </div>
)

/** 极简 CSS 柱状图：不引图表库，按日 runs 高度比例渲染 */
const DailyBars = ({
  points,
}: {
  points: { date: string; runs: number; tokens: number }[]
}) => {
  const max = Math.max(1, ...points.map((p) => p.runs))
  return (
    <div className="flex h-40 items-end gap-1">
      {points.map((p) => (
        <div
          key={p.date}
          className="flex h-full flex-1 flex-col justify-end"
          title={`${p.date}：${p.runs} 次运行 · ${p.tokens} tokens`}
        >
          <div
            className="w-full rounded-t bg-primary/70 transition-[height] duration-200 ease-out motion-reduce:transition-none"
            style={{ height: `${(p.runs / max) * 100}%` }}
          />
        </div>
      ))}
    </div>
  )
}

const StatsDashboard = () => {
  const [range, setRange] = useState("14")
  const days = Number(range)

  const overviewQuery = useQuery({
    queryKey: ["stats-overview", days],
    queryFn: () => AgentService.statsOverview({ days }),
    refetchInterval: 15_000,
  })
  const runsQuery = useQuery({
    queryKey: ["stats-runs"],
    queryFn: () => AgentService.statsRecentRuns({ limit: 20 }),
    refetchInterval: 15_000,
  })

  const overview = overviewQuery.data
  // 补齐无数据的日期，柱子才均匀
  const dailyPoints = (() => {
    if (!overview) return []
    const map = new Map(overview.daily.map((d) => [d.date, d]))
    const out: { date: string; runs: number; tokens: number }[] = []
    // 以今天为终点向前取 days 天（UTC 口径，与后端一致）
    const end = new Date()
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(end.getTime() - i * 86_400_000)
      const key = d.toISOString().slice(0, 10)
      const point = map.get(key)
      out.push({
        date: key,
        runs: point?.runs ?? 0,
        tokens: point?.tokens ?? 0,
      })
    }
    return out
  })()

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">统计</h2>
          <p className="text-sm text-muted-foreground">
            每次对话运行的 token 用量、耗时与工具调用（数据源 agent_runs）。
          </p>
        </div>
        <Select value={range} onValueChange={setRange}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RANGE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {overview && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard
            label="运行次数"
            value={String(overview.summary.runs)}
            sub={`完成 ${overview.summary.completed} · 失败 ${overview.summary.failed} · 中断 ${overview.summary.interrupted}`}
          />
          <StatCard
            label="Token 用量"
            value={overview.summary.tokens.toLocaleString()}
          />
          <StatCard
            label="平均耗时"
            value={formatDuration(overview.summary.avg_duration_ms)}
          />
          <StatCard
            label="工具调用"
            value={String(overview.summary.tool_calls)}
          />
        </div>
      )}

      <div className="rounded-lg border p-4">
        <p className="mb-3 text-sm font-medium">每日运行次数</p>
        {dailyPoints.length > 0 ? (
          <DailyBars points={dailyPoints} />
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            暂无数据
          </p>
        )}
      </div>

      <div className="rounded-lg border">
        <p className="border-b px-4 py-3 text-sm font-medium">最近运行</p>
        {(runsQuery.data ?? []).length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            还没有运行记录。去聊天页发起一次对话吧。
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>输入</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">耗时</TableHead>
                <TableHead className="text-right">工具调用</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(runsQuery.data ?? []).map((r) => {
                const st =
                  STATUS_LABEL[r.status] ??
                  ({ label: r.status, variant: "outline" } as const)
                return (
                  <TableRow key={r.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {r.created_at
                        ? new Date(r.created_at).toLocaleString()
                        : "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </TableCell>
                    <TableCell className="max-w-72 truncate">
                      {r.input_text}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.tokens_used.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatDuration(r.duration_ms)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.tool_calls_made}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}

export default StatsDashboard

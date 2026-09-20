import { useCallback, useEffect, useRef, useState } from "react"

import {
  type LogEntryOut,
  LogsService,
  type LogsOut,
} from "@/client"

const POLL_INTERVAL_MS = 2000
const MAX_VIEW_ENTRIES = 2000 // 与后端环形缓冲同容量，视图层不再额外堆积

/**
 * 控制台日志流：2 秒轮询 + after_id 游标增量追加。
 *
 * 不用 react-query：日志视图是「只追加、不重渲染整表」的流，
 * query 缓存语义（key 失效重拉）与它天然错位，setInterval + 游标直取更直白。
 * 页面不可见时自动暂停，回来立即拉一次再恢复节奏。
 */
export function useLogStream(enabled: boolean) {
  const [entries, setEntries] = useState<LogEntryOut[]>([])
  const [connected, setConnected] = useState(true)
  const cursorRef = useRef(0)
  const startedRef = useRef(false)

  const pull = useCallback(async () => {
    try {
      const res: LogsOut = await LogsService.readLogs({
        afterId: cursorRef.current,
        limit: 500,
      })
      cursorRef.current = res.latest_id
      setConnected(true)
      if (res.items.length > 0) {
        setEntries((prev) => {
          const next = startedRef.current
            ? [...prev, ...res.items]
            : res.items // 首屏：直接用服务端最近一批，不与空列表拼接
          startedRef.current = true
          return next.length > MAX_VIEW_ENTRIES
            ? next.slice(next.length - MAX_VIEW_ENTRIES)
            : next
        })
      } else {
        startedRef.current = true
      }
    } catch {
      setConnected(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    startedRef.current = false
    void pull()
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void pull()
    }, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [enabled, pull])

  const clear = useCallback(() => setEntries([]), [])

  return { entries, connected, clear }
}

export default useLogStream

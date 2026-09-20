import { useCallback, useSyncExternalStore } from "react"
import { toast } from "sonner"

import { AgentService } from "@/client"
import { setConversationGenerating } from "@/hooks/useChatActivity"

export interface ToolCall {
  name: string
  phase: "start" | "end"
  /** 工具入参（后端序列化为字符串并截断） */
  input?: string
  /** 工具结果（end 阶段带回） */
  output?: string
}

export interface Citation {
  /** 知识库名称 */
  kb: string
  /** 来源文件名（uploads 相对路径） */
  source: string
  /** 命中片段摘录（后端已截断） */
  snippet: string
  /** 相关度：rerank 0~1，或 RRF 融合分（~0.0x 量级） */
  score?: number
}

/** 已落库的附件元数据（后端按磁盘真实文件反推，前端只做展示） */
export interface MessageAttachment {
  id: string
  kind: string
  filename: string
  size: number
  /** 文档解析出的字符数（图片没有） */
  extracted_chars?: number | null
  /** 文档是否因超长被截断 */
  truncated?: boolean
}

export interface ChatMessage {
  id: string
  /** 数据库消息 ID（history 恢复或 done 事件回填；本地乐观新增时为空） */
  dbId?: string
  role: "user" | "assistant"
  content: string
  toolCalls?: ToolCall[]
  /** RAG 检索来源（sources 事件 / history 还原） */
  citations?: Citation[]
  /** 用户消息携带的附件（history 回放 / 本地乐观新增） */
  attachments?: MessageAttachment[]
  streaming?: boolean
  /** 本轮被用户中断，回复是半成品 */
  stopped?: boolean
  /** 后端生成失败的中文化错误提示气泡 */
  error?: boolean
}

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed"

// 重连退避：指数增长封顶，超过上限判定为彻底断开
const MAX_RECONNECT = 6

// 同时保留的会话连接数上限（超出淘汰最久不活跃的空闲连接）。
// 每个连接常驻一份消息数组，10 个对内存毫无压力，又足够覆盖
// 「同时开多个会话并行生成」的真实用法。
const MAX_CONNECTIONS = 10

// 模块级：useCustomToast 每次渲染返回新函数，不能进 WS 回调；
// 全中文文案，不复用其英文标题。
const errorToast = (description: string) => {
  toast.error(description)
}

export interface AgentChatState {
  messages: ChatMessage[]
  connState: ConnectionState
  isStreaming: boolean
  isConnected: boolean
}

/**
 * 单个会话的聊天连接：WS 生命周期 + 消息流状态，**独立于 React 组件树**。
 *
 * 这是「多会话并行生成」的核心：以前 WS 挂在聊天页组件的 effect 里，
 * 切走会话 → 组件卸载 → 连接关闭 → 后端收到断开**取消生成任务**。
 * 现在连接常驻本管理器，切换会话只是换一个订阅对象，后台会话继续生成，
 * 侧边栏的「生成中」指示器（useChatActivity）对后台会话同样生效。
 */
class ChatConnection {
  readonly conversationId: string
  private listeners = new Set<() => void>()

  private _messages: ChatMessage[] = []
  private _connState: ConnectionState = "connecting"
  private _isStreaming = false

  /** 缓存的不可变快照：getSnapshot 必须返回同一引用（useSyncExternalStore 约定） */
  private snapshot: AgentChatState

  private ws: WebSocket | null = null
  private closedIntentionally = false
  private attempt = 0
  private reconnectTimer: number | undefined
  lastActive = Date.now()

  constructor(conversationId: string) {
    this.conversationId = conversationId
    this.snapshot = {
      messages: this._messages,
      connState: this._connState,
      isStreaming: this._isStreaming,
      isConnected: false,
    }
    this.connect()
  }

  // ── 订阅（useSyncExternalStore） ─────────────────────────────

  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  getSnapshot = () => this.snapshot

  private emit() {
    this.snapshot = {
      messages: this._messages,
      connState: this._connState,
      isStreaming: this._isStreaming,
      isConnected: this._connState === "open",
    }
    for (const listener of this.listeners) listener()
  }

  private setMessages(update: (prev: ChatMessage[]) => ChatMessage[]) {
    this._messages = update(this._messages)
    this.emit()
  }

  private setConnState(state: ConnectionState) {
    this._connState = state
    this.emit()
  }

  private setStreaming(value: boolean) {
    if (this._isStreaming === value) return
    this._isStreaming = value
    // 侧边栏「生成中」指示器的全局登记：后台会话也在跟踪范围内
    setConversationGenerating(this.conversationId, value)
    this.emit()
  }

  // ── WS 建连与消息处理 ────────────────────────────────────────

  private connect() {
    // WebSocket 地址必须**动态**从当前页面推导（同源 + ws/wss 自适应），
    // 不能烤进构建产物；详见旧实现的推导注释。
    const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl =
      `${wsProtocol}//${location.host}` +
      `/api/v1/agent/chat/ws/${this.conversationId}` +
      `?token=${localStorage.getItem("access_token")}`

    this.closedIntentionally = false
    this.setConnState(this.attempt === 0 ? "connecting" : "reconnecting")
    const ws = new WebSocket(wsUrl)
    this.ws = ws

    ws.onopen = () => {
      if (this.ws !== ws) return
      this.attempt = 0
      this.setConnState("open")
    }

    ws.onmessage = (event) => {
      if (this.ws !== ws) return
      this.handleMessage(JSON.parse(event.data))
    }

    ws.onclose = (event) => {
      if (this.ws !== ws || this.closedIntentionally) return
      this.setStreaming(false)
      // 4404 = 会话不存在/无权限：重连也没用，直接终态
      if (event.code === 4404) {
        this.setConnState("closed")
        return
      }
      if (this.attempt >= MAX_RECONNECT) {
        this.setConnState("closed")
        errorToast("连接已断开，请刷新页面重试")
        return
      }
      // 指数退避：1s / 2s / 4s …… 上限 ~13s
      const delay =
        Math.min(1000 * 2 ** this.attempt, 13000) + Math.random() * 400
      this.attempt += 1
      this.setConnState("reconnecting")
      this.reconnectTimer = window.setTimeout(() => this.connect(), delay)
    }
  }

  private handleMessage(msg: Record<string, unknown>) {
    const type = msg.type
    if (type === "history") {
      // 建连后后端推送的历史消息，据此恢复已有对话（刷新不丢）
      this._messages = (
        (msg.messages ?? []) as Array<Record<string, unknown>>
      ).map((h) => ({
        id: (h.id as string) ?? crypto.randomUUID(),
        dbId: h.id as string,
        role: h.role as "user" | "assistant",
        content: h.content as string,
        toolCalls: h.tool_calls as ToolCall[],
        citations: h.citations as Citation[],
        attachments: h.attachments as MessageAttachment[],
        stopped: h.stopped as boolean | undefined,
        streaming: false,
      }))
      this.emit()
    } else if (type === "text_chunk") {
      // AI 回复流式生成中，往最后一条 assistant 消息追加文字
      this.setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last?.role !== "assistant") {
          return [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: msg.content as string,
              streaming: true,
            },
          ]
        }
        return [
          ...prev.slice(0, -1),
          { ...last, content: last.content + (msg.content as string) },
        ]
      })
    } else if (type === "tool_call") {
      // 与后端 merge_tool_trace 同口径：start 追加一条，
      // end 回填到同名最近一条未完成的 start，面板只留一行。
      // 注意：工具通常先于任何 text_chunk 触发，此时还没有 assistant
      // 消息，要先建一条空占位，否则事件会被直接丢掉、面板不出现。
      this.setMessages((prev) => {
        const last = prev[prev.length - 1]
        const hasAssistant = last?.role === "assistant"
        const base = hasAssistant ? prev.slice(0, -1) : prev
        const target: ChatMessage = hasAssistant
          ? last
          : {
              id: crypto.randomUUID(),
              role: "assistant",
              content: "",
              streaming: true,
            }
        const calls = [...(target.toolCalls ?? [])]
        if (msg.phase === "start") {
          calls.push({
            name: msg.name as string,
            phase: "start",
            input: msg.input as string | undefined,
          })
        } else {
          let idx = -1
          for (let i = calls.length - 1; i >= 0; i--) {
            if (calls[i].name === msg.name && calls[i].phase === "start") {
              idx = i
              break
            }
          }
          if (idx >= 0)
            calls[idx] = {
              ...calls[idx],
              phase: "end",
              output: msg.output as string | undefined,
            }
          else
            calls.push({
              name: msg.name as string,
              phase: "end",
              output: msg.output as string | undefined,
            })
        }
        return [...base, { ...target, toolCalls: calls }]
      })
    } else if (type === "sources") {
      // RAG 检索来源：挂到最后一条 assistant 消息
      this.setMessages((prev) => {
        const last = prev[prev.length - 1]
        const hasAssistant = last?.role === "assistant"
        const base = hasAssistant ? prev.slice(0, -1) : prev
        const target: ChatMessage = hasAssistant
          ? last
          : {
              id: crypto.randomUUID(),
              role: "assistant",
              content: "",
              streaming: true,
            }
        return [...base, { ...target, citations: msg.citations as Citation[] }]
      })
    } else if (type === "done") {
      // 本轮回复结束；后端回传落库消息 ID，回填给本地乐观消息，
      // 之后删除/编辑重发/重新生成才能按 ID 调 REST
      this.setStreaming(false)
      this.setMessages((prev) => {
        let lastUser = -1
        let lastAssistant = -1
        prev.forEach((m, i) => {
          if (m.role === "user") lastUser = i
          if (m.role === "assistant") lastAssistant = i
        })
        return prev.map((m, i) => {
          let next = m
          if (m.streaming) next = { ...next, streaming: false }
          if (i === lastUser && msg.user_message_id)
            next = { ...next, dbId: msg.user_message_id as string }
          if (i === lastAssistant && msg.assistant_message_id)
            next = { ...next, dbId: msg.assistant_message_id as string }
          if (i === lastAssistant && msg.interrupted)
            next = { ...next, stopped: true }
          return next
        })
      })
      // 通知任意挂载的界面刷新会话列表（后台会话收尾时聊天页感知不到，
      // 这里用 window 事件解耦：首条消息的新标题 / updated_at 排序都要刷新）
      window.dispatchEvent(
        new CustomEvent("irsbot:turn-done", {
          detail: { conversationId: this.conversationId },
        }),
      )
    } else if (type === "error") {
      // 后端生成异常：中文化提示以红字气泡固定展示（不是一闪而过的 toast）
      this.setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: (msg.message as string) || "回复生成失败，请稍后重试。",
          error: true,
        },
      ])
    }
  }

  // ── 对外动作（hook 返回的 API） ──────────────────────────────

  /**
   * 发送一条消息。`attachments` 只传 att_id 列表——字节与元数据都由
   * 后端自己从磁盘取（见 agent_ws.py 的 _resolve_attachments）。
   */
  sendMessage = (content: string, attachments?: MessageAttachment[]) => {
    const ws = this.ws
    if (!ws || ws.readyState !== WebSocket.OPEN) return

    this.setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        content,
        attachments: attachments?.length ? attachments : undefined,
      },
    ])
    this.setStreaming(true)

    ws.send(
      JSON.stringify({
        type: "message",
        content,
        ...(attachments?.length
          ? { attachments: attachments.map((a) => ({ id: a.id })) }
          : {}),
      }),
    )
  }

  /** 中断当前生成：通知后端 cancel 本轮任务。
   *  真正的收尾（isStreaming 置假、部分回复落库）由后端随后的 done 事件驱动，
   *  这里不本地置状态，避免与 done 竞态导致半成品消息丢失 ID。 */
  interrupt = () => {
    const ws = this.ws
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: "interrupt" }))
  }

  /** 截断本地状态：删掉 dbId 对应消息及其后的所有消息 */
  private truncateLocal = (dbId: string, inclusive: boolean) => {
    this.setMessages((prev) => {
      const idx = prev.findIndex((m) => m.dbId === dbId)
      if (idx < 0) return prev
      return idx === 0 && inclusive
        ? []
        : prev.slice(0, inclusive ? idx : idx + 1)
    })
  }

  /** 删除单条消息 */
  deleteMessage = async (dbId: string) => {
    try {
      await AgentService.deleteConversationMessage({
        conversationId: this.conversationId,
        messageId: dbId,
      })
      this.setMessages((prev) => prev.filter((m) => m.dbId !== dbId))
    } catch {
      errorToast("删除消息失败，请重试")
    }
  }

  /** 重新生成：截掉最后一条用户消息及其后回复，重新发送同一问题 */
  regenerate = async () => {
    if (this._isStreaming) return
    let target: ChatMessage | undefined
    for (let i = this._messages.length - 1; i >= 0; i--) {
      if (this._messages[i].role === "user") {
        target = this._messages[i]
        break
      }
    }
    if (!target?.dbId) return
    try {
      await AgentService.truncateConversationMessages({
        conversationId: this.conversationId,
        requestBody: { message_id: target.dbId, inclusive: true },
      })
      this.truncateLocal(target.dbId, true)
      // 带上原附件一起重发：文档内容只在"发送那一刻"进上下文，
      // 不带的话重新生成就变成了"对空文档提问"
      this.sendMessage(target.content, target.attachments)
    } catch {
      errorToast("重新生成失败，请重试")
    }
  }

  /** 编辑重发：改用户消息内容并删掉其后的所有消息，重新发送 */
  editAndResend = async (dbId: string, newContent: string) => {
    if (this._isStreaming) return
    const target = this._messages.find((m) => m.dbId === dbId)
    try {
      await AgentService.truncateConversationMessages({
        conversationId: this.conversationId,
        requestBody: { message_id: dbId, inclusive: true },
      })
      this.truncateLocal(dbId, true)
      // 附件文件仍在会话目录里（截断消息不删文件），可以原样带上
      this.sendMessage(newContent, target?.attachments)
    } catch {
      errorToast("编辑重发失败，请重试")
    }
  }

  /** 主动关闭（LRU 淘汰）：后台生成会被后端取消，仅对空闲连接使用 */
  close() {
    this.closedIntentionally = true
    if (this.reconnectTimer !== undefined) {
      window.clearTimeout(this.reconnectTimer)
    }
    this.setStreaming(false)
    this.ws?.close()
    this.ws = null
    this.listeners.clear()
  }
}

// ── 连接管理器（模块级单例） ────────────────────────────────────

const connections = new Map<string, ChatConnection>()

/** 会话删除后清理其连接（后台若有生成会被后端 4404/级联删除中止） */
export function closeChatConnection(conversationId: string) {
  connections.get(conversationId)?.close()
  connections.delete(conversationId)
}

function evictIdleConnections(keepId: string) {
  while (connections.size >= MAX_CONNECTIONS) {
    // 找最久不活跃的空闲连接淘汰；全在流式中则允许暂时超限
    let victim: ChatConnection | null = null
    for (const c of connections.values()) {
      if (c.conversationId === keepId || c.getSnapshot().isStreaming) continue
      if (!victim || c.lastActive < victim.lastActive) victim = c
    }
    if (!victim) return
    victim.close()
    connections.delete(victim.conversationId)
  }
}

/**
 * 取（或创建）一个会话连接。允许在渲染期调用：
 * Map 保证同一会话全应用只有一个连接实例（StrictMode 双渲染也幂等）。
 */
function getChatConnection(conversationId: string): ChatConnection {
  let conn = connections.get(conversationId)
  if (!conn) {
    evictIdleConnections(conversationId)
    conn = new ChatConnection(conversationId)
    connections.set(conversationId, conn)
  }
  conn.lastActive = Date.now()
  return conn
}

/**
 * 聊天室的数据与动作入口（原 useAgentChat）。
 *
 * 连接由模块级管理器持有，本 hook 只是它的 React 视图：
 * 切换会话 → 组件按新 conversationId 订阅另一个连接，
 * 旧连接继续在后台收流。返回的动作为稳定引用（绑定在连接对象上）。
 */
export function useAgentChat(conversationId: string) {
  const conn = getChatConnection(conversationId)
  const state = useSyncExternalStore(
    conn.subscribe,
    conn.getSnapshot,
    conn.getSnapshot,
  )

  // 动作直接引用连接实例（连接按会话 ID 恒定，不存在过期闭包问题）
  return {
    messages: state.messages,
    connState: state.connState,
    isStreaming: state.isStreaming,
    isConnected: state.isConnected,
    sendMessage: conn.sendMessage,
    interrupt: conn.interrupt,
    deleteMessage: conn.deleteMessage,
    regenerate: conn.regenerate,
    editAndResend: conn.editAndResend,
  }
}

/** 会话删除时同时清理连接（ConversationList 的删除流程调用） */
export function useCloseChatConnection() {
  return useCallback((conversationId: string) => {
    closeChatConnection(conversationId)
  }, [])
}

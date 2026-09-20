import { useSyncExternalStore } from "react"

/**
 * 「哪个对话正在生成」的全局登记处。
 *
 * useAgentChat 的 isStreaming 是聊天页局部状态，而侧边栏对话列表在
 * 组件树另一支上，需要跨分支共享。这里不引入 zustand —— 一个 Set +
 * useSyncExternalStore 就够了：唯一写方是 useAgentChat 的流式生命周期。
 *
 * getSnapshot 返回缓存的同一引用，仅在集合真正增减时才替换，
 * 满足 useSyncExternalStore 的引用相等要求。
 */

let generatingIds: readonly string[] = []
const listeners = new Set<() => void>()

export function setConversationGenerating(
  conversationId: string,
  generating: boolean,
) {
  const has = generatingIds.includes(conversationId)
  if (generating === has) return
  generatingIds = generating
    ? [...generatingIds, conversationId]
    : generatingIds.filter((id) => id !== conversationId)
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** 订阅当前正在生成的对话 id 列表（侧边栏列表行渲染状态指示器用） */
export function useGeneratingConversationIds(): readonly string[] {
  return useSyncExternalStore(subscribe, () => generatingIds, () => generatingIds)
}

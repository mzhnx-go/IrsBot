import { ArrowDownUp, Braces, MessagesSquare, Mic, Volume2 } from "lucide-react"

/**
 * 能力 Tab 元数据（P5）。
 *
 * key 与后端 `ProviderConfig.capability` 的取值一一对应
 * （`backend/app/api/routes/providers.py` 的 `Capability` Literal）。
 * 每个能力各自一条默认源，切 Tab 就是切一份独立的模型源清单。
 */
export const CAPABILITY_TABS = [
  { key: "chat", label: "对话", icon: MessagesSquare },
  { key: "stt", label: "语音转文字", icon: Mic },
  { key: "tts", label: "文字转语音", icon: Volume2 },
  { key: "embedding", label: "嵌入", icon: Braces },
  { key: "rerank", label: "重排序", icon: ArrowDownUp },
] as const

export type ProviderCapability = (typeof CAPABILITY_TABS)[number]["key"]

const LABELS = Object.fromEntries(
  CAPABILITY_TABS.map((t) => [t.key, t.label]),
) as Record<ProviderCapability, string>

/** 能力的中文名，用于弹窗与详情文案（如「新增对话模型源」）。 */
export const capabilityLabel = (c: ProviderCapability) => LABELS[c]

/** 各能力下「模型名」的含义不同，用不同占位符提示用户该填什么。 */
export const MODEL_NAME_PLACEHOLDER: Record<ProviderCapability, string> = {
  chat: "如：qwen-plus",
  stt: "如：whisper-1",
  tts: "如：tts-1",
  embedding: "如：BAAI/bge-m3",
  rerank: "如：BAAI/bge-reranker-v2-m3",
}

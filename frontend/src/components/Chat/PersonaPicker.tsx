import { useQuery } from "@tanstack/react-query"
import { Drama } from "lucide-react"

import { AgentService } from "@/client"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import usePersonas from "@/hooks/usePersonas"

const DEFAULT_VALUE = "__default__"

/**
 * 会话人设选择器（chat 页顶部小控件）。
 * 绑定关系存在 Conversation.persona_id，切换即 PATCH /conversations/{id}/persona。
 */
const PersonaPicker = ({ conversationId }: { conversationId: string }) => {
  const { personasQuery, bindPersona } = usePersonas()

  // 复用侧边栏的会话列表缓存，取当前会话已绑定的 persona_id
  const { data: conversations } = useQuery({
    queryKey: ["conversations"],
    queryFn: () => AgentService.listConversations(),
  })
  const current = conversations?.find((c) => c.id === conversationId)

  const personas = personasQuery.data ?? []
  // 已停用/已删除的人设不出现在选项里；若会话仍绑定着它们则显示为空
  const boundId = personas.some(
    (p) => p.id === current?.persona_id && p.is_active,
  )
    ? (current?.persona_id as string)
    : null

  return (
    <Select
      value={boundId ?? DEFAULT_VALUE}
      disabled={bindPersona.isPending}
      onValueChange={(v) =>
        bindPersona.mutate({
          conversationId,
          personaId: v === DEFAULT_VALUE ? null : v,
        })
      }
    >
      <SelectTrigger
        size="sm"
        className="w-auto gap-1.5 border-none bg-transparent text-xs text-muted-foreground shadow-none hover:bg-muted/50"
      >
        <Drama className="size-3.5" />
        <SelectValue placeholder="默认角色" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={DEFAULT_VALUE}>默认角色</SelectItem>
        {personas
          .filter((p) => p.is_active)
          .map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {p.avatar ? `${p.avatar} ` : ""}
              {p.name}
            </SelectItem>
          ))}
      </SelectContent>
    </Select>
  )
}

export default PersonaPicker

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { AgentService, type PersonaCreate, type PersonaUpdate } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

/**
 * Persona（人设）管理 hook。
 *
 * - personasQuery: 列表（缓存 key "personas"）
 * - create/update/delete: 写操作，成功后失效列表缓存
 * - bindPersona: 把某个人设绑定到会话（null 解绑）；会改变会话响应，
 *   所以同时失效 ["conversations"]
 */
const usePersonas = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const personasQuery = useQuery({
    queryKey: ["personas"],
    queryFn: () => AgentService.listPersonasRoute(),
  })

  const createPersona = useMutation({
    mutationFn: (body: PersonaCreate) =>
      AgentService.createPersonaRoute({ requestBody: body }),
    onSuccess: () => {
      showSuccessToast("人设已创建")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["personas"] })
    },
  })

  const updatePersona = useMutation({
    mutationFn: ({
      personaId,
      body,
    }: {
      personaId: string
      body: PersonaUpdate
    }) => AgentService.updatePersonaRoute({ personaId, requestBody: body }),
    onSuccess: () => {
      showSuccessToast("人设已更新")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["personas"] })
      // is_active 变化会影响会话里人设是否生效，列表端也要刷新
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const deletePersona = useMutation({
    mutationFn: (personaId: string) =>
      AgentService.deletePersonaRoute({ personaId }),
    onSuccess: () => {
      showSuccessToast("人设已删除")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["personas"] })
      // 后端删除时会解绑所有会话，会话列表里的 persona_id 已变
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const bindPersona = useMutation({
    mutationFn: ({
      conversationId,
      personaId,
    }: {
      conversationId: string
      personaId: string | null
    }) =>
      AgentService.bindConversationPersona({
        conversationId,
        requestBody: { persona_id: personaId },
      }),
    onSuccess: () => {
      showSuccessToast("会话人设已更新")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  return {
    personasQuery,
    createPersona,
    updatePersona,
    deletePersona,
    bindPersona,
  }
}

export default usePersonas

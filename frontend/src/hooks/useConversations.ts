import { AgentService, type ConversationCreate } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

/**
 * 会话列表层的数据 hook（侧边栏用）。
 *
 * - conversationsQuery: 当前用户的会话列表（后端按 updated_at 倒序返回）
 * - createConversation: 新建会话（返回带 id 的完整对象，供跳转用）
 * - deleteConversation: 删除会话
 *
 * 职责边界：只负责「调接口 + 管缓存」，不做任何界面渲染。
 */
const useConversations = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const conversationsQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: () => AgentService.listConversations(),
  })

  const createConversation = useMutation({
    mutationFn: (body: ConversationCreate = { title: "新对话" }) =>
      AgentService.createConversation({ requestBody: body }),
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const deleteConversation = useMutation({
    mutationFn: (conversationId: string) =>
      AgentService.deleteConversation({ conversationId }),
    onSuccess: () => {
      showSuccessToast("对话已删除")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const renameConversation = useMutation({
    mutationFn: ({
      conversationId,
      title,
    }: {
      conversationId: string
      title: string
    }) => AgentService.renameConversation({ conversationId, requestBody: { title } }),
    onSuccess: () => {
      showSuccessToast("已重命名")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  return {
    conversationsQuery,
    createConversation,
    deleteConversation,
    renameConversation,
  }
}

export default useConversations

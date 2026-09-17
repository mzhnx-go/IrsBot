import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { type SystemPromptUpdate, UsersService } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

/**
 * 系统提示词数据 hook（系统提示词功能 F3）。
 *
 * - systemPromptQuery: 读取当前提示词状态（缓存 key "system-prompt"）
 * - updateSystemPrompt: 保存/清空共用的写操作（空串即清空回落默认），
 *   成功后失效缓存，UI 自动刷新
 */
const useSystemPrompt = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const systemPromptQuery = useQuery({
    queryKey: ["system-prompt"],
    queryFn: () => UsersService.readMySystemPrompt(),
  })

  const updateSystemPrompt = useMutation({
    mutationFn: (body: SystemPromptUpdate) =>
      UsersService.updateMySystemPrompt({ requestBody: body }),
    onSuccess: () => {
      showSuccessToast("系统提示词已保存")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["system-prompt"] })
    },
  })

  return { systemPromptQuery, updateSystemPrompt }
}

export default useSystemPrompt

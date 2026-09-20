import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { SettingsService, type ToolPermissionsUpdate } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

/**
 * 工具权限 hook（超管专属）。
 *
 * shell / file 类工具具备破坏力，是否注册给 Agent 由运行时开关决定
 * （优先级：app_settings 表 > `.env` > 代码默认）。开关保存即生效，
 * 下一轮对话就会按新配置组装工具集 —— 无需重启后端。
 */
const useToolPermissions = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const toolPermissionsQuery = useQuery({
    queryKey: ["tool-permissions"],
    queryFn: () => SettingsService.readToolPermissions(),
  })

  const updateToolPermissions = useMutation({
    mutationFn: (body: ToolPermissionsUpdate) =>
      SettingsService.updateToolPermissions({ requestBody: body }),
    onSuccess: (data) => {
      const parts: string[] = []
      if (data.shell_enabled) parts.push("shell")
      if (data.file_write_enabled) parts.push("文件读写")
      showSuccessToast(
        parts.length > 0
          ? `工具权限已更新：${parts.join("、")} 开启`
          : "危险工具已全部关闭",
      )
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["tool-permissions"] })
    },
  })

  return { toolPermissionsQuery, updateToolPermissions }
}

export default useToolPermissions

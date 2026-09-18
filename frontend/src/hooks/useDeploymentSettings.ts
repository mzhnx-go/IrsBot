import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  type DeploymentSettingsUpdate,
  SettingsService,
  UtilsService,
} from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

/**
 * 部署设置 hook（单用户 / 多租户运行时开关）。
 *
 * - deploymentSettingsQuery: 超管读部署设置（缓存 key "deployment-settings"）
 * - updateDeploymentSettings: 保存开关，成功后同时失效公开设置的缓存，
 *   让登录页的注册入口**立刻**跟随变化
 */
const useDeploymentSettings = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const deploymentSettingsQuery = useQuery({
    queryKey: ["deployment-settings"],
    queryFn: () => SettingsService.readDeploymentSettings(),
  })

  const updateDeploymentSettings = useMutation({
    mutationFn: (body: DeploymentSettingsUpdate) =>
      SettingsService.updateDeploymentSettings({ requestBody: body }),
    onSuccess: (data) => {
      showSuccessToast(
        data.open_registration ? "已切换为多租户模式" : "已切换为单用户模式",
      )
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["deployment-settings"] })
      queryClient.invalidateQueries({ queryKey: ["public-settings"] })
    },
  })

  return { deploymentSettingsQuery, updateDeploymentSettings }
}

/**
 * 公开设置 hook（**无需登录**）。
 *
 * 登录页用它决定要不要渲染「注册」入口。缓存 key 与上面刻意分开：
 * 这个 key 下只缓存「能不能注册」这一位布尔，不含任何超管信息。
 */
export const usePublicSettings = () =>
  useQuery({
    queryKey: ["public-settings"],
    queryFn: () => UtilsService.readPublicSettings(),
  })

export default useDeploymentSettings

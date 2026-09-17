import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  type ProviderCreate,
  ProvidersService,
  type ProviderUpdate,
} from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

/**
 * Provider 管理的统一数据 hook（Task 10.5）。
 *
 * - providersQuery: 列表查询（缓存 key "providers"）
 * - createProvider / updateProvider / deleteProvider: 三个写操作，
 *   成功后自动失效列表缓存，UI 自动刷新
 */
const useProviders = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const providersQuery = useQuery({
    queryKey: ["providers"],
    queryFn: () => ProvidersService.listProviders(),
  })

  const createProvider = useMutation({
    mutationFn: (body: ProviderCreate) =>
      ProvidersService.createProvider({ requestBody: body }),
    onSuccess: () => {
      showSuccessToast("模型源已创建")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["providers"] })
    },
  })

  const updateProvider = useMutation({
    mutationFn: ({
      providerId,
      body,
    }: {
      providerId: string
      body: ProviderUpdate
    }) => ProvidersService.updateProvider({ providerId, requestBody: body }),
    onSuccess: () => {
      showSuccessToast("模型源已更新")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["providers"] })
    },
  })

  const deleteProvider = useMutation({
    mutationFn: (providerId: string) =>
      ProvidersService.deleteProvider({ providerId }),
    onSuccess: () => {
      showSuccessToast("模型源已删除")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["providers"] })
    },
  })

  return { providersQuery, createProvider, updateProvider, deleteProvider }
}

export default useProviders

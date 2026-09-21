import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  type ProviderCreate,
  ProvidersService,
  type ProviderUpdate,
} from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import type { ProviderCapability } from "@/components/Providers/capabilities"
import { handleError } from "@/utils"

/**
 * Provider 管理的统一数据 hook（Task 10.5 / P5 能力维度）。
 *
 * - providersQuery: 列表查询（缓存 key ["providers", capability]）——
 *   能力维度参与 key，切 Tab 时各自缓存，互不覆盖
 * - createProvider / updateProvider / deleteProvider: 三个写操作，
 *   成功后按前缀失效 ["providers"]（带能力的 key 一并失效）
 *
 * @param capability 能力维度；不传表示「全部能力」（首屏兜底 / 引导页判断用）
 */
const useProviders = (capability?: ProviderCapability) => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const providersQuery = useQuery({
    queryKey: ["providers", capability ?? "all"],
    queryFn: () => ProvidersService.listProviders({ capability }),
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

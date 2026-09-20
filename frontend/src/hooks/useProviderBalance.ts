import { useQuery } from "@tanstack/react-query"

import { ProvidersService } from "@/client"

/**
 * 查询某个模型源的账户余额（上游服务商接口）。
 *
 * 用 `enabled: false` + 手动 `refetch()`：余额查询是会打上游的外部调用，
 * 不该在页面加载时对每个模型源自动发起；由用户点「查余额」触发，
 * 结果按 providerId 缓存在 query 里（每个模型源各自一份，互不干扰）。
 */
const useProviderBalance = (providerId: string) => {
  const balanceQuery = useQuery({
    queryKey: ["provider-balance", providerId],
    queryFn: () => ProvidersService.getProviderBalance({ providerId }),
    enabled: false,
    retry: false,
    // 余额变化不快，30 秒内重复点击直接用缓存，避免连续打上游
    staleTime: 30_000,
  })

  return { balanceQuery }
}

export default useProviderBalance

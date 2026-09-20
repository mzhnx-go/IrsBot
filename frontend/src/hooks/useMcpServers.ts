import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  AgentService,
  type MCPServerCreate,
  type MCPServerUpdate,
} from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

/**
 * MCP Server 管理的数据 hook（Phase 15.2a）。
 *
 * - mcpQuery：列表（缓存 key ["mcp-servers"]）
 * - create / update / delete：写操作，成功后失效列表缓存
 * - connect：连接测试，后端会把发现的工具列表缓存到该条记录上，
 *   因此成功后同样要刷新列表（工具预览直接读行数据）
 */
const useMcpServers = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const mcpQuery = useQuery({
    queryKey: ["mcp-servers"],
    queryFn: () => AgentService.listMcpServers(),
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["mcp-servers"] })

  const createServer = useMutation({
    mutationFn: (body: MCPServerCreate) =>
      AgentService.createMcpServer({ requestBody: body }),
    onSuccess: () => {
      showSuccessToast("MCP 服务已创建")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  const updateServer = useMutation({
    mutationFn: ({
      serverId,
      body,
    }: {
      serverId: string
      body: MCPServerUpdate
    }) => AgentService.updateMcpServer({ serverId, requestBody: body }),
    onSuccess: () => {
      showSuccessToast("MCP 服务已更新")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  const deleteServer = useMutation({
    mutationFn: (serverId: string) =>
      AgentService.deleteMcpServer({ serverId }),
    onSuccess: () => {
      showSuccessToast("MCP 服务已删除")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  const connectServer = useMutation({
    mutationFn: (serverId: string) =>
      AgentService.connectMcpServer({ serverId }),
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  return {
    mcpQuery,
    createServer,
    updateServer,
    deleteServer,
    connectServer,
  }
}

export default useMcpServers

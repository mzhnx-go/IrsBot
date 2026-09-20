import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  type AgentExportConversationData,
  AgentService,
  type ConversationCreate,
  OpenAPI,
} from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { closeChatConnection } from "@/hooks/useAgentChat"
import { handleError } from "@/utils"

/** 导出格式：直接取自 OpenAPI 生成的类型，前端不再手抄一份字符串联合 */
export type ConversationExportFormat = NonNullable<
  AgentExportConversationData["format"]
>

/**
 * 从 Content-Disposition 响应头里解析下载文件名。
 *
 * 后端按 RFC 6266 双写：`filename="<ASCII兜底>"` + `filename*=UTF-8''<百分号编码真名>`。
 * 这里优先取后者，与浏览器的选择保持一致（中文标题才不会变成下划线或乱码）。
 */
const parseFilename = (disposition: string | null): string => {
  if (!disposition) return "conversation"
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1])
    } catch {
      // 百分号编码不合法 → 落到下面的 ASCII 兜底，不抛异常
    }
  }
  const plain = disposition.match(/filename="([^"]+)"/i)
  return plain ? plain[1] : "conversation"
}

/**
 * 请求导出接口并把文件存到本地。
 *
 * 为什么不复用 src/client 里生成的 SDK：
 *   SDK 基于 axios，默认按 JSON 解析响应体，docx / pdf 这类二进制会先被
 *   当字符串解码再重新编码 → 下载下来的文件损坏打不开。
 * 所以这里直接用 fetch 取 Blob，并手动补上 Authorization 头。
 *
 * 参数:
 *   conversationId: 会话 ID。
 *   format: 导出格式（md / txt / json / docx / pdf）。
 */
const downloadConversationExport = async (
  conversationId: string,
  format: ConversationExportFormat,
) => {
  const res = await fetch(
    `${OpenAPI.BASE}/api/v1/agent/conversations/${conversationId}/export?format=${format}`,
    {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("access_token") ?? ""}`,
      },
    },
  )

  if (!res.ok) {
    // 后端错误体是 {"detail": "..."}；解析不出来就退回状态码，别吞掉失败原因
    let detail = `导出失败（HTTP ${res.status}）`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // 响应不是 JSON（如网关错误页），保持上面的默认提示
    }
    throw new Error(detail)
  }

  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)

  // 用隐藏的 <a download> 触发浏览器「另存为」，这是纯前端落盘的标准做法
  const link = document.createElement("a")
  link.href = objectUrl
  link.download = parseFilename(res.headers.get("content-disposition"))
  document.body.appendChild(link)
  link.click()
  link.remove()

  // 立刻 revoke 有概率掐断还没开始的下载，放到下一个宏任务里释放更稳
  setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}

/**
 * 会话列表层的数据 hook（侧边栏用）。
 *
 * - conversationsQuery: 当前用户的会话列表（后端按 updated_at 倒序返回）
 * - createConversation: 新建会话（返回带 id 的完整对象，供跳转用）
 * - deleteConversation: 删除会话
 * - renameConversation: 重命名会话
 * - exportConversation: 按格式导出会话为文件并触发下载
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
    onSuccess: (_data, conversationId) => {
      // 该会话的 WS 连接（可能在后台正生成）一并关闭，避免残留
      closeChatConnection(conversationId)
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
    }) =>
      AgentService.renameConversation({
        conversationId,
        requestBody: { title },
      }),
    onSuccess: () => {
      showSuccessToast("已重命名")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const setConversationStatus = useMutation({
    mutationFn: ({
      conversationId,
      isEnabled,
    }: {
      conversationId: string
      isEnabled: boolean
    }) =>
      AgentService.setConversationStatus({
        conversationId,
        requestBody: { is_enabled: isEnabled },
      }),
    onSuccess: (_data, { isEnabled }) => {
      showSuccessToast(isEnabled ? "会话已启用" : "会话已停用")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const exportConversation = useMutation({
    mutationFn: ({
      conversationId,
      format,
    }: {
      conversationId: string
      format: ConversationExportFormat
    }) => downloadConversationExport(conversationId, format),
    onSuccess: () => {
      showSuccessToast("对话已导出")
    },
    // 不复用 utils 的 handleError：它按 axios 的 ApiError 结构解析错误体，
    // 这里抛的是 fetch 路径上的普通 Error，直接取 message 才不会丢原因
    onError: (error) => {
      showErrorToast(error instanceof Error ? error.message : "导出失败")
    },
  })

  return {
    conversationsQuery,
    createConversation,
    deleteConversation,
    renameConversation,
    setConversationStatus,
    exportConversation,
  }
}

export default useConversations

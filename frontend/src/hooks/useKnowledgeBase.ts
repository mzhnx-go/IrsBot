import {
    type Body_knowledge_base_upload_kb_document,
    type KBCreate,
    KnowledgeBaseService,
} from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"


/**
 * 知识库列表层的数据 hook。
 *
 * - kbListQuery: 知识库列表（缓存 key "knowledge-base"）
 * - createKb / deleteKb: 知识库的增删
 *
 * 职责边界：只负责「调接口 + 管缓存」，不做任何界面渲染。
 * 库内文档与检索的能力见 useKbDetail。
 */
const useKnowledgeBase = () => {
    const queryClient = useQueryClient()
    const { showSuccessToast, showErrorToast } = useCustomToast()

    const kbListQuery = useQuery({
        queryKey: ["knowledge-base"],
        queryFn: () => KnowledgeBaseService.listKbs(),
    })

    const createKb = useMutation({
        mutationFn: (body: KBCreate) =>
            KnowledgeBaseService.createKb({ requestBody: body }),
        onSuccess: () => {
            showSuccessToast("知识库已创建")
        },
        onError: handleError.bind(showErrorToast),
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["knowledge-base"] })
        },
    })

    const deleteKb = useMutation({
        mutationFn: (kbId: string) => KnowledgeBaseService.deleteKb({ kbId }),
        onSuccess: () => {
            showSuccessToast("知识库已删除")
        },
        onError: handleError.bind(showErrorToast),
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["knowledge-base"] })
        },
    })

    return { kbListQuery, createKb, deleteKb }
}

/**
 * 单个知识库内部的数据 hook（文档列表 / 上传 / 删除 / 检索测试）。
 *
 * - kbQuery: 该库的详情（名称/描述，缓存 key ["knowledge-base", kbId]）
 * - docsQuery: 该库的文档列表（缓存 key ["kb-documents", kbId]）
 * - uploadDoc: 上传并解析入库，入参只有 File（kbId 从闭包取）
 * - deleteDoc: 删除单个文档（后端端点已就绪，等第四章生成 SDK 后接通）
 * - queryKb: 检索测试（查询型写操作，结果由调用方读 queryKb.data）
 *
 * 职责边界：同样只负责「调接口 + 管缓存」。
 */
export const useKbDetail = (kbId: string) => {
    const queryClient = useQueryClient()
    const { showSuccessToast, showErrorToast } = useCustomToast()

    const kbQuery = useQuery({
        // key 以 ["knowledge-base"] 开头 → 列表层失效时会连带刷新本库详情
        queryKey: ["knowledge-base", kbId],
        queryFn: () => KnowledgeBaseService.getKb({ kbId }),
    })

    const docsQuery = useQuery({
        queryKey: ["kb-documents", kbId],
        queryFn: () => KnowledgeBaseService.listKbDocuments({ kbId }),
    })

    const uploadDoc = useMutation({
        mutationFn: (file: File) =>
            // 传普通对象而非 FormData 实例：客户端 getFormData() 会用
            // Object.entries() 遍历它自己组装 multipart——FormData 实例
            // 遍历出来是空数组，会发一个空表单（后端 422: file 字段缺失）。
            // 双重断言绕生成器 bug（file 被标成 string，运行时是 File）。
            KnowledgeBaseService.uploadKbDocument({
                kbId,
                formData: { file } as unknown as Body_knowledge_base_upload_kb_document,
            }),
        onSuccess: () => {
            showSuccessToast("文档已上传，正在解析入库")
        },
        onError: handleError.bind(showErrorToast),
        onSettled: () => {
            // 文档列表变了；库列表的 document_count 也变了 → 两个 key 都要失效
            queryClient.invalidateQueries({ queryKey: ["kb-documents"] })
            queryClient.invalidateQueries({ queryKey: ["knowledge-base"] })
        },
    })

    const deleteDoc = useMutation({
        mutationFn: (docId: string) =>
            KnowledgeBaseService.deleteKbDocument({ kbId, docId }),
        onSuccess: () => {
            showSuccessToast("文档已删除")
        },
        onError: handleError.bind(showErrorToast),
        onSettled: () => {
            // 文档列表变了；库列表的 document_count 也变了 → 两个 key 都要失效
            queryClient.invalidateQueries({ queryKey: ["kb-documents"] })
            queryClient.invalidateQueries({ queryKey: ["knowledge-base"] })
        },
    })

    const queryKb = useMutation({
        mutationFn: (query: string) =>
            KnowledgeBaseService.queryKb({ kbId, requestBody: { query } }),
        onError: handleError.bind(showErrorToast),
    })

    return { kbQuery, docsQuery, uploadDoc, deleteDoc, queryKb }
}

export default useKnowledgeBase
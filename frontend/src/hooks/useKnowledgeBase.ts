import {
    type Body_knowledge_base_upload_kb_document,
    type KBCreate,
    KnowledgeBaseService,
} from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"


/**
 * 知识库管理的统一数据 hook。
 *
 * - kbListQuery: 知识库列表（缓存 key "knowledge-base"）
 * - createKb / deleteKb: 知识库的增删
 * - uploadDoc / deleteDoc: 知识库内的文档上传与删除（key "kb-documents"）
 * - queryKb: 检索测试（查询型写操作，结果由调用方保存）
 *
 * 职责边界：这里只负责「调接口 + 管缓存」，不做任何界面渲染。
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
        onError: handleError.bind(showErrorToast), onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["knowledge-base"] })
        },
    })

const uploadDoc = useMutation({
    mutationFn: ({kbId, file}: {kbId: string, file: File}) => {
        const fd = new FormData()
        fd.append("file", file)
        return KnowledgeBaseService.uploadKbDocument({
            kbId,
            formData: fd as unknown as Body_knowledge_base_upload_kb_document,
        })
    },
    onSuccess: () => {
        showSuccessToast("文档已上传，正在解析入库")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
        queryClient.invalidateQueries({queryKey: ["kb-documents"]})
    }
})

const deleteDoc = useMutation({
    // 注意：后端目前没有「删除文档」端点（只有上传/列表），
    // 此 mutation 暂留占位，待后端补 DELETE /kb/{kb_id}/documents/{doc_id} 后启用
    mutationFn: async () => {
        throw new Error("删除文档端点尚未实现")
    },
    onError: handleError.bind(showErrorToast),
})



const queryKb = useMutation({
    mutationFn: ({kbId, query}: {kbId: string; query:string}) =>
        KnowledgeBaseService.queryKb({kbId, requestBody: {query}}),
    onError: handleError.bind(showErrorToast)
})

return { kbListQuery, createKb, deleteKb, uploadDoc, deleteDoc, queryKb }


}

export default useKnowledgeBase
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { AgentService, type Body_agent_install_skill } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

/**
 * Skill 管理的数据 hook（Phase 15.2b）。
 *
 * Skill 以服务器 `skills/` 目录为存储（SKILL.md 描述文件），
 * install/delete 后端会自动重扫，前端只需失效列表缓存。
 */
const useSkills = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const skillsQuery = useQuery({
    queryKey: ["skills"],
    queryFn: () => AgentService.listSkills(),
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["skills"] })

  const installSkill = useMutation({
    mutationFn: (file: File) =>
      AgentService.installSkill({
        formData: { skill_zip: file } as unknown as Body_agent_install_skill,
      }),
    onSuccess: (res) => {
      showSuccessToast(
        typeof res.name === "string"
          ? `技能「${res.name}」已安装`
          : "技能已安装",
      )
    },
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  const deleteSkill = useMutation({
    mutationFn: (skillName: string) => AgentService.deleteSkill({ skillName }),
    onSuccess: () => {
      showSuccessToast("技能已删除")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  const scanSkills = useMutation({
    mutationFn: () => AgentService.scanSkills(),
    onSuccess: (res) => {
      showSuccessToast(
        typeof res.count === "number"
          ? `扫描完成，共 ${res.count} 个技能`
          : "扫描完成",
      )
    },
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  return { skillsQuery, installSkill, deleteSkill, scanSkills }
}

export default useSkills

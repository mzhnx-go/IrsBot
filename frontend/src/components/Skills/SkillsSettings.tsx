import { useQuery } from "@tanstack/react-query"
import { FileArchive, RefreshCw, Trash2, Upload, Zap } from "lucide-react"
import { useRef, useState } from "react"
import { AgentService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import useSkills from "@/hooks/useSkills"

/** 列表接口返回 dict 数组，这里收窄为已知字段 */
interface SkillSummary {
  name?: unknown
  description?: unknown
  trigger?: unknown
}
const str = (v: unknown): string => (typeof v === "string" ? v : "")

const SkillDetailDialog = ({
  skillName,
  open,
  onOpenChange,
}: {
  skillName: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) => {
  const detailQuery = useQuery({
    queryKey: ["skill-detail", skillName],
    queryFn: () => AgentService.getSkillDetail({ skillName: skillName ?? "" }),
    enabled: open && !!skillName,
  })

  const detail = detailQuery.data as Record<string, unknown> | undefined

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-mono">{skillName}</DialogTitle>
          <DialogDescription>{str(detail?.description)}</DialogDescription>
        </DialogHeader>
        {detailQuery.isPending ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            加载中…
          </p>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto rounded-lg border bg-muted/30 p-4">
            <pre className="font-mono text-xs leading-6 whitespace-pre-wrap">
              {str(detail?.instructions) || "（无指令内容）"}
            </pre>
          </div>
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">关闭</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const SkillRow = ({
  name,
  description,
  trigger,
  onView,
}: {
  name: string
  description: string
  trigger: string
  onView: () => void
}) => {
  const { deleteSkill } = useSkills()
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border p-4">
      <button type="button" onClick={onView} className="min-w-0 text-left">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono font-medium">{name}</span>
          {trigger && (
            <Badge variant="secondary" className="gap-1">
              <Zap className="size-2.5" />
              {trigger}
            </Badge>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
          {description || "（无描述）"}
        </p>
      </button>
      <div className="flex shrink-0 items-center gap-2">
        <Button variant="outline" size="sm" onClick={onView}>
          详情
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-label="删除技能"
          className="text-destructive"
          onClick={() => setConfirmOpen(true)}
        >
          <Trash2 />
        </Button>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>删除技能</DialogTitle>
            <DialogDescription>
              确定删除「{name}」吗？将移除服务器上该技能的整个目录，不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <DialogClose asChild>
              <Button variant="outline">取消</Button>
            </DialogClose>
            <Button
              variant="destructive"
              onClick={() => {
                deleteSkill.mutate(name)
                setConfirmOpen(false)
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

const SkillsSettings = () => {
  const { skillsQuery, installSkill, scanSkills } = useSkills()
  const fileRef = useRef<HTMLInputElement>(null)
  const [detailName, setDetailName] = useState<string | null>(null)

  if (skillsQuery.isPending) {
    return null
  }

  const skills = (skillsQuery.data ?? []) as SkillSummary[]

  const handleFile = (file: File | undefined) => {
    if (!file) return
    installSkill.mutate(file)
    // 允许连续上传同一文件
    if (fileRef.current) fileRef.current.value = ""
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">技能</h2>
          <p className="text-sm text-muted-foreground">
            Skill 是以 SKILL.md 描述的指令包，安装后 AI
            在对话中按触发条件自动遵循。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => scanSkills.mutate()}
            disabled={scanSkills.isPending}
          >
            <RefreshCw
              className={`mr-2 ${scanSkills.isPending ? "animate-spin motion-reduce:animate-none" : ""}`}
            />
            重新扫描
          </Button>
          <Button
            onClick={() => fileRef.current?.click()}
            disabled={installSkill.isPending}
          >
            <Upload className="mr-2" />
            {installSkill.isPending ? "上传中…" : "上传技能 (ZIP)"}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
        </div>
      </div>

      {installSkill.isError && (
        <p className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <FileArchive className="size-4 shrink-0" />
          安装失败：ZIP 需包含合法的 SKILL.md，且通过安全检查。
        </p>
      )}

      {skills.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          还没有已安装的技能。准备一个含 SKILL.md 的 ZIP
          包，点击「上传技能」安装。
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {skills.map((s, i) => (
            <SkillRow
              key={str(s.name) || i}
              name={str(s.name)}
              description={str(s.description)}
              trigger={str(s.trigger)}
              onView={() => setDetailName(str(s.name))}
            />
          ))}
        </div>
      )}

      <SkillDetailDialog
        skillName={detailName}
        open={detailName !== null}
        onOpenChange={(open) => !open && setDetailName(null)}
      />
    </div>
  )
}

export default SkillsSettings

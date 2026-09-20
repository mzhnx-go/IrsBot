import { useNavigate } from "@tanstack/react-router"
import { KeyRound } from "lucide-react"

import { Button } from "@/components/ui/button"
import useProviders from "@/hooks/useProviders"

/**
 * 聊天空状态引导（配置闭环 15.2g）。
 *
 * 模型源按用户归属：新用户进来一个 Key 都没有，直接发消息只会得到
 * 后端报错。与其让他撞墙，不如在**第一次进入聊天**的空状态里把路
 * 指出来。providersQuery 与模型源页共用缓存 key（"providers"），
 * 配置完成回到本页会自动重新取数、引导卡自动消失。
 */
const ChatOnboarding = () => {
  const { providersQuery } = useProviders()
  const navigate = useNavigate()

  // 加载中 / 读失败 / 已有可用模型源 → 不引导（失败时保持普通空状态，不添乱）
  if (providersQuery.isPending || providersQuery.isError) return null
  const usable = (providersQuery.data ?? []).some((p) => p.is_active)
  if (usable) return null

  return (
    <div className="mx-auto max-w-md rounded-xl border bg-card p-6 text-left shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
          <KeyRound className="size-5" />
        </div>
        <h2 className="text-base font-semibold">先配置一个模型源</h2>
      </div>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">
        对话需要一套模型 API 配置（API Key 加密存储，仅你可见）。
      </p>
      <ol className="mt-1 flex list-decimal flex-col gap-1.5 pl-5 text-sm text-muted-foreground marker:font-medium marker:text-foreground">
        <li>填写名称、类型与 API Key，保存为默认模型源</li>
        <li>回到这里，直接开始第一轮对话</li>
      </ol>
      <Button
        className="mt-5 w-full"
        onClick={() => navigate({ to: "/providers", search: { new: 1 } })}
        data-testid="onboarding-go-providers"
      >
        去配置模型源
      </Button>
    </div>
  )
}

export default ChatOnboarding

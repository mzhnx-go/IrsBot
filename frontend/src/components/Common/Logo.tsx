import { Link } from "@tanstack/react-router"

import { cn } from "@/lib/utils"

/**
 * IrsBot 品牌标记：圆角蓝底 + 机器人头像剪影（纯内联 SVG）。
 * 替换模板自带的 FastAPI logo，无需图片资源、随主题清晰缩放。
 */
export function IrsBotMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="IrsBot"
    >
      <rect width="40" height="40" rx="10" fill="#165DFF" />
      <line
        x1="20"
        y1="8.5"
        x2="20"
        y2="12"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="20" cy="6.8" r="1.8" fill="white" />
      <rect x="9" y="12" width="22" height="17" rx="5.5" fill="white" />
      <circle cx="16" cy="20" r="2.2" fill="#165DFF" />
      <circle cx="24" cy="20" r="2.2" fill="#165DFF" />
      <rect x="16" y="24" width="8" height="2" rx="1" fill="#165DFF" />
      <rect x="5.6" y="17.5" width="2.6" height="6" rx="1.3" fill="white" />
      <rect x="31.8" y="17.5" width="2.6" height="6" rx="1.3" fill="white" />
    </svg>
  )
}

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const content =
    variant === "responsive" ? (
      <>
        {/* 展开态：标记 + 字标；收起成图标条时只留标记 */}
        <span
          className={cn(
            "flex items-center gap-2 group-data-[collapsible=icon]:hidden",
            className,
          )}
        >
          <IrsBotMark className="size-7 shrink-0" />
          <span className="text-lg font-bold tracking-tight">IrsBot</span>
        </span>
        <IrsBotMark className="hidden size-6 group-data-[collapsible=icon]:block" />
      </>
    ) : variant === "full" ? (
      <span className={cn("flex items-center gap-2.5", className)}>
        <IrsBotMark className="size-9 shrink-0" />
        <span className="text-2xl font-bold tracking-tight">IrsBot</span>
      </span>
    ) : (
      <IrsBotMark className={cn("size-6", className)} />
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}

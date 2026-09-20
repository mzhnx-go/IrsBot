import { Check, Copy } from "lucide-react"
import { type ReactNode, useState } from "react"
import ReactMarkdown from "react-markdown"
import rehypeHighlight from "rehype-highlight"
import remarkGfm from "remark-gfm"

import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"

// hast 节点 → 纯文本。rehype-highlight 会把 code 的 children 变成
// 一组 span 元素，所以不能只取一层 .value，必须递归收集。
interface HastNode {
  value?: string
  children?: HastNode[]
  properties?: { className?: string[] }
}
const textOf = (n: HastNode | undefined): string =>
  n?.value ?? n?.children?.map(textOf).join("") ?? ""

const CodeBlock = ({
  language,
  rawCode,
  children,
}: {
  language: string
  rawCode: string
  children: ReactNode
}) => {
  const [, copy] = useCopyToClipboard()
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    copy(rawCode)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="group/code relative my-3 overflow-hidden rounded-lg border border-border/60">
      <div className="flex items-center justify-between border-b border-border/40 bg-muted/60 px-3 py-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {language || "text"}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          aria-label="复制代码"
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors duration-100 hover:text-foreground active:scale-95"
        >
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre className="overflow-x-auto bg-muted/30 p-3 text-[13px] leading-6 dark:bg-[#0d1117]/60">
        <code>{children}</code>
      </pre>
    </div>
  )
}

// 围栏代码块：children 是已高亮的 span 树，hast node 用于取语言与原文
const FencedPre = ({
  node,
  children,
}: {
  node?: unknown
  children?: ReactNode
}) => {
  const codeNode = (node as HastNode | undefined)?.children?.[0]
  const language =
    codeNode?.properties?.className
      ?.find((c) => c.startsWith("language-"))
      ?.slice(9) ?? ""
  return (
    <CodeBlock language={language} rawCode={textOf(codeNode)}>
      {children}
    </CodeBlock>
  )
}

const MarkdownContent = ({
  content,
  streaming,
}: {
  content: string
  streaming?: boolean
}) => {
  return (
    <div className="chat-markdown text-sm leading-7">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          [rehypeHighlight, { detect: true, ignoreMissing: true }],
        ]}
        components={{
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="text-[var(--chat-accent)] underline underline-offset-2"
            >
              {children}
            </a>
          ),
          p: ({ children }) => (
            <p className="my-2 first:mt-0 last:mb-0">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>
          ),
          h1: ({ children }) => (
            <h1 className="mb-2 mt-4 text-xl font-bold tracking-tight first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-lg font-bold tracking-tight first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-1.5 mt-3 text-base font-semibold first:mt-0">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="mb-1 mt-3 text-sm font-semibold first:mt-0">
              {children}
            </h4>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-[var(--chat-accent)]/50 pl-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-4 border-border" />,
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-border">
              <table className="w-full border-collapse text-[13px]">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-muted/60">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="border-b border-border px-3 py-1.5 text-left font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border/50 px-3 py-1.5 align-top">
              {children}
            </td>
          ),
          pre: FencedPre,
          code: ({ children, className }) => {
            // 围栏代码块由 pre 渲染成 CodeBlock；命中这里的多为行内代码
            if (
              className?.includes("language-") ||
              className?.includes("hljs")
            ) {
              return <>{children}</>
            }
            return (
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12.5px] text-foreground">
                {children}
              </code>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
      {streaming && (
        <span
          aria-hidden
          className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse rounded-full bg-foreground/70"
        />
      )}
    </div>
  )
}

export default MarkdownContent

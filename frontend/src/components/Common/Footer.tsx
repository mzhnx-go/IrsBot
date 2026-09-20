export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="border-t py-4 px-6">
      <div className="flex items-center justify-center">
        <p className="text-muted-foreground text-sm">
          IrsBot · 本地优先的 Agent 平台 - {currentYear}
        </p>
      </div>
    </footer>
  )
}

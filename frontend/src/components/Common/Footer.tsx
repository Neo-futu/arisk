export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="border-t py-3 px-6">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-xs">
          ARISK — Agent for Risk &amp; Investment Analysis System &copy; {currentYear}
        </p>
        <p className="text-muted-foreground text-xs">
          阿雷斯 · 智能風控和投資分析系統
        </p>
      </div>
    </footer>
  )
}

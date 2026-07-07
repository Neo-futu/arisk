import { createFileRoute } from "@tanstack/react-router"
import { Download, FileSpreadsheet, FileText } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export const Route = createFileRoute("/_layout/reports")({
  component: ReportsPage,
  head: () => ({ meta: [{ title: "報表中心 — ARISK" }] }),
})

const FUNDS = [
  { id: "BHMMF001", name: "博匯港元貨幣市場基金 I" },
  { id: "BHMMF002", name: "博匯港元貨幣市場基金 II" },
]

type ReportDef = {
  id: string
  name: string
  description: string
  type: "xlsx" | "docx" | "pdf"
  frequency: "daily" | "monthly"
  endpoint: string
}

const REPORTS: ReportDef[] = [
  {
    id: "report_03_mmf",
    name: "MMF 日報（SFC 合規版）",
    description: "涵蓋 WAM/WAL、流動性、集中度、壓力測試，SFC 第 8.2 章完整核查",
    type: "xlsx",
    frequency: "daily",
    endpoint: "/tools/mmf/run_report.py",
  },
  {
    id: "report_04_mmf_monthly",
    name: "MMF 月報 Factsheet",
    description: "基金業績、資產配置、到期分佈，含 PDF + Word 版本",
    type: "pdf",
    frequency: "monthly",
    endpoint: "/tools/mmf/report_04/run_monthly.py",
  },
  {
    id: "report_06",
    name: "基金詳細分析報告",
    description: "特定基金深度分析：偏離度、信用敞口、發行人集中度",
    type: "xlsx",
    frequency: "daily",
    endpoint: "/tools/mmf/run_report.py?report=report_06",
  },
]

const TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  xlsx: FileSpreadsheet,
  docx: FileText,
  pdf: FileText,
}

const TYPE_COLORS: Record<string, string> = {
  xlsx: "text-green-600",
  docx: "text-blue-600",
  pdf: "text-red-600",
}

function ReportCard({ report, fundId, asOfDate }: { report: ReportDef; fundId: string; asOfDate: string }) {
  const [isGenerating, setIsGenerating] = useState(false)
  const Icon = TYPE_ICONS[report.type] ?? FileText

  const handleGenerate = async () => {
    setIsGenerating(true)
    // 實際調用後端生成接口（目前為 stub）
    await new Promise((resolve) => setTimeout(resolve, 1500))
    setIsGenerating(false)
    alert(`報表生成任務已提交：${report.name}\n基金：${fundId}\n日期：${asOfDate}\n\n（功能開發中，實際輸出請執行 python ${report.endpoint}）`)
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between">
        <div className="flex items-start gap-3">
          <Icon className={`h-6 w-6 mt-1 ${TYPE_COLORS[report.type] ?? ""}`} />
          <div>
            <CardTitle className="text-base">{report.name}</CardTitle>
            <CardDescription className="mt-1">{report.description}</CardDescription>
          </div>
        </div>
        <div className="flex flex-col gap-1 items-end shrink-0">
          <Badge variant="outline" className="text-xs uppercase">
            {report.type}
          </Badge>
          <Badge variant="secondary" className="text-xs">
            {report.frequency === "daily" ? "每日" : "每月"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground font-mono">
            {report.endpoint}
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={handleGenerate}
            disabled={isGenerating}
            className="gap-2"
          >
            <Download className="h-3.5 w-3.5" />
            {isGenerating ? "生成中..." : "生成報表"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function ReportsPage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 1)
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1)
    return d.toISOString().split("T")[0]
  })

  const daily = REPORTS.filter((r) => r.frequency === "daily")
  const monthly = REPORTS.filter((r) => r.frequency === "monthly")

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">報表中心</h1>
        <p className="text-muted-foreground text-sm">
          生成 MMF 日報、月報 Factsheet 及詳細分析報告
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select value={fundId} onValueChange={setFundId}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FUNDS.map((f) => (
              <SelectItem key={f.id} value={f.id}>
                {f.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Badge variant="outline" className="h-10 px-3 text-sm">
          {asOfDate}
        </Badge>
      </div>

      <div className="space-y-4">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          每日報表
        </h2>
        {daily.map((r) => (
          <ReportCard key={r.id} report={r} fundId={fundId} asOfDate={asOfDate} />
        ))}
      </div>

      <div className="space-y-4">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          月度報表
        </h2>
        {monthly.map((r) => (
          <ReportCard key={r.id} report={r} fundId={fundId} asOfDate={asOfDate} />
        ))}
      </div>
    </div>
  )
}

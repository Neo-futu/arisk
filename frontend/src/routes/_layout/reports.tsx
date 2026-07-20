import { useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  RefreshCw,
} from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Progress } from "@/components/ui/progress"
import { fsiApi, type ReportTask } from "@/fsiClient"

export const Route = createFileRoute("/_layout/reports")({
  component: ReportsPage,
  head: () => ({ meta: [{ title: "報表中心 — ARISK" }] }),
})

// ── 報表定義 ──────────────────────────────────────────────────────
type ReportDef = {
  id: string
  name: string
  description: string
  type: "xlsx" | "docx" | "pdf"
  frequency: "daily" | "monthly"
  dateHint?: string      // 日期選擇提示
  useFund?: boolean      // 是否將選擇的基金傳給腳本
}

const REPORT_DEFS: ReportDef[] = [
  {
    id: "report_03_mmf",
    name: "MMF 日報（SFC 合規版）",
    description: "WAM/WAL、流動性、集中度、壓力測試，SFC 第 8.2 章完整核查",
    type: "xlsx",
    frequency: "daily",
    useFund: true,
  },
  {
    id: "report_04_mmf_monthly",
    name: "MMF 月報 Factsheet",
    description: "基金業績、資產配置、到期分佈，輸出 Word（.docx）或 Excel",
    type: "docx",
    frequency: "monthly",
    dateHint: "請選擇月末估值日期（如 2026-06-25）",
    useFund: true,
  },
  {
    id: "report_06",
    name: "基金詳細分析報告",
    description: "偏離度、信用敞口、發行人集中度深度分析",
    type: "xlsx",
    frequency: "daily",
  },
]

const TYPE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  xlsx: FileSpreadsheet,
  docx: FileText,
  pdf: FileText,
}
const TYPE_COLOR: Record<string, string> = {
  xlsx: "text-green-600",
  docx: "text-blue-600",
  pdf: "text-red-600",
}

const REPORT_FILTERS_STORAGE_KEY = "fsi.reports.filters.v1"

function getInitialReportFilters() {
  if (typeof window === "undefined") {
    return { fundId: FUNDS[0].id, asOfDate: lastTradeDate() }
  }
  try {
    const raw = window.localStorage.getItem(REPORT_FILTERS_STORAGE_KEY)
    if (!raw) return { fundId: FUNDS[0].id, asOfDate: lastTradeDate() }
    const parsed = JSON.parse(raw) as Partial<{ fundId: string; asOfDate: string }>
    const hasFund = !!parsed.fundId && FUNDS.some((f) => f.id === parsed.fundId)
    const hasDate = typeof parsed.asOfDate === "string" && parsed.asOfDate.length > 0
    return {
      fundId: hasFund ? parsed.fundId! : FUNDS[0].id,
      asOfDate: hasDate ? parsed.asOfDate! : lastTradeDate(),
    }
  } catch {
    return { fundId: FUNDS[0].id, asOfDate: lastTradeDate() }
  }
}

function StatusBadge({ status }: { status: ReportTask["status"] }) {
  const map = {
    queued:    { label: "排隊中", cls: "bg-muted text-muted-foreground" },
    running:   { label: "生成中", cls: "bg-blue-100 text-blue-700" },
    completed: { label: "已完成", cls: "bg-green-100 text-green-700" },
    failed:    { label: "失敗",   cls: "bg-red-100 text-red-700" },
  }
  const { label, cls } = map[status] ?? map.queued
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  )
}

// ── 確認對話框（使用已有 Dialog，無多實例問題） ───────────────────
function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  title: string
  description: string
  onConfirm: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={() => { onOpenChange(false); onConfirm() }}>
            重新生成
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 單個報表卡片 ──────────────────────────────────────────────────
function ReportCard({
  def,
  fundId,
  asOfDate,
}: {
  def: ReportDef
  fundId: string
  asOfDate: string
}) {
  const [task, setTask] = useState<ReportTask | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const queryClient = useQueryClient()
  const Icon = TYPE_ICON[def.type] ?? FileText

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  const startPoll = useCallback((taskId: string) => {
    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const res = await fsiApi.getReportTask(taskId)
        setTask(res.data)
        if (res.data.status === "completed" || res.data.status === "failed") {
          stopPoll()
          queryClient.invalidateQueries({
            queryKey: ["report-result", def.id, fundId, asOfDate],
          })
        }
      } catch { stopPoll() }
    }, 1500)
  }, [queryClient, def.id, fundId, asOfDate])

  useEffect(() => () => stopPoll(), [])

  // 頁面刷新後自動恢復：查詢 artefacts/ 是否有已生成文件
  const { data: existingResult } = useQuery({
    queryKey: ["report-result", def.id, fundId, asOfDate],
    queryFn: () => fsiApi.getReportResult(def.id, fundId, asOfDate).then(r => r.data),
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.found ? false : 2000
    },
  })

  useEffect(() => {
    if (existingResult?.found && existingResult.output_files.length > 0 && !task) {
      setTask({
        task_id:      "cached",
        report_id:    def.id,
        fund_id:      fundId,
        as_of_date:   asOfDate,
        status:       "completed",
        progress:     100,
        message:      `已有 ${existingResult.output_files.length} 個文件（頁面刷新恢復）`,
        output_file:  existingResult.output_files[0] ?? null,
        output_files: existingResult.output_files,
        created_at:   "",
        finished_at:  "",
      })
    }
  }, [existingResult])

  useEffect(() => { setTask(null); stopPoll() }, [fundId, asOfDate])

  const doGenerate = async () => {
    setTask({
      task_id: "", report_id: def.id, fund_id: fundId, as_of_date: asOfDate,
      status: "queued", progress: 0, message: "提交中...",
      output_file: null, created_at: new Date().toISOString(), finished_at: null,
    })
    try {
      const res = await fsiApi.generateReport(def.id, fundId, asOfDate)
      setTask(res.data)
      startPoll(res.data.task_id)
    } catch (e: any) {
      setTask(prev => prev && ({
        ...prev,
        status: "failed",
        progress: 0,
        message: e?.response?.data?.detail ?? e?.message ?? "請求失敗",
        finished_at: new Date().toISOString(),
      }))
    }
  }

  const handleGenerate = () => {
    if (task && (task.status === "completed" || task.status === "failed")) {
      setConfirmOpen(true)
    } else {
      doGenerate()
    }
  }

  const [downloadingFile, setDownloadingFile] = useState<string | null>(null)

  const handleDownload = async (filename: string) => {
    setDownloadingFile(filename)
    try { await fsiApi.downloadReport(def.id, filename) }
    finally { setDownloadingFile(null) }
  }

  const isRunning = task?.status === "queued" || task?.status === "running"
  const completedFiles = existingResult?.found
    ? existingResult.output_files
    : task?.status === "completed"
      ? (task.output_files ?? (task.output_file ? [task.output_file] : []))
      : []

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between pb-3">
          <div className="flex items-start gap-3">
            <Icon className={`h-6 w-6 mt-0.5 shrink-0 ${TYPE_COLOR[def.type] ?? ""}`} />
            <div>
              <CardTitle className="text-base">{def.name}</CardTitle>
              <CardDescription className="mt-1 text-xs">{def.description}</CardDescription>
              {def.dateHint && (
                <p className="mt-1 text-xs text-yellow-600 dark:text-yellow-400">
                  ⚠ {def.dateHint}
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <Badge variant="outline" className="text-xs uppercase">{def.type}</Badge>
            <Badge variant="secondary" className="text-xs">
              {def.frequency === "daily" ? "每日" : "每月"}
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {/* 進度區 */}
          {task && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5 min-w-0">
                  {isRunning
                    ? <Loader2 className="h-3 w-3 animate-spin text-blue-600 shrink-0" />
                    : task.status === "completed"
                      ? <CheckCircle2 className="h-3 w-3 text-green-600 shrink-0" />
                      : <AlertTriangle className="h-3 w-3 text-destructive shrink-0" />}
                  <span className="text-muted-foreground truncate">{task.message}</span>
                </div>
                <StatusBadge status={task.status} />
              </div>
              <Progress value={task.progress} className="h-1.5" />
            </div>
          )}

          {/* 按鈕行 */}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={task?.status === "completed" ? "outline" : "default"}
              onClick={handleGenerate}
              disabled={isRunning}
              className="gap-1.5"
            >
              {isRunning
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
              {isRunning ? "生成中..." : task?.status === "completed" ? "重新生成" : "生成報表"}
            </Button>

            {completedFiles.map(filename => {
              const ext = filename.split(".").pop()?.toUpperCase() ?? ""
              const extColor = ext === "XLSX" ? "text-green-700" : ext === "DOCX" ? "text-blue-700" : "text-red-700"
              return (
                <Button
                  key={filename}
                  size="sm"
                  onClick={() => handleDownload(filename)}
                  disabled={downloadingFile === filename}
                  className="gap-1.5"
                  title={filename}
                >
                  {downloadingFile === filename
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    : <Download className="h-3.5 w-3.5" />}
                  <span className={extColor}>{ext}</span>
                </Button>
              )
            })}

          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="重新生成報表？"
        description={`已存在 ${def.name}（${asOfDate}）的生成結果，重新生成將覆蓋現有文件。`}
        onConfirm={doGenerate}
      />
    </>
  )
}

// ── 主頁面 ────────────────────────────────────────────────────────
function ReportsPage() {
  const [fundId, setFundId] = useState(() => getInitialReportFilters().fundId)
  const [asOfDate, setAsOfDate] = useState(() => getInitialReportFilters().asOfDate)

  useEffect(() => {
    window.localStorage.setItem(
      REPORT_FILTERS_STORAGE_KEY,
      JSON.stringify({ fundId, asOfDate }),
    )
  }, [fundId, asOfDate])

  const daily   = REPORT_DEFS.filter((r) => r.frequency === "daily")
  const monthly = REPORT_DEFS.filter((r) => r.frequency === "monthly")

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">報表中心</h1>
        <p className="text-muted-foreground text-sm">
          生成 MMF 日報、月報 Factsheet 及詳細分析報告
        </p>
      </div>

      <FsiToolbar
        fundId={fundId} onFundChange={setFundId}
        asOfDate={asOfDate} onDateChange={setAsOfDate}
        onRefresh={() => {}}
      />

      <div className="space-y-3">
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          每日報表
        </h2>
        {daily.map((r) => (
          <ReportCard key={r.id} def={r} fundId={fundId} asOfDate={asOfDate} />
        ))}
      </div>

      <div className="space-y-3">
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          月度報表
        </h2>
        {monthly.map((r) => (
          <ReportCard key={r.id} def={r} fundId={fundId} asOfDate={asOfDate} />
        ))}
      </div>
    </div>
  )
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  CheckCircle2,
  Clock,
  Download,
  FileText,
  History,
  Loader2,
  Play,
  Plus,
  Trash2,
  XCircle,
} from "lucide-react"
import { useState } from "react"

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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi, type Schedule, type ScheduleHistory, type ScheduleFile } from "@/fsiClient"

export const Route = createFileRoute("/_layout/schedules")({
  component: SchedulesPage,
  head: () => ({ meta: [{ title: "定時報表 — ARISK" }] }),
})

// ── 常量 ─────────────────────────────────────────────────────────
const REPORT_OPTIONS = [
  { value: "report_03_mmf",        label: "MMF 日報（SFC 合規版）" },
  { value: "report_04_mmf_monthly", label: "MMF 月報 Factsheet" },
  { value: "report_06",             label: "基金詳細分析報告" },
]

const FUND_OPTIONS = [
  { value: "BHMMF001", label: "博匯港元貨幣市場基金 I" },
  { value: "BHMMF002", label: "博匯港元貨幣市場基金 II" },
]

const HOURS   = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]

function fmtTime(h: number, m: number) {
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`
}

function fmtDate(iso: string | null) {
  if (!iso) return "—"
  return iso.replace("T", " ").slice(0, 16)
}

// ── 新建/編輯對話框 ───────────────────────────────────────────────
interface FormState {
  name: string; report_id: string; fund_id: string; hour: number; minute: number; enabled: boolean
}

function ScheduleDialog({
  open,
  onOpenChange,
  initial,
  onSave,
  isSaving,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  initial?: Partial<FormState>
  onSave: (data: FormState) => void
  isSaving: boolean
}) {
  const [form, setForm] = useState<FormState>({
    name:      initial?.name      ?? "",
    report_id: initial?.report_id ?? "report_03_mmf",
    fund_id:   initial?.fund_id   ?? "BHMMF001",
    hour:      initial?.hour      ?? 8,
    minute:    initial?.minute    ?? 0,
    enabled:   initial?.enabled   ?? true,
  })

  const set = (k: keyof FormState, v: any) => setForm(f => ({ ...f, [k]: v }))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{initial?.name ? "編輯定時任務" : "新建定時任務"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* 任務名稱 */}
          <div className="space-y-1">
            <label className="text-sm font-medium">任務名稱</label>
            <input
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={form.name}
              onChange={e => set("name", e.target.value)}
              placeholder="例：每日 MMF 日報 BHMMF001"
            />
          </div>

          {/* 報表類型 */}
          <div className="space-y-1">
            <label className="text-sm font-medium">報表類型</label>
            <select
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={form.report_id}
              onChange={e => set("report_id", e.target.value)}
            >
              {REPORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          {/* 基金選擇 */}
          <div className="space-y-1">
            <label className="text-sm font-medium">基金</label>
            <select
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={form.fund_id}
              onChange={e => set("fund_id", e.target.value)}
            >
              {FUND_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          {/* 定時時間 */}
          <div className="space-y-1">
            <label className="text-sm font-medium">每日執行時間</label>
            <div className="flex items-center gap-2">
              <select
                className="h-9 w-24 rounded-md border border-input bg-background px-2 text-sm"
                value={form.hour}
                onChange={e => set("hour", Number(e.target.value))}
              >
                {HOURS.map(h => <option key={h} value={h}>{String(h).padStart(2,"0")} 時</option>)}
              </select>
              <span className="text-muted-foreground">:</span>
              <select
                className="h-9 w-24 rounded-md border border-input bg-background px-2 text-sm"
                value={form.minute}
                onChange={e => set("minute", Number(e.target.value))}
              >
                {MINUTES.map(m => <option key={m} value={m}>{String(m).padStart(2,"0")} 分</option>)}
              </select>
              <span className="text-xs text-muted-foreground ml-1">
                → 每天 {fmtTime(form.hour, form.minute)} 自動生成
              </span>
            </div>
          </div>

          {/* 啟用開關 */}
          <div className="flex items-center gap-3">
            <Switch checked={form.enabled} onCheckedChange={v => set("enabled", v)} />
            <span className="text-sm">{form.enabled ? "啟用" : "停用"}</span>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={() => onSave(form)} disabled={isSaving || !form.name.trim()}>
            {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 歷史與文件面板 ────────────────────────────────────────────────
function ScheduleDetail({ schedule }: { schedule: Schedule }) {
  const qc = useQueryClient()

  const { data: history } = useQuery({
    queryKey: ["schedule-history", schedule.schedule_id],
    queryFn: () => fsiApi.getScheduleHistory(schedule.schedule_id).then(r => r.data),
    refetchInterval: 5000,
  })

  const { data: files } = useQuery({
    queryKey: ["schedule-files", schedule.schedule_id],
    queryFn: () => fsiApi.getScheduleFiles(schedule.schedule_id).then(r => r.data),
    refetchInterval: 10000,
  })

  const [downloading, setDownloading] = useState<string | null>(null)

  const download = async (filename: string) => {
    setDownloading(filename)
    try { await fsiApi.downloadScheduleFile(schedule.schedule_id, filename) }
    finally { setDownloading(null) }
  }

  return (
    <div className="grid md:grid-cols-2 gap-4 mt-4">
      {/* 歷史記錄 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <History className="h-4 w-4" /> 執行歷史
            <span className="text-xs font-normal text-muted-foreground">（本地時間）</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!history?.length
            ? <p className="text-xs text-muted-foreground">暫無執行記錄</p>
            : (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {history.map(h => (
                  <div key={h.run_id} className="flex items-start gap-2 text-xs border-b pb-2 last:border-0">
                    {h.status === "completed"
                      ? <CheckCircle2 className="h-3.5 w-3.5 text-green-500 mt-0.5 shrink-0" />
                      : <XCircle className="h-3.5 w-3.5 text-destructive mt-0.5 shrink-0" />}
                    <div className="min-w-0">
                      <div className="text-muted-foreground">{fmtDate(h.started_at)}</div>
                      <div className="truncate">{h.message}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
        </CardContent>
      </Card>

      {/* 已生成文件 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <FileText className="h-4 w-4" /> 已生成文件
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!files?.length
            ? <p className="text-xs text-muted-foreground">暫無文件</p>
            : (
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {files.map(f => (
                  <div key={f.filename} className="flex items-center justify-between text-xs">
                    <div className="min-w-0">
                      <div className="truncate font-mono">{f.filename}</div>
                      <div className="text-muted-foreground">{f.size_kb} KB · {fmtDate(f.modified)}</div>
                    </div>
                    <Button
                      size="icon" variant="ghost" className="h-7 w-7 shrink-0"
                      disabled={downloading === f.filename}
                      onClick={() => download(f.filename)}
                    >
                      {downloading === f.filename
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <Download className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                ))}
              </div>
            )}
        </CardContent>
      </Card>
    </div>
  )
}

// ── 主頁面 ────────────────────────────────────────────────────────
function SchedulesPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Schedule | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set())

  const { data: schedules = [], isLoading } = useQuery({
    queryKey: ["schedules"],
    queryFn: () => fsiApi.listSchedules().then(r => r.data),
    refetchInterval: 30000,
  })

  const createMut = useMutation({
    mutationFn: (d: any) => fsiApi.createSchedule(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["schedules"] }); setCreateOpen(false) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => fsiApi.updateSchedule(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["schedules"] }); setEditTarget(null) },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => fsiApi.deleteSchedule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  })

  const toggleEnabled = (sch: Schedule) =>
    fsiApi.updateSchedule(sch.schedule_id, { enabled: !sch.enabled }).then(() =>
      qc.invalidateQueries({ queryKey: ["schedules"] })
    )

  const runNow = async (sch: Schedule) => {
    setRunningIds(s => new Set(s).add(sch.schedule_id))
    try {
      await fsiApi.runScheduleNow(sch.schedule_id)
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["schedule-history", sch.schedule_id] })
        qc.invalidateQueries({ queryKey: ["schedule-files", sch.schedule_id] })
        qc.invalidateQueries({ queryKey: ["schedules"] })
        setRunningIds(s => { const n = new Set(s); n.delete(sch.schedule_id); return n })
      }, 15000)
    } catch {
      setRunningIds(s => { const n = new Set(s); n.delete(sch.schedule_id); return n })
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">定時報表</h1>
          <p className="text-muted-foreground text-sm">
            設置報表自動生成任務，每天指定時間執行，結果存儲於 artefacts/scheduled/
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="gap-1.5">
          <Plus className="h-4 w-4" />新建任務
        </Button>
      </div>

      {/* 任務列表 */}
      {isLoading ? (
        <p className="text-muted-foreground text-sm animate-pulse">載入中...</p>
      ) : schedules.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <Clock className="h-10 w-10 text-muted-foreground" />
            <p className="text-muted-foreground">尚未創建任何定時任務</p>
            <Button size="sm" onClick={() => setCreateOpen(true)}>新建第一個任務</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {schedules.map(sch => (
            <Card key={sch.schedule_id} className={sch.enabled ? "" : "opacity-60"}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-base">{sch.name}</CardTitle>
                      <Badge variant={sch.enabled ? "default" : "outline"} className="text-xs">
                        {sch.enabled ? "啟用" : "停用"}
                      </Badge>
                      {sch.last_status && (
                        <Badge
                          variant={sch.last_status === "completed" ? "outline" : "destructive"}
                          className="text-xs"
                        >
                          上次：{sch.last_status === "completed" ? "成功" : "失敗"}
                        </Badge>
                      )}
                    </div>
                    <CardDescription className="mt-0.5 text-xs">
                      {sch.report_name} · {sch.fund_name} · 每天{" "}
                      <span className="font-mono font-medium text-foreground">
                        {fmtTime(sch.hour, sch.minute)}
                      </span>{" "}
                      執行 · 已執行 {sch.run_count} 次
                      {sch.last_run && ` · 上次：${fmtDate(sch.last_run)}`}
                    </CardDescription>
                  </div>

                  {/* 操作按鈕組 */}
                  <div className="flex items-center gap-2 shrink-0">
                    <Switch
                      checked={sch.enabled}
                      onCheckedChange={() => toggleEnabled(sch)}
                      title={sch.enabled ? "點擊停用" : "點擊啟用"}
                    />
                    <Button
                      size="sm" variant="outline" className="gap-1"
                      onClick={() => runNow(sch)}
                      disabled={runningIds.has(sch.schedule_id)}
                      title="立即執行一次"
                    >
                      {runningIds.has(sch.schedule_id)
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <Play className="h-3.5 w-3.5" />}
                      立即執行
                    </Button>
                    <Button
                      size="sm" variant="ghost" className="gap-1"
                      onClick={() => setEditTarget(sch)}
                    >
                      編輯
                    </Button>
                    <Button
                      size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground"
                      onClick={() => deleteMut.mutate(sch.schedule_id)}
                      title="刪除任務"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="sm" variant="ghost"
                      onClick={() => setExpandedId(expandedId === sch.schedule_id ? null : sch.schedule_id)}
                    >
                      {expandedId === sch.schedule_id ? "收起" : "歷史▾"}
                    </Button>
                  </div>
                </div>
              </CardHeader>

              {expandedId === sch.schedule_id && (
                <CardContent>
                  <ScheduleDetail schedule={sch} />
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* 新建對話框 */}
      <ScheduleDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSave={data => createMut.mutate(data)}
        isSaving={createMut.isPending}
      />

      {/* 編輯對話框 */}
      {editTarget && (
        <ScheduleDialog
          open={!!editTarget}
          onOpenChange={v => !v && setEditTarget(null)}
          initial={editTarget}
          onSave={data => updateMut.mutate({ id: editTarget.schedule_id, data })}
          isSaving={updateMut.isPending}
        />
      )}
    </div>
  )
}

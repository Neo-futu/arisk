import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Download,
  LineChart as LineChartIcon,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi, type IndicatorSeries } from "@/fsiClient"

const PALETTE = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]
const PERIODS = ["1Y", "3Y", "5Y", "10Y", "MAX"] as const
const MAX_COMPARE = 8
const ALL = "__all__"

type Period = (typeof PERIODS)[number]

function numeric(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : Number(value).toLocaleString("en-US", { maximumFractionDigits: digits })
}

function ZoneTitle({ index, title, detail, action }: { index: string; title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-semibold text-primary">
          {index}
        </span>
        <div>
          <CardTitle className="text-base">{title}</CardTitle>
          {detail ? <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p> : null}
        </div>
      </div>
      {action}
    </div>
  )
}

/** Multi-series line chart (dashboard-kit TrendLineChart is single-series only). */
function MultiLineChart({ series }: { series: IndicatorSeries[] }) {
  const { t } = useTranslation()
  const withPoints = series.filter((s) => s.points.length > 0)
  if (!withPoints.length) {
    return <div className="flex h-56 items-center justify-center text-sm text-muted-foreground">{t("indicatorExplorer.noChartData")}</div>
  }

  const allDates = Array.from(new Set(withPoints.flatMap((s) => s.points.map((p) => p.obs_date)))).sort()
  const W = 720
  const H = 260
  const padX = 44
  const padY = 24
  const xOf = (i: number) => padX + (i / Math.max(allDates.length - 1, 1)) * (W - padX * 2)

  // Each series normalised to its own min/max so different units share the frame.
  const lines = withPoints.map((s, si) => {
    const values = s.points.map((p) => Number(p.value))
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    const byDate = new Map(s.points.map((p) => [p.obs_date, Number(p.value)]))
    const path = allDates
      .map((d) => (byDate.has(d) ? { d, v: byDate.get(d)! } : null))
      .filter((x): x is { d: string; v: number } => x !== null)
      .map((pt, idx) => {
        const x = xOf(allDates.indexOf(pt.d))
        const y = padY + (1 - (pt.v - min) / range) * (H - padY * 2)
        return `${idx === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(" ")
    return { color: PALETTE[si % PALETTE.length], path }
  })

  const labelStep = Math.max(1, Math.ceil(allDates.length / 8))

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-64 w-full">
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={padX} y1={padY + f * (H - padY * 2)} x2={W - padX} y2={padY + f * (H - padY * 2)} stroke="currentColor" strokeOpacity="0.12" />
        ))}
        {lines.map((line, i) => (
          <path key={i} d={line.path} fill="none" stroke={line.color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        ))}
      </svg>
      <div className="mt-1 flex justify-between px-10 text-[10px] text-muted-foreground">
        {allDates.filter((_, i) => i % labelStep === 0).map((d) => (
          <span key={d}>{d.slice(0, 7)}</span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-xs">
        {withPoints.map((s, si) => (
          <span key={s.indicator_id} className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: PALETTE[si % PALETTE.length] }} />
            {s.name} <span className="text-muted-foreground">({s.unit})</span>
          </span>
        ))}
      </div>
    </div>
  )
}

export function IndicatorExplorerPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [category, setCategory] = useState<string>(ALL)
  const [country, setCountry] = useState<string>(ALL)
  const [selected, setSelected] = useState<string[]>([])
  const [period, setPeriod] = useState<Period>("3Y")
  const [obsDialog, setObsDialog] = useState<{ open: boolean; indicatorId: string | null }>({ open: false, indicatorId: null })
  const [defDialogOpen, setDefDialogOpen] = useState(false)

  const access = useQuery({
    queryKey: ["my-access-context"],
    queryFn: () => fsiApi.getMyAccessContext().then((r) => r.data),
    staleTime: 30_000,
  })
  const canManage = Boolean(access.data?.is_superuser) || (access.data?.permission_codes ?? []).includes("market_data.manage")

  const catalog = useQuery({
    queryKey: ["indicator-catalog", category, country],
    queryFn: () => fsiApi.getIndicatorCatalog({
      category: category === ALL ? undefined : category,
      country: country === ALL ? undefined : country,
    }).then((r) => r.data),
    retry: 1,
  })

  const indicators = catalog.data?.indicators ?? []

  // Seed a sensible default selection once the catalog first loads.
  useEffect(() => {
    if (!selected.length && indicators.length) {
      setSelected(indicators.slice(0, 2).map((i) => i.indicator_id))
    }
  }, [indicators, selected.length])

  // Drop selections no longer present under the active filters.
  const visibleIds = new Set(indicators.map((i) => i.indicator_id))
  const effectiveSelected = selected.filter((id) => visibleIds.has(id))

  const series = useQuery({
    queryKey: ["indicator-series", effectiveSelected, period],
    queryFn: () => fsiApi.getIndicatorSeries(effectiveSelected, { period }).then((r) => r.data),
    enabled: effectiveSelected.length > 0,
    retry: 1,
  })

  const seriesData = series.data?.series ?? []

  function toggle(id: string) {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= MAX_COMPARE) {
        toast.error(t("indicatorExplorer.maxCompare", { count: MAX_COMPARE }))
        return prev
      }
      return [...prev, id]
    })
  }

  // Pivot: date rows × indicator columns.
  const pivot = useMemo(() => {
    const byDate = new Map<string, Record<string, number>>()
    for (const s of seriesData) {
      for (const p of s.points) {
        const row = byDate.get(p.obs_date) ?? {}
        row[s.indicator_id] = p.value
        byDate.set(p.obs_date, row)
      }
    }
    return Array.from(byDate.entries()).sort((a, b) => b[0].localeCompare(a[0]))
  }, [seriesData])

  async function exportCsv() {
    if (!effectiveSelected.length) return
    try {
      const response = await fsiApi.exportIndicatorSeries(effectiveSelected, { period })
      const blob = new Blob([response.data as unknown as string], { type: "text/csv;charset=utf-8;" })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = `indicators_${effectiveSelected.join("_").slice(0, 60)}.csv`
      link.click()
      window.URL.revokeObjectURL(url)
    } catch {
      toast.error(t("indicatorExplorer.operationFailed"))
    }
  }

  async function deleteObs(indicatorId: string, obsDate: string) {
    if (!window.confirm(t("indicatorExplorer.confirmDelete"))) return
    try {
      await fsiApi.deleteIndicatorObservation(indicatorId, obsDate)
      await queryClient.invalidateQueries({ queryKey: ["indicator-series"] })
      toast.success(t("indicatorExplorer.deleted"))
    } catch {
      toast.error(t("indicatorExplorer.operationFailed"))
    }
  }

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["indicator-series"] })
    await queryClient.invalidateQueries({ queryKey: ["indicator-catalog"] })
  }

  return (
    <div id="quotes" className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge className="gap-1"><LineChartIcon className="h-3.5 w-3.5" />DataJungle</Badge>
            <Badge variant="outline">Module 3.2</Badge>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("indicatorExplorer.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("indicatorExplorer.subtitle")}</p>
        </div>
      </div>

      <div className="space-y-5">
          <Card id="catalog" className="scroll-mt-20 border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
            <CardHeader>
              <ZoneTitle index="01" title={t("indicatorExplorer.parameters")} detail={t("indicatorExplorer.selectHint", { count: effectiveSelected.length, max: MAX_COMPARE })} />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">{t("indicatorExplorer.category")}</Label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger className="h-9 w-36"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>{t("indicatorExplorer.all")}</SelectItem>
                      {(catalog.data?.categories ?? []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{t("indicatorExplorer.country")}</Label>
                  <Select value={country} onValueChange={setCountry}>
                    <SelectTrigger className="h-9 w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>{t("indicatorExplorer.all")}</SelectItem>
                      {(catalog.data?.countries ?? []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{t("indicatorExplorer.period")}</Label>
                  <Select value={period} onValueChange={(v) => setPeriod(v as Period)}>
                    <SelectTrigger className="h-9 w-28"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PERIODS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <Button variant="outline" size="sm" className="mt-5" onClick={() => void series.refetch()} disabled={series.isFetching}>
                  <RefreshCw className={`mr-2 h-4 w-4 ${series.isFetching ? "animate-spin" : ""}`} />{t("indicatorExplorer.refresh")}
                </Button>
                {canManage ? (
                  <Button variant="outline" size="sm" className="mt-5" onClick={() => setDefDialogOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" />{t("indicatorExplorer.newIndicator")}
                  </Button>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                {catalog.isFetching ? <span className="text-sm text-muted-foreground">{t("indicatorExplorer.loading")}</span> : null}
                {indicators.map((ind) => {
                  const active = effectiveSelected.includes(ind.indicator_id)
                  return (
                    <button
                      key={ind.indicator_id}
                      type="button"
                      onClick={() => toggle(ind.indicator_id)}
                      className={`rounded-full border px-3 py-1 text-xs transition ${active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40"}`}
                    >
                      <span className="font-medium">{ind.indicator_name}</span>
                      <span className="ml-1 opacity-60">{ind.country}·{ind.unit}</span>
                    </button>
                  )
                })}
                {!catalog.isFetching && !indicators.length ? <span className="text-sm text-muted-foreground">{t("indicatorExplorer.empty")}</span> : null}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <ZoneTitle
                index="03"
                title={t("indicatorExplorer.chartArea")}
                detail={t("indicatorExplorer.chartHint")}
              />
            </CardHeader>
            <CardContent>
              {series.isError ? <p className="py-10 text-center text-sm text-destructive">{t("indicatorExplorer.operationFailed")}</p> : <MultiLineChart series={seriesData} />}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <ZoneTitle
                index="02"
                title={t("indicatorExplorer.dataArea")}
                detail={t("indicatorExplorer.rowCount", { count: pivot.length })}
                action={<Button size="sm" variant="outline" onClick={exportCsv} disabled={!effectiveSelected.length}><Download className="mr-1 h-4 w-4" />{t("indicatorExplorer.exportCsv")}</Button>}
              />
            </CardHeader>
            <CardContent>
              <div className="max-h-[26rem] overflow-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="sticky left-0 bg-background">{t("indicatorExplorer.date")}</TableHead>
                      {seriesData.map((s) => <TableHead key={s.indicator_id} className="text-right">{s.indicator_id}</TableHead>)}
                      {canManage ? <TableHead className="text-right">{t("indicatorExplorer.actions")}</TableHead> : null}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pivot.map(([obsDate, values]) => (
                      <TableRow key={obsDate}>
                        <TableCell className="sticky left-0 bg-background font-mono text-xs">{obsDate}</TableCell>
                        {seriesData.map((s) => <TableCell key={s.indicator_id} className="text-right font-mono">{numeric(values[s.indicator_id], 4)}</TableCell>)}
                        {canManage ? (
                          <TableCell className="text-right">
                            {seriesData.length === 1 ? (
                              <div className="flex justify-end gap-1">
                                <Button variant="ghost" size="icon" title={t("indicatorExplorer.edit")} onClick={() => setObsDialog({ open: true, indicatorId: seriesData[0].indicator_id })}><Pencil className="h-4 w-4" /></Button>
                                <Button variant="ghost" size="icon" title={t("indicatorExplorer.delete")} onClick={() => deleteObs(seriesData[0].indicator_id, obsDate)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                              </div>
                            ) : <span className="text-xs text-muted-foreground">{t("indicatorExplorer.singleEditHint")}</span>}
                          </TableCell>
                        ) : null}
                      </TableRow>
                    ))}
                    {!pivot.length ? (
                      <TableRow><TableCell colSpan={seriesData.length + 2} className="h-28 text-center text-muted-foreground">{t("indicatorExplorer.selectPrompt")}</TableCell></TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
      </div>
      {obsDialog.open && obsDialog.indicatorId ? (
        <ObservationDialog
          indicatorId={obsDialog.indicatorId}
          onClose={() => setObsDialog({ open: false, indicatorId: null })}
          onSaved={async () => { setObsDialog({ open: false, indicatorId: null }); await invalidate() }}
        />
      ) : null}
      {defDialogOpen ? (
        <IndicatorDefDialog
          onClose={() => setDefDialogOpen(false)}
          onSaved={async () => { setDefDialogOpen(false); await invalidate() }}
        />
      ) : null}
    </div>
  )
}

function FormField({ label, value, onChange, type = "text", required = false, disabled = false }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; required?: boolean; disabled?: boolean
}) {
  return <div className="space-y-1.5"><Label>{label}{required ? " *" : ""}</Label><Input type={type} value={value} onChange={(e) => onChange(e.target.value)} required={required} disabled={disabled} /></div>
}

function ObservationDialog({ indicatorId, onClose, onSaved }: { indicatorId: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [obsDate, setObsDate] = useState(new Date().toISOString().slice(0, 10))
  const [value, setValue] = useState("")

  async function save() {
    if (!obsDate || !value.trim()) { toast.error(t("indicatorExplorer.required")); return }
    setSaving(true)
    try {
      await fsiApi.upsertIndicatorObservation(indicatorId, { obs_date: obsDate, value: Number(value) })
      await onSaved()
      toast.success(t("indicatorExplorer.saved"))
    } catch {
      toast.error(t("indicatorExplorer.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(o) => { if (!o) onClose() }}><DialogContent className="sm:max-w-md">
    <DialogHeader><DialogTitle>{t("indicatorExplorer.editObservation")}</DialogTitle><DialogDescription>{indicatorId}</DialogDescription></DialogHeader>
    <div className="grid gap-4">
      <FormField label={t("indicatorExplorer.date")} value={obsDate} onChange={setObsDate} type="date" required />
      <FormField label={t("indicatorExplorer.value")} value={value} onChange={setValue} type="number" required />
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("indicatorExplorer.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("indicatorExplorer.saving") : t("indicatorExplorer.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}

function IndicatorDefDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ indicator_id: "", indicator_name: "", category: "", country: "", unit: "%", frequency: "MONTHLY" })
  const set = (k: keyof typeof form) => (v: string) => setForm((p) => ({ ...p, [k]: v }))

  async function save() {
    if (!form.indicator_id.trim() || !form.indicator_name.trim() || !form.category.trim() || form.country.trim().length !== 2) {
      toast.error(t("indicatorExplorer.required")); return
    }
    setSaving(true)
    try {
      await fsiApi.createIndicatorDef({
        indicator_id: form.indicator_id.trim().toUpperCase(),
        indicator_name: form.indicator_name.trim(),
        category: form.category.trim(),
        country: form.country.trim().toUpperCase(),
        unit: form.unit.trim(),
        frequency: form.frequency,
      })
      await onSaved()
      toast.success(t("indicatorExplorer.created"))
    } catch {
      toast.error(t("indicatorExplorer.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(o) => { if (!o) onClose() }}><DialogContent className="sm:max-w-lg">
    <DialogHeader><DialogTitle>{t("indicatorExplorer.newIndicator")}</DialogTitle></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("indicatorExplorer.indicatorId")} value={form.indicator_id} onChange={set("indicator_id")} required />
      <FormField label={t("indicatorExplorer.indicatorName")} value={form.indicator_name} onChange={set("indicator_name")} required />
      <FormField label={t("indicatorExplorer.category")} value={form.category} onChange={set("category")} required />
      <FormField label={t("indicatorExplorer.country")} value={form.country} onChange={set("country")} required />
      <FormField label={t("indicatorExplorer.unit")} value={form.unit} onChange={set("unit")} required />
      <div className="space-y-1.5"><Label>{t("indicatorExplorer.frequency")}</Label><Select value={form.frequency} onValueChange={set("frequency")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["DAILY", "MONTHLY", "QUARTERLY", "ANNUAL"].map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}</SelectContent></Select></div>
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("indicatorExplorer.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("indicatorExplorer.saving") : t("indicatorExplorer.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}


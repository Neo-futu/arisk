import { useQuery } from "@tanstack/react-query"
import { Download, Wallet } from "lucide-react"
import { useEffect, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { FloatingAiChat } from "@/components/FloatingAiChat"
import { FsiToolbar, FUNDS } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fsiApi, type PnlAnalysis, type ValuationReport } from "@/fsiClient"
import { exportCsv, HorizontalBarList, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"

type Mode = "report" | "pnl"

function money(value: number | null | undefined, currency = "HKD", digits = 2) {
  if (value == null) return "—"
  return new Intl.NumberFormat("zh-HK", { style: "currency", currency, maximumFractionDigits: digits }).format(value)
}
function numeric(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : Number(value).toLocaleString("en-US", { maximumFractionDigits: digits })
}
function pct(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${Number(value).toFixed(digits)}%`
}
function signed(value: number | null | undefined) {
  return value == null ? "text-muted-foreground" : value < 0 ? "text-destructive" : "text-emerald-600"
}

function ZoneTitle({ index, title, detail, action }: { index: string; title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-semibold text-primary">{index}</span>
        <div>
          <CardTitle className="text-base">{title}</CardTitle>
          {detail ? <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p> : null}
        </div>
      </div>
      {action}
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-lg font-semibold ${tone ?? ""}`}>{value}</div>
    </div>
  )
}

export function ValuationPnlPage() {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>("report")
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState<string>("")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")

  const report = useQuery({
    queryKey: ["valuation-report", fundId, asOfDate],
    queryFn: () => fsiApi.getValuationReport(fundId, asOfDate).then((r) => r.data),
    enabled: mode === "report" && Boolean(asOfDate),
    retry: 1,
  })

  // Discover available valuation dates for the picker (defaults to latest).
  const dateProbe = useQuery({
    queryKey: ["valuation-dates", fundId],
    queryFn: () => fsiApi.getValuationReport(fundId, "2100-01-01").then((r) => r.data),
    enabled: mode === "report" && !asOfDate,
    retry: 1,
  })
  useEffect(() => {
    const dates = dateProbe.data?.available_dates ?? []
    if (mode === "report" && !asOfDate && dates.length) setAsOfDate(dates[0])
  }, [dateProbe.data, mode, asOfDate])

  const pnl = useQuery({
    queryKey: ["valuation-pnl", fundId, start, end],
    queryFn: () => fsiApi.getPnlAnalysis(fundId, { start: start || undefined, end: end || undefined }).then((r) => r.data),
    enabled: mode === "pnl",
    retry: 1,
  })

  // Keep the range inputs in sync with the server-resolved default range.
  useEffect(() => {
    if (mode === "pnl" && pnl.data) {
      if (!start) setStart(pnl.data.start)
      if (!end) setEnd(pnl.data.end)
    }
  }, [pnl.data, mode, start, end])

  const availableDates = report.data?.available_dates ?? dateProbe.data?.available_dates ?? []
  const currency = report.data?.nav_summary?.currency ?? "HKD"

  const refresh = () => (mode === "report" ? void report.refetch() : void pnl.refetch())

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge className="gap-1"><Wallet className="h-3.5 w-3.5" />{t("valuation.badge")}</Badge>
            <Badge variant="outline">Module 4</Badge>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("valuation.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("valuation.subtitle")}</p>
        </div>
      </div>

      <div className="space-y-5">
          <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
            <CardHeader>
              <ZoneTitle index="01" title={t("valuation.parameters")} detail={`${fundId}`} />
            </CardHeader>
            <CardContent className="space-y-4">
              <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
                <TabsList className="grid w-full max-w-md grid-cols-2">
                  <TabsTrigger value="report">{t("valuation.reportTab")}</TabsTrigger>
                  <TabsTrigger value="pnl">{t("valuation.pnlTab")}</TabsTrigger>
                </TabsList>
              </Tabs>
              <FsiToolbar
                fundId={fundId}
                onFundChange={(id) => { setFundId(id); setAsOfDate(""); setStart(""); setEnd("") }}
                asOfDate={asOfDate}
                onDateChange={setAsOfDate}
                onRefresh={refresh}
                isFetching={mode === "report" ? report.isFetching : pnl.isFetching}
                extra={mode === "report" ? (
                  availableDates.length ? (
                    <div className="flex items-center gap-2">
                      <Label className="text-xs">{t("valuation.valuationDate")}</Label>
                      <Select value={asOfDate} onValueChange={setAsOfDate}>
                        <SelectTrigger className="h-9 w-40"><SelectValue /></SelectTrigger>
                        <SelectContent>{availableDates.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                  ) : null
                ) : (
                  <div className="flex flex-wrap items-center gap-2">
                    <Label className="text-xs">{t("valuation.from")}</Label>
                    <Input type="date" className="h-9 w-40" value={start} onChange={(e) => setStart(e.target.value)} />
                    <Label className="text-xs">{t("valuation.to")}</Label>
                    <Input type="date" className="h-9 w-40" value={end} onChange={(e) => setEnd(e.target.value)} />
                  </div>
                )}
              />
            </CardContent>
          </Card>

          {mode === "report" ? <ReportView report={report.data} loading={report.isFetching} error={report.isError} currency={currency} /> : null}
          {mode === "pnl" ? <PnlView pnl={pnl.data} loading={pnl.isFetching} error={pnl.isError} /> : null}
      </div>
      <FloatingAiChat
        title={t("valuation.aiArea")}
        hint={t("valuation.aiHint")}
        placeholder={t("valuation.aiPlaceholder")}
        context={{ fund_id: fundId }}
        buildPrompt={(q) => {
          const summary = mode === "report"
            ? { mode, fund: fundId, as_of: report.data?.as_of_date, totals: report.data?.totals, nav: report.data?.nav_summary, top: (report.data?.subjects ?? []).slice(0, 8).map((s) => ({ code: s.subject_code, mv: s.market_value, pnl: s.unrealized_pnl })) }
            : { mode, fund: fundId, range: pnl.data ? `${pnl.data.start}~${pnl.data.end}` : null, summary: pnl.data?.summary, attr: (pnl.data?.attribution.items ?? []).slice(0, 8) }
          return [
            "你正在 ARISK 组合估值与损益模块协助投资风控人员。",
            `当前视图：${mode === "report" ? "每日估值报表" : "阶段损益分析"}；基金：${fundId}。`,
            "以下是当前页面数据摘要（只作分析，不得杜撰数据）：",
            JSON.stringify(summary),
            `用户问题：${q}`,
          ].join("\n")
        }}
      />
    </div>
  )
}

function ReportView({ report, loading, error, currency }: { report?: ValuationReport; loading: boolean; error: boolean; currency: string }) {
  const { t } = useTranslation()
  const subjects = report?.subjects ?? []
  const nav = report?.nav_summary
  const totals = report?.totals
  const chartItems = subjects.slice(0, 12).map((s) => ({ label: s.subject_name || s.subject_code, value: Number(s.market_value) }))

  return (
    <>
      <Card>
        <CardHeader>
          <ZoneTitle index="02" title={t("valuation.dataArea")} detail={t("valuation.subjectCount", { count: totals?.subject_count ?? 0 })}
            action={<Button size="sm" variant="outline" disabled={!subjects.length} onClick={() => exportCsv(
              `valuation_${report?.fund_id}_${report?.as_of_date}.csv`,
              ["subject_code", "subject_name", "currency", "market_value", "cost", "unrealized_pnl", "weight_pct"],
              subjects.map((s) => [s.subject_code, s.subject_name, s.currency, s.market_value, s.cost, s.unrealized_pnl, s.weight_pct]),
            )}><Download className="mr-1 h-4 w-4" />{t("valuation.exportCsv")}</Button>} />
        </CardHeader>
        <CardContent className="space-y-4">
          {nav ? (
            <div className="grid gap-3 sm:grid-cols-4">
              <Kpi label={t("valuation.netAsset")} value={money(nav.net_asset, nav.currency, 0)} />
              <Kpi label={t("valuation.unitNav")} value={numeric(nav.unit_nav, 6)} />
              <Kpi label={t("valuation.accUnitNav")} value={numeric(nav.acc_unit_nav, 6)} />
              <Kpi label={t("valuation.dayReturn")} value={pct(nav.day_return != null ? nav.day_return * 100 : null, 4)} tone={signed(nav.day_return)} />
            </div>
          ) : null}
          {loading ? <p className="py-8 text-center text-sm text-muted-foreground">{t("valuation.loading")}</p> : null}
          {error ? <p className="py-8 text-center text-sm text-destructive">{t("valuation.operationFailed")}</p> : null}
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>{t("valuation.subjectCode")}</TableHead><TableHead>{t("valuation.subjectName")}</TableHead>
                <TableHead className="text-right">{t("valuation.marketValue")}</TableHead><TableHead className="text-right">{t("valuation.cost")}</TableHead>
                <TableHead className="text-right">{t("valuation.unrealizedPnl")}</TableHead><TableHead className="text-right">{t("valuation.returnPct")}</TableHead>
                <TableHead className="text-right">{t("valuation.weight")}</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {subjects.map((s) => (
                  <TableRow key={s.subject_code}>
                    <TableCell className="font-mono text-xs">{s.subject_code}</TableCell>
                    <TableCell className="font-medium">{s.subject_name}</TableCell>
                    <TableCell className="text-right font-mono">{money(s.market_value, s.currency, 0)}</TableCell>
                    <TableCell className="text-right font-mono">{money(s.cost, s.currency, 0)}</TableCell>
                    <TableCell className={`text-right font-mono ${signed(s.unrealized_pnl)}`}>{money(s.unrealized_pnl, s.currency, 0)}</TableCell>
                    <TableCell className={`text-right font-mono ${signed(s.return_pct)}`}>{pct(s.return_pct)}</TableCell>
                    <TableCell className="text-right font-mono">{pct(s.weight_pct)}</TableCell>
                  </TableRow>
                ))}
                {!subjects.length && !loading ? <TableRow><TableCell colSpan={7} className="h-24 text-center text-muted-foreground">{t("valuation.noData")}</TableCell></TableRow> : null}
                {totals && subjects.length ? (
                  <TableRow className="border-t-2 font-semibold">
                    <TableCell colSpan={2}>{t("valuation.total")}</TableCell>
                    <TableCell className="text-right font-mono">{money(totals.total_market_value, currency, 0)}</TableCell>
                    <TableCell className="text-right font-mono">{money(totals.total_cost, currency, 0)}</TableCell>
                    <TableCell className={`text-right font-mono ${signed(totals.total_unrealized_pnl)}`}>{money(totals.total_unrealized_pnl, currency, 0)}</TableCell>
                    <TableCell colSpan={2} />
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><ZoneTitle index="03" title={t("valuation.chartArea")} detail={t("valuation.mvDistribution")} /></CardHeader>
        <CardContent><HorizontalBarList items={chartItems} formatter={(v) => money(v, currency, 0)} /></CardContent>
      </Card>
    </>
  )
}

function PnlView({ pnl, loading, error }: { pnl?: PnlAnalysis; loading: boolean; error: boolean }) {
  const { t } = useTranslation()
  const s = pnl?.summary
  const ts = pnl?.timeseries ?? []
  const attribution = pnl?.attribution
  const step = Math.max(1, Math.ceil(ts.length / 60))
  const sampled = ts.filter((_, i) => i % step === 0)

  return (
    <>
      <Card>
        <CardHeader>
          <ZoneTitle index="02" title={t("valuation.pnlKpis")} detail={pnl ? `${pnl.start} → ${pnl.end} · ${s?.days} ${t("valuation.days")}` : undefined}
            action={<Button size="sm" variant="outline" disabled={!ts.length} onClick={() => exportCsv(
              `pnl_${pnl?.fund_id}_${pnl?.start}_${pnl?.end}.csv`,
              ["date", "net_asset", "unit_nav", "cum_return_pct"],
              ts.map((p) => [p.date, p.net_asset, p.unit_nav, p.cum_return_pct]),
            )}><Download className="mr-1 h-4 w-4" />{t("valuation.exportCsv")}</Button>} />
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? <p className="py-8 text-center text-sm text-muted-foreground">{t("valuation.loading")}</p> : null}
          {error ? <p className="py-8 text-center text-sm text-destructive">{t("valuation.operationFailed")}</p> : null}
          {s ? (
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Kpi label={t("valuation.cumReturn")} value={pct(s.cumulative_return_pct)} tone={signed(s.cumulative_return_pct)} />
              <Kpi label={t("valuation.absPnl")} value={money(s.net_asset_change, s.currency, 0)} tone={signed(s.net_asset_change)} />
              <Kpi label={t("valuation.annualized")} value={pct(s.annualized_return_pct)} tone={signed(s.annualized_return_pct)} />
              <Kpi label={t("valuation.volatility")} value={pct(s.volatility_pct)} />
              <Kpi label={t("valuation.maxDrawdown")} value={pct(s.max_drawdown_pct)} tone="text-destructive" />
              <Kpi label={t("valuation.positiveDays")} value={pct(s.positive_day_ratio * 100, 0)} />
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><ZoneTitle index="03" title={t("valuation.chartArea")} detail={t("valuation.cumReturnCurve")} /></CardHeader>
        <CardContent>
          <TrendLineChart
            values={sampled.map((p) => p.cum_return_pct)}
            labels={sampled.filter((_, i) => i % Math.max(1, Math.ceil(sampled.length / 8)) === 0).map((p) => p.date.slice(0, 7))}
            lineColor="#059669"
            pointColor="#6ee7b7"
          />
        </CardContent>
      </Card>

      {attribution && attribution.items.length ? (
        <Card>
          <CardHeader><ZoneTitle index="04" title={t("valuation.attribution")} detail={attribution.mode === "period" ? t("valuation.attrPeriod", { start: attribution.start_date, end: attribution.end_date }) : t("valuation.attrUnrealized", { date: attribution.snapshot_date ?? "" })} /></CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>{t("valuation.subjectCode")}</TableHead><TableHead>{t("valuation.subjectName")}</TableHead>
                  <TableHead className="text-right">{t("valuation.contribution")}</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {attribution.items.map((it) => (
                    <TableRow key={it.subject_code}>
                      <TableCell className="font-mono text-xs">{it.subject_code}</TableCell>
                      <TableCell className="font-medium">{it.subject_name}</TableCell>
                      <TableCell className={`text-right font-mono ${signed(it.contribution)}`}>{money(it.contribution, s?.currency, 0)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </>
  )
}


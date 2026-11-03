import { useQuery } from "@tanstack/react-query"
import { Download } from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { FsiToolbar, FUNDS } from "@/components/FsiToolbar"
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
import { fsiApi, type PnlAnalysis, type ValuationReport, type ValuationSubject } from "@/fsiClient"
import { exportCsv, HorizontalBarList, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"
import { useBindPageContext } from "@/platform/page-context"

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

function Kpi({ label, value, tone, hint }: { label: string; value: string; tone?: string; hint?: string }) {
  return (
    <div className="rounded-lg border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-lg font-semibold ${tone ?? ""}`}>{value}</div>
      {hint ? <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div> : null}
    </div>
  )
}

function lineSubjects(subjects: ValuationSubject[]) {
  return subjects.filter((s) => !s.is_aggregate)
}

export function ValuationPnlPage() {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>("report")
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState<string>("")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [subjectFilter, setSubjectFilter] = useState("")

  const report = useQuery({
    queryKey: ["valuation-report", fundId, asOfDate],
    queryFn: () => fsiApi.getValuationReport(fundId, asOfDate).then((r) => r.data),
    enabled: mode === "report" && Boolean(asOfDate),
    retry: 1,
  })

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

  useEffect(() => {
    const effective = report.data?.effective_date ?? report.data?.as_of_date
    if (mode === "report" && report.data?.date_fallback && effective && effective !== asOfDate) {
      setAsOfDate(effective)
    }
  }, [report.data, mode, asOfDate])

  const pnl = useQuery({
    queryKey: ["valuation-pnl", fundId, start, end],
    queryFn: () => fsiApi.getPnlAnalysis(fundId, { start: start || undefined, end: end || undefined }).then((r) => r.data),
    enabled: mode === "pnl",
    retry: 1,
  })

  useEffect(() => {
    if (mode === "pnl" && pnl.data) {
      if (!start) setStart(pnl.data.start)
      if (!end) setEnd(pnl.data.end)
    }
  }, [pnl.data, mode, start, end])

  const availableDates = report.data?.available_dates ?? dateProbe.data?.available_dates ?? []
  const currency = report.data?.nav_summary?.currency ?? pnl.data?.summary.currency ?? "HKD"

  useBindPageContext({
    portfolio: fundId,
    date: mode === "report" ? asOfDate : (end || start || undefined),
    module: "valuation",
    result: mode,
    riskMetrics: mode === "report"
      ? {
          subject_count: report.data?.totals.subject_count,
          net_asset: report.data?.nav_summary?.net_asset,
          unrealized_pnl: report.data?.totals.total_unrealized_pnl,
        }
      : {
          days: pnl.data?.summary.days,
          cumulative_return_pct: pnl.data?.summary.cumulative_return_pct,
          max_drawdown_pct: pnl.data?.summary.max_drawdown_pct,
        },
  })

  const refresh = () => (mode === "report" ? void report.refetch() : void pnl.refetch())

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
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
              onFundChange={(id) => { setFundId(id); setAsOfDate(""); setStart(""); setEnd(""); setSubjectFilter("") }}
              asOfDate={asOfDate}
              onDateChange={setAsOfDate}
              onRefresh={refresh}
              isFetching={mode === "report" ? report.isFetching : pnl.isFetching}
              extra={mode === "report" ? (
                availableDates.length ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Label className="text-xs">{t("valuation.valuationDate")}</Label>
                    <Select value={asOfDate} onValueChange={setAsOfDate}>
                      <SelectTrigger className="h-9 w-40"><SelectValue /></SelectTrigger>
                      <SelectContent>{availableDates.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
                    </Select>
                    <Input
                      className="h-9 w-48"
                      placeholder={t("valuation.filterSubject")}
                      value={subjectFilter}
                      onChange={(e) => setSubjectFilter(e.target.value)}
                    />
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

        {mode === "report" ? (
          <ReportView
            report={report.data}
            loading={report.isFetching || dateProbe.isFetching}
            error={report.isError || dateProbe.isError}
            currency={currency}
            filter={subjectFilter}
            noDates={!asOfDate && !dateProbe.isFetching && !(dateProbe.data?.available_dates?.length)}
          />
        ) : null}
        {mode === "pnl" ? <PnlView pnl={pnl.data} loading={pnl.isFetching} error={pnl.isError} /> : null}
      </div>
    </div>
  )
}

function ReportView({
  report,
  loading,
  error,
  currency,
  filter,
  noDates,
}: {
  report?: ValuationReport
  loading: boolean
  error: boolean
  currency: string
  filter: string
  noDates: boolean
}) {
  const { t } = useTranslation()
  const subjects = useMemo(() => {
    const rows = report?.subjects ?? []
    const q = filter.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((s) =>
      s.subject_code.toLowerCase().includes(q) || (s.subject_name || "").toLowerCase().includes(q))
  }, [report?.subjects, filter])
  const lines = lineSubjects(subjects)
  const nav = report?.nav_summary
  const totals = report?.totals
  const chartItems = lines
    .slice()
    .sort((a, b) => Math.abs(b.market_value) - Math.abs(a.market_value))
    .slice(0, 12)
    .map((s) => ({ label: s.subject_name || s.subject_code, value: Math.abs(Number(s.market_value)) }))
  const pnlChartItems = lines
    .filter((s) => s.unrealized_pnl != null)
    .slice()
    .sort((a, b) => Math.abs(Number(b.unrealized_pnl)) - Math.abs(Number(a.unrealized_pnl)))
    .slice(0, 10)
    .map((s) => ({ label: s.subject_name || s.subject_code, value: Math.abs(Number(s.unrealized_pnl)) }))

  return (
    <>
      <Card>
        <CardHeader>
          <ZoneTitle
            index="02"
            title={t("valuation.dataArea")}
            detail={t("valuation.subjectCount", { count: totals?.subject_count ?? 0 })}
            action={(
              <Button
                size="sm"
                variant="outline"
                disabled={!subjects.length}
                onClick={() => exportCsv(
                  `valuation_${report?.fund_id}_${report?.as_of_date}.csv`,
                  ["subject_code", "subject_name", "currency", "quantity", "unit_price", "market_value", "cost", "unrealized_pnl", "weight_pct"],
                  subjects.map((s) => [s.subject_code, s.subject_name, s.currency, s.quantity, s.unit_price, s.market_value, s.cost, s.unrealized_pnl, s.weight_pct]),
                )}
              >
                <Download className="mr-1 h-4 w-4" />{t("valuation.exportCsv")}
              </Button>
            )}
          />
        </CardHeader>
        <CardContent className="space-y-4">
          {nav ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
              <Kpi label={t("valuation.netAsset")} value={money(nav.net_asset, nav.currency, 0)} />
              <Kpi label={t("valuation.totalAsset")} value={money(nav.total_asset, nav.currency, 0)} />
              <Kpi label={t("valuation.totalLiability")} value={money(nav.total_liability, nav.currency, 0)} />
              <Kpi label={t("valuation.unitNav")} value={numeric(nav.unit_nav, 6)} />
              <Kpi label={t("valuation.accUnitNav")} value={numeric(nav.acc_unit_nav, 6)} />
              <Kpi label={t("valuation.dayReturn")} value={pct(nav.day_return != null ? nav.day_return * 100 : null, 4)} tone={signed(nav.day_return)} />
              <Kpi label={t("valuation.unrealizedPnl")} value={money(totals?.total_unrealized_pnl, currency, 0)} tone={signed(totals?.total_unrealized_pnl)} />
            </div>
          ) : null}
          {report?.date_fallback ? (
            <p className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
              {t("valuation.dateFallback", { requested: report.requested_date, effective: report.effective_date ?? report.as_of_date })}
            </p>
          ) : null}
          {loading ? <p className="py-8 text-center text-sm text-muted-foreground">{t("valuation.loading")}</p> : null}
          {error ? <p className="py-8 text-center text-sm text-destructive">{t("valuation.operationFailed")}</p> : null}
          {noDates && !loading ? <p className="py-8 text-center text-sm text-muted-foreground">{t("valuation.noDates")}</p> : null}
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("valuation.subjectCode")}</TableHead>
                  <TableHead>{t("valuation.subjectName")}</TableHead>
                  <TableHead className="text-right">{t("valuation.quantity")}</TableHead>
                  <TableHead className="text-right">{t("valuation.unitPrice")}</TableHead>
                  <TableHead className="text-right">{t("valuation.marketValue")}</TableHead>
                  <TableHead className="text-right">{t("valuation.cost")}</TableHead>
                  <TableHead className="text-right">{t("valuation.unrealizedPnl")}</TableHead>
                  <TableHead className="text-right">{t("valuation.returnPct")}</TableHead>
                  <TableHead className="text-right">{t("valuation.weight")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subjects.map((s) => (
                  <TableRow key={s.subject_code} className={s.is_aggregate ? "bg-muted/40 font-medium" : undefined}>
                    <TableCell className="font-mono text-xs">{s.subject_code}</TableCell>
                    <TableCell className="font-medium">{s.subject_name}</TableCell>
                    <TableCell className="text-right font-mono">{numeric(s.quantity, 4)}</TableCell>
                    <TableCell className="text-right font-mono">{numeric(s.unit_price, 6)}</TableCell>
                    <TableCell className="text-right font-mono">{money(s.market_value, s.currency, 0)}</TableCell>
                    <TableCell className="text-right font-mono">{money(s.cost, s.currency, 0)}</TableCell>
                    <TableCell className={`text-right font-mono ${signed(s.unrealized_pnl)}`}>{money(s.unrealized_pnl, s.currency, 0)}</TableCell>
                    <TableCell className={`text-right font-mono ${signed(s.return_pct)}`}>{pct(s.return_pct)}</TableCell>
                    <TableCell className="text-right font-mono">{pct(s.weight_pct)}</TableCell>
                  </TableRow>
                ))}
                {!subjects.length && !loading && !noDates ? (
                  <TableRow><TableCell colSpan={9} className="h-24 text-center text-muted-foreground">{t("valuation.noData")}</TableCell></TableRow>
                ) : null}
                {totals && lines.length ? (
                  <TableRow className="border-t-2 font-semibold">
                    <TableCell colSpan={4}>{t("valuation.total")}</TableCell>
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

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader><ZoneTitle index="03" title={t("valuation.chartArea")} detail={t("valuation.mvDistribution")} /></CardHeader>
          <CardContent><HorizontalBarList items={chartItems} formatter={(v) => money(v, currency, 0)} /></CardContent>
        </Card>
        <Card>
          <CardHeader><ZoneTitle index="04" title={t("valuation.unrealizedChart")} detail={t("valuation.unrealizedTop")} /></CardHeader>
          <CardContent><HorizontalBarList items={pnlChartItems} formatter={(v) => money(v, currency, 0)} /></CardContent>
        </Card>
      </div>
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
  const labelStep = Math.max(1, Math.ceil(sampled.length / 8))
  const attrItems = (attribution?.items ?? [])
    .slice()
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 12)
    .map((it) => ({ label: it.subject_name || it.subject_code, value: Math.abs(it.contribution) }))

  return (
    <>
      <Card>
        <CardHeader>
          <ZoneTitle
            index="02"
            title={t("valuation.pnlKpis")}
            detail={pnl ? `${pnl.start} → ${pnl.end} · ${s?.days} ${t("valuation.days")}` : undefined}
            action={(
              <Button
                size="sm"
                variant="outline"
                disabled={!ts.length}
                onClick={() => exportCsv(
                  `pnl_${pnl?.fund_id}_${pnl?.start}_${pnl?.end}.csv`,
                  ["date", "net_asset", "unit_nav", "day_return_pct", "cum_return_pct"],
                  ts.map((p) => [p.date, p.net_asset, p.unit_nav, p.day_return_pct ?? "", p.cum_return_pct]),
                )}
              >
                <Download className="mr-1 h-4 w-4" />{t("valuation.exportCsv")}
              </Button>
            )}
          />
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? <p className="py-8 text-center text-sm text-muted-foreground">{t("valuation.loading")}</p> : null}
          {error ? <p className="py-8 text-center text-sm text-destructive">{t("valuation.operationFailed")}</p> : null}
          {s ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
              <Kpi label={t("valuation.cumReturn")} value={pct(s.cumulative_return_pct)} tone={signed(s.cumulative_return_pct)} />
              <Kpi label={t("valuation.absPnl")} value={money(s.net_asset_change, s.currency, 0)} tone={signed(s.net_asset_change)} hint={`${money(s.net_asset_start, s.currency, 0)} → ${money(s.net_asset_end, s.currency, 0)}`} />
              <Kpi label={t("valuation.annualized")} value={pct(s.annualized_return_pct)} tone={signed(s.annualized_return_pct)} />
              <Kpi label={t("valuation.volatility")} value={pct(s.volatility_pct)} />
              <Kpi label={t("valuation.maxDrawdown")} value={pct(s.max_drawdown_pct)} tone="text-destructive" />
              <Kpi label={t("valuation.avgDaily")} value={pct(s.avg_daily_return_pct, 4)} tone={signed(s.avg_daily_return_pct)} />
              <Kpi label={t("valuation.bestDay")} value={pct(s.best_day_pct, 4)} tone="text-emerald-600" />
              <Kpi label={t("valuation.worstDay")} value={pct(s.worst_day_pct, 4)} tone="text-destructive" />
              <Kpi label={t("valuation.positiveDays")} value={pct(s.positive_day_ratio * 100, 0)} />
              <Kpi label={t("valuation.unitNavRange")} value={`${numeric(s.unit_nav_start, 6)} → ${numeric(s.unit_nav_end, 6)}`} />
            </div>
          ) : null}
          {!loading && !error && !s ? (
            <p className="py-8 text-center text-sm text-muted-foreground">{t("valuation.noPnlData")}</p>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader><ZoneTitle index="03" title={t("valuation.chartArea")} detail={t("valuation.cumReturnCurve")} /></CardHeader>
          <CardContent>
            <TrendLineChart
              values={sampled.map((p) => p.cum_return_pct)}
              labels={sampled.filter((_, i) => i % labelStep === 0).map((p) => p.date.slice(0, 7))}
              lineColor="#059669"
              pointColor="#6ee7b7"
              valueFormatter={(v) => `${v.toFixed(2)}%`}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><ZoneTitle index="04" title={t("valuation.navCurve")} detail={t("valuation.netAssetTrend")} /></CardHeader>
          <CardContent>
            <TrendLineChart
              values={sampled.map((p) => Number(p.net_asset ?? 0))}
              labels={sampled.filter((_, i) => i % labelStep === 0).map((p) => p.date.slice(0, 7))}
              lineColor="#2563eb"
              pointColor="#93c5fd"
              valueFormatter={(v) => money(v, s?.currency ?? "HKD", 0)}
            />
          </CardContent>
        </Card>
      </div>

      {pnl && !loading && !error ? (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <ZoneTitle
                index="05"
                title={t("valuation.attribution")}
                detail={attribution?.items?.length
                  ? (attribution.mode === "period"
                    ? t("valuation.attrPeriod", { start: attribution.start_date, end: attribution.end_date })
                    : t("valuation.attrUnrealized", { date: attribution.snapshot_date ?? "" }))
                  : t("valuation.attrEmpty")}
              />
            </CardHeader>
            <CardContent>
              {attribution?.items?.length ? (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("valuation.subjectCode")}</TableHead>
                        <TableHead>{t("valuation.subjectName")}</TableHead>
                        {attribution.mode === "period" ? (
                          <>
                            <TableHead className="text-right">{t("valuation.mvStart")}</TableHead>
                            <TableHead className="text-right">{t("valuation.mvEnd")}</TableHead>
                          </>
                        ) : null}
                        <TableHead className="text-right">{t("valuation.contribution")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {attribution.items.slice(0, 30).map((it) => (
                        <TableRow key={it.subject_code}>
                          <TableCell className="font-mono text-xs">{it.subject_code}</TableCell>
                          <TableCell className="font-medium">{it.subject_name}</TableCell>
                          {attribution.mode === "period" ? (
                            <>
                              <TableCell className="text-right font-mono">{money(it.mv_start, s?.currency, 0)}</TableCell>
                              <TableCell className="text-right font-mono">{money(it.mv_end, s?.currency, 0)}</TableCell>
                            </>
                          ) : null}
                          <TableCell className={`text-right font-mono ${signed(it.contribution)}`}>{money(it.contribution, s?.currency, 0)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="py-6 text-center text-sm text-muted-foreground">{t("valuation.attrEmpty")}</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><ZoneTitle index="06" title={t("valuation.attributionChart")} detail={t("valuation.topContributors")} /></CardHeader>
            <CardContent>
              {attrItems.length ? (
                <HorizontalBarList items={attrItems} formatter={(v) => money(v, s?.currency, 0)} />
              ) : (
                <p className="py-6 text-center text-sm text-muted-foreground">{t("valuation.attrEmpty")}</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </>
  )
}

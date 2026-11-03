import { useQuery } from "@tanstack/react-query"
import { Download, Search } from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { DatePicker } from "@/components/DatePicker"
import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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
import { fsiApi } from "@/fsiClient"
import { exportCsv, HorizontalBarList, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"
import { EngineKpiPanel } from "@/modules/investment-risk/EngineKpiPanel"
function defaultStartDate() {
  const result = new Date(`${lastTradeDate()}T00:00:00`)
  result.setDate(result.getDate() - 180)
  return result.toISOString().split("T")[0]
}

function money(value: number | null | undefined) {
  if (value == null) return "—"
  return Number(value).toLocaleString("zh-HK", { maximumFractionDigits: 0 })
}

function percent(value: number | null | undefined, digits = 2) {
  if (value == null) return "—"
  return `${Number(value).toFixed(digits)}%`
}

/** Beta 接近 0 时保留有效位数，避免 toFixed(3) 显示成 0.000 */
function formatBeta(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—"
  const abs = Math.abs(value)
  if (abs === 0) return "0"
  if (abs >= 0.01) return value.toFixed(3)
  if (abs >= 0.0001) return value.toFixed(6)
  return value.toExponential(2)
}

function EmptyRow({ columns, label }: { columns: number; label: string }) {
  return <TableRow><TableCell colSpan={columns} className="h-16 text-center text-muted-foreground">{label}</TableCell></TableRow>
}

export function RatesCreditRuntimePage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [issuerQuery, setIssuerQuery] = useState("")
  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["rates-credit", fundId, asOfDate],
    queryFn: () => fsiApi.getRatesCredit(fundId, asOfDate).then((r) => r.data),
    retry: 1,
  })

  const filteredIssuers = useMemo(() => {
    const rows = data?.issuer_concentration.top_issuers ?? []
    return rows.filter((row) => row.issuer.toLowerCase().includes(issuerQuery.toLowerCase()))
  }, [data?.issuer_concentration.top_issuers, issuerQuery])

  function exportIssuers() {
    if (!data) return
    exportCsv(
      `investment-risk-rates-credit-${fundId}-${asOfDate}.csv`,
      [t("investmentRisk.module.csvIssuer"), t("investmentRisk.module.csvMarketValue"), t("investmentRisk.module.csvWeight")],
      filteredIssuers.map((row) => [row.issuer, row.market_value, row.weight_pct]),
    )
  }

  return (
    <div className="space-y-6">
      <span id="concentration-risk" className="scroll-mt-20" />
      <span id="counterparty-risk" className="scroll-mt-20" />
      <div>
        <div className="mb-1 flex items-center gap-2"><Badge variant="outline">{t("investmentRisk.module.tag")}</Badge><span className="text-muted-foreground text-sm">{t("investmentRisk.module.ratesCreditLabel")}</span></div>
        <h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.module.topics.rates-credit.title")}</h1>
      </div>
      <FsiToolbar fundId={fundId} onFundChange={setFundId} asOfDate={asOfDate} onDateChange={setAsOfDate} onRefresh={() => refetch()} isFetching={isFetching} />
      <EngineKpiPanel domain="rates_credit" fundId={fundId} asOfDate={asOfDate} />
      <EngineKpiPanel domain="concentration" fundId={fundId} asOfDate={asOfDate} title={t("nav.concentrationRisk")} />
      <EngineKpiPanel domain="counterparty" fundId={fundId} asOfDate={asOfDate} title={t("nav.counterpartyRisk")} />
      {isError && <Card className="border-destructive"><CardContent className="pt-4 text-sm text-destructive">{t("investmentRisk.module.ratesCreditLoadError")}</CardContent></Card>}
      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard label={t("investmentRisk.module.bondHoldings")} value={money(data.total_bond_market_value)} detail={percent(data.bond_exposure_pct_nav)} />
            <MetricCard label={t("investmentRisk.module.weightedDuration")} value={data.weighted_duration_years == null ? "—" : data.weighted_duration_years.toFixed(3)} detail={t("investmentRisk.common.years")} />
            <MetricCard label="DV01" value={money(data.portfolio_dv01)} detail={t("investmentRisk.module.perBp")} />
            <MetricCard label="CS01" value={money(data.portfolio_cs01)} detail={t("investmentRisk.module.perBp")} />
            <MetricCard label={t("investmentRisk.module.issuerHhi")} value={data.issuer_concentration.hhi.toFixed(1)} detail={t("investmentRisk.module.concentration")} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.krdCurve")}</CardTitle></CardHeader>
              <CardContent>
                <TrendLineChart
                  values={data.krd_buckets.map((row) => row.weight_pct_bond)}
                  labels={data.krd_buckets.map((row) => row.bucket)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.ratingDist")}</CardTitle></CardHeader>
              <CardContent>
                <HorizontalBarList
                  items={data.rating_distribution.map((row) => ({ label: row.rating, value: row.weight_pct }))}
                  formatter={(value) => percent(value, 2)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.krdBuckets")}</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow><TableHead>{t("investmentRisk.module.tenorBucket")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.durationWeightedMv")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.weight")}</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {data.krd_buckets.map((row) => (
                      <TableRow key={row.bucket}>
                        <TableCell>{row.bucket}</TableCell>
                        <TableCell className="text-right font-mono">{money(row.duration_weighted_mv)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.weight_pct_bond, 2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <CardTitle className="text-base">{t("investmentRisk.module.issuerConcentration")}</CardTitle>
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                      <Search className="h-4 w-4 text-muted-foreground" />
                      <Input
                        className="h-8 w-48 border-0 p-0 shadow-none focus-visible:ring-0"
                        placeholder={t("investmentRisk.module.searchIssuer")}
                        value={issuerQuery}
                        onChange={(event) => setIssuerQuery(event.target.value)}
                      />
                    </div>
                    <Button variant="outline" size="sm" onClick={exportIssuers}>
                      <Download className="mr-2 h-4 w-4" />
                      {t("investmentRisk.module.exportShort")}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow><TableHead>Issuer</TableHead><TableHead className="text-right">{t("investmentRisk.module.marketValue")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.weight")}</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {filteredIssuers.map((row) => (
                      <TableRow key={row.issuer}>
                        <TableCell>{row.issuer}</TableCell>
                        <TableCell className="text-right font-mono">{money(row.market_value)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.weight_pct)}</TableCell>
                      </TableRow>
                    ))}
                    {!filteredIssuers.length && <EmptyRow columns={3} label={t("investmentRisk.module.emptyRow")} />}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

export function LiquidityStressRuntimePage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [redemptionPct, setRedemptionPct] = useState("20")
  const [rateShockBps, setRateShockBps] = useState("50")
  const [ladderQuery, setLadderQuery] = useState("")

  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["liquidity-stress", fundId, asOfDate, redemptionPct, rateShockBps],
    queryFn: () => fsiApi.getLiquidityStress(fundId, asOfDate, { redemptionPct: Number(redemptionPct), rateShockBps: Number(rateShockBps) }).then((r) => r.data),
    retry: 1,
  })

  const filteredLadder = useMemo(() => {
    const rows = data?.liquidity_ladder ?? []
    return rows.filter((row) => row.asset_class.toLowerCase().includes(ladderQuery.toLowerCase()))
  }, [data?.liquidity_ladder, ladderQuery])

  function exportLiquidityLadder() {
    if (!data) return
    exportCsv(
      `investment-risk-liquidity-${fundId}-${asOfDate}.csv`,
      [t("investmentRisk.module.csvAssetClass"), t("investmentRisk.module.csvMarketValue"), t("investmentRisk.module.csvTtlDays"), t("investmentRisk.module.csvCumulativeMv"), t("investmentRisk.module.csvCumulativeNavPct")],
      filteredLadder.map((row) => [row.asset_class, row.market_value, row.ttl_days, row.cumulative_market_value, row.cumulative_pct_nav]),
    )
  }

  const extra = (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground text-xs">{t("investmentRisk.module.redemptionPct")}</span>
      <Select value={redemptionPct} onValueChange={setRedemptionPct}><SelectTrigger className="w-24"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="10">10</SelectItem><SelectItem value="20">20</SelectItem><SelectItem value="30">30</SelectItem></SelectContent></Select>
      <span className="text-muted-foreground text-xs">{t("investmentRisk.module.rateShock")}</span>
      <Select value={rateShockBps} onValueChange={setRateShockBps}><SelectTrigger className="w-24"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="25">25bps</SelectItem><SelectItem value="50">50bps</SelectItem><SelectItem value="100">100bps</SelectItem></SelectContent></Select>
    </div>
  )

  return (
    <div className="space-y-6">
      <div><div className="mb-1 flex items-center gap-2"><Badge variant="outline">{t("investmentRisk.module.tag")}</Badge><span className="text-muted-foreground text-sm">{t("investmentRisk.module.liquidityStressLabel")}</span></div><h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.module.topics.liquidity-stress.title")}</h1></div>
      <FsiToolbar fundId={fundId} onFundChange={setFundId} asOfDate={asOfDate} onDateChange={setAsOfDate} onRefresh={() => refetch()} isFetching={isFetching} extra={extra} />
      <EngineKpiPanel domain="liquidity" fundId={fundId} asOfDate={asOfDate} />
      {isError && <Card className="border-destructive"><CardContent className="pt-4 text-sm text-destructive">{t("investmentRisk.module.liquidityLoadError")}</CardContent></Card>}
      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="TTL 10%" value={data.ttl_snapshot.ttl_10pct_days == null ? "—" : `${data.ttl_snapshot.ttl_10pct_days} ${t("investmentRisk.common.days")}`} />
            <MetricCard label="TTL 25%" value={data.ttl_snapshot.ttl_25pct_days == null ? "—" : `${data.ttl_snapshot.ttl_25pct_days} ${t("investmentRisk.common.days")}`} />
            <MetricCard label="TTL 50%" value={data.ttl_snapshot.ttl_50pct_days == null ? "—" : `${data.ttl_snapshot.ttl_50pct_days} ${t("investmentRisk.common.days")}`} />
            <MetricCard label={t("investmentRisk.module.lcr7d")} value={data.stress_summary.liquidity_coverage_ratio == null ? "—" : data.stress_summary.liquidity_coverage_ratio.toFixed(2)} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.ttlCurve")}</CardTitle></CardHeader>
              <CardContent>
                <TrendLineChart
                  values={[
                    data.ttl_snapshot.ttl_10pct_days ?? 0,
                    data.ttl_snapshot.ttl_25pct_days ?? 0,
                    data.ttl_snapshot.ttl_50pct_days ?? 0,
                  ]}
                  labels={["10%", "25%", "50%"]}
                  lineColor="#7c3aed"
                  pointColor="#a78bfa"
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.liquidityLadderStructure")}</CardTitle></CardHeader>
              <CardContent>
                <HorizontalBarList
                  items={data.liquidity_ladder.map((row) => ({
                    label: row.asset_class,
                    value: row.cumulative_pct_nav ?? 0,
                  }))}
                  formatter={(value) => percent(value, 2)}
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.stressSummary")}</CardTitle></CardHeader>
            <CardContent className="grid gap-2 text-sm md:grid-cols-2">
              <p>{t("investmentRisk.module.redemptionAmount", { value: money(data.stress_summary.redemption_amount) })}</p>
              <p>{t("investmentRisk.module.liquidWithin7d", { value: money(data.stress_summary.liquid_within_7d) })}</p>
              <p>{t("investmentRisk.module.rateShockLoss", { value: money(data.stress_summary.stressed_bond_loss) })}</p>
              <p>{t("investmentRisk.module.projectedStressedNav", { value: money(data.stress_summary.projected_stressed_nav) })}</p>
              <p>{t("investmentRisk.module.worst1d", { value: percent(data.historical_stress.worst_1d_return_pct, 3) })}</p>
              <p>{t("investmentRisk.module.worst5d", { value: percent(data.historical_stress.worst_5d_cumulative_return_pct, 3) })}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">{t("investmentRisk.module.liquidityLadderDetail")}</CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-8 w-48 border-0 p-0 shadow-none focus-visible:ring-0"
                      placeholder={t("investmentRisk.module.searchAssetClass")}
                      value={ladderQuery}
                      onChange={(event) => setLadderQuery(event.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={exportLiquidityLadder}>
                    <Download className="mr-2 h-4 w-4" />
                    {t("investmentRisk.module.exportShort")}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.module.assetClass")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.marketValue")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.ttlDaysCol")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.cumulativeMv")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.cumulativeNavPct")}</TableHead></TableRow></TableHeader>
                <TableBody>
                  {filteredLadder.map((row) => (
                    <TableRow key={`${row.asset_class}-${row.ttl_days}`}>
                      <TableCell>{row.asset_class}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.market_value)}</TableCell>
                      <TableCell className="text-right font-mono">{row.ttl_days}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.cumulative_market_value)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.cumulative_pct_nav, 2)}</TableCell>
                    </TableRow>
                  ))}
                  {!filteredLadder.length && <EmptyRow columns={5} label={t("investmentRisk.module.emptyRow")} />}
                </TableBody>
              </Table>
              {data.breach_flags.length ? <p className="mt-4 text-sm text-amber-600">{t("investmentRisk.module.alertPrefix", { items: data.breach_flags.join("；") })}</p> : null}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

export function PretradeBudgetRuntimePage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [tradeAmount, setTradeAmount] = useState("10000000")
  const [tradeSide, setTradeSide] = useState<"BUY" | "SELL">("BUY")
  const [assetClass, setAssetClass] = useState("BOND")
  const [durationYears, setDurationYears] = useState("2.0")
  const [issuerName, setIssuerName] = useState("UNKNOWN_ISSUER")

  const queryPayload = useMemo(() => ({
    tradeAmount: Number(tradeAmount),
    tradeSide,
    assetClass,
    durationYears: Number(durationYears),
    issuerName,
  }), [tradeAmount, tradeSide, assetClass, durationYears, issuerName])

  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["pretrade-budget", fundId, asOfDate, queryPayload],
    queryFn: () => fsiApi.getPretradeCheck(fundId, asOfDate, queryPayload).then((r) => r.data),
    retry: 1,
    enabled: queryPayload.tradeAmount > 0,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  })

  function exportScenario() {
    if (!data) return
    exportCsv(
      `investment-risk-pretrade-${fundId}-${asOfDate}.csv`,
      [t("investmentRisk.module.csvMetric"), t("investmentRisk.module.csvCurrent"), t("investmentRisk.module.csvProjected"), t("investmentRisk.module.csvLimit")],
      [
        [t("investmentRisk.module.csvDurationYears"), data.current.duration_years, data.projected.duration_years, data.limits.duration_years],
        [t("investmentRisk.module.issuerPctNavRow"), data.current.issuer_pct_nav, data.projected.issuer_pct_nav, data.limits.issuer_pct_nav],
        ["VaR % NAV", data.current.var_pct_nav ?? "", data.projected.var_pct_nav ?? "", data.limits.var_pct_nav ?? ""],
        ["CVaR % NAV", data.current.cvar_pct_nav ?? "", data.projected.cvar_pct_nav ?? "", ""],
        ["DV01", data.current.portfolio_dv01, data.projected.portfolio_dv01, ""],
        [t("investmentRisk.module.tradeImpact"), "", data.projected.tracking_error_proxy_pct, data.limits.tracking_error_proxy_pct],
      ],
    )
  }

  const budgetRows = data?.risk_budget?.by_asset_class ?? []
  const projectedBudgetRows = data?.projected_risk_budget?.by_asset_class ?? []
  const rpRows = data?.risk_budget?.rp_reference?.rows ?? []
  const shocksCurrent = data?.engine_metrics?.factor_shocks_current ?? []
  const shocksProjected = data?.engine_metrics?.factor_shocks_projected ?? []
  const shockPairs = useMemo(() => {
    const map = new Map<string, { factor: string; current: number; projected: number }>()
    for (const row of shocksCurrent) {
      map.set(row.factor, { factor: row.factor, current: row.pnl, projected: 0 })
    }
    for (const row of shocksProjected) {
      const prev = map.get(row.factor) ?? { factor: row.factor, current: 0, projected: 0 }
      prev.projected = row.pnl
      map.set(row.factor, prev)
    }
    return Array.from(map.values()).sort((a, b) => Math.abs(b.projected || b.current) - Math.abs(a.projected || a.current))
  }, [shocksCurrent, shocksProjected])

  const topRc = data?.engine_metrics?.top_risk_contributors ?? []
  const topRcText = topRc.length
    ? topRc.slice(0, 3).map((row) => `${row.security_code} ${percent(row.contribution_pct, 1)}`).join(" · ")
    : "—"
  const decisionLabel = data?.decision === "ALLOW"
    ? t("investmentRisk.module.decisionAllow")
    : data?.decision === "ALLOW_WITH_WARNING"
      ? t("investmentRisk.module.decisionWarning")
      : data?.decision === "BLOCK"
        ? t("investmentRisk.module.decisionBlock")
        : (data?.decision ?? "—")
  const decisionBadgeVariant = data?.decision === "ALLOW"
    ? "default"
    : data?.decision === "ALLOW_WITH_WARNING"
      ? "secondary"
      : "destructive"

  const kpiRows = data
    ? [
        {
          kpi: t("investmentRisk.module.decision"),
          result: decisionLabel,
          formula: t("investmentRisk.module.pretradeDecisionFormula"),
        },
        {
          kpi: t("investmentRisk.module.currentDuration"),
          result: Number(data.current.duration_years).toFixed(3),
          formula: t("investmentRisk.module.pretradeDurationFormula"),
        },
        {
          kpi: t("investmentRisk.module.projectedDuration"),
          result: Number(data.projected.duration_years).toFixed(3),
          formula: t("investmentRisk.module.pretradeProjectedDurationFormula"),
        },
        {
          kpi: "VaR % NAV",
          result: percent(data.current.var_pct_nav, 3),
          formula: t("investmentRisk.module.pretradeVarFormula"),
        },
        {
          kpi: "CVaR % NAV",
          result: percent(data.current.cvar_pct_nav, 3),
          formula: t("investmentRisk.module.pretradeCvarFormula"),
        },
        {
          kpi: "Δ VaR % NAV",
          result: percent(data.projected.var_delta_pct_nav, 3),
          formula: t("investmentRisk.module.pretradeVarDeltaFormula"),
        },
        {
          kpi: t("investmentRisk.module.grossExposureKpi"),
          result: percent(data.current.gross_exposure_pct),
          formula: "Gross = Σ|MV_i| / NAV",
        },
        {
          kpi: t("investmentRisk.module.riskContributionKpi"),
          result: topRcText,
          formula: "RC_i = PnL_i(shock) / Σ PnL_j",
        },
        {
          kpi: t("investmentRisk.module.tradeImpact"),
          result: percent(data.projected.tracking_error_proxy_pct),
          formula: "|交易名义| / NAV",
        },
      ]
    : []

  return (
    <div id="risk-budget" className="scroll-mt-20 space-y-6">
      <div className="space-y-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.module.topics.pretrade-budget.title")}</h1>
          <p className="text-muted-foreground mt-1 text-sm">{t("investmentRisk.module.pretradeSubtitle")}</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("investmentRisk.module.pretradeCalcTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex min-w-[12rem] flex-col gap-1 text-xs">
              <span className="text-muted-foreground">{t("investmentRisk.module.fundLabel")}</span>
              <select className="rounded-md border bg-background px-2 py-2 text-sm" value={fundId} onChange={(e) => setFundId(e.target.value)}>
                {FUNDS.map((fund) => <option key={fund.id} value={fund.id}>{fund.name}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-muted-foreground">{t("platform.asOfDate")}</span>
              <DatePicker value={asOfDate} onChange={setAsOfDate} />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-muted-foreground">{t("investmentRisk.module.tradeSideLabel")}</span>
              <Select value={tradeSide} onValueChange={(v: "BUY" | "SELL") => setTradeSide(v)}>
                <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="BUY">BUY</SelectItem><SelectItem value="SELL">SELL</SelectItem></SelectContent>
              </Select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-muted-foreground">{t("investmentRisk.module.tradeAmountPlaceholder")}</span>
              <Input className="w-36" value={tradeAmount} onChange={(e) => setTradeAmount(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-muted-foreground">{t("investmentRisk.module.assetClassPlaceholder")}</span>
              <select className="h-9 rounded-md border bg-background px-2 text-sm" value={assetClass} onChange={(e) => setAssetClass(e.target.value)}>
                {["BOND", "CD", "DEPOSIT", "EQUITY", "FUND", "CASH"].map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-muted-foreground">{t("investmentRisk.module.durationPlaceholder")}</span>
              <Input className="w-28" value={durationYears} onChange={(e) => setDurationYears(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-muted-foreground">Issuer</span>
              <Input className="w-40" value={issuerName} onChange={(e) => setIssuerName(e.target.value)} />
            </label>
            <Button size="sm" disabled={isFetching || queryPayload.tradeAmount <= 0} onClick={() => refetch()}>
              {isFetching ? t("investmentRisk.attribution.calculating") : t("investmentRisk.attribution.modelCalc")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {isError && <Card className="border-destructive"><CardContent className="pt-4 text-sm text-destructive">{t("investmentRisk.module.pretradeLoadError")}</CardContent></Card>}

      {data && (
        <div className={isFetching ? "space-y-6 opacity-70" : "space-y-6"}>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label={t("investmentRisk.module.decision")} value={decisionLabel} detail={<Badge variant={decisionBadgeVariant}>{data.decision}</Badge>} />
            <MetricCard
              label={t("investmentRisk.module.budgetDurationRemain")}
              value={data.budget_utilization?.duration_remaining_years == null ? "—" : `${data.budget_utilization.duration_remaining_years.toFixed(3)}y`}
              detail={data.budget_utilization?.duration_used_pct == null ? undefined : t("investmentRisk.module.budgetUsed", { value: percent(data.budget_utilization.duration_used_pct) })}
            />
            <MetricCard
              label={t("investmentRisk.module.budgetVarRemain")}
              value={percent(data.budget_utilization?.var_remaining_pct_nav, 3)}
              detail={data.budget_utilization?.var_used_pct == null ? undefined : t("investmentRisk.module.budgetUsed", { value: percent(data.budget_utilization.var_used_pct) })}
            />
            <MetricCard
              label="DV01"
              value={money(data.projected.portfolio_dv01)}
              detail={`${money(data.current.portfolio_dv01)} → ${money(data.projected.portfolio_dv01)}`}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("investmentRisk.module.pretradeKpiTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("engine.colKpi")}</TableHead>
                    <TableHead>{t("engine.colResult")}</TableHead>
                    <TableHead>{t("engine.colFormula")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {kpiRows.map((row) => (
                    <TableRow key={row.kpi}>
                      <TableCell className="font-medium">{row.kpi}</TableCell>
                      <TableCell className="max-w-[22rem] truncate font-mono text-xs" title={row.result}>{row.result}</TableCell>
                      <TableCell className="max-w-[18rem] truncate text-xs text-muted-foreground" title={row.formula}>{row.formula}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card className="min-h-[16rem]">
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.riskBudgetRc")}</CardTitle></CardHeader>
              <CardContent className="h-52 overflow-auto">
                <HorizontalBarList
                  items={budgetRows.map((row) => ({ label: row.asset_class, value: Math.abs(Number(row.share_pct) || 0) }))}
                  formatter={(value) => percent(value)}
                />
              </CardContent>
            </Card>
            <Card className="min-h-[16rem]">
              <CardHeader>
                <CardTitle className="text-base">{t("investmentRisk.module.riskBudgetProjected")}</CardTitle>
              </CardHeader>
              <CardContent className="h-52 overflow-auto">
                <HorizontalBarList
                  items={projectedBudgetRows.map((row) => ({ label: row.asset_class, value: Math.abs(Number(row.share_pct) || 0) }))}
                  formatter={(value) => percent(value)}
                />
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card className="min-h-[16rem]">
              <CardHeader>
                <CardTitle className="text-base">{t("investmentRisk.module.riskParityRef")}</CardTitle>
                <p className="text-muted-foreground text-xs">
                  {data.risk_budget?.rp_reference?.note
                    ?? t("investmentRisk.module.riskParityHint")}
                  {data.risk_budget?.rp_reference?.engine ? ` · ${data.risk_budget.rp_reference.engine}` : ""}
                  {data.risk_budget?.rp_reference?.status ? ` · ${data.risk_budget.rp_reference.status}` : ""}
                </p>
              </CardHeader>
              <CardContent className="h-52 overflow-auto">
                {rpRows.length ? (
                  <HorizontalBarList
                    items={rpRows.slice(0, 12).map((row) => ({ label: row.asset_class, value: Math.abs(Number(row.weight_pct) || 0) }))}
                    formatter={(value) => percent(value)}
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">{t("investmentRisk.module.riskParityEmpty")}</p>
                )}
              </CardContent>
            </Card>
            <Card className="min-h-[16rem]">
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <CardTitle className="text-base">{t("investmentRisk.module.pretradeDecisionSummary")}</CardTitle>
                  <Button variant="outline" size="sm" onClick={exportScenario}>
                    <Download className="mr-2 h-4 w-4" />
                    {t("investmentRisk.module.exportShort")}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p className="font-medium">{data.decision_summary?.headline || decisionLabel}</p>
                <p className="text-muted-foreground">{data.decision_summary?.recommendation}</p>
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  {(data.decision_summary?.rationale ?? [
                    t("investmentRisk.module.tradeSide", { value: data.trade.trade_side }),
                    t("investmentRisk.module.tradeAmount", { value: money(data.trade.trade_amount) }),
                    t("investmentRisk.module.decisionResult", { value: decisionLabel }),
                  ]).map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                {data.decision_summary?.model ? (
                  <p className="text-muted-foreground text-xs">{data.decision_summary.model}</p>
                ) : null}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("investmentRisk.module.factorShockCompare")}</CardTitle>
              <p className="text-muted-foreground text-xs">{t("investmentRisk.module.factorShockHint")}</p>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("investmentRisk.module.factorName")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.module.currentCol")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.module.projectedCol")}</TableHead>
                    <TableHead className="text-right">Δ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shockPairs.map((row) => (
                    <TableRow key={row.factor}>
                      <TableCell className="font-medium">{row.factor}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.current)}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.projected)}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.projected - row.current)}</TableCell>
                    </TableRow>
                  ))}
                  {!shockPairs.length && <EmptyRow columns={4} label={t("investmentRisk.module.emptyRow")} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("investmentRisk.module.limitComparison")}</CardTitle>
              <p className="text-muted-foreground text-xs">{t("investmentRisk.module.limitComparisonHint")}</p>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("investmentRisk.module.metricCol2")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.module.currentCol")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.module.projectedCol")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.module.limitColShort")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell>{t("investmentRisk.module.durationYearsRow")}</TableCell>
                    <TableCell className="text-right font-mono">{data.current.duration_years.toFixed(3)}</TableCell>
                    <TableCell className="text-right font-mono">{data.projected.duration_years.toFixed(3)}</TableCell>
                    <TableCell className="text-right font-mono">{data.limits.duration_years.toFixed(2)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>{t("investmentRisk.module.issuerPctNavRow")}</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.current.issuer_pct_nav)}</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.projected.issuer_pct_nav)}</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.limits.issuer_pct_nav)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>VaR % NAV</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.current.var_pct_nav, 3)}</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.projected.var_pct_nav, 3)}</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.limits.var_pct_nav, 2)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>CVaR % NAV</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.current.cvar_pct_nav, 3)}</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.projected.cvar_pct_nav, 3)}</TableCell>
                    <TableCell className="text-right font-mono">—</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>DV01</TableCell>
                    <TableCell className="text-right font-mono">{money(data.current.portfolio_dv01)}</TableCell>
                    <TableCell className="text-right font-mono">{money(data.projected.portfolio_dv01)}</TableCell>
                    <TableCell className="text-right font-mono">—</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>{t("investmentRisk.module.tradeImpact")}</TableCell>
                    <TableCell className="text-right font-mono">—</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.projected.tracking_error_proxy_pct)}</TableCell>
                    <TableCell className="text-right font-mono">{percent(data.limits.tracking_error_proxy_pct)}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
              {(data.breach_flags?.length ?? 0) > 0 && (
                <div className="mt-3 space-y-1 rounded-md border border-amber-300 bg-amber-50/50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/20 dark:text-amber-100">
                  {data.breach_flags.map((item) => <p key={item}>{item}</p>)}
                </div>
              )}
            </CardContent>
          </Card>

          {(data.adapter_usage || data.applied_rules?.length) ? (
            <div className="grid gap-6 xl:grid-cols-2">
              {data.adapter_usage ? (
                <Card>
                  <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.adapterUsageTitle")}</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm text-muted-foreground">
                    <p><span className="font-medium text-foreground">FinancePy：</span>{data.adapter_usage.financepy}</p>
                    <p><span className="font-medium text-foreground">Riskfolio-Lib：</span>{data.adapter_usage.riskfolio}</p>
                    <p><span className="font-medium text-foreground">ORE / QuantLib：</span>{data.adapter_usage.ore}</p>
                  </CardContent>
                </Card>
              ) : null}
              {(data.applied_rules?.length ?? 0) > 0 ? (
                <Card>
                  <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.appliedRulesTitle")}</CardTitle></CardHeader>
                  <CardContent className="max-h-48 overflow-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>{t("investmentRisk.module.ruleCode")}</TableHead>
                          <TableHead>{t("investmentRisk.module.ruleName")}</TableHead>
                          <TableHead className="text-right">{t("investmentRisk.module.limitColShort")}</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.applied_rules?.map((rule) => (
                          <TableRow key={`${rule.application_id}-${rule.code}`}>
                            <TableCell className="font-mono text-xs">{rule.code}</TableCell>
                            <TableCell>{rule.name}</TableCell>
                            <TableCell className="text-right font-mono">{rule.limit_value}{rule.limit_unit ? ` ${rule.limit_unit}` : ""}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              ) : null}
            </div>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{data.logic?.title || t("investmentRisk.module.pretradeLogicTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <ol className="list-decimal space-y-1 pl-5">
                {(data.logic?.steps?.length
                  ? data.logic.steps
                  : [
                      t("investmentRisk.module.pretradeLogicStep1"),
                      t("investmentRisk.module.pretradeLogicStep2"),
                      t("investmentRisk.module.pretradeLogicStep3"),
                      t("investmentRisk.module.pretradeLogicStep4"),
                    ]
                ).map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

export function MacroDynamicsRuntimePage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [startDate, setStartDate] = useState(defaultStartDate)
  const [endDate, setEndDate] = useState(lastTradeDate)
  const [correlationQuery, setCorrelationQuery] = useState("")
  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["macro-dynamics", fundId, startDate, endDate],
    queryFn: () => fsiApi.getMacroDynamics(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })

  const filteredCorrelations = useMemo(() => {
    const rows = data?.cross_asset_correlations ?? []
    return rows.filter((row) => `${row.left} ${row.right}`.toLowerCase().includes(correlationQuery.toLowerCase()))
  }, [data?.cross_asset_correlations, correlationQuery])

  function exportCorrelations() {
    if (!data) return
    exportCsv(
      `investment-risk-macro-${fundId}-${endDate}.csv`,
      ["Left", "Right", "Correlation"],
      filteredCorrelations.map((row) => [row.left, row.right, row.correlation]),
    )
  }

  const extra = <div className="flex items-center gap-2"><span className="text-muted-foreground text-xs">{t("investmentRisk.module.startLabel")}</span><DatePicker value={startDate} onChange={setStartDate} /></div>

  return (
    <div id="market-risk" className="scroll-mt-20 space-y-6">
      <div><div className="mb-1 flex items-center gap-2"><Badge variant="outline">{t("investmentRisk.module.tag")}</Badge><span className="text-muted-foreground text-sm">{t("investmentRisk.module.macroDynamicsLabel")}</span></div><h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.module.topics.macro-dynamics.title")}</h1></div>
      <FsiToolbar fundId={fundId} onFundChange={setFundId} asOfDate={endDate} onDateChange={setEndDate} onRefresh={() => refetch()} isFetching={isFetching} extra={extra} />
      <EngineKpiPanel domain="market_risk" fundId={fundId} asOfDate={endDate} />
      <EngineKpiPanel domain="macro_dynamics" fundId={fundId} asOfDate={endDate} title={t("nav.macroDynamics")} />
      {isError && <Card className="border-destructive"><CardContent className="pt-4 text-sm text-destructive">{t("investmentRisk.module.macroLoadError")}</CardContent></Card>}
      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <MetricCard label={t("investmentRisk.module.marketRegime")} value={data.fund_regime.regime} />
            <MetricCard label={t("investmentRisk.module.fundAnnualizedVol")} value={percent(data.fund_regime.annualized_volatility_pct)} />
            <MetricCard label={t("investmentRisk.module.sampleCount")} value={`${data.fund_regime.sample_size}`} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.macroReturnProfile")}</CardTitle></CardHeader>
              <CardContent>
                <TrendLineChart
                  values={data.macro_indicators.map((row) => row.period_return_pct ?? 0)}
                  labels={data.macro_indicators.map((row) => row.index_code)}
                  lineColor="#0f766e"
                  pointColor="#2dd4bf"
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.fundVsMarket")}</CardTitle></CardHeader>
              <CardContent>
                <HorizontalBarList
                  items={data.fund_vs_market_correlations.map((row) => ({
                    label: row.index_code,
                    value: Math.abs(row.correlation),
                  }))}
                  formatter={(value) => value.toFixed(4)}
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.macroIndicatorDetail")}</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.module.metricCol2")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.periodReturn")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.annualizedVol")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.sampleCount")}</TableHead></TableRow></TableHeader>
                <TableBody>
                  {data.macro_indicators.map((row) => (
                    <TableRow key={row.index_code}>
                      <TableCell>{row.index_code}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.period_return_pct, 3)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.annualized_volatility_pct, 3)}</TableCell>
                      <TableCell className="text-right">{row.sample_size}</TableCell>
                    </TableRow>
                  ))}
                  {!data.macro_indicators.length && <EmptyRow columns={4} label={t("investmentRisk.module.emptyRow")} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">{t("investmentRisk.module.crossMarketTop")}</CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-8 w-48 border-0 p-0 shadow-none focus-visible:ring-0"
                      placeholder={t("investmentRisk.module.searchMarketPair")}
                      value={correlationQuery}
                      onChange={(event) => setCorrelationQuery(event.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={exportCorrelations}>
                    <Download className="mr-2 h-4 w-4" />
                    {t("investmentRisk.module.exportShort")}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>Left</TableHead><TableHead>Right</TableHead><TableHead className="text-right">Correlation</TableHead></TableRow></TableHeader>
                <TableBody>
                  {filteredCorrelations.map((row, idx) => <TableRow key={`${row.left}-${row.right}-${idx}`}><TableCell>{row.left}</TableCell><TableCell>{row.right}</TableCell><TableCell className="text-right font-mono">{row.correlation.toFixed(4)}</TableCell></TableRow>)}
                  {!filteredCorrelations.length && <EmptyRow columns={3} label={t("investmentRisk.module.emptyRow")} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

export function FactorBehaviorRuntimePage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [startDate, setStartDate] = useState(defaultStartDate)
  const [endDate, setEndDate] = useState(lastTradeDate)
  const [crowdingQuery, setCrowdingQuery] = useState("")

  const factorQuery = useQuery({
    queryKey: ["factor-behavior", fundId, startDate, endDate],
    queryFn: () => fsiApi.getFactorBehavior(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  })

  const data = factorQuery.data
  const isFetching = factorQuery.isFetching
  const isError = factorQuery.isError
  const style = data?.style_exposure
  const filteredCrowding = useMemo(() => {
    const rows = data?.trading_behavior.crowding_top ?? []
    return rows.filter((row) => `${row.security_code} ${row.security_name} ${row.sector}`.toLowerCase().includes(crowdingQuery.toLowerCase()))
  }, [data?.trading_behavior.crowding_top, crowdingQuery])

  function exportCrowding() {
    if (!data) return
    exportCsv(
      `investment-risk-factor-behavior-${fundId}-${endDate}.csv`,
      [t("investmentRisk.module.csvCode"), t("investmentRisk.module.csvName2"), t("investmentRisk.module.csvSector"), t("investmentRisk.module.csvWeightShort"), t("investmentRisk.module.csvAvgVolume"), t("investmentRisk.module.csvPositionQty"), t("investmentRisk.module.csvCrowdingRatio")],
      filteredCrowding.map((row) => [row.security_code, row.security_name, row.sector, row.weight_pct, row.avg_daily_volume, row.position_quantity, row.crowding_ratio]),
    )
  }

  const styleBars = useMemo(() => {
    if (!style) return []
    return [
      { label: "Momentum", value: Math.abs(style.momentum_exposure ?? 0) },
      { label: "LowVol", value: Math.abs(style.low_volatility_exposure ?? 0) },
      { label: "Size", value: Math.abs(style.size_exposure ?? 0) },
      { label: "Coverage", value: Math.abs(style.coverage_weight ?? 0) },
    ]
  }, [style])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.module.factorTitle")}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t("investmentRisk.module.factorBehaviorSubtitle")}</p>
      </div>

      <FsiToolbar
        fundId={fundId}
        onFundChange={setFundId}
        asOfDate={endDate}
        onDateChange={setEndDate}
        onRefresh={() => factorQuery.refetch()}
        isFetching={isFetching}
        extra={(
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground text-xs">{t("investmentRisk.module.startLabel")}</span>
            <DatePicker value={startDate} onChange={setStartDate} />
          </div>
        )}
      />

      {isError && <Card className="border-destructive"><CardContent className="pt-4 text-sm text-destructive">{t("investmentRisk.module.factorBehaviorLoadError")}</CardContent></Card>}

      {data && style && (
        <div className={isFetching ? "space-y-6 opacity-70" : "space-y-6"}>
          {(data.warnings?.length ?? 0) > 0 && (
            <Card className="border-amber-300 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/20">
              <CardContent className="space-y-1 pt-4 text-sm text-amber-900 dark:text-amber-100">
                {data.warnings.map((warning) => <p key={warning}>{warning}</p>)}
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label={t("investmentRisk.module.momentumExposure")}
              value={style.momentum_exposure == null ? "—" : style.momentum_exposure.toFixed(4)}
            />
            <MetricCard
              label={t("investmentRisk.module.lowVolExposure")}
              value={style.low_volatility_exposure == null ? "—" : style.low_volatility_exposure.toFixed(4)}
            />
            <MetricCard
              label={t("investmentRisk.module.sizeExposure")}
              value={style.size_exposure == null ? "—" : style.size_exposure.toFixed(4)}
            />
            <MetricCard
              label={t("investmentRisk.module.sectorHhi")}
              value={data.sector_concentration.hhi.toFixed(1)}
              detail={
                data.trading_behavior.turnover_pct == null
                  ? t("investmentRisk.module.noWarning")
                  : t("investmentRisk.module.turnoverShort", {
                      value: percent(data.trading_behavior.turnover_pct),
                    })
              }
            />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card className="min-h-[16rem]">
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.styleFactorExposure")}</CardTitle></CardHeader>
              <CardContent className="h-48 overflow-auto">
                <HorizontalBarList items={styleBars} formatter={(value) => value.toFixed(4)} />
              </CardContent>
            </Card>
            <Card className="min-h-[16rem]">
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.sectorConcentration")}</CardTitle></CardHeader>
              <CardContent className="h-48 overflow-auto">
                <HorizontalBarList
                  items={data.sector_concentration.weights.map((row) => ({ label: row.sector, value: row.weight_pct }))}
                  formatter={(value) => percent(value, 2)}
                />
              </CardContent>
            </Card>
          </div>

          {(style.value_weight_pct != null || style.growth_weight_pct != null) && (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard label={t("investmentRisk.module.valueWeight")} value={style.value_weight_pct == null ? "—" : percent(style.value_weight_pct)} />
              <MetricCard label={t("investmentRisk.module.growthWeight")} value={style.growth_weight_pct == null ? "—" : percent(style.growth_weight_pct)} />
              <MetricCard label={t("investmentRisk.module.largeWeight")} value={style.large_weight_pct == null ? "—" : percent(style.large_weight_pct)} />
              <MetricCard label={t("investmentRisk.module.smallWeight")} value={style.small_weight_pct == null ? "—" : percent(style.small_weight_pct)} />
            </div>
          )}

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">{t("investmentRisk.module.crowdingTop")}</CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
                      placeholder={t("investmentRisk.module.searchSecuritySector")}
                      value={crowdingQuery}
                      onChange={(event) => setCrowdingQuery(event.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={exportCrowding}>
                    <Download className="mr-2 h-4 w-4" />
                    {t("investmentRisk.module.exportShort")}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="h-72 overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("investmentRisk.module.security")}</TableHead>
                    <TableHead>{t("investmentRisk.module.sector")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.module.csvWeightShort")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.module.crowdingRatio")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredCrowding.map((row) => (
                    <TableRow key={row.security_code}>
                      <TableCell>{row.security_name}</TableCell>
                      <TableCell>{row.sector}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.weight_pct)}</TableCell>
                      <TableCell className="text-right font-mono">{row.crowding_ratio == null ? "—" : row.crowding_ratio.toFixed(3)}</TableCell>
                    </TableRow>
                  ))}
                  {!filteredCrowding.length && <EmptyRow columns={4} label={t("investmentRisk.module.emptyRow")} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {data.logic?.steps?.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{data.logic.title}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <ol className="list-decimal space-y-1 pl-5">
                  {data.logic.steps.map((step) => <li key={step}>{step}</li>)}
                </ol>
                {data.formulas ? (
                  <div className="rounded-md border bg-muted/30 p-3 font-mono text-xs">
                    <p>Momentum: {data.formulas.momentum}</p>
                    <p>LowVol: {data.formulas.low_volatility}</p>
                    <p>Size: {data.formulas.size}</p>
                    <p>HHI: {data.formulas.hhi}</p>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  )
}

export function FactorRiskRuntimePage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [startDate, setStartDate] = useState(defaultStartDate)
  const [endDate, setEndDate] = useState(lastTradeDate)
  const [benchmarkId, setBenchmarkId] = useState("")

  const benchmarks = useQuery({
    queryKey: ["attribution-benchmarks", fundId, endDate],
    queryFn: () => fsiApi.getAttributionBenchmarks(fundId, endDate).then((response) => response.data),
    retry: 1,
  })

  useEffect(() => {
    if (benchmarkId) return
    const assigned = benchmarks.data?.benchmarks.find((item) => item.assigned && item.benchmark_role === "PRIMARY")
      ?? benchmarks.data?.benchmarks.find((item) => item.assigned)
      ?? benchmarks.data?.benchmarks[0]
    if (assigned) setBenchmarkId(assigned.benchmark_id)
  }, [benchmarks.data, benchmarkId])

  const factorQuery = useQuery({
    queryKey: ["factor-risk", fundId, startDate, endDate, benchmarkId],
    queryFn: () => fsiApi.getFactorRisk(fundId, startDate, endDate, benchmarkId || undefined).then((r) => r.data),
    enabled: startDate <= endDate && Boolean(benchmarkId),
    retry: 1,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  })

  const data = factorQuery.data
  const isFetching = factorQuery.isFetching
  const isError = factorQuery.isError
  const factorRisk = data?.factor_risk
  const benchmarkOptions = (benchmarks.data?.benchmarks ?? []).map((item) => [
    item.benchmark_id,
    `${item.assigned ? "★ " : ""}${item.benchmark_name} (${item.benchmark_id})`,
  ] as const)
  const beta = factorRisk?.beta?.beta
  const tePct = factorRisk?.tracking_error?.annualized_pct
  const kpiRows = useMemo(() => {
    if (!factorRisk) return []
    return [
      {
        kpi: t("investmentRisk.module.factorBeta"),
        result: formatBeta(beta),
        formula: factorRisk.formulas?.beta ?? "β = Cov(R_p, R_b) / Var(R_b)",
      },
      {
        kpi: t("investmentRisk.module.factorTrackingError"),
        result: tePct == null ? "—" : percent(tePct),
        formula: factorRisk.formulas?.tracking_error ?? "TE = stdev(R_p - R_b) × √252",
      },
    ]
  }, [beta, factorRisk, t, tePct])

  return (
    <div id="factor-risk" className="scroll-mt-20 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("nav.factorRisk")}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t("investmentRisk.module.factorRiskSubtitle")}</p>
      </div>

      <FsiToolbar
        fundId={fundId}
        onFundChange={(id) => {
          setFundId(id)
          setBenchmarkId("")
        }}
        asOfDate={endDate}
        onDateChange={setEndDate}
        onRefresh={() => factorQuery.refetch()}
        isFetching={isFetching}
        extra={(
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground text-xs">{t("investmentRisk.module.startLabel")}</span>
            <DatePicker value={startDate} onChange={setStartDate} />
            <span className="text-muted-foreground text-xs">{t("investmentRisk.attribution.modelBenchmarkPick")}</span>
            <select
              className="h-9 min-w-[12rem] rounded-md border bg-background px-2 text-sm"
              value={benchmarkId}
              onChange={(event) => setBenchmarkId(event.target.value)}
            >
              <option value="">{t("investmentRisk.attribution.benchmarkUnset")}</option>
              {benchmarkOptions.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
            <Button
              size="sm"
              disabled={isFetching || startDate > endDate || !benchmarkId}
              onClick={() => factorQuery.refetch()}
            >
              {isFetching ? t("investmentRisk.attribution.calculating") : t("investmentRisk.attribution.modelCalc")}
            </Button>
          </div>
        )}
      />

      {isError && <Card className="border-destructive"><CardContent className="pt-4 text-sm text-destructive">{t("investmentRisk.module.factorLoadError")}</CardContent></Card>}

      <Card data-testid="engine-kpi-factor_risk">
        <CardHeader>
          <CardTitle className="text-base">{t("investmentRisk.module.factorKpiSectionTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="min-h-[8rem]">
          {kpiRows.length ? (
            <div className={`overflow-auto ${isFetching ? "opacity-70" : ""}`}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("engine.colKpi")}</TableHead>
                    <TableHead>{t("engine.colResult")}</TableHead>
                    <TableHead>{t("engine.colFormula")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {kpiRows.map((row) => (
                    <TableRow key={row.kpi}>
                      <TableCell className="font-medium">{row.kpi}</TableCell>
                      <TableCell className="font-mono text-xs" title={row.result}>{row.result}</TableCell>
                      <TableCell className="max-w-[20rem] truncate text-xs text-muted-foreground" title={row.formula}>{row.formula}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {isFetching ? t("platform.loading") : t("investmentRisk.module.factorCalcHint")}
            </p>
          )}
        </CardContent>
      </Card>

      {data && factorRisk && (
        <div className={isFetching ? "space-y-6 opacity-70" : "space-y-6"}>
          {(data.warnings?.length ?? 0) > 0 && (
            <Card className="border-amber-300 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/20">
              <CardContent className="space-y-1 pt-4 text-sm text-amber-900 dark:text-amber-100">
                {data.warnings.map((warning) => <p key={warning}>{warning}</p>)}
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <MetricCard
              label={t("investmentRisk.module.factorExposureTop")}
              value={factorRisk.factor_exposure[0] ? `${factorRisk.factor_exposure[0].factor} ${percent(factorRisk.factor_exposure[0].pct_nav)}` : "—"}
            />
            <MetricCard label={t("investmentRisk.module.factorBeta")} value={formatBeta(beta)} />
            <MetricCard
              label={t("investmentRisk.module.factorTrackingError")}
              value={tePct == null ? "—" : percent(tePct)}
            />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card className="min-h-[16rem]">
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.factorExposureTitle")}</CardTitle></CardHeader>
              <CardContent className="h-48 overflow-auto">
                <HorizontalBarList
                  items={factorRisk.factor_exposure.map((row) => ({ label: row.factor, value: Math.abs(row.pct_nav) }))}
                  formatter={(value) => percent(value)}
                />
              </CardContent>
            </Card>
            <Card className="min-h-[16rem]">
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.factorShockTitle")}</CardTitle></CardHeader>
              <CardContent className="h-48 overflow-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("investmentRisk.module.factorName")}</TableHead>
                      <TableHead className="text-right">PnL</TableHead>
                      <TableHead className="text-right">% NAV</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {factorRisk.factor_shocks.map((row) => (
                      <TableRow key={row.factor}>
                        <TableCell className="font-medium">{row.factor}</TableCell>
                        <TableCell className="text-right font-mono">{money(row.pnl)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.pnl_pct_nav)}</TableCell>
                      </TableRow>
                    ))}
                    {!factorRisk.factor_shocks.length && <EmptyRow columns={3} label={t("investmentRisk.module.emptyRow")} />}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          <Card className="min-h-[16rem]">
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.factorRcByClass")}</CardTitle></CardHeader>
            <CardContent className="h-48 overflow-auto">
              <HorizontalBarList
                items={factorRisk.risk_contribution_by_asset_class.map((row) => ({ label: row.asset_class, value: Math.abs(row.share_pct) }))}
                formatter={(value) => percent(value)}
              />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: ReactNode }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className="mt-1 text-xl font-semibold">{value}</p>
        {detail ? <div className="text-muted-foreground mt-1 text-xs">{detail}</div> : null}
      </CardContent>
    </Card>
  )
}

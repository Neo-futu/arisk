import { useQuery } from "@tanstack/react-query"
import { Download, Search } from "lucide-react"
import { useMemo, useState } from "react"
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
  const [assetClass, setAssetClass] = useState("BOND_CORP")
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
  })

  function exportScenario() {
    if (!data) return
    exportCsv(
      `investment-risk-pretrade-${fundId}-${asOfDate}.csv`,
      [t("investmentRisk.module.csvMetric"), t("investmentRisk.module.csvCurrent"), t("investmentRisk.module.csvProjected"), t("investmentRisk.module.csvLimit")],
      [
        [t("investmentRisk.module.csvDurationYears"), data.current.duration_years, data.projected.duration_years, data.limits.duration_years],
        ["Issuer % NAV", data.current.issuer_pct_nav, data.projected.issuer_pct_nav, data.limits.issuer_pct_nav],
        ["Tracking Error Proxy", "—", data.projected.tracking_error_proxy_pct, data.limits.tracking_error_proxy_pct],
      ],
    )
  }

  const extra = (
    <div className="flex flex-wrap items-center gap-2">
      <Select value={tradeSide} onValueChange={(v: "BUY" | "SELL") => setTradeSide(v)}><SelectTrigger className="w-24"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="BUY">BUY</SelectItem><SelectItem value="SELL">SELL</SelectItem></SelectContent></Select>
      <Input className="w-36" value={tradeAmount} onChange={(e) => setTradeAmount(e.target.value)} placeholder={t("investmentRisk.module.tradeAmountPlaceholder")} />
      <Input className="w-32" value={assetClass} onChange={(e) => setAssetClass(e.target.value)} placeholder={t("investmentRisk.module.assetClassPlaceholder")} />
      <Input className="w-28" value={durationYears} onChange={(e) => setDurationYears(e.target.value)} placeholder={t("investmentRisk.module.durationPlaceholder")} />
      <Input className="w-40" value={issuerName} onChange={(e) => setIssuerName(e.target.value)} placeholder="Issuer" />
    </div>
  )

  return (
    <div id="risk-budget" className="scroll-mt-20 space-y-6">
      <div><div className="mb-1 flex items-center gap-2"><Badge variant="outline">{t("investmentRisk.module.tag")}</Badge><span className="text-muted-foreground text-sm">{t("investmentRisk.module.pretradeBudgetLabel")}</span></div><h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.module.topics.pretrade-budget.title")}</h1></div>
      <FsiToolbar fundId={fundId} onFundChange={setFundId} asOfDate={asOfDate} onDateChange={setAsOfDate} onRefresh={() => refetch()} isFetching={isFetching} extra={extra} />
      <EngineKpiPanel domain="risk_budget" fundId={fundId} asOfDate={asOfDate} />
      {isError && <Card className="border-destructive"><CardContent className="pt-4 text-sm text-destructive">{t("investmentRisk.module.pretradeLoadError")}</CardContent></Card>}
      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label={t("investmentRisk.module.decision")} value={data.decision} detail={data.breach_flags.join("；") || t("investmentRisk.module.noAnomaly")} />
            <MetricCard label={t("investmentRisk.module.currentDuration")} value={data.current.duration_years.toFixed(3)} detail={t("investmentRisk.common.years")} />
            <MetricCard label={t("investmentRisk.module.projectedDuration")} value={data.projected.duration_years.toFixed(3)} detail={t("investmentRisk.common.years")} />
            <MetricCard label={t("investmentRisk.module.tradeImpact")} value={percent(data.projected.tracking_error_proxy_pct)} detail="% NAV" />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.durationLimitTrack")}</CardTitle></CardHeader>
              <CardContent>
                <TrendLineChart
                  values={[data.current.duration_years, data.projected.duration_years, data.limits.duration_years]}
                  labels={[t("investmentRisk.module.currentCol"), t("investmentRisk.module.projectedCol"), t("investmentRisk.module.limitColShort")]}
                  lineColor="#ea580c"
                  pointColor="#fb923c"
                />
              </CardContent>
            </Card>

            <Card>
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
                <p>{t("investmentRisk.module.tradeSide", { value: data.trade.trade_side })}</p>
                <p>{t("investmentRisk.module.tradeAmount", { value: money(data.trade.trade_amount) })}</p>
                <p>{t("investmentRisk.module.tradeAssetClass", { value: data.trade.asset_class })}</p>
                <p>{t("investmentRisk.module.tradeIssuer", { value: data.trade.issuer_name })}</p>
                <p>{t("investmentRisk.module.decisionResult", { value: data.decision })}</p>
                <p>{t("investmentRisk.module.alertLabel", { value: data.breach_flags.join("；") || t("investmentRisk.module.noAnomaly") })}</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.limitComparison")}</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.module.metricCol2")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.currentCol")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.projectedCol")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.limitColShort")}</TableHead></TableRow></TableHeader>
                <TableBody>
                  <TableRow><TableCell>{t("investmentRisk.module.durationYearsRow")}</TableCell><TableCell className="text-right font-mono">{data.current.duration_years.toFixed(3)}</TableCell><TableCell className="text-right font-mono">{data.projected.duration_years.toFixed(3)}</TableCell><TableCell className="text-right font-mono">{data.limits.duration_years.toFixed(2)}</TableCell></TableRow>
                  <TableRow><TableCell>{t("investmentRisk.module.issuerPctNavRow")}</TableCell><TableCell className="text-right font-mono">{percent(data.current.issuer_pct_nav)}</TableCell><TableCell className="text-right font-mono">{percent(data.projected.issuer_pct_nav)}</TableCell><TableCell className="text-right font-mono">{percent(data.limits.issuer_pct_nav)}</TableCell></TableRow>
                  <TableRow><TableCell>Tracking Error Proxy</TableCell><TableCell className="text-right font-mono">—</TableCell><TableCell className="text-right font-mono">{percent(data.projected.tracking_error_proxy_pct)}</TableCell><TableCell className="text-right font-mono">{percent(data.limits.tracking_error_proxy_pct)}</TableCell></TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
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
  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["factor-behavior", fundId, startDate, endDate],
    queryFn: () => fsiApi.getFactorBehavior(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })

  const filteredCrowding = useMemo(() => {
    const rows = data?.trading_behavior.crowding_top ?? []
    return rows.filter((row) => `${row.security_code} ${row.security_name} ${row.sector}`.toLowerCase().includes(crowdingQuery.toLowerCase()))
  }, [data?.trading_behavior.crowding_top, crowdingQuery])

  function exportCrowding() {
    if (!data) return
    exportCsv(
      `investment-risk-factor-${fundId}-${endDate}.csv`,
      [t("investmentRisk.module.csvCode"), t("investmentRisk.module.csvName2"), t("investmentRisk.module.csvSector"), t("investmentRisk.module.csvWeightShort"), t("investmentRisk.module.csvAvgVolume"), t("investmentRisk.module.csvPositionQty"), t("investmentRisk.module.csvCrowdingRatio")],
      filteredCrowding.map((row) => [row.security_code, row.security_name, row.sector, row.weight_pct, row.avg_daily_volume, row.position_quantity, row.crowding_ratio]),
    )
  }

  const extra = <div className="flex items-center gap-2"><span className="text-muted-foreground text-xs">{t("investmentRisk.module.startLabel")}</span><DatePicker value={startDate} onChange={setStartDate} /></div>

  return (
    <div id="factor-risk" className="scroll-mt-20 space-y-6">
      <div><div className="mb-1 flex items-center gap-2"><Badge variant="outline">{t("investmentRisk.module.tag")}</Badge><span className="text-muted-foreground text-sm">{t("investmentRisk.module.factorBehaviorLabel")}</span></div><h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.module.topics.factor-behavior.title")}</h1></div>
      <FsiToolbar fundId={fundId} onFundChange={setFundId} asOfDate={endDate} onDateChange={setEndDate} onRefresh={() => refetch()} isFetching={isFetching} extra={extra} />
      <EngineKpiPanel domain="factor_risk" fundId={fundId} asOfDate={endDate} />
      <EngineKpiPanel domain="factor_behavior" fundId={fundId} asOfDate={endDate} title={t("nav.factorBehavior")} />
      {isError && <Card className="border-destructive"><CardContent className="pt-4 text-sm text-destructive">{t("investmentRisk.module.factorLoadError")}</CardContent></Card>}
      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label={t("investmentRisk.module.momentumExposure")} value={data.style_exposure.momentum_exposure == null ? "—" : data.style_exposure.momentum_exposure.toFixed(4)} />
            <MetricCard label={t("investmentRisk.module.lowVolExposure")} value={data.style_exposure.low_volatility_exposure == null ? "—" : data.style_exposure.low_volatility_exposure.toFixed(4)} />
            <MetricCard label={t("investmentRisk.module.sizeExposure")} value={data.style_exposure.size_exposure == null ? "—" : data.style_exposure.size_exposure.toFixed(4)} />
            <MetricCard label={t("investmentRisk.module.sectorHhi")} value={data.sector_concentration.hhi.toFixed(1)} detail={data.warnings.join("；") || t("investmentRisk.module.noWarning")} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.styleFactorExposure")}</CardTitle></CardHeader>
              <CardContent>
                <HorizontalBarList
                  items={[
                    { label: "Momentum", value: Math.abs(data.style_exposure.momentum_exposure ?? 0) },
                    { label: "LowVol", value: Math.abs(data.style_exposure.low_volatility_exposure ?? 0) },
                    { label: "Size", value: Math.abs(data.style_exposure.size_exposure ?? 0) },
                    { label: "Coverage", value: data.style_exposure.coverage_weight },
                  ]}
                  formatter={(value) => value.toFixed(4)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.module.sectorConcentration")}</CardTitle></CardHeader>
              <CardContent>
                <HorizontalBarList
                  items={data.sector_concentration.weights.map((row) => ({ label: row.sector, value: row.weight_pct }))}
                  formatter={(value) => percent(value, 2)}
                />
              </CardContent>
            </Card>
          </div>

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
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.module.security")}</TableHead><TableHead>{t("investmentRisk.module.sector")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.csvWeightShort")}</TableHead><TableHead className="text-right">{t("investmentRisk.module.crowdingRatio")}</TableHead></TableRow></TableHeader>
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
        </>
      )}
    </div>
  )
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className="mt-1 text-xl font-semibold">{value}</p>
        {detail ? <p className="text-muted-foreground mt-1 text-xs">{detail}</p> : null}
      </CardContent>
    </Card>
  )
}

import { useMutation, useQuery } from "@tanstack/react-query"
import { AlertTriangle, Download, Play, ShieldCheck } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import type { AxiosError } from "axios"

import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import {
  fsiApi,
  type RiskTestingAnalytic,
  type RiskTestingHoldings,
  type RiskTestingReport,
  type RiskTestingRunRequest,
  type RiskTestingShock,
} from "@/fsiClient"
import { exportCsv } from "@/modules/investment-risk/dashboard-kit"
import { useBindPageContext } from "@/platform/page-context"

type RiskTestingPath =
  | "/risk-testing/sensitivity" | "/risk-testing/stress" | "/risk-testing/scenario"
  | "/risk-testing/reverse-stress" | "/risk-testing/tail-risk" | "/risk-testing/krd"
  | "/risk-testing/pnl-explain" | "/risk-testing/historical-backtest"
  | "/risk-testing/var-backtest" | "/risk-testing/xva"

const ANALYTICS: Array<{ analytic: RiskTestingAnalytic; path: RiskTestingPath; label: string; description: string }> = [
  { analytic: "SENSITIVITY", path: "/risk-testing/sensitivity", label: "敏感度测试", description: "单一风险因子 PV / Delta / Gamma 重估" },
  { analytic: "STRESS", path: "/risk-testing/stress", label: "压力测试", description: "历史及假设压力情景冲击" },
  { analytic: "SCENARIO", path: "/risk-testing/scenario", label: "情景测试", description: "多因子同步变化与组合损益" },
  { analytic: "REVERSE_STRESS", path: "/risk-testing/reverse-stress", label: "反向压力测试", description: "由损失临界点反推灾难冲击" },
  { analytic: "TAIL_RISK", path: "/risk-testing/tail-risk", label: "尾部风险测试", description: "3σ–5σ、VaR、CVaR 与资本充足率" },
  { analytic: "KRD", path: "/risk-testing/krd", label: "关键利率久期 KRD", description: "期限节点 PV01 与关键利率久期" },
  { analytic: "PNL_EXPLAIN", path: "/risk-testing/pnl-explain", label: "PnL 归因", description: "Carry、利率、外汇、持仓与残差解释" },
  { analytic: "HISTORICAL_BACKTEST", path: "/risk-testing/historical-backtest", label: "历史收益回测", description: "以当前持仓或调整后权重回放区间真实市场行情" },
  { analytic: "VAR_BACKTEST", path: "/risk-testing/var-backtest", label: "VaR 回测", description: "滚动历史 VaR、例外与 Kupiec 检验" },
  { analytic: "XVA", path: "/risk-testing/xva", label: "估值调整 XVA", description: "CVA、DVA、FVA、MVA 暴露积分" },
]

const RANGE_ANALYTICS = new Set<RiskTestingAnalytic>([
  "TAIL_RISK",
  "PNL_EXPLAIN",
  "HISTORICAL_BACKTEST",
  "VAR_BACKTEST",
])

const DEFAULT_CUSTOM_SHOCKS = JSON.stringify([
  { factor_type: "RATE", value: 0.0075, mode: "ABSOLUTE", label: "利率 +75bps" },
  { factor_type: "EQUITY", value: -0.08, mode: "RELATIVE", label: "权益 -8%" },
], null, 2)

const STANDARD_SENSITIVITY_SHOCKS: RiskTestingShock[] = [
  { factor_type: "RATE", value: 0.0001, mode: "ABSOLUTE", label: "利率 +1bp" },
  { factor_type: "FX", value: 0.01, mode: "RELATIVE", label: "外汇 +1%" },
  { factor_type: "VOLATILITY", value: 0.10, mode: "RELATIVE", label: "波动率 +10%" },
  { factor_type: "EQUITY", value: 0.01, mode: "RELATIVE", label: "权益 +1%" },
  { factor_type: "CREDIT_SPREAD", value: 0.0001, mode: "ABSOLUTE", label: "信用利差 +1bp" },
]

function number(value: unknown, digits = 2) {
  return typeof value === "number" ? value.toLocaleString("zh-HK", { maximumFractionDigits: digits }) : "—"
}

function pct(value: number | undefined) {
  if (typeof value !== "number") return "—"
  return `${(value * 100).toFixed(2)}%`
}

function bps(value: number | undefined) {
  if (typeof value !== "number") return "—"
  return `${(value * 10000).toFixed(1)} bps`
}

function reportRows(report: RiskTestingReport | undefined): Array<Record<string, unknown>> {
  if (!report) return []
  const keys = ["backtest_points", "sensitivities", "buckets", "positions", "tail_scenarios", "points", "trade_values", "exposure_profile"]
  for (const key of keys) {
    if (Array.isArray(report[key])) return report[key] as Array<Record<string, unknown>>
  }
  return []
}

function mapPositionsToRiskTestingHoldings(
  fundId: string,
  asOfDate: string,
  positions: Array<{ asset_id: string; asset_name: string; asset_type: string; market_value_hkd?: number | null; market_value?: number | null; weight_pct?: number | null }>,
): RiskTestingHoldings {
  const totalByValue = positions.reduce(
    (sum, position) => sum + Math.max(Number(position.market_value_hkd ?? position.market_value ?? 0), 0),
    0,
  )
  return {
    fund_id: fundId,
    requested_date: asOfDate,
    effective_date: asOfDate,
    reporting_currency: "HKD",
    holdings: positions.map((position) => {
      const marketValue = Number(position.market_value_hkd ?? position.market_value ?? 0)
      const currentWeightPct = typeof position.weight_pct === "number"
        ? position.weight_pct
        : totalByValue > 0
          ? Math.max(marketValue, 0) / totalByValue * 100
          : 0
      return {
        security_code: position.asset_id,
        security_name: position.asset_name,
        asset_class: position.asset_type,
        market_value_base: marketValue,
        current_weight_pct: currentWeightPct,
      }
    }),
  }
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as AxiosError<{ detail?: unknown }>
  const detail = axiosError?.response?.data?.detail
  if (typeof detail === "string" && detail.trim().length > 0) return detail
  return fallback
}

function BacktestCurve({ points }: { points: Array<Record<string, unknown>> }) {
  const values = points
    .map((point) => Number(point.cumulative_return_pct))
    .filter((value) => Number.isFinite(value))
  if (values.length < 2) return null
  const width = 960
  const height = 240
  const padding = 24
  const minimum = Math.min(...values, 0)
  const maximum = Math.max(...values, 0)
  const span = maximum - minimum || 1
  const coordinates = values.map((value, index) => {
    const x = padding + (index / (values.length - 1)) * (width - padding * 2)
    const y = padding + ((maximum - value) / span) * (height - padding * 2)
    return `${x},${y}`
  }).join(" ")
  const zeroY = padding + ((maximum - 0) / span) * (height - padding * 2)
  return (
    <div className="overflow-hidden rounded-lg border bg-muted/20 p-3">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-60 w-full" role="img" aria-label="累计收益曲线">
        <line x1={padding} y1={zeroY} x2={width - padding} y2={zeroY} stroke="currentColor" opacity="0.2" />
        <polyline points={coordinates} fill="none" stroke="currentColor" strokeWidth="3" className="text-emerald-600" />
      </svg>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{String(points[0]?.date ?? "")}</span>
        <span>累计收益 {number(values[values.length - 1], 3)}%</span>
        <span>{String(points[points.length - 1]?.date ?? "")}</span>
      </div>
    </div>
  )
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-xl font-semibold">{value}</div>{detail ? <div className="mt-1 text-xs text-muted-foreground">{detail}</div> : null}</CardContent></Card>
}

function ResultTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  const columns = useMemo(() => {
    const keys = new Set<string>()
    for (const row of rows.slice(0, 20)) for (const key of Object.keys(row)) if (typeof row[key] !== "object") keys.add(key)
    return Array.from(keys).slice(0, 10)
  }, [rows])
  if (!rows.length) return <div className="py-12 text-center text-sm text-muted-foreground">当前结果没有明细行</div>
  return (
    <div className="max-h-[34rem] overflow-auto rounded-lg border">
      <Table>
        <TableHeader><TableRow>{columns.map((column) => <TableHead key={column}>{column}</TableHead>)}</TableRow></TableHeader>
        <TableBody>{rows.map((row, index) => (
          <TableRow key={index}>{columns.map((column) => (
            <TableCell key={column} className="font-mono text-xs">
              {typeof row[column] === "number" ? number(row[column], 6) : String(row[column] ?? "—")}
            </TableCell>
          ))}</TableRow>
        ))}</TableBody>
      </Table>
    </div>
  )
}

export function RiskTestingPage({ analytic }: { analytic: RiskTestingAnalytic }) {
  const meta = ANALYTICS.find((item) => item.analytic === analytic) ?? ANALYTICS[0]
  const isRangeAnalytic = RANGE_ANALYTICS.has(analytic)
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(() => lastTradeDate())
  const [startDate, setStartDate] = useState(() => { const d = new Date(`${lastTradeDate()}T00:00:00`); d.setDate(d.getDate() - 365); return d.toISOString().slice(0, 10) })
  const [scenarioId, setScenarioId] = useState("gfc_2008")
  const [sensitivityMode, setSensitivityMode] = useState<"SINGLE" | "STANDARD">("STANDARD")
  const [factorType, setFactorType] = useState<RiskTestingShock["factor_type"]>("RATE")
  const [shockValue, setShockValue] = useState("0.0001")
  const [shockMode, setShockMode] = useState<RiskTestingShock["mode"]>("ABSOLUTE")
  const [customShocks, setCustomShocks] = useState(DEFAULT_CUSTOM_SHOCKS)
  const [rateBump, setRateBump] = useState("1")
  const [targetLoss, setTargetLoss] = useState("10")
  const [capitalBuffer, setCapitalBuffer] = useState("10")
  const [confidence, setConfidence] = useState("0.99")
  const [backtestWindow, setBacktestWindow] = useState("60")
  const [xvaHazard, setXvaHazard] = useState("0.02")
  const [weightMode, setWeightMode] = useState<"CURRENT" | "CUSTOM">("CURRENT")
  const [customWeights, setCustomWeights] = useState<Record<string, string>>({})
  const catalog = useQuery({ queryKey: ["risk-testing-catalog"], queryFn: () => fsiApi.getRiskTestingCatalog().then((r) => r.data.items), staleTime: 300_000 })
  const holdings = useQuery({
    queryKey: ["risk-testing-holdings", fundId, asOfDate],
    queryFn: async () => {
      try {
        const preferred = await fsiApi.getRiskTestingHoldings(fundId, asOfDate).then((response) => response.data)
        if ((preferred.holdings?.length ?? 0) > 0) return preferred
      } catch {
        // fall through to positions API
      }
      try {
        const fallback = await fsiApi.getPositions(fundId, asOfDate).then((response) => response.data)
        const mapped = mapPositionsToRiskTestingHoldings(fundId, asOfDate, fallback.positions)
        if ((mapped.holdings?.length ?? 0) > 0) return mapped
      } catch (error) {
        const status = (error as { response?: { status?: number } })?.response?.status
        if (status !== 404) throw error
      }
      return mapPositionsToRiskTestingHoldings(fundId, asOfDate, [])
    },
    enabled: analytic === "HISTORICAL_BACKTEST",
    retry: false,
    refetchOnWindowFocus: false,
  })

  useEffect(() => {
    const effective = holdings.data?.effective_date
    if (analytic !== "HISTORICAL_BACKTEST" || !effective || effective === asOfDate) return
    if ((holdings.data?.holdings?.length ?? 0) === 0) return
    setAsOfDate(effective)
  }, [analytic, asOfDate, holdings.data?.effective_date, holdings.data?.holdings?.length])

  const customWeightTotal = (holdings.data?.holdings ?? []).reduce(
    (sum, holding) => sum + Number(customWeights[holding.security_code] ?? holding.current_weight_pct),
    0,
  )
  const invalidRange = isRangeAnalytic && startDate >= asOfDate

  const run = useMutation({
    mutationFn: () => {
      const request: RiskTestingRunRequest = {
        analytic,
        as_of_date: asOfDate,
        scenario_id: scenarioId,
        rate_bump_bps: Number(rateBump),
        target_loss_pct_nav: Number(targetLoss),
        capital_buffer_pct_nav: Number(capitalBuffer),
        confidence: Number(confidence),
        backtest_window: Number(backtestWindow),
        counterparty_hazard: Number(xvaHazard),
      }
      if (isRangeAnalytic) request.start_date = startDate
      if (analytic === "SENSITIVITY") {
        request.shocks = sensitivityMode === "STANDARD"
          ? STANDARD_SENSITIVITY_SHOCKS
          : [{ factor_type: factorType, value: Number(shockValue), mode: shockMode, label: `${factorType} ${shockValue}` }]
      }
      if ((analytic === "SCENARIO" || analytic === "STRESS" || analytic === "REVERSE_STRESS") && scenarioId === "custom") {
        request.scenario_name = "用户自定义情景"
        request.shocks = JSON.parse(customShocks) as RiskTestingShock[]
      }
      if (analytic === "HISTORICAL_BACKTEST") {
        request.weight_mode = weightMode
        if (weightMode === "CUSTOM") {
          if ((holdings.data?.holdings?.length ?? 0) === 0 || customWeightTotal <= 0) {
            throw new Error("调整持仓权重合计必须大于 0%，请先选择有持仓的估值日")
          }
          request.custom_weights = Object.fromEntries(
            (holdings.data?.holdings ?? []).map((holding) => [
              holding.security_code,
              Number(customWeights[holding.security_code] ?? holding.current_weight_pct),
            ]),
          )
        }
      }
      return fsiApi.runRiskTest(fundId, request).then((response) => response.data)
    },
  })

  useEffect(() => {
    if (invalidRange) return
    if (analytic === "HISTORICAL_BACKTEST" && (holdings.isLoading || holdings.isError)) return
    run.mutate()
    // 仅在切换分析类型 / 基金 / 日期后自动重跑；参数微调请点「运行测试」
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analytic, fundId, asOfDate, startDate, holdings.isLoading, holdings.isError, invalidRange])

  const data = run.data
  const rows = reportRows(data)
  const totals = data?.totals as Record<string, number> | undefined
  const sensitivityUpPnl = analytic === "SENSITIVITY"
    ? rows.reduce((sum, row) => sum + (typeof row.up_pnl === "number" ? row.up_pnl : 0), 0)
    : undefined
  const primaryPnl = typeof data?.pnl === "number"
    ? data.pnl
    : typeof totals?.total === "number"
      ? totals.total
      : typeof sensitivityUpPnl === "number" && rows.length > 0
        ? sensitivityUpPnl
        : typeof rows[0]?.up_pnl === "number"
          ? rows[0].up_pnl
          : typeof rows[0]?.pv01 === "number"
            ? rows[0].pv01
            : undefined

  const selectedScenario = useMemo(
    () => (catalog.data ?? []).find((item) => item.scenario_id === scenarioId),
    [catalog.data, scenarioId],
  )

  const displayedScenarioShocks = useMemo(() => {
    if (scenarioId !== "custom") return selectedScenario?.shocks ?? []
    try {
      const parsed = JSON.parse(customShocks) as RiskTestingShock[]
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }, [customShocks, scenarioId, selectedScenario])

  const scenarioSummary = useMemo(() => {
    const equity = displayedScenarioShocks.find((s) => s.factor_type === "EQUITY")?.value
    const rate = displayedScenarioShocks.find((s) => s.factor_type === "RATE")?.value
    const creditSpread = displayedScenarioShocks.find((s) => s.factor_type === "CREDIT_SPREAD")?.value
    const volatility = displayedScenarioShocks.find((s) => s.factor_type === "VOLATILITY")?.value
    const fx = displayedScenarioShocks.find((s) => s.factor_type === "FX")?.value
    return {
      equity,
      rate,
      creditSpread,
      volatility,
      fx,
      mmfProxyRate: (rate ?? 0) + (creditSpread ?? 0),
    }
  }, [displayedScenarioShocks])

  const dataQuality = (data?.data_quality ?? {}) as Record<string, unknown>
  const effectiveDate = String(dataQuality.effective_date ?? data?.as_of_date ?? asOfDate)
  const dateFallback = Boolean(data && effectiveDate && effectiveDate !== asOfDate)

  function downloadCsv() {
    if (!rows.length) return
    const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row).filter((key) => typeof row[key] !== "object"))))
    exportCsv(
      `risk-testing-${analytic.toLowerCase()}-${fundId}-${asOfDate}.csv`,
      columns,
      rows.map((row) => columns.map((column) => {
        const value = row[column]
        if (typeof value === "number" || typeof value === "string") return value
        if (value == null) return ""
        return JSON.stringify(value)
      })),
    )
  }

  const extra = <Button onClick={() => run.mutate()} disabled={run.isPending || invalidRange}><Play className="mr-2 h-4 w-4" />{run.isPending ? "计算中…" : "运行测试"}</Button>
  useBindPageContext({
    portfolio: fundId,
    date: asOfDate,
    module: "risk-testing",
    result: data ? String(data.analytic ?? analytic) : undefined,
    chart: analytic === "HISTORICAL_BACKTEST" ? "backtest-curve" : undefined,
    riskMetrics: data ? { status: data.status, analytic: data.analytic, library: data.library } : undefined,
  })
  return (
    <div className="space-y-6" data-testid="platform-workbench">
      <div>
        <h1 className="text-2xl font-bold">{meta.label}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{meta.description}</p>
      </div>
      <div data-testid="platform-parameter">
      <FsiToolbar
        fundId={fundId}
        onFundChange={setFundId}
        startDate={isRangeAnalytic ? startDate : undefined}
        onStartDateChange={isRangeAnalytic ? setStartDate : undefined}
        startDateLabel="开始日期"
        asOfDate={asOfDate}
        onDateChange={setAsOfDate}
        asOfDateLabel={isRangeAnalytic ? "结束日期" : "估值时点"}
        onRefresh={() => { if (!invalidRange) run.mutate() }}
        isFetching={run.isPending}
        extra={extra}
      />
      </div>
      {run.isPending ? <p className="animate-pulse text-sm text-muted-foreground" data-testid="platform-loading">正在加载…</p> : null}
      {run.isError ? <p className="text-sm text-destructive" data-testid="platform-error">{apiErrorMessage(run.error, "运行失败")}</p> : null}
      {dateFallback ? (
        <Card className="border-amber-300 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/20">
          <CardContent className="pt-4 text-sm text-amber-900 dark:text-amber-100">
            请求估值日 {asOfDate} 无持仓，已自动回退到最近有效日 {effectiveDate}。
          </CardContent>
        </Card>
      ) : null}
      {!run.isPending && !run.isError && !data ? <p className="text-sm text-muted-foreground" data-testid="platform-empty">暂无数据</p> : null}

      <Card><CardHeader><CardTitle className="text-base">参数配置</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {analytic === "SENSITIVITY" ? <>
          <div className="space-y-1"><Label>冲击包</Label><Select value={sensitivityMode} onValueChange={(v) => setSensitivityMode(v as "SINGLE" | "STANDARD")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="STANDARD">标准五因子</SelectItem><SelectItem value="SINGLE">单一因子</SelectItem></SelectContent></Select></div>
          {sensitivityMode === "SINGLE" ? <>
            <div className="space-y-1"><Label>风险因子</Label><Select value={factorType} onValueChange={(v) => setFactorType(v as RiskTestingShock["factor_type"])}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["RATE", "FX", "VOLATILITY", "EQUITY", "CREDIT_SPREAD"].map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-1"><Label>冲击值</Label><Input type="number" step="0.0001" value={shockValue} onChange={(e) => setShockValue(e.target.value)} /></div>
            <div className="space-y-1"><Label>冲击模式</Label><Select value={shockMode} onValueChange={(v) => setShockMode(v as RiskTestingShock["mode"])}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="ABSOLUTE">绝对变化</SelectItem><SelectItem value="RELATIVE">相对变化</SelectItem></SelectContent></Select></div>
          </> : <div className="text-sm text-muted-foreground md:col-span-3">RATE +1bp · FX +1% · VOL +10% · EQUITY +1% · CREDIT_SPREAD +1bp</div>}
        </> : null}
        {["STRESS", "SCENARIO", "REVERSE_STRESS"].includes(analytic) ? <>
          <div className="space-y-1"><Label>情景</Label><Select value={scenarioId} onValueChange={setScenarioId}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(catalog.data ?? []).map((s) => <SelectItem key={s.scenario_id} value={s.scenario_id}>{s.name}</SelectItem>)}<SelectItem value="custom">自定义多因子情景</SelectItem></SelectContent></Select></div>
          {scenarioId === "custom" ? <div className="space-y-1 md:col-span-2 xl:col-span-3"><Label>冲击配置 JSON</Label><Textarea className="min-h-32 font-mono text-xs" value={customShocks} onChange={(e) => setCustomShocks(e.target.value)} /></div> : null}
          <div className="rounded-lg border bg-muted/30 p-3 md:col-span-2 xl:col-span-2">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-sm font-medium">情景参数明细</div>
              {scenarioId === "gfc_2008" ? <Badge variant="secondary">2008 全球金融危机</Badge> : null}
            </div>
            <div className="grid gap-2 text-xs md:grid-cols-2">
              <div>Equity 冲击: <span className="font-mono">{pct(scenarioSummary.equity)}</span></div>
              <div>MMF 利率代理: <span className="font-mono">{bps(scenarioSummary.mmfProxyRate)}</span></div>
              <div>Bond 利率冲击: <span className="font-mono">{bps(scenarioSummary.rate)}</span></div>
              <div>Bond 信用利差: <span className="font-mono">{bps(scenarioSummary.creditSpread)}</span></div>
              <div>波动率冲击: <span className="font-mono">{pct(scenarioSummary.volatility)}</span></div>
              <div>FX 冲击: <span className="font-mono">{pct(scenarioSummary.fx)}</span></div>
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              底层配置以情景 shocks 为准；MMF 采用当前模型中的利率/信用利差代理。
            </div>
            {selectedScenario?.description ? <div className="mt-2 text-xs text-muted-foreground">{selectedScenario.description}</div> : null}
          </div>
        </> : null}
        {analytic === "REVERSE_STRESS" ? <div className="space-y-1"><Label>目标损失（% NAV）</Label><Input type="number" value={targetLoss} onChange={(e) => setTargetLoss(e.target.value)} /></div> : null}
        {analytic === "TAIL_RISK" ? <div className="space-y-1"><Label>资本缓冲（% NAV）</Label><Input type="number" value={capitalBuffer} onChange={(e) => setCapitalBuffer(e.target.value)} /></div> : null}
        {analytic === "KRD" ? <div className="space-y-1"><Label>节点冲击（bps）</Label><Input type="number" value={rateBump} onChange={(e) => setRateBump(e.target.value)} /></div> : null}
        {analytic === "HISTORICAL_BACKTEST" ? <>
          <div className="space-y-1"><Label>持仓权重方式</Label><Select value={weightMode} onValueChange={(value) => setWeightMode(value as "CURRENT" | "CUSTOM")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="CURRENT">当前持仓权重</SelectItem><SelectItem value="CUSTOM">调整持仓权重</SelectItem></SelectContent></Select></div>
          <div className="flex items-end text-sm text-muted-foreground">回测采用区间首日建仓、之后买入持有；调整权重会按输入值自动归一化。</div>
          <div className="md:col-span-2 xl:col-span-4">
            <div className="mb-2 flex items-center justify-between gap-3"><Label>当前持仓与目标权重</Label><span className="text-xs text-muted-foreground">输入合计 {number(customWeightTotal, 3)}%</span></div>
            <div className="max-h-80 overflow-auto rounded-lg border">
              <Table>
                <TableHeader><TableRow><TableHead>证券</TableHead><TableHead>资产类别</TableHead><TableHead className="text-right">当前权重</TableHead><TableHead className="w-36 text-right">目标权重（%）</TableHead></TableRow></TableHeader>
                <TableBody>
                  {(holdings.data?.holdings ?? []).map((holding) => <TableRow key={holding.security_code}>
                    <TableCell><div className="font-medium">{holding.security_name}</div><div className="font-mono text-xs text-muted-foreground">{holding.security_code}</div></TableCell>
                    <TableCell>{holding.asset_class}</TableCell>
                    <TableCell className="text-right font-mono">{number(holding.current_weight_pct, 4)}%</TableCell>
                    <TableCell><Input className="text-right font-mono" type="number" min="0" step="0.01" disabled={weightMode === "CURRENT"} value={customWeights[holding.security_code] ?? String(holding.current_weight_pct)} onChange={(event) => setCustomWeights((current) => ({ ...current, [holding.security_code]: event.target.value }))} /></TableCell>
                  </TableRow>)}
                  {holdings.isLoading ? <TableRow><TableCell colSpan={4} className="py-8 text-center text-muted-foreground">正在读取当前持仓…</TableCell></TableRow> : null}
                  {!holdings.isLoading && !holdings.isError && (holdings.data?.holdings?.length ?? 0) === 0 ? <TableRow><TableCell colSpan={4} className="py-8 text-center text-muted-foreground">当前日期没有可用持仓数据，请更换组合或日期。</TableCell></TableRow> : null}
                  {holdings.isError ? <TableRow><TableCell colSpan={4} className="py-8 text-center text-destructive">读取持仓失败：请确认 backend 已更新并可访问 /api/v1/fsi/positions 与 /api/v1/fsi/risk-testing。</TableCell></TableRow> : null}
                </TableBody>
              </Table>
            </div>
          </div>
        </> : null}
        {analytic === "VAR_BACKTEST" ? <><div className="space-y-1"><Label>置信度</Label><Input type="number" step="0.001" value={confidence} onChange={(e) => setConfidence(e.target.value)} /></div><div className="space-y-1"><Label>滚动窗口</Label><Input type="number" value={backtestWindow} onChange={(e) => setBacktestWindow(e.target.value)} /></div></> : null}
        {analytic === "XVA" ? <div className="space-y-1"><Label>交易对手年化违约强度</Label><Input type="number" step="0.001" value={xvaHazard} onChange={(e) => setXvaHazard(e.target.value)} /></div> : null}
      </CardContent></Card>

      {run.isError ? <Card className="border-destructive"><CardContent className="flex items-center gap-2 pt-4 text-sm text-destructive"><AlertTriangle className="h-4 w-4" />测试失败：{apiErrorMessage(run.error, "请检查参数、估值数据与 FinancePy 运行环境")}</CardContent></Card> : null}
      {!data && !run.isPending ? <Card><CardContent className="py-16 text-center text-muted-foreground">选择组合和参数后点击“运行测试”</CardContent></Card> : null}
      {data ? <>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="组合净资产" value={`${data.reporting_currency} ${number(data.net_asset, 0)}`} />
          <Metric label="估值/冲击损益" value={number(primaryPnl, 0)} detail={data.pnl_pct_nav == null ? undefined : `${number(data.pnl_pct_nav, 4)}% NAV`} />
          <Metric label="数据持仓数" value={number((data.data_quality as Record<string, unknown>)?.position_count, 0)} detail={String((data.data_quality as Record<string, unknown>)?.effective_date ?? data.as_of_date)} />
          <Metric label="运行状态" value={String(data.status ?? "OK")} detail={`${data.library} · ${data.analytic}`} />
        </div>
        {analytic === "XVA" ? <div className="grid gap-4 md:grid-cols-4">{["cva", "dva", "fva", "mva"].map((key) => <Metric key={key} label={key.toUpperCase()} value={number(data[key], 2)} />)}</div> : null}
        {analytic === "HISTORICAL_BACKTEST" ? <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><Metric label="区间总收益" value={`${number(data.total_return_pct, 3)}%`} /><Metric label="年化收益" value={`${number(data.annualized_return_pct, 3)}%`} /><Metric label="年化波动率" value={`${number(data.annualized_volatility_pct, 3)}%`} /><Metric label="最大回撤" value={`${number(data.max_drawdown_pct, 3)}%`} /></div>
          <div data-testid="platform-charts"><BacktestCurve points={(data.backtest_points as Array<Record<string, unknown>> | undefined) ?? []} /></div>
        </> : null}
        {analytic === "VAR_BACKTEST" ? <div className="grid gap-4 md:grid-cols-4"><Metric label="例外次数" value={number(data.exceptions, 0)} /><Metric label="例外率" value={`${number(data.exception_rate_pct, 3)}%`} /><Metric label="Kupiec LR" value={number(data.kupiec_lr, 4)} /><Metric label="交通灯" value={String(data.traffic_light ?? "—")} /></div> : null}
        <Card><CardHeader><div className="flex items-center justify-between gap-3"><CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4 text-emerald-600" />结构化风险结果</CardTitle><Button variant="outline" size="sm" data-testid="platform-export" onClick={downloadCsv} disabled={!rows.length}><Download className="mr-2 h-4 w-4" />CSV / Excel</Button></div></CardHeader><CardContent data-testid="platform-data"><ResultTable rows={rows} /></CardContent></Card>
        <Card>
          <CardHeader><CardTitle className="text-base">数据质量与模型假设</CardTitle></CardHeader>
          <CardContent>
            <Tabs defaultValue="business" className="w-full">
              <TabsList>
                <TabsTrigger value="business">业务描述</TabsTrigger>
                <TabsTrigger value="json">JSON 数据</TabsTrigger>
              </TabsList>
              <TabsContent value="business" className="mt-3 space-y-3 text-sm">
                <div className="rounded-lg border bg-muted/30 p-3">
                  数据覆盖：持仓 <span className="font-mono">{String(dataQuality.position_count ?? "—")}</span> 条，行情观测 <span className="font-mono">{String(dataQuality.quote_observations ?? "—")}</span> 条，生效日期 <span className="font-mono">{String(dataQuality.effective_date ?? data.as_of_date)}</span>。
                </div>
                {analytic === "HISTORICAL_BACKTEST" ? <div className="grid gap-3 md:grid-cols-3"><Metric label="真实市场行情权重" value={`${number(dataQuality.real_market_weight_pct, 2)}%`} /><Metric label="历史估值权重" value={`${number(dataQuality.historical_valuation_weight_pct, 2)}%`} /><Metric label="代理定价权重" value={`${number(dataQuality.proxy_weight_pct, 2)}%`} /></div> : null}
                <div className="rounded-lg border bg-muted/30 p-3">
                  <div className="mb-2 font-medium">模型假设</div>
                  <ul className="list-disc space-y-1 pl-5">
                    {(Array.isArray(data.assumptions) ? data.assumptions : []).map((item, idx) => <li key={idx}>{String(item)}</li>)}
                  </ul>
                </div>
              </TabsContent>
              <TabsContent value="json" className="mt-3">
                <pre className="overflow-auto rounded-lg bg-muted p-4 text-xs">{JSON.stringify({ data_quality: data.data_quality, assumptions: data.assumptions }, null, 2)}</pre>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </> : null}
    </div>
  )
}

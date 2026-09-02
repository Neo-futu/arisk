import { useMutation, useQuery } from "@tanstack/react-query"
import { AlertTriangle, Download, Play, ShieldCheck } from "lucide-react"
import { useMemo, useState } from "react"

import { DatePicker } from "@/components/DatePicker"
import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  fsiApi,
  type RiskTestingAnalytic,
  type RiskTestingReport,
  type RiskTestingRunRequest,
  type RiskTestingShock,
} from "@/fsiClient"
import { exportCsv } from "@/modules/investment-risk/dashboard-kit"

type RiskTestingPath =
  | "/risk-testing/sensitivity" | "/risk-testing/stress" | "/risk-testing/scenario"
  | "/risk-testing/reverse-stress" | "/risk-testing/tail-risk" | "/risk-testing/krd"
  | "/risk-testing/pnl-explain" | "/risk-testing/var-backtest" | "/risk-testing/xva"

const ANALYTICS: Array<{ analytic: RiskTestingAnalytic; path: RiskTestingPath; label: string; description: string }> = [
  { analytic: "SENSITIVITY", path: "/risk-testing/sensitivity", label: "敏感度测试", description: "单一风险因子 PV / Delta / Gamma 重估" },
  { analytic: "STRESS", path: "/risk-testing/stress", label: "压力测试", description: "历史及假设压力情景冲击" },
  { analytic: "SCENARIO", path: "/risk-testing/scenario", label: "情景测试", description: "多因子同步变化与组合损益" },
  { analytic: "REVERSE_STRESS", path: "/risk-testing/reverse-stress", label: "反向压力测试", description: "由损失临界点反推灾难冲击" },
  { analytic: "TAIL_RISK", path: "/risk-testing/tail-risk", label: "尾部风险测试", description: "3σ–5σ、VaR、CVaR 与资本充足率" },
  { analytic: "KRD", path: "/risk-testing/krd", label: "关键利率久期 KRD", description: "期限节点 PV01 与关键利率久期" },
  { analytic: "PNL_EXPLAIN", path: "/risk-testing/pnl-explain", label: "PnL 归因", description: "Carry、利率、外汇、持仓与残差解释" },
  { analytic: "VAR_BACKTEST", path: "/risk-testing/var-backtest", label: "VaR 回测", description: "滚动历史 VaR、例外与 Kupiec 检验" },
  { analytic: "XVA", path: "/risk-testing/xva", label: "估值调整 XVA", description: "CVA、DVA、FVA、MVA 暴露积分" },
]

const DEFAULT_CUSTOM_SHOCKS = JSON.stringify([
  { factor_type: "RATE", value: 0.0075, mode: "ABSOLUTE", label: "利率 +75bps" },
  { factor_type: "EQUITY", value: -0.08, mode: "RELATIVE", label: "权益 -8%" },
], null, 2)

function number(value: unknown, digits = 2) {
  return typeof value === "number" ? value.toLocaleString("zh-HK", { maximumFractionDigits: digits }) : "—"
}

function reportRows(report: RiskTestingReport | undefined): Array<Record<string, unknown>> {
  if (!report) return []
  const keys = ["sensitivities", "buckets", "positions", "tail_scenarios", "points", "trade_values", "exposure_profile"]
  for (const key of keys) {
    if (Array.isArray(report[key])) return report[key] as Array<Record<string, unknown>>
  }
  return []
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
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [startDate, setStartDate] = useState(() => { const d = new Date(`${lastTradeDate()}T00:00:00`); d.setDate(d.getDate() - 365); return d.toISOString().slice(0, 10) })
  const [scenarioId, setScenarioId] = useState("gfc_2008")
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
  const catalog = useQuery({ queryKey: ["risk-testing-catalog"], queryFn: () => fsiApi.getRiskTestingCatalog().then((r) => r.data.items), staleTime: 300_000 })

  const run = useMutation({
    mutationFn: () => {
      const request: RiskTestingRunRequest = {
        analytic,
        as_of_date: asOfDate,
        start_date: startDate,
        scenario_id: scenarioId,
        rate_bump_bps: Number(rateBump),
        target_loss_pct_nav: Number(targetLoss),
        capital_buffer_pct_nav: Number(capitalBuffer),
        confidence: Number(confidence),
        backtest_window: Number(backtestWindow),
        counterparty_hazard: Number(xvaHazard),
      }
      if (analytic === "SENSITIVITY") request.shocks = [{ factor_type: factorType, value: Number(shockValue), mode: shockMode, label: `${factorType} ${shockValue}` }]
      if ((analytic === "SCENARIO" || analytic === "STRESS" || analytic === "REVERSE_STRESS") && scenarioId === "custom") {
        request.scenario_name = "用户自定义情景"
        request.shocks = JSON.parse(customShocks) as RiskTestingShock[]
      }
      return fsiApi.runRiskTest(fundId, request).then((response) => response.data)
    },
  })
  const data = run.data
  const rows = reportRows(data)
  const totals = data?.totals as Record<string, number> | undefined
  const implementation = data?.implementation as Record<string, unknown> | undefined
  const primaryPnl = typeof data?.pnl === "number"
    ? data.pnl
    : typeof totals?.total === "number"
      ? totals.total
      : typeof rows[0]?.up_pnl === "number"
        ? rows[0].up_pnl
        : typeof rows[0]?.pv01 === "number"
          ? rows[0].pv01
          : undefined

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

  const extra = <Button onClick={() => run.mutate()} disabled={run.isPending}><Play className="mr-2 h-4 w-4" />{run.isPending ? "计算中…" : "运行测试"}</Button>
  return (
    <div className="space-y-6">
      <div><div className="mb-1 flex items-center gap-2"><Badge variant="outline">FinancePy Risk Engine</Badge><span className="text-sm text-muted-foreground">{data?.engine ?? "专业组合重估"}</span></div><h1 className="text-2xl font-bold">{meta.label}</h1><p className="mt-1 text-sm text-muted-foreground">{meta.description}</p></div>
      <FsiToolbar fundId={fundId} onFundChange={setFundId} asOfDate={asOfDate} onDateChange={setAsOfDate} onRefresh={() => run.mutate()} isFetching={run.isPending} extra={extra} />

      <Card><CardHeader><CardTitle className="text-base">测试参数</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {analytic === "PNL_EXPLAIN" ? <div className="space-y-1"><Label>起始日期</Label><DatePicker value={startDate} onChange={setStartDate} /></div> : null}
        {analytic === "SENSITIVITY" ? <><div className="space-y-1"><Label>风险因子</Label><Select value={factorType} onValueChange={(v) => setFactorType(v as RiskTestingShock["factor_type"])}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["RATE", "FX", "VOLATILITY", "EQUITY", "CREDIT_SPREAD"].map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent></Select></div><div className="space-y-1"><Label>冲击值</Label><Input type="number" step="0.0001" value={shockValue} onChange={(e) => setShockValue(e.target.value)} /></div><div className="space-y-1"><Label>冲击模式</Label><Select value={shockMode} onValueChange={(v) => setShockMode(v as RiskTestingShock["mode"])}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="ABSOLUTE">绝对变化</SelectItem><SelectItem value="RELATIVE">相对变化</SelectItem></SelectContent></Select></div></> : null}
        {["STRESS", "SCENARIO", "REVERSE_STRESS"].includes(analytic) ? <><div className="space-y-1"><Label>情景</Label><Select value={scenarioId} onValueChange={setScenarioId}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(catalog.data ?? []).map((s) => <SelectItem key={s.scenario_id} value={s.scenario_id}>{s.name}</SelectItem>)}<SelectItem value="custom">自定义多因子情景</SelectItem></SelectContent></Select></div>{scenarioId === "custom" ? <div className="space-y-1 md:col-span-2 xl:col-span-3"><Label>冲击配置 JSON</Label><Textarea className="min-h-32 font-mono text-xs" value={customShocks} onChange={(e) => setCustomShocks(e.target.value)} /></div> : null}</> : null}
        {analytic === "REVERSE_STRESS" ? <div className="space-y-1"><Label>目标损失（% NAV）</Label><Input type="number" value={targetLoss} onChange={(e) => setTargetLoss(e.target.value)} /></div> : null}
        {analytic === "TAIL_RISK" ? <div className="space-y-1"><Label>资本缓冲（% NAV）</Label><Input type="number" value={capitalBuffer} onChange={(e) => setCapitalBuffer(e.target.value)} /></div> : null}
        {analytic === "KRD" ? <div className="space-y-1"><Label>节点冲击（bps）</Label><Input type="number" value={rateBump} onChange={(e) => setRateBump(e.target.value)} /></div> : null}
        {analytic === "VAR_BACKTEST" ? <><div className="space-y-1"><Label>置信度</Label><Input type="number" step="0.001" value={confidence} onChange={(e) => setConfidence(e.target.value)} /></div><div className="space-y-1"><Label>滚动窗口</Label><Input type="number" value={backtestWindow} onChange={(e) => setBacktestWindow(e.target.value)} /></div></> : null}
        {analytic === "XVA" ? <div className="space-y-1"><Label>交易对手年化违约强度</Label><Input type="number" step="0.001" value={xvaHazard} onChange={(e) => setXvaHazard(e.target.value)} /></div> : null}
      </CardContent></Card>

      {run.isError ? <Card className="border-destructive"><CardContent className="flex items-center gap-2 pt-4 text-sm text-destructive"><AlertTriangle className="h-4 w-4" />测试失败：请检查参数、估值数据与 FinancePy 运行环境。</CardContent></Card> : null}
      {!data && !run.isPending ? <Card><CardContent className="py-16 text-center text-muted-foreground">选择组合和参数后点击“运行测试”</CardContent></Card> : null}
      {data ? <>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="组合净资产" value={`${data.reporting_currency} ${number(data.net_asset, 0)}`} />
          <Metric label="估值/冲击损益" value={number(primaryPnl, 0)} detail={data.pnl_pct_nav == null ? undefined : `${number(data.pnl_pct_nav, 4)}% NAV`} />
          <Metric label="数据持仓数" value={number((data.data_quality as Record<string, unknown>)?.position_count, 0)} detail={String((data.data_quality as Record<string, unknown>)?.effective_date ?? data.as_of_date)} />
          <Metric label="运行状态" value={String(data.status ?? "OK")} detail={`${data.library} · ${data.analytic}`} />
        </div>
        {analytic === "XVA" ? <div className="grid gap-4 md:grid-cols-4">{["cva", "dva", "fva", "mva"].map((key) => <Metric key={key} label={key.toUpperCase()} value={number(data[key], 2)} />)}</div> : null}
        {analytic === "VAR_BACKTEST" ? <div className="grid gap-4 md:grid-cols-4"><Metric label="例外次数" value={number(data.exceptions, 0)} /><Metric label="例外率" value={`${number(data.exception_rate_pct, 3)}%`} /><Metric label="Kupiec LR" value={number(data.kupiec_lr, 4)} /><Metric label="交通灯" value={String(data.traffic_light ?? "—")} /></div> : null}
        <Card><CardHeader><div className="flex items-center justify-between gap-3"><CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4 text-emerald-600" />结构化风险结果</CardTitle><Button variant="outline" size="sm" onClick={downloadCsv} disabled={!rows.length}><Download className="mr-2 h-4 w-4" />CSV / Excel</Button></div></CardHeader><CardContent><ResultTable rows={rows} /></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-base">Python 模块与 FinancePy 调用链</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-lg bg-muted p-4 text-xs">{JSON.stringify(implementation ?? {}, null, 2)}</pre></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-base">数据质量与模型假设</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-lg bg-muted p-4 text-xs">{JSON.stringify({ data_quality: data.data_quality, assumptions: data.assumptions }, null, 2)}</pre></CardContent></Card>
      </> : null}
    </div>
  )
}

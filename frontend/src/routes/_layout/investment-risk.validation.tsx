import { createFileRoute } from "@tanstack/react-router"
import { useMemo, useState } from "react"

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
import {
  callEndpoint,
  safeJson,
  summarize,
  type IndicatorResult,
  type RunnerParams,
} from "@/modules/investment-risk/indicatorRunner"
import {
  PROCESSING_INDICATORS,
  type EndpointKey,
  type ProcessingIndicator,
} from "@/modules/investment-risk/processingIndicatorCatalog"

export const Route = createFileRoute("/_layout/investment-risk/validation")({
  component: InvestmentRiskValidationPage,
  head: () => ({ meta: [{ title: "指標驗證 — 投資風險分析 — ARISK" }] }),
})

function shiftDate(dateText: string, offsetDays: number) {
  const date = new Date(`${dateText}T00:00:00`)
  date.setDate(date.getDate() + offsetDays)
  return date.toISOString().split("T")[0]
}

function InvestmentRiskValidationPage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [scope, setScope] = useState<"single" | "all">("single")
  const [category, setCategory] = useState("ALL")
  const [startDate, setStartDate] = useState(() => shiftDate(lastTradeDate(), -90))
  const [endDate, setEndDate] = useState(lastTradeDate)
  const [redemptionPct, setRedemptionPct] = useState("20")
  const [rateShockBps, setRateShockBps] = useState("50")
  const [tradeAmount, setTradeAmount] = useState("10000000")
  const [tradeSide, setTradeSide] = useState<"BUY" | "SELL">("BUY")
  const [assetClass, setAssetClass] = useState("BOND_CORP")
  const [durationYears, setDurationYears] = useState("2")
  const [issuerName, setIssuerName] = useState("UNKNOWN_ISSUER")
  const [confidence, setConfidence] = useState("0.99")
  const [horizonDays, setHorizonDays] = useState("1")
  const [results, setResults] = useState<Record<string, IndicatorResult>>({})
  const [runningAll, setRunningAll] = useState(false)

  const categories = useMemo(
    () => ["ALL", ...Array.from(new Set(PROCESSING_INDICATORS.map((item) => item.category)))],
    [],
  )

  const filteredIndicators = useMemo(() => {
    return PROCESSING_INDICATORS.filter((item) => category === "ALL" || item.category === category)
  }, [category])

  const targets = scope === "single" ? [fundId] : FUNDS.map((f) => f.id)

  const runnerParams: RunnerParams = {
    asOfDate,
    startDate,
    endDate,
    redemptionPct: Number(redemptionPct),
    rateShockBps: Number(rateShockBps),
    tradeAmount: Number(tradeAmount),
    tradeSide,
    assetClass,
    durationYears: Number(durationYears),
    issuerName,
    confidence: Number(confidence),
    horizonDays: Number(horizonDays),
  }

  async function runIndicator(item: ProcessingIndicator) {
    if (!item.endpointKey) {
      setResults((previous) => ({
        ...previous,
        [item.id]: {
          running: false,
          ok: false,
          latencyMs: 0,
          outputPreview: "—",
          message: "該指標尚未掛接前端可調用 API，僅做映射展示。",
        },
      }))
      return
    }

    const started = Date.now()
    setResults((previous) => ({
      ...previous,
      [item.id]: {
        running: true,
        ok: false,
        latencyMs: 0,
        outputPreview: "執行中...",
      },
    }))

    try {
      const allOutputs = await Promise.all(
        targets.map(async (target) => {
          const payload = await callEndpoint(item.endpointKey as EndpointKey, target, runnerParams)
          return {
            fundId: target,
            summary: summarize(item.endpointKey as EndpointKey, payload),
            payload,
          }
        }),
      )
      const first = allOutputs[0]
      setResults((previous) => ({
        ...previous,
        [item.id]: {
          running: false,
          ok: true,
          latencyMs: Date.now() - started,
          outputPreview: first.summary,
          rawOutput: scope === "single" ? first.payload : allOutputs,
        },
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setResults((previous) => ({
        ...previous,
        [item.id]: {
          running: false,
          ok: false,
          latencyMs: Date.now() - started,
          outputPreview: "失敗",
          message,
        },
      }))
    }
  }

  async function runAllIndicators() {
    setRunningAll(true)
    try {
      for (const item of filteredIndicators) {
        await runIndicator(item)
      }
    } finally {
      setRunningAll(false)
    }
  }

  const summary = useMemo(() => {
    const selectedResults = filteredIndicators.map((item) => results[item.id]).filter(Boolean)
    const passed = selectedResults.filter((result) => result.ok).length
    const failed = selectedResults.filter((result) => !result.ok && !result.running).length
    return {
      total: filteredIndicators.length,
      executed: selectedResults.length,
      passed,
      failed,
    }
  }, [filteredIndicators, results])

  const scopeSelect = (
    <div className="flex items-center gap-2">
      <Select value={scope} onValueChange={(value: "single" | "all") => setScope(value)}>
        <SelectTrigger className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="single">單一組合</SelectItem>
          <SelectItem value="all">全部組合</SelectItem>
        </SelectContent>
      </Select>
      <Select value={category} onValueChange={setCategory}>
        <SelectTrigger className="w-44">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {categories.map((item) => (
            <SelectItem key={item} value={item}>{item}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )

  const tradeSideSelect = (
    <Select value={tradeSide} onValueChange={(value: "BUY" | "SELL") => setTradeSide(value)}>
      <SelectTrigger className="w-40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="BUY">BUY</SelectItem>
        <SelectItem value="SELL">SELL</SelectItem>
      </SelectContent>
    </Select>
  )

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <Badge variant="outline">投資風險分析</Badge>
          <span className="text-muted-foreground text-sm">指標驗證</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">指標驗證</h1>
        <p className="text-muted-foreground text-sm">
          每個指標一個手工測試按鈕，支持輸入參數、逐條執行、查看輸出結果。
        </p>
      </div>

      <FsiToolbar
        fundId={fundId}
        onFundChange={setFundId}
        asOfDate={asOfDate}
        onDateChange={setAsOfDate}
        onRefresh={() => {
          setResults({})
        }}
        isFetching={runningAll}
        extra={scopeSelect}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">基本輸入參數</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <p className="text-xs text-muted-foreground">開始日期（區間型指標）</p>
            <Input value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">結束日期（區間型指標）</p>
            <Input value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">流動性壓測贖回(%)</p>
            <Input value={redemptionPct} onChange={(event) => setRedemptionPct(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">流動性壓測利率(bps)</p>
            <Input value={rateShockBps} onChange={(event) => setRateShockBps(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">前置試算交易金額</p>
            <Input value={tradeAmount} onChange={(event) => setTradeAmount(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">前置試算方向</p>
            {tradeSideSelect}
          </div>
          <div>
            <p className="text-xs text-muted-foreground">前置試算資產類別</p>
            <Input value={assetClass} onChange={(event) => setAssetClass(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">前置試算久期(年)</p>
            <Input value={durationYears} onChange={(event) => setDurationYears(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">前置試算Issuer</p>
            <Input value={issuerName} onChange={(event) => setIssuerName(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">VaR置信度</p>
            <Input value={confidence} onChange={(event) => setConfidence(event.target.value)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">VaR持有期(天)</p>
            <Input value={horizonDays} onChange={(event) => setHorizonDays(event.target.value)} />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard label="當前指標數" value={`${summary.total}`} />
        <MetricCard label="已執行" value={`${summary.executed}`} />
        <MetricCard label="通過" value={`${summary.passed}`} />
        <MetricCard label="失敗" value={`${summary.failed}`} />
      </div>

      <div className="flex items-center gap-2">
        <Button onClick={runAllIndicators} disabled={runningAll}>
          {runningAll ? "批量執行中..." : "執行當前分類全部指標"}
        </Button>
        <Button variant="outline" onClick={() => setResults({})}>清空輸出</Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">逐項手工驗證</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>指標</TableHead>
                <TableHead>來源</TableHead>
                <TableHead>操作</TableHead>
                <TableHead>狀態</TableHead>
                <TableHead>輸出預覽</TableHead>
                <TableHead className="text-right">耗時(ms)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredIndicators.map((item) => {
                const result = results[item.id]
                const running = result?.running ?? false
                return (
                  <TableRow key={item.id}>
                    <TableCell>
                      <p className="font-medium">{item.title}</p>
                      <p className="text-xs text-muted-foreground">{item.id}</p>
                      {item.note ? <p className="text-xs text-muted-foreground">{item.note}</p> : null}
                    </TableCell>
                    <TableCell className="text-xs">
                      <p>SQL: {item.sqlFile ?? "—"}</p>
                      <p>PY: {item.toolFile}</p>
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        disabled={running}
                        onClick={() => runIndicator(item)}
                      >
                        {running ? "執行中..." : "測試"}
                      </Button>
                    </TableCell>
                    <TableCell>
                      {!item.endpointKey && <Badge variant="secondary">待接入API</Badge>}
                      {item.endpointKey && !result && <Badge variant="outline">未執行</Badge>}
                      {result?.ok && <Badge variant="outline">通過</Badge>}
                      {result && !result.ok && !result.running && <Badge variant="destructive">失敗</Badge>}
                    </TableCell>
                    <TableCell>
                      {result ? (
                        <div className="space-y-1">
                          <p className="text-xs font-mono">{result.outputPreview}</p>
                          {result.message ? <p className="text-xs text-destructive">{result.message}</p> : null}
                          {result.rawOutput !== undefined ? (
                            <pre className="max-h-28 overflow-auto rounded bg-muted p-2 text-[10px] leading-4">
                              {safeJson(result.rawOutput)}
                            </pre>
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono">{result ? result.latencyMs : "—"}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
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

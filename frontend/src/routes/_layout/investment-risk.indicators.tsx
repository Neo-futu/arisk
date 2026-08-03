import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Download, Search } from "lucide-react"
import { useMemo, useState } from "react"

import { DatePicker } from "@/components/DatePicker"
import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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

export const Route = createFileRoute("/_layout/investment-risk/indicators")({
  component: RiskIndicatorsPage,
  head: () => ({ meta: [{ title: "風險指標 — 投資風險分析 — ARISK" }] }),
})

const METHOD_LABELS: Record<string, string> = {
  historical: "歷史模擬法",
  monte_carlo: "蒙特卡洛法",
  distribution: "參數法",
}

function defaultStartDate() {
  const result = new Date(`${lastTradeDate()}T00:00:00`)
  result.setDate(result.getDate() - 90)
  return result.toISOString().split("T")[0]
}

function percent(value: number | null | undefined, digits = 3) {
  return value == null ? "—" : `${Number(value).toFixed(digits)}%`
}

function money(value: number | null | undefined) {
  return value == null ? "—" : Number(value).toLocaleString("zh-HK", { maximumFractionDigits: 0 })
}

function RiskIndicatorsPage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [startDate, setStartDate] = useState(defaultStartDate)
  const [endDate, setEndDate] = useState(lastTradeDate)
  const [constituentQuery, setConstituentQuery] = useState("")

  const indicators = useQuery({
    queryKey: ["investment-risk-indicators", fundId, startDate, endDate],
    queryFn: () => fsiApi.getRiskIndicators(fundId, startDate, endDate).then((response) => response.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const indicatorSeries = useQuery({
    queryKey: ["investment-risk-indicator-timeseries", fundId, startDate, endDate],
    queryFn: () => fsiApi.getRiskIndicatorTimeseries(fundId, startDate, endDate).then((response) => response.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const varCompare = useQuery({
    queryKey: ["investment-var-compare", fundId, endDate],
    queryFn: () => fsiApi.getVarCompare(fundId, endDate).then((response) => response.data),
    retry: 1,
  })
  const isFetching = indicators.isFetching || varCompare.isFetching || indicatorSeries.isFetching
  const isError = indicators.isError || varCompare.isError || indicatorSeries.isError
  const filteredConstituents = useMemo(() => {
    const rows = indicators.data?.equity_beta.constituents ?? []
    return rows.filter((row) => {
      const keyword = `${row.security_code} ${row.security_name}`.toLowerCase()
      return keyword.includes(constituentQuery.toLowerCase())
    })
  }, [indicators.data?.equity_beta.constituents, constituentQuery])

  function exportConstituents() {
    if (!indicators.data) return
    exportCsv(
      `investment-risk-indicators-beta-${fundId}-${endDate}.csv`,
      ["代碼", "名稱", "權重", "Beta", "樣本數"],
      filteredConstituents.map((row) => [row.security_code, row.security_name, row.weight_pct, row.beta, row.sample_size]),
    )
  }

  const startPicker = (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground text-xs">開始</span>
      <DatePicker value={startDate} onChange={setStartDate} />
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <Badge variant="outline">投資風險分析</Badge>
          <span className="text-muted-foreground text-sm">風險指標</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">風險指標</h1>
        <p className="text-muted-foreground text-sm">
          區間收益率、波動率、最大回撤、股票交易換手率、股票 Beta 及 VaR
        </p>
      </div>

      <FsiToolbar
        fundId={fundId}
        onFundChange={setFundId}
        asOfDate={endDate}
        onDateChange={setEndDate}
        onRefresh={() => {
          indicators.refetch()
          varCompare.refetch()
        }}
        isFetching={isFetching}
        extra={startPicker}
      />

      {startDate > endDate && <p className="text-sm text-destructive">開始日期不得晚於結束日期。</p>}
      {isFetching && <p className="text-muted-foreground animate-pulse text-sm">計算指標中...</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            無法載入風險指標，請確認 Processing API 和區間數據可用。
          </CardContent>
        </Card>
      )}

      {indicators.data && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard label="區間收益率" value={percent(indicators.data.interval_return_pct)} detail={`${indicators.data.period_start} 至 ${indicators.data.period_end}`} />
            <MetricCard label="年化波動率" value={percent(indicators.data.annualized_volatility_pct)} detail={`${indicators.data.sample_size} 個日收益樣本`} />
            <MetricCard label="最大回撤" value={percent(indicators.data.max_drawdown_pct)} detail={`${indicators.data.max_drawdown_start ?? "—"} → ${indicators.data.max_drawdown_end ?? "—"}`} />
            <MetricCard label="股票年化換手率" value={percent(indicators.data.equity_turnover.annualized_turnover_pct)} detail={`區間 ${percent(indicators.data.equity_turnover.period_turnover_pct)}`} />
            <MetricCard label="股票 Beta" value={indicators.data.equity_beta.value == null ? "—" : indicators.data.equity_beta.value.toFixed(3)} detail={`基準 ${indicators.data.equity_beta.benchmark_id ?? "未配置"}`} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">核心風險輪廓</CardTitle>
              </CardHeader>
              <CardContent>
                <HorizontalBarList
                  items={[
                    { label: "區間收益", value: Math.abs(indicators.data.interval_return_pct ?? 0) },
                    { label: "年化波動", value: indicators.data.annualized_volatility_pct ?? 0 },
                    { label: "最大回撤", value: Math.abs(indicators.data.max_drawdown_pct ?? 0) },
                    { label: "換手率", value: indicators.data.equity_turnover.annualized_turnover_pct ?? 0 },
                    { label: "VaR上限", value: varCompare.data?.max_var_pct_nav ?? 0 },
                  ]}
                  formatter={(value) => percent(value, 3)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">滾動波動率時序</CardTitle>
              </CardHeader>
              <CardContent>
                <TrendLineChart
                  values={(indicatorSeries.data?.points ?? []).map((row) => row.rolling_volatility_pct ?? 0)}
                  labels={(indicatorSeries.data?.points ?? []).map((row) => String(row.date).slice(5))}
                  lineColor="#dc2626"
                  pointColor="#fb7185"
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">回撤與滾動 VaR 時序摘要</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>日期</TableHead><TableHead className="text-right">日收益</TableHead><TableHead className="text-right">回撤</TableHead><TableHead className="text-right">滾動 VaR 95%</TableHead></TableRow></TableHeader>
                <TableBody>
                  {(indicatorSeries.data?.points ?? []).slice(-10).map((row) => (
                    <TableRow key={row.date}>
                      <TableCell>{row.date}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.daily_return_pct, 3)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.drawdown_pct, 3)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.rolling_var_95_pct, 3)}</TableCell>
                    </TableRow>
                  ))}
                  {!(indicatorSeries.data?.points ?? []).length && <EmptyRow columns={4} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">股票交易換手率明細</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-3">
                <MetricBlock label="買入額" value={money(indicators.data.equity_turnover.buy_amount)} />
                <MetricBlock label="賣出額" value={money(indicators.data.equity_turnover.sell_amount)} />
                <MetricBlock label="日均股票餘額" value={money(indicators.data.equity_turnover.average_equity_balance)} />
              </div>
              <p className="text-muted-foreground mt-4 text-xs">{indicators.data.equity_turnover.method}，再按區間日數年化。</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">個股 Beta 貢獻（前十大權重）</CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
                      placeholder="搜尋個股代碼或名稱"
                      value={constituentQuery}
                      onChange={(event) => setConstituentQuery(event.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={exportConstituents}>
                    <Download className="mr-2 h-4 w-4" />
                    匯出
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>代碼</TableHead><TableHead>名稱</TableHead><TableHead className="text-right">權重</TableHead><TableHead className="text-right">Beta</TableHead><TableHead className="text-right">樣本數</TableHead></TableRow></TableHeader>
                <TableBody>
                  {filteredConstituents.map((row) => (
                    <TableRow key={row.security_code}>
                      <TableCell className="font-mono">{row.security_code}</TableCell>
                      <TableCell>{row.security_name}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.weight_pct, 2)}</TableCell>
                      <TableCell className="text-right font-mono">{row.beta.toFixed(3)}</TableCell>
                      <TableCell className="text-right">{row.sample_size}</TableCell>
                    </TableRow>
                  ))}
                  {!filteredConstituents.length && <EmptyRow columns={5} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}

      {varCompare.data && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-base">VaR 三方法對比（99%，1日）</CardTitle>
              <Badge variant="secondary">最大 VaR {percent(varCompare.data.max_var_pct_nav, 4)}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader><TableRow><TableHead>方法</TableHead><TableHead className="text-right">VaR（HKD）</TableHead><TableHead className="text-right">VaR（% NAV）</TableHead><TableHead className="text-right">CVaR（HKD）</TableHead><TableHead className="text-right">樣本數</TableHead></TableRow></TableHeader>
              <TableBody>
                {varCompare.data.results.map((row) => (
                  <TableRow key={row.method_requested ?? row.method}>
                    <TableCell className="font-medium">{METHOD_LABELS[row.method_requested ?? ""] ?? row.method}</TableCell>
                    <TableCell className="text-right font-mono">{money(row.var_hkd)}</TableCell>
                    <TableCell className="text-right font-mono">{percent(row.var_pct_nav, 4)}</TableCell>
                    <TableCell className="text-right font-mono">{money(row.cvar_hkd)}</TableCell>
                    <TableCell className="text-right">{row.sample_size}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className="mt-1 text-xl font-semibold">{value}</p>
        <p className="text-muted-foreground mt-1 truncate text-xs" title={detail}>{detail}</p>
      </CardContent>
    </Card>
  )
}

function MetricBlock({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border p-3"><p className="text-muted-foreground text-xs">{label}</p><p className="mt-1 font-mono text-lg">{value}</p></div>
}

function EmptyRow({ columns }: { columns: number }) {
  return <TableRow><TableCell colSpan={columns} className="h-20 text-center text-muted-foreground">暫無數據</TableCell></TableRow>
}

import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useState } from "react"

import { DatePicker } from "@/components/DatePicker"
import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi } from "@/fsiClient"

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

  const indicators = useQuery({
    queryKey: ["investment-risk-indicators", fundId, startDate, endDate],
    queryFn: () => fsiApi.getRiskIndicators(fundId, startDate, endDate).then((response) => response.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const varCompare = useQuery({
    queryKey: ["investment-var-compare", fundId, endDate],
    queryFn: () => fsiApi.getVarCompare(fundId, endDate).then((response) => response.data),
    retry: 1,
  })
  const isFetching = indicators.isFetching || varCompare.isFetching
  const isError = indicators.isError || varCompare.isError

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
            <CardHeader><CardTitle className="text-base">個股 Beta 貢獻（前十大權重）</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>代碼</TableHead><TableHead>名稱</TableHead><TableHead className="text-right">權重</TableHead><TableHead className="text-right">Beta</TableHead><TableHead className="text-right">樣本數</TableHead></TableRow></TableHeader>
                <TableBody>
                  {indicators.data.equity_beta.constituents.map((row) => (
                    <TableRow key={row.security_code}>
                      <TableCell className="font-mono">{row.security_code}</TableCell>
                      <TableCell>{row.security_name}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.weight_pct, 2)}</TableCell>
                      <TableCell className="text-right font-mono">{row.beta.toFixed(3)}</TableCell>
                      <TableCell className="text-right">{row.sample_size}</TableCell>
                    </TableRow>
                  ))}
                  {!indicators.data.equity_beta.constituents.length && <EmptyRow columns={5} />}
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

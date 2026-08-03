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
import { fsiApi, type SecurityPnl } from "@/fsiClient"
import { exportCsv, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"

export const Route = createFileRoute("/_layout/investment-risk/attribution")({
  component: PerformanceAttributionPage,
  head: () => ({ meta: [{ title: "績效歸因 — 投資風險分析 — ARISK" }] }),
})

const ASSET_LABELS: Record<string, string> = {
  CASH: "現金",
  DEPOSIT: "存款",
  CD: "存款證",
  CP: "商業票據",
  BOND_GOVT: "政府債券",
  BOND_CORP: "企業債券",
  BOND_CONVERT: "可轉換債券",
  BOND_ABS: "資產支持證券",
  STOCK: "股票",
  FUND_PUBLIC: "公募基金",
  FUND_ETF: "ETF",
  FUTURES: "期貨",
  OPTIONS: "期權",
  REPO: "回購",
  REV_REPO: "逆回購",
  OTHER: "其他",
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

function PerformanceAttributionPage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [startDate, setStartDate] = useState(defaultStartDate)
  const [endDate, setEndDate] = useState(lastTradeDate)
  const [securityQuery, setSecurityQuery] = useState("")
  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["performance-attribution", fundId, startDate, endDate],
    queryFn: () => fsiApi.getPerformanceAttribution(fundId, startDate, endDate).then((response) => response.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const attributionSeries = useQuery({
    queryKey: ["performance-attribution-timeseries", fundId, startDate, endDate],
    queryFn: () => fsiApi.getPerformanceAttributionTimeseries(fundId, startDate, endDate).then((response) => response.data),
    enabled: startDate <= endDate,
    retry: 1,
  })

  const filteredTopHoldings = useMemo(() => {
    if (!data) return []
    return data.average_top_holdings.filter((row) => {
      const keyword = `${row.security_code} ${row.security_name} ${row.sector}`.toLowerCase()
      return keyword.includes(securityQuery.toLowerCase())
    })
  }, [data, securityQuery])

  function exportTopHoldings() {
    if (!data) return
    exportCsv(
      `investment-risk-attribution-holdings-${fundId}-${endDate}.csv`,
      ["代碼", "名稱", "行業", "日均權重", "持倉日數", "區間損益"],
      filteredTopHoldings.map((row) => [
        row.security_code,
        row.security_name,
        row.sector,
        row.average_weight_pct,
        row.holding_days,
        row.net_pnl,
      ]),
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
          <span className="text-muted-foreground text-sm">績效歸因</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">績效歸因</h1>
        <p className="text-muted-foreground text-sm">
          收益貢獻、行業配置收益、行業超配、個股損益排名及日均十大重倉
        </p>
      </div>

      <FsiToolbar
        fundId={fundId}
        onFundChange={setFundId}
        asOfDate={endDate}
        onDateChange={setEndDate}
        onRefresh={() => refetch()}
        isFetching={isFetching}
        extra={startPicker}
      />

      {startDate > endDate && <p className="text-sm text-destructive">開始日期不得晚於結束日期。</p>}
      {(isFetching || attributionSeries.isFetching) && <p className="text-muted-foreground animate-pulse text-sm">執行績效歸因中...</p>}
      {(isError || attributionSeries.isError) && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            無法載入績效歸因，請確認持倉、行情、損益及基準數據可用。
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
            <MetricCard label="組合收益" value={percent(data.summary.fund_return_pct)} />
            <MetricCard label="基準收益" value={percent(data.summary.benchmark_return_pct)} detail={data.benchmark_id ?? "未配置基準"} />
            <MetricCard label="超額收益" value={percent(data.summary.active_return_pct)} />
            <MetricCard label="配置效應" value={percent(data.summary.allocation_effect_pct)} />
            <MetricCard label="選股效應" value={percent(data.summary.selection_effect_pct)} />
            <MetricCard label="交互效應" value={percent(data.summary.interaction_effect_pct)} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">超額收益累積時序</CardTitle>
              </CardHeader>
              <CardContent>
                <TrendLineChart
                  values={(attributionSeries.data?.cumulative_points ?? []).map((row) => row.active_cumulative_return_pct)}
                  labels={(attributionSeries.data?.cumulative_points ?? []).map((row) => String(row.date).slice(5))}
                  lineColor="#0f766e"
                  pointColor="#2dd4bf"
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">日度損益貢獻時序</CardTitle>
              </CardHeader>
              <CardContent>
                <TrendLineChart
                  values={(attributionSeries.data?.pnl_points ?? []).map((row) => row.contribution_pct ?? 0)}
                  labels={(attributionSeries.data?.pnl_points ?? []).map((row) => String(row.date).slice(5))}
                  lineColor="#7c2d12"
                  pointColor="#fb923c"
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle className="text-base">各類資產收益貢獻</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>資產類別</TableHead><TableHead className="text-right">盯市損益</TableHead><TableHead className="text-right">利息/股息</TableHead><TableHead className="text-right">已實現</TableHead><TableHead className="text-right">外匯</TableHead><TableHead className="text-right">淨損益</TableHead><TableHead className="text-right">收益貢獻</TableHead></TableRow></TableHeader>
                <TableBody>
                  {data.asset_contribution.map((row) => (
                    <TableRow key={row.asset_class}>
                      <TableCell className="font-medium">{ASSET_LABELS[row.asset_class] ?? row.asset_class}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.mtm_delta)}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.interest_income)}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.realized_gain)}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.fx_pnl)}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.net_pnl)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.contribution_pct)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.asset_contribution.length && <EmptyRow columns={7} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">行業配置收益與超配情況（Brinson）</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>行業</TableHead><TableHead className="text-right">組合權重</TableHead><TableHead className="text-right">基準權重</TableHead><TableHead className="text-right">超配</TableHead><TableHead className="text-right">配置效應</TableHead><TableHead className="text-right">選股效應</TableHead><TableHead className="text-right">交互效應</TableHead></TableRow></TableHeader>
                <TableBody>
                  {data.sector_attribution.map((row) => (
                    <TableRow key={row.sector}>
                      <TableCell className="font-medium">{row.sector}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.fund_weight_pct, 2)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.benchmark_weight_pct, 2)}</TableCell>
                      <TableCell className={`text-right font-mono ${row.overweight_pct < 0 ? "text-destructive" : "text-emerald-600"}`}>{percent(row.overweight_pct, 2)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.allocation_effect_pct)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.selection_effect_pct)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.interaction_effect_pct)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.sector_attribution.length && <EmptyRow columns={7} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <div className="grid gap-6 xl:grid-cols-2">
            <PnlTable title="個股損益前十大" rows={data.top_winners} />
            <PnlTable title="個股損益後十大" rows={data.top_losers} />
          </div>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">日均十大重倉股</CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
                      placeholder="搜尋個股代碼、名稱或行業"
                      value={securityQuery}
                      onChange={(event) => setSecurityQuery(event.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={exportTopHoldings}>
                    <Download className="mr-2 h-4 w-4" />
                    匯出
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>代碼</TableHead><TableHead>名稱</TableHead><TableHead>行業</TableHead><TableHead className="text-right">日均權重</TableHead><TableHead className="text-right">持倉日數</TableHead><TableHead className="text-right">區間損益</TableHead></TableRow></TableHeader>
                <TableBody>
                  {filteredTopHoldings.map((row) => (
                    <TableRow key={row.security_code}>
                      <TableCell className="font-mono">{row.security_code}</TableCell>
                      <TableCell className="font-medium">{row.security_name}</TableCell>
                      <TableCell>{row.sector}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.average_weight_pct, 2)}</TableCell>
                      <TableCell className="text-right">{row.holding_days}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.net_pnl)}</TableCell>
                    </TableRow>
                  ))}
                  {!filteredTopHoldings.length && <EmptyRow columns={6} />}
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
        {detail && <p className="text-muted-foreground mt-1 truncate text-xs">{detail}</p>}
      </CardContent>
    </Card>
  )
}

function PnlTable({ title, rows }: { title: string; rows: SecurityPnl[] }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow><TableHead>個股</TableHead><TableHead>行業</TableHead><TableHead className="text-right">損益</TableHead><TableHead className="text-right">貢獻</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow key={`${row.security_code}-${index}`}>
                <TableCell><div className="font-medium">{row.security_name}</div><div className="text-muted-foreground font-mono text-xs">{row.security_code ?? "—"}</div></TableCell>
                <TableCell>{row.sector}</TableCell>
                <TableCell className="text-right font-mono">{money(row.net_pnl)}</TableCell>
                <TableCell className="text-right font-mono">{percent(row.contribution_pct)}</TableCell>
              </TableRow>
            ))}
            {!rows.length && <EmptyRow columns={4} />}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function EmptyRow({ columns }: { columns: number }) {
  return <TableRow><TableCell colSpan={columns} className="h-20 text-center text-muted-foreground">暫無數據</TableCell></TableRow>
}

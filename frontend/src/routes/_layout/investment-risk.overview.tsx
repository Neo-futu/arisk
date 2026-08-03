import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Download, Search } from "lucide-react"
import { useMemo, useState } from "react"

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

export const Route = createFileRoute("/_layout/investment-risk/overview")({
  component: PortfolioOverviewPage,
  head: () => ({ meta: [{ title: "組合概況 — 投資風險分析 — ARISK" }] }),
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

function money(value: number | null | undefined, currency = "HKD") {
  if (value == null) return "—"
  return new Intl.NumberFormat("zh-HK", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value))
}

function percent(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${Number(value).toFixed(digits)}%`
}

function defaultChartStartDate(asOfDate: string) {
  const result = new Date(`${asOfDate}T00:00:00`)
  result.setDate(result.getDate() - 180)
  return result.toISOString().split("T")[0]
}

function PortfolioOverviewPage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [stockQuery, setStockQuery] = useState("")
  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["investment-overview", fundId, asOfDate],
    queryFn: () => fsiApi.getPortfolioOverview(fundId, asOfDate).then((response) => response.data),
    retry: 1,
  })
  const overviewSeries = useQuery({
    queryKey: ["investment-overview-timeseries", fundId, asOfDate],
    queryFn: () => fsiApi.getPortfolioOverviewTimeseries(fundId, defaultChartStartDate(asOfDate), asOfDate).then((response) => response.data),
    retry: 1,
  })

  const currency = data?.portfolio.base_currency ?? "HKD"
  const filteredTopStocks = useMemo(() => {
    if (!data) return []
    return data.top_stocks.filter((row) => {
      const keyword = `${row.security_code} ${row.security_name} ${row.sector}`.toLowerCase()
      return keyword.includes(stockQuery.toLowerCase())
    })
  }, [data, stockQuery])

  function exportTopStocks() {
    if (!data) return
    exportCsv(
      `investment-risk-overview-top-stocks-${fundId}-${asOfDate}.csv`,
      ["代碼", "名稱", "行業", "市值", "佔NAV", "浮動損益"],
      filteredTopStocks.map((row) => [
        row.security_code,
        row.security_name,
        row.sector,
        row.market_value_base,
        row.weight_pct,
        row.unrealized_pnl,
      ]),
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <Badge variant="outline">投資風險分析</Badge>
          <span className="text-muted-foreground text-sm">組合概況</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">組合概況</h1>
        <p className="text-muted-foreground text-sm">
          總體業績、資產配置、前十大個股及股票行業配置
        </p>
      </div>

      <FsiToolbar
        fundId={fundId}
        onFundChange={setFundId}
        asOfDate={asOfDate}
        onDateChange={setAsOfDate}
        onRefresh={() => refetch()}
        isFetching={isFetching}
      />

      {isFetching && <p className="text-muted-foreground animate-pulse text-sm">載入組合數據中...</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            無法載入組合概況，請確認 Processing API 和資料庫已啟動。
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="基金" value={data.portfolio.port_name || fundId} detail={data.portfolio.portfolio_type ?? "—"} />
            <MetricCard label="淨資產" value={money(data.portfolio.net_asset, currency)} detail={`數據日 ${data.portfolio.data_date ?? "—"}`} />
            <MetricCard label="單位淨值" value={data.portfolio.unit_nav == null ? "—" : Number(data.portfolio.unit_nav).toFixed(4)} detail={`累計 ${data.portfolio.acc_unit_nav == null ? "—" : Number(data.portfolio.acc_unit_nav).toFixed(4)}`} />
            <MetricCard label="當日收益" value={percent(data.portfolio.day_return == null ? null : Number(data.portfolio.day_return) * 100, 3)} detail={`${data.performance.length} 個業績區間`} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">區間收益走勢</CardTitle>
              </CardHeader>
              <CardContent>
                <TrendLineChart
                  values={(overviewSeries.data?.points ?? []).map((row) => row.cumulative_return_pct ?? 0)}
                  labels={(overviewSeries.data?.points ?? []).map((row) => String(row.date).slice(5))}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">資產配置結構</CardTitle>
              </CardHeader>
              <CardContent>
                <HorizontalBarList
                  items={data.asset_allocation.map((row) => ({
                    label: ASSET_LABELS[row.asset_class] ?? row.asset_class,
                    value: row.weight_pct,
                  }))}
                  formatter={(value) => percent(value, 2)}
                />
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">總體業績</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow><TableHead>區間</TableHead><TableHead>開始日</TableHead><TableHead className="text-right">收益率</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {data.performance.map((row) => (
                      <TableRow key={row.period}>
                        <TableCell className="font-medium">{row.period}</TableCell>
                        <TableCell>{row.start_date}</TableCell>
                        <TableCell className={`text-right font-mono ${row.return_pct < 0 ? "text-destructive" : "text-emerald-600"}`}>
                          {percent(row.return_pct, 3)}
                        </TableCell>
                      </TableRow>
                    ))}
                    {!data.performance.length && <EmptyRow columns={3} />}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">資產配置</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow><TableHead>資產類別</TableHead><TableHead className="text-right">市值</TableHead><TableHead className="text-right">佔比</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {data.asset_allocation.map((row) => (
                      <TableRow key={row.asset_class}>
                        <TableCell className="font-medium">{ASSET_LABELS[row.asset_class] ?? row.asset_class}</TableCell>
                        <TableCell className="text-right font-mono">{money(row.market_value_base, currency)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.weight_pct)}</TableCell>
                      </TableRow>
                    ))}
                    {!data.asset_allocation.length && <EmptyRow columns={3} />}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">前十大個股</CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
                      placeholder="搜尋代碼、名稱或行業"
                      value={stockQuery}
                      onChange={(event) => setStockQuery(event.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={exportTopStocks}>
                    <Download className="mr-2 h-4 w-4" />
                    匯出
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>代碼</TableHead><TableHead>名稱</TableHead><TableHead>行業</TableHead><TableHead className="text-right">市值</TableHead><TableHead className="text-right">佔 NAV</TableHead><TableHead className="text-right">浮動損益</TableHead></TableRow></TableHeader>
                <TableBody>
                  {filteredTopStocks.map((row) => (
                    <TableRow key={row.security_code}>
                      <TableCell className="font-mono">{row.security_code}</TableCell>
                      <TableCell className="font-medium">{row.security_name}</TableCell>
                      <TableCell>{row.sector}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.market_value_base, currency)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.weight_pct)}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.unrealized_pnl, currency)}</TableCell>
                    </TableRow>
                  ))}
                  {!filteredTopStocks.length && <EmptyRow columns={6} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">股票行業配置</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>行業</TableHead><TableHead className="text-right">持倉數</TableHead><TableHead className="text-right">市值</TableHead><TableHead className="text-right">佔 NAV</TableHead></TableRow></TableHeader>
                <TableBody>
                  {data.stock_sectors.map((row) => (
                    <TableRow key={row.sector}>
                      <TableCell className="font-medium">{row.sector}</TableCell>
                      <TableCell className="text-right">{row.position_count}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.market_value_base, currency)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.weight_pct)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.stock_sectors.length && <EmptyRow columns={4} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className="mt-1 truncate text-xl font-semibold">{value}</p>
        <p className="text-muted-foreground mt-1 text-xs">{detail}</p>
      </CardContent>
    </Card>
  )
}

function EmptyRow({ columns }: { columns: number }) {
  return <TableRow><TableCell colSpan={columns} className="h-20 text-center text-muted-foreground">暫無數據</TableCell></TableRow>
}

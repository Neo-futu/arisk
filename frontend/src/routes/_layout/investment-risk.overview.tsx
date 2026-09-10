import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Download, Search } from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

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
import { EngineKpiPanel } from "@/modules/investment-risk/EngineKpiPanel"

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

// YTM / coupon are stored as decimal rates (0.035 → 3.50%)
function ratePercent(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${(Number(value) * 100).toFixed(digits)}%`
}

function years(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${Number(value).toFixed(digits)} 年`
}

function defaultChartStartDate(asOfDate: string) {
  const result = new Date(`${asOfDate}T00:00:00`)
  result.setDate(result.getDate() - 180)
  return result.toISOString().split("T")[0]
}

function PortfolioOverviewPage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [stockQuery, setStockQuery] = useState("")
  const [bondQuery, setBondQuery] = useState("")
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

  const filteredTopBonds = useMemo(() => {
    if (!data?.top_bonds) return []
    return data.top_bonds.filter((row) => {
      const keyword = `${row.security_code} ${row.security_name} ${row.issuer_name} ${row.rating ?? ""}`.toLowerCase()
      return keyword.includes(bondQuery.toLowerCase())
    })
  }, [data, bondQuery])

  function exportTopStocks() {
    if (!data) return
    exportCsv(
      `investment-risk-overview-top-stocks-${fundId}-${asOfDate}.csv`,
      [
        t("investmentRisk.overview.code"),
        t("investmentRisk.overview.name"),
        t("investmentRisk.overview.sector"),
        t("investmentRisk.overview.marketValue"),
        t("investmentRisk.overview.pctNav"),
        t("investmentRisk.overview.unrealizedPnl"),
      ],
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

  function exportTopBonds() {
    if (!data?.top_bonds) return
    exportCsv(
      `investment-risk-overview-top-bonds-${fundId}-${asOfDate}.csv`,
      [
        t("investmentRisk.overview.code"),
        t("investmentRisk.overview.name"),
        t("investmentRisk.overview.issuer"),
        t("investmentRisk.overview.rating"),
        t("investmentRisk.overview.marketValue"),
        t("investmentRisk.overview.pctNav"),
        "YTM%",
        t("investmentRisk.overview.duration"),
        "票息%",
        t("investmentRisk.overview.maturity"),
        "剩餘天數",
      ],
      filteredTopBonds.map((row) => [
        row.security_code,
        row.security_name,
        row.issuer_name,
        row.rating ?? "",
        row.market_value_base,
        row.weight_pct,
        row.ytm == null ? "" : row.ytm * 100,
        row.duration,
        row.coupon_rate == null ? "" : row.coupon_rate * 100,
        row.maturity_date ?? "",
        row.remaining_days,
      ]),
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <Badge variant="outline">{t("investmentRisk.tag")}</Badge>
          <span className="text-muted-foreground text-sm">{t("investmentRisk.overview.title")}</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.overview.title")}</h1>
        <p className="text-muted-foreground text-sm">
          {t("investmentRisk.overview.subtitle")}
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

      <EngineKpiPanel domain="overview" fundId={fundId} asOfDate={asOfDate} />

      <section id="asset-risk" className="scroll-mt-20 space-y-4">
      <EngineKpiPanel domain="fx" fundId={fundId} asOfDate={asOfDate} title={t("nav.fxAssetRisk")} />
      {isFetching && <p className="text-muted-foreground animate-pulse text-sm">{t("investmentRisk.common.loading")}</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {t("investmentRisk.overview.loadError")}
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          {data.snapshot_dates && (data.snapshot_dates.stock || data.snapshot_dates.bond || data.snapshot_dates.asset) ? (
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{t("investmentRisk.overview.snapshotDates")}</span>
              {data.snapshot_dates.asset ? <Badge variant="outline">{t("investmentRisk.overview.snapshotAsset", { date: data.snapshot_dates.asset })}</Badge> : null}
              {data.snapshot_dates.stock ? <Badge variant="outline">{t("investmentRisk.overview.snapshotStock", { date: data.snapshot_dates.stock })}</Badge> : null}
              {data.snapshot_dates.bond ? <Badge variant="outline">{t("investmentRisk.overview.snapshotBond", { date: data.snapshot_dates.bond })}</Badge> : null}
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label={t("investmentRisk.overview.fund")} value={data.portfolio.port_name || fundId} detail={data.portfolio.portfolio_type ?? "—"} />
            <MetricCard label={t("investmentRisk.overview.netAsset")} value={money(data.portfolio.net_asset, currency)} detail={t("investmentRisk.overview.dataDate", { date: data.portfolio.data_date ?? "—" })} />
            <MetricCard label={t("investmentRisk.overview.unitNav")} value={data.portfolio.unit_nav == null ? "—" : Number(data.portfolio.unit_nav).toFixed(4)} detail={t("investmentRisk.overview.accNav", { value: data.portfolio.acc_unit_nav == null ? "—" : Number(data.portfolio.acc_unit_nav).toFixed(4) })} />
            <MetricCard label={t("investmentRisk.overview.dayReturn")} value={percent(data.portfolio.day_return == null ? null : Number(data.portfolio.day_return) * 100, 3)} detail={t("investmentRisk.overview.periodCount", { count: data.performance.length })} />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("investmentRisk.overview.returnTrend")}</CardTitle>
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
                <CardTitle className="text-base">{t("investmentRisk.overview.allocationStructure")}</CardTitle>
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
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.overview.performance")}</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow><TableHead>{t("investmentRisk.overview.period")}</TableHead><TableHead>{t("investmentRisk.overview.startDate")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.returnPct")}</TableHead></TableRow></TableHeader>
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
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.overview.allocationTable")}</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow><TableHead>{t("investmentRisk.overview.assetClass")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.marketValue")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.weight")}</TableHead></TableRow></TableHeader>
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
                <CardTitle className="text-base">{t("investmentRisk.overview.topStocks")}</CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
                      placeholder={t("investmentRisk.overview.searchStock")}
                      value={stockQuery}
                      onChange={(event) => setStockQuery(event.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={exportTopStocks}>
                    <Download className="mr-2 h-4 w-4" />
                    {t("investmentRisk.common.export")}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.overview.code")}</TableHead><TableHead>{t("investmentRisk.overview.name")}</TableHead><TableHead>{t("investmentRisk.overview.sector")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.marketValue")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.pctNav")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.unrealizedPnl")}</TableHead></TableRow></TableHeader>
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
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">{t("investmentRisk.overview.topBonds")}</CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
                      placeholder={t("investmentRisk.overview.searchBond")}
                      value={bondQuery}
                      onChange={(event) => setBondQuery(event.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={exportTopBonds}>
                    <Download className="mr-2 h-4 w-4" />
                    {t("investmentRisk.common.export")}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("investmentRisk.overview.code")}</TableHead>
                    <TableHead>{t("investmentRisk.overview.name")}</TableHead>
                    <TableHead>{t("investmentRisk.overview.issuer")}</TableHead>
                    <TableHead>{t("investmentRisk.overview.rating")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.overview.marketValue")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.overview.pctNav")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.overview.ytm")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.overview.duration")}</TableHead>
                    <TableHead className="text-right">{t("investmentRisk.overview.coupon")}</TableHead>
                    <TableHead>{t("investmentRisk.overview.maturity")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTopBonds.map((row) => (
                    <TableRow key={row.security_code}>
                      <TableCell className="font-mono">{row.security_code}</TableCell>
                      <TableCell className="font-medium">{row.security_name}</TableCell>
                      <TableCell className="max-w-40 truncate" title={row.issuer_name}>{row.issuer_name}</TableCell>
                      <TableCell>{row.rating ?? "—"}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.market_value_base, currency)}</TableCell>
                      <TableCell className="text-right font-mono">{percent(row.weight_pct)}</TableCell>
                      <TableCell className="text-right font-mono">{ratePercent(row.ytm)}</TableCell>
                      <TableCell className="text-right font-mono">{years(row.duration)}</TableCell>
                      <TableCell className="text-right font-mono">{ratePercent(row.coupon_rate)}</TableCell>
                      <TableCell className="font-mono text-xs">{row.maturity_date ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                  {!filteredTopBonds.length && <EmptyRow columns={10} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.overview.stockSectors")}</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.overview.sector")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.positionCount")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.marketValue")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.pctNav")}</TableHead></TableRow></TableHeader>
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
      </section>
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
  const { t } = useTranslation()
  return <TableRow><TableCell colSpan={columns} className="h-20 text-center text-muted-foreground">{t("investmentRisk.common.empty")}</TableCell></TableRow>
}

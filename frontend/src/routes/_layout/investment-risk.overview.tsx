import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { fsiApi } from "@/fsiClient"
import { HorizontalBarList, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"
import { WorkbenchTable, type WorkbenchColumn } from "@/platform/WorkbenchTable"

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
  const performance = data?.performance ?? []
  const allocation = data?.asset_allocation ?? []
  const topStocks = data?.top_stocks ?? []
  const topBonds = data?.top_bonds ?? []
  const stockSectors = data?.stock_sectors ?? []

  const performanceColumns = useMemo<WorkbenchColumn<(typeof performance)[number]>[]>(() => [
    { key: "period", header: t("investmentRisk.overview.period"), accessor: (row) => row.period },
    { key: "start_date", header: t("investmentRisk.overview.startDate"), accessor: (row) => row.start_date },
    {
      key: "return_pct",
      header: t("investmentRisk.overview.returnPct"),
      align: "right",
      accessor: (row) => row.return_pct,
      cell: (row) => (
        <span className={`font-mono ${row.return_pct < 0 ? "text-destructive" : "text-emerald-600"}`}>
          {percent(row.return_pct, 3)}
        </span>
      ),
    },
  ], [t])

  const allocationColumns = useMemo<WorkbenchColumn<(typeof allocation)[number]>[]>(() => [
    {
      key: "asset_class",
      header: t("investmentRisk.overview.assetClass"),
      filterable: true,
      accessor: (row) => ASSET_LABELS[row.asset_class] ?? row.asset_class,
    },
    {
      key: "market_value_base",
      header: t("investmentRisk.overview.marketValue"),
      align: "right",
      accessor: (row) => row.market_value_base,
      cell: (row) => <span className="font-mono">{money(row.market_value_base, currency)}</span>,
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.overview.weight"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{percent(row.weight_pct)}</span>,
    },
  ], [currency, t])

  const stockColumns = useMemo<WorkbenchColumn<(typeof topStocks)[number]>[]>(() => [
    { key: "security_code", header: t("investmentRisk.overview.code"), accessor: (row) => row.security_code, cell: (row) => <span className="font-mono">{row.security_code}</span> },
    { key: "security_name", header: t("investmentRisk.overview.name"), accessor: (row) => row.security_name },
    { key: "sector", header: t("investmentRisk.overview.sector"), filterable: true, accessor: (row) => row.sector },
    {
      key: "market_value_base",
      header: t("investmentRisk.overview.marketValue"),
      align: "right",
      accessor: (row) => row.market_value_base,
      cell: (row) => <span className="font-mono">{money(row.market_value_base, currency)}</span>,
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.overview.pctNav"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{percent(row.weight_pct)}</span>,
    },
    {
      key: "unrealized_pnl",
      header: t("investmentRisk.overview.unrealizedPnl"),
      align: "right",
      accessor: (row) => row.unrealized_pnl,
      cell: (row) => <span className="font-mono">{money(row.unrealized_pnl, currency)}</span>,
    },
  ], [currency, t])

  const bondColumns = useMemo<WorkbenchColumn<(typeof topBonds)[number]>[]>(() => [
    { key: "security_code", header: t("investmentRisk.overview.code"), accessor: (row) => row.security_code, cell: (row) => <span className="font-mono">{row.security_code}</span> },
    { key: "security_name", header: t("investmentRisk.overview.name"), accessor: (row) => row.security_name },
    { key: "issuer_name", header: t("investmentRisk.overview.issuer"), accessor: (row) => row.issuer_name },
    { key: "rating", header: t("investmentRisk.overview.rating"), filterable: true, accessor: (row) => row.rating ?? "—" },
    {
      key: "market_value_base",
      header: t("investmentRisk.overview.marketValue"),
      align: "right",
      accessor: (row) => row.market_value_base,
      cell: (row) => <span className="font-mono">{money(row.market_value_base, currency)}</span>,
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.overview.pctNav"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{percent(row.weight_pct)}</span>,
    },
    {
      key: "ytm",
      header: t("investmentRisk.overview.ytm"),
      align: "right",
      accessor: (row) => row.ytm,
      cell: (row) => <span className="font-mono">{ratePercent(row.ytm)}</span>,
      exportValue: (row) => (row.ytm == null ? "" : row.ytm * 100),
    },
    {
      key: "duration",
      header: t("investmentRisk.overview.duration"),
      align: "right",
      accessor: (row) => row.duration,
      cell: (row) => <span className="font-mono">{years(row.duration)}</span>,
    },
    {
      key: "coupon_rate",
      header: t("investmentRisk.overview.coupon"),
      align: "right",
      accessor: (row) => row.coupon_rate,
      cell: (row) => <span className="font-mono">{ratePercent(row.coupon_rate)}</span>,
      exportValue: (row) => (row.coupon_rate == null ? "" : row.coupon_rate * 100),
    },
    { key: "maturity_date", header: t("investmentRisk.overview.maturity"), accessor: (row) => row.maturity_date ?? "—" },
  ], [currency, t])

  const sectorColumns = useMemo<WorkbenchColumn<(typeof stockSectors)[number]>[]>(() => [
    { key: "sector", header: t("investmentRisk.overview.sector"), filterable: true, accessor: (row) => row.sector },
    {
      key: "position_count",
      header: t("investmentRisk.overview.positionCount"),
      align: "right",
      accessor: (row) => row.position_count,
    },
    {
      key: "market_value_base",
      header: t("investmentRisk.overview.marketValue"),
      align: "right",
      accessor: (row) => row.market_value_base,
      cell: (row) => <span className="font-mono">{money(row.market_value_base, currency)}</span>,
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.overview.pctNav"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{percent(row.weight_pct)}</span>,
    },
  ], [currency, t])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t("investmentRisk.overview.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
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

      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {t("investmentRisk.overview.loadError")}
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label={t("investmentRisk.overview.fund")} value={data.portfolio.port_name || fundId} detail={data.portfolio.portfolio_type ?? "—"} />
            <MetricCard label={t("investmentRisk.overview.netAsset")} value={money(data.portfolio.net_asset, currency)} detail={t("investmentRisk.overview.dataDate", { date: data.portfolio.data_date ?? "—" })} />
            <MetricCard label={t("investmentRisk.overview.unitNav")} value={data.portfolio.unit_nav == null ? "—" : Number(data.portfolio.unit_nav).toFixed(4)} detail={t("investmentRisk.overview.accNav", { value: data.portfolio.acc_unit_nav == null ? "—" : Number(data.portfolio.acc_unit_nav).toFixed(4) })} />
            <MetricCard
              label={t("investmentRisk.overview.dayReturn")}
              value={percent(data.portfolio.day_return == null ? null : Number(data.portfolio.day_return) * 100, 3)}
              detail={t("investmentRisk.overview.dayReturnHint", {
                date: data.portfolio.data_date ?? "—",
              })}
            />
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
                  valueFormatter={(value) => `${value.toFixed(2)}%`}
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
            <WorkbenchTable
              title={t("investmentRisk.overview.performance")}
              rows={performance}
              columns={performanceColumns}
              rowId={(row) => row.period}
              exportFilename={`overview-performance-${fundId}-${asOfDate}.csv`}
              initialSortKey="return_pct"
            />
            <WorkbenchTable
              title={t("investmentRisk.overview.allocationTable")}
              rows={allocation}
              columns={allocationColumns}
              rowId={(row) => row.asset_class}
              exportFilename={`overview-allocation-${fundId}-${asOfDate}.csv`}
              initialSortKey="weight_pct"
            />
          </div>

          <WorkbenchTable
            title={t("investmentRisk.overview.topStocks")}
            rows={topStocks}
            columns={stockColumns}
            rowId={(row) => row.security_code}
            exportFilename={`overview-top-stocks-${fundId}-${asOfDate}.csv`}
            initialSortKey="weight_pct"
          />

          <WorkbenchTable
            title={t("investmentRisk.overview.topBonds")}
            rows={topBonds}
            columns={bondColumns}
            rowId={(row) => row.security_code}
            exportFilename={`overview-top-bonds-${fundId}-${asOfDate}.csv`}
            initialSortKey="weight_pct"
          />

          <WorkbenchTable
            title={t("investmentRisk.overview.stockSectors")}
            rows={stockSectors}
            columns={sectorColumns}
            rowId={(row) => row.sector}
            exportFilename={`overview-stock-sectors-${fundId}-${asOfDate}.csv`}
            initialSortKey="weight_pct"
          />
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

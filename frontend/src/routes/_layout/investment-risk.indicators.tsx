import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fsiApi, type PortfolioBasicInfo } from "@/fsiClient"
import { exportCsv, HorizontalBarList, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"
import { RISK_DOMAINS } from "@/modules/investment-risk/RiskDomainTabs"
import { SqlViewButton } from "@/modules/investment-risk/SqlViewButton"

export const Route = createFileRoute("/_layout/investment-risk/indicators")({
  component: RiskIndicatorsPage,
  head: () => ({ meta: [{ title: "風險指標 — 投資風險分析 — ARISK" }] }),
})

const FUND_CATEGORY_LABELS: Record<string, string> = {
  MONEY_MARKET: "貨幣市場基金",
  BOND: "債券基金",
  EQUITY: "股票基金",
  MIXED: "混合基金",
  OTHER: "其他",
}

const PERSON_ROLE_LABELS: Record<string, string> = {
  FUND_MANAGER: "基金經理",
  DEPUTY_MANAGER: "副基金經理",
  RISK_OFFICER: "風控",
  COMPLIANCE_OFFICER: "合規",
  PORTFOLIO_ANALYST: "組合分析師",
  TRADER: "交易員",
  ADMIN: "行政",
}

type FundCategory = PortfolioBasicInfo["portfolio"]["fund_category"]

// 每個模塊「建議適用」的基金類型；未命中僅提示，不隱藏模塊（便於查詢全部指標）。
const ALL_CATEGORIES: FundCategory[] = ["MONEY_MARKET", "BOND", "EQUITY", "MIXED", "OTHER"]
const EQUITY_CATEGORIES: FundCategory[] = ["EQUITY", "MIXED"]

/** 模塊卡片頭部：標題 + 適用性徽章 + 查看SQL。所有模塊照常顯示，僅標注是否建議適用於當前基金。 */
function ModuleHeader({
  title,
  sqlIds,
  applicable,
  category,
  notApplicableHint,
}: {
  title: string
  sqlIds: string[]
  applicable: FundCategory[]
  category?: FundCategory
  notApplicableHint?: string
}) {
  const isApplicable = !category || applicable.includes(category)
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle className="text-base">{title}</CardTitle>
        {category ? (
          isApplicable ? (
            <Badge className="bg-emerald-600 hover:bg-emerald-600">{t("investmentRisk.common.applicableSuggested")}</Badge>
          ) : (
            <Badge variant="outline" className="text-muted-foreground" title={notApplicableHint}>
              {t("investmentRisk.common.notApplicable")}
            </Badge>
          )
        ) : null}
      </div>
      <SqlViewButton sqlIds={sqlIds} />
    </div>
  )
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
  const { t } = useTranslation()
  const methodLabels: Record<string, string> = {
    historical: t("investmentRisk.indicators.methodHistorical"),
    monte_carlo: t("investmentRisk.indicators.methodMonteCarlo"),
    distribution: t("investmentRisk.indicators.methodDistribution"),
  }
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
  const basicInfo = useQuery({
    queryKey: ["investment-basic-info", fundId, endDate],
    queryFn: () => fsiApi.getBasicInfo(fundId, endDate).then((response) => response.data),
    retry: 1,
  })
  const fundCategory = basicInfo.data?.portfolio.fund_category
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
      [
        t("investmentRisk.overview.code"),
        t("investmentRisk.overview.name"),
        t("investmentRisk.overview.weight"),
        t("investmentRisk.indicators.betaValue"),
        t("investmentRisk.indicators.sampleSize"),
      ],
      filteredConstituents.map((row) => [row.security_code, row.security_name, row.weight_pct, row.beta, row.sample_size]),
    )
  }

  const startPicker = (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground text-xs">{t("investmentRisk.indicators.start")}</span>
      <DatePicker value={startDate} onChange={setStartDate} />
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <Badge variant="outline">{t("investmentRisk.tag")}</Badge>
          <span className="text-muted-foreground text-sm">{t("investmentRisk.indicators.title")}</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.indicators.title")}</h1>
        <p className="text-muted-foreground text-sm">
          {t("investmentRisk.indicators.subtitle")}
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
          basicInfo.refetch()
        }}
        isFetching={isFetching}
        extra={startPicker}
      />

      {startDate > endDate && <p className="text-sm text-destructive">{t("investmentRisk.indicators.dateRangeError")}</p>}
      {isFetching && <p className="text-muted-foreground animate-pulse text-sm">{t("investmentRisk.indicators.calculating")}</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {t("investmentRisk.indicators.loadError")}
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="basic-info">
        <TabsList className="flex-wrap">
          <TabsTrigger value="basic-info">{t("investmentRisk.indicators.tabBasicInfo")}</TabsTrigger>
          <TabsTrigger value="core">{t("investmentRisk.indicators.tabCore")}</TabsTrigger>
          {RISK_DOMAINS.map((domain) => (
            <TabsTrigger key={domain.key} value={domain.key}>{t(`investmentRisk.domains.${domain.label}`)}</TabsTrigger>
          ))}
        </TabsList>

        {/* 基本信息 */}
        <TabsContent value="basic-info" className="mt-4">
          {basicInfo.isFetching && !basicInfo.data ? (
            <p className="text-muted-foreground animate-pulse text-sm">{t("investmentRisk.common.loading")}</p>
          ) : basicInfo.data ? (
            <Card>
              <CardHeader>
                <ModuleHeader title={t("investmentRisk.indicators.basicInfoTitle")} sqlIds={["SQL-OV-01"]} applicable={ALL_CATEGORIES} />
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                  <InfoBlock label={t("investmentRisk.indicators.fund")} value={basicInfo.data.portfolio.port_name || fundId} />
                  <InfoBlock
                    label={t("investmentRisk.indicators.fundType")}
                    value={FUND_CATEGORY_LABELS[basicInfo.data.portfolio.fund_category] ?? (basicInfo.data.portfolio.port_type ?? "—")}
                  />
                  <InfoBlock label={t("investmentRisk.indicators.currency")} value={basicInfo.data.portfolio.base_currency ?? "—"} />
                  <InfoBlock label={t("investmentRisk.indicators.inceptionDate")} value={basicInfo.data.portfolio.inception_date ?? "—"} />
                  <InfoBlock label={t("investmentRisk.indicators.dataDate")} value={basicInfo.data.data_date ?? "—"} />
                  <InfoBlock
                    label={t("investmentRisk.indicators.statusLabel")}
                    value={basicInfo.data.portfolio.is_active === false ? t("investmentRisk.indicators.statusClosed") : t("investmentRisk.indicators.statusActive")}
                  />
                  {basicInfo.data.portfolio.is_mmf ? (
                    <>
                      <InfoBlock label={t("investmentRisk.indicators.wamLimit")} value={`${basicInfo.data.portfolio.mmf_wam_limit_days ?? "—"} 天`} />
                      <InfoBlock label={t("investmentRisk.indicators.walLimit")} value={`${basicInfo.data.portfolio.mmf_wal_limit_days ?? "—"} 天`} />
                    </>
                  ) : null}
                </div>

                <div>
                  <p className="mb-2 text-sm font-semibold">{t("investmentRisk.indicators.managers")}</p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("investmentRisk.indicators.managerName")}</TableHead>
                        <TableHead>{t("investmentRisk.indicators.managerRole")}</TableHead>
                        <TableHead>{t("investmentRisk.indicators.managerLead")}</TableHead>
                        <TableHead>{t("investmentRisk.indicators.managerTenure")}</TableHead>
                        <TableHead>{t("investmentRisk.indicators.managerStatus")}</TableHead>
                        <TableHead>{t("investmentRisk.indicators.sfcLicence")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {basicInfo.data.managers.map((manager) => (
                        <TableRow key={`${manager.person_id}-${manager.role}-${manager.begin_date}`}>
                          <TableCell className="font-medium">
                            {manager.person_name}
                            {manager.person_name_en ? <span className="ml-1 text-xs text-muted-foreground">{manager.person_name_en}</span> : null}
                          </TableCell>
                          <TableCell>{PERSON_ROLE_LABELS[manager.role] ?? manager.role}</TableCell>
                          <TableCell>{manager.is_lead ? <Badge className="bg-orange-600 hover:bg-orange-600">{t("investmentRisk.indicators.managerLead")}</Badge> : "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{manager.begin_date ?? "—"} ~ {manager.end_date ?? t("investmentRisk.indicators.present")}</TableCell>
                          <TableCell>
                            {manager.is_current ? <Badge variant="secondary">{t("investmentRisk.indicators.managerCurrent")}</Badge> : <Badge variant="outline">{t("investmentRisk.indicators.managerFormer")}</Badge>}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{manager.sfc_licence_no ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                      {!basicInfo.data.managers.length && <EmptyRow columns={6} />}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          ) : (
            <p className="text-muted-foreground text-sm">{t("investmentRisk.indicators.noBasicInfo")}</p>
          )}
        </TabsContent>

        {/* 核心風控指標 */}
        <TabsContent value="core" className="mt-4 space-y-6">
          {indicators.data ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">{t("investmentRisk.indicators.coreTitle")}</h2>
                <SqlViewButton sqlIds={["SQL-RI-01"]} />
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                <MetricCard label={t("investmentRisk.indicators.intervalReturn")} value={percent(indicators.data.interval_return_pct)} detail={`${indicators.data.period_start} 至 ${indicators.data.period_end}`} />
                <MetricCard label={t("investmentRisk.indicators.annualizedVol")} value={percent(indicators.data.annualized_volatility_pct)} detail={t("investmentRisk.indicators.sampleReturns", { count: indicators.data.sample_size })} />
                <MetricCard label={t("investmentRisk.indicators.maxDrawdown")} value={percent(indicators.data.max_drawdown_pct)} detail={`${indicators.data.max_drawdown_start ?? "—"} → ${indicators.data.max_drawdown_end ?? "—"}`} />
                <MetricCard label={t("investmentRisk.indicators.equityTurnover")} value={percent(indicators.data.equity_turnover.annualized_turnover_pct)} detail={t("investmentRisk.indicators.interval", { value: percent(indicators.data.equity_turnover.period_turnover_pct) })} />
                <MetricCard label={t("investmentRisk.indicators.equityBeta")} value={indicators.data.equity_beta.value == null ? "—" : indicators.data.equity_beta.value.toFixed(3)} detail={t("investmentRisk.indicators.benchmark", { value: indicators.data.equity_beta.benchmark_id ?? t("investmentRisk.indicators.benchmarkUnset") })} />
              </div>

              <div className="grid gap-6 xl:grid-cols-2">
                <Card>
                  <CardHeader>
                    <ModuleHeader title={t("investmentRisk.indicators.riskProfile")} sqlIds={["SQL-RI-01", "SQL-VAR-01"]} applicable={ALL_CATEGORIES} />
                  </CardHeader>
                  <CardContent>
                    <HorizontalBarList
                      items={[
                        { label: t("investmentRisk.indicators.profileReturn"), value: Math.abs(indicators.data.interval_return_pct ?? 0) },
                        { label: t("investmentRisk.indicators.profileVol"), value: indicators.data.annualized_volatility_pct ?? 0 },
                        { label: t("investmentRisk.indicators.profileDrawdown"), value: Math.abs(indicators.data.max_drawdown_pct ?? 0) },
                        { label: t("investmentRisk.indicators.profileTurnover"), value: indicators.data.equity_turnover.annualized_turnover_pct ?? 0 },
                        { label: t("investmentRisk.indicators.profileVar"), value: varCompare.data?.max_var_pct_nav ?? 0 },
                      ]}
                      formatter={(value) => percent(value, 3)}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <ModuleHeader title={t("investmentRisk.indicators.rollingVol")} sqlIds={["SQL-RI-02"]} applicable={ALL_CATEGORIES} />
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
                  <ModuleHeader title={t("investmentRisk.indicators.drawdownVarSummary")} sqlIds={["SQL-RI-02", "SQL-VAR-01"]} applicable={ALL_CATEGORIES} />
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader><TableRow><TableHead>{t("investmentRisk.indicators.date")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.dailyReturn")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.drawdown")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.rollingVar95")}</TableHead></TableRow></TableHeader>
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
                  <ModuleHeader
                    title={t("investmentRisk.indicators.turnoverDetail")}
                    sqlIds={["SQL-RI-03"]}
                    applicable={EQUITY_CATEGORIES}
                    category={fundCategory}
                    notApplicableHint={t("investmentRisk.indicators.turnoverNotApplicable")}
                  />
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-3">
                    <MetricBlock label={t("investmentRisk.indicators.buyAmount")} value={money(indicators.data.equity_turnover.buy_amount)} />
                    <MetricBlock label={t("investmentRisk.indicators.sellAmount")} value={money(indicators.data.equity_turnover.sell_amount)} />
                    <MetricBlock label={t("investmentRisk.indicators.avgEquityBalance")} value={money(indicators.data.equity_turnover.average_equity_balance)} />
                  </div>
                  <p className="text-muted-foreground mt-4 text-xs">{t("investmentRisk.indicators.turnoverMethodHint", { method: indicators.data.equity_turnover.method })}</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle className="text-base">{t("investmentRisk.indicators.betaTitle")}</CardTitle>
                      {fundCategory ? (
                        EQUITY_CATEGORIES.includes(fundCategory) ? (
                          <Badge className="bg-emerald-600 hover:bg-emerald-600">{t("investmentRisk.common.applicableSuggested")}</Badge>
                        ) : (
                          <Badge variant="outline" className="text-muted-foreground" title={t("investmentRisk.indicators.betaNotApplicable")}>
                            {t("investmentRisk.common.notApplicable")}
                          </Badge>
                        )
                      ) : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                        <Search className="h-4 w-4 text-muted-foreground" />
                        <Input
                          className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
                          placeholder={t("investmentRisk.indicators.searchConstituent")}
                          value={constituentQuery}
                          onChange={(event) => setConstituentQuery(event.target.value)}
                        />
                      </div>
                      <Button variant="outline" size="sm" onClick={exportConstituents}>
                        <Download className="mr-2 h-4 w-4" />
                        {t("investmentRisk.common.export")}
                      </Button>
                      <SqlViewButton sqlIds={["SQL-RI-04"]} />
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader><TableRow><TableHead>{t("investmentRisk.overview.code")}</TableHead><TableHead>{t("investmentRisk.overview.name")}</TableHead><TableHead className="text-right">{t("investmentRisk.overview.weight")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.betaValue")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.sampleSize")}</TableHead></TableRow></TableHeader>
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

              {varCompare.data && (
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-3">
                      <CardTitle className="text-base">{t("investmentRisk.indicators.varTitle")}</CardTitle>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">{t("investmentRisk.indicators.varMax", { value: percent(varCompare.data.max_var_pct_nav, 4) })}</Badge>
                        <SqlViewButton sqlIds={["SQL-VAR-01"]} />
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader><TableRow><TableHead>{t("investmentRisk.indicators.method")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.varHkd")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.varPctNav")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.cvarHkd")}</TableHead><TableHead className="text-right">{t("investmentRisk.indicators.sampleSize")}</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {varCompare.data.results.map((row) => (
                          <TableRow key={row.method_requested ?? row.method}>
                            <TableCell className="font-medium">{methodLabels[row.method_requested ?? ""] ?? row.method}</TableCell>
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
            </>
          ) : (
            <p className="text-muted-foreground text-sm">{t("investmentRisk.indicators.noIndicators")}</p>
          )}
        </TabsContent>

        {/* 六大業務域 */}
        {RISK_DOMAINS.map(({ key, Component }) => (
          <TabsContent key={key} value={key} className="mt-4">
            <Component fundId={fundId} asOfDate={endDate} startDate={startDate} endDate={endDate} />
          </TabsContent>
        ))}
      </Tabs>
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

function InfoBlock({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border p-3"><p className="text-muted-foreground text-xs">{label}</p><p className="mt-1 truncate text-sm font-medium" title={value}>{value}</p></div>
}

function EmptyRow({ columns }: { columns: number }) {
  const { t } = useTranslation()
  return <TableRow><TableCell colSpan={columns} className="h-20 text-center text-muted-foreground">{t("investmentRisk.common.empty")}</TableCell></TableRow>
}

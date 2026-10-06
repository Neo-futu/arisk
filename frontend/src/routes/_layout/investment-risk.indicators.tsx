import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fsiApi, type PortfolioBasicInfo } from "@/fsiClient"
import { TrendLineChart } from "@/modules/investment-risk/dashboard-kit"
import { EngineKpiPanel } from "@/modules/investment-risk/EngineKpiPanel"
import { HoldingsDetailSection } from "@/modules/investment-risk/HoldingsDetailSection"
import { RiskMetricBoardSection } from "@/modules/investment-risk/RiskMetricBoardSection"
import { RISK_DOMAINS } from "@/modules/investment-risk/RiskDomainTabs"
import { SqlViewButton } from "@/modules/investment-risk/SqlViewButton"

export const Route = createFileRoute("/_layout/investment-risk/indicators")({
  component: RiskIndicatorsPage,
  head: () => ({ meta: [{ title: "風險暴露 — 投資風險分析 — ARISK" }] }),
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

function defaultTabFromHash() {
  if (typeof window === "undefined") return "basic-info"
  const hash = window.location.hash.replace(/^#/, "")
  if (hash === "risk-exposure" || hash === "leverage-derivatives-risk") return "core"
  return "basic-info"
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
  const [activeTab, setActiveTab] = useState(defaultTabFromHash)

  // 菜單帶 #risk-exposure 時只切到核心頁籤；回頂由 useHashScroll 統一處理
  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "")
    if (hash !== "risk-exposure" && hash !== "leverage-derivatives-risk") return
    setActiveTab("core")
  }, [])

  const basicInfo = useQuery({
    queryKey: ["investment-basic-info", fundId, endDate],
    queryFn: () => fsiApi.getBasicInfo(fundId, endDate).then((response) => response.data),
    retry: 1,
  })

  // 結束日若晚於庫內最近 NAV 日，自動回退並保持原窗口長度
  useEffect(() => {
    const dataDate = basicInfo.data?.data_date
    if (!dataDate || typeof dataDate !== "string") return
    if (endDate <= dataDate) return
    const spanMs =
      new Date(`${endDate}T00:00:00`).getTime() -
      new Date(`${startDate}T00:00:00`).getTime()
    const spanDays = Math.max(Math.round(spanMs / 86_400_000), 0)
    const nextEnd = dataDate
    const nextStartDate = new Date(`${dataDate}T00:00:00`)
    nextStartDate.setDate(nextStartDate.getDate() - spanDays)
    const nextStart = nextStartDate.toISOString().split("T")[0]
    setEndDate(nextEnd)
    setStartDate(nextStart)
  }, [basicInfo.data?.data_date, endDate, startDate])

  const indicators = useQuery({
    queryKey: ["investment-risk-indicators", fundId, startDate, endDate],
    queryFn: () => fsiApi.getRiskIndicators(fundId, startDate, endDate).then((response) => response.data),
    enabled: startDate <= endDate,
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
  const positions = useQuery({
    queryKey: ["investment-risk-security-holdings", fundId, endDate],
    queryFn: () => fsiApi.getSecurityHoldings(fundId, endDate).then((response) => response.data),
    retry: 1,
  })
  const isFetching = indicators.isFetching || varCompare.isFetching || indicatorSeries.isFetching || positions.isFetching
  const isError = indicators.isError || varCompare.isError || indicatorSeries.isError

  return (
    <div className="space-y-6">
      {/* 保留 id 供菜單高亮；實際回頂由 useHashScroll 處理，避免滾到頁中 */}
      <div>
        <span id="leverage-derivatives-risk" className="sr-only" />
        <h1 id="risk-exposure" className="scroll-mt-0 text-2xl font-bold">
          {t("investmentRisk.indicators.title")}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("investmentRisk.indicators.subtitle")}
        </p>
      </div>

      <FsiToolbar
        fundId={fundId}
        onFundChange={setFundId}
        startDate={startDate}
        onStartDateChange={setStartDate}
        startDateLabel={t("platform.startDate")}
        asOfDate={endDate}
        onDateChange={setEndDate}
        asOfDateLabel={t("platform.endDate")}
        onRefresh={() => {
          indicators.refetch()
          varCompare.refetch()
          basicInfo.refetch()
          positions.refetch()
        }}
        isFetching={isFetching}
      />

      {startDate > endDate && <p className="text-sm text-destructive">{t("investmentRisk.indicators.dateRangeError")}</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {t("investmentRisk.indicators.loadError")}
          </CardContent>
        </Card>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1 p-1">
          <TabsTrigger value="basic-info">{t("investmentRisk.indicators.tabBasicInfo")}</TabsTrigger>
          <TabsTrigger value="holdings">{t("investmentRisk.indicators.tabHoldings")}</TabsTrigger>
          <TabsTrigger value="core">{t("investmentRisk.indicators.tabCore")}</TabsTrigger>
          {RISK_DOMAINS.map((domain) => (
            <TabsTrigger key={domain.key} value={domain.key}>{t(`investmentRisk.domains.${domain.label}`)}</TabsTrigger>
          ))}
        </TabsList>

        {/* 基本信息 */}
        <TabsContent value="basic-info" className="mt-0 space-y-4">
          {basicInfo.isFetching && !basicInfo.data ? (
            <p className="text-muted-foreground animate-pulse text-sm">{t("investmentRisk.common.loading")}</p>
          ) : basicInfo.data ? (
            <Card>
              <CardHeader>
                <ModuleHeader title={t("investmentRisk.indicators.basicInfoTitle")} sqlIds={["SQL-OV-01"]} applicable={ALL_CATEGORIES} />
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <MetricCard label={t("investmentRisk.indicators.fund")} value={basicInfo.data.portfolio.port_name || fundId} detail={FUND_CATEGORY_LABELS[basicInfo.data.portfolio.fund_category] ?? (basicInfo.data.portfolio.port_type ?? "—")} />
                  <MetricCard label={t("investmentRisk.indicators.currency")} value={basicInfo.data.portfolio.base_currency ?? "—"} detail={t("investmentRisk.indicators.dataDate") + " " + (basicInfo.data.data_date ?? "—")} />
                  <MetricCard label={t("investmentRisk.indicators.inceptionDate")} value={basicInfo.data.portfolio.inception_date ?? "—"} detail={basicInfo.data.portfolio.is_active === false ? t("investmentRisk.indicators.statusClosed") : t("investmentRisk.indicators.statusActive")} />
                  {basicInfo.data.portfolio.is_mmf ? (
                    <MetricCard
                      label={t("investmentRisk.indicators.wamLimit")}
                      value={`${basicInfo.data.portfolio.mmf_wam_limit_days ?? "—"} 天`}
                      detail={`${t("investmentRisk.indicators.walLimit")} ${basicInfo.data.portfolio.mmf_wal_limit_days ?? "—"} 天`}
                    />
                  ) : (
                    <MetricCard
                      label={t("investmentRisk.indicators.fundType")}
                      value={FUND_CATEGORY_LABELS[basicInfo.data.portfolio.fund_category] ?? (basicInfo.data.portfolio.port_type ?? "—")}
                      detail={t("investmentRisk.indicators.statusLabel")}
                    />
                  )}
                </div>

                <div>
                  <p className="mb-2 text-sm font-semibold">{t("investmentRisk.indicators.managers")}</p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("investmentRisk.indicators.managerName")}</TableHead>
                        <TableHead>{t("investmentRisk.indicators.managerRole")}</TableHead>
                        <TableHead>{t("investmentRisk.indicators.managerTenure")}</TableHead>
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
                          <TableCell className="font-mono text-xs">{manager.begin_date ?? "—"} ~ {manager.end_date ?? t("investmentRisk.indicators.present")}</TableCell>
                        </TableRow>
                      ))}
                      {!basicInfo.data.managers.length && <EmptyRow columns={3} />}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          ) : (
            <p className="text-muted-foreground text-sm">{t("investmentRisk.indicators.noBasicInfo")}</p>
          )}
        </TabsContent>

        {/* 持倉明細 */}
        <TabsContent value="holdings" className="mt-0 space-y-4">
          <HoldingsDetailSection
            fundId={fundId}
            asOfDate={endDate}
            data={positions.data}
            isFetching={positions.isFetching}
            isError={positions.isError}
          />
        </TabsContent>

        {/* 核心風控指標 */}
        <TabsContent value="core" className="mt-0 space-y-5">
          <section>
            <EngineKpiPanel
              domain="overview"
              fundId={fundId}
              asOfDate={endDate}
              variant="metrics"
              title={t("investmentRisk.overview.exposureTitle")}
            />
          </section>

          {indicators.data ? (
            <>
              {(indicators.data.message || indicatorSeries.data?.message) ? (
                <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                  {indicators.data.message || indicatorSeries.data?.message}
                </p>
              ) : null}
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-semibold">{t("investmentRisk.indicators.coreTitle")}</h2>
                <SqlViewButton sqlIds={["SQL-RI-01"]} />
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                <MetricCard
                  label={t("investmentRisk.indicators.intervalReturn")}
                  value={percent(indicators.data.interval_return_pct)}
                />
                <MetricCard
                  label={t("investmentRisk.indicators.annualizedVol")}
                  value={percent(indicators.data.annualized_volatility_pct)}
                />
                <MetricCard
                  label={t("investmentRisk.indicators.maxDrawdown")}
                  value={percent(indicators.data.max_drawdown_pct)}
                />
                <MetricCard
                  label={t("investmentRisk.indicators.equityTurnover")}
                  value={percent(indicators.data.equity_turnover?.annualized_turnover_pct)}
                />
                <MetricCard
                  label={t("investmentRisk.indicators.equityBeta")}
                  value={indicators.data.equity_beta?.value == null ? "—" : indicators.data.equity_beta.value.toFixed(3)}
                />
              </div>

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
                    valueFormatter={(value) =>
                      Math.abs(value) >= 1 ? `${value.toFixed(2)}%` : `${value.toFixed(4)}%`
                    }
                  />
                </CardContent>
              </Card>

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
                    <MetricBlock label={t("investmentRisk.indicators.buyAmount")} value={money(indicators.data.equity_turnover?.buy_amount)} />
                    <MetricBlock label={t("investmentRisk.indicators.sellAmount")} value={money(indicators.data.equity_turnover?.sell_amount)} />
                    <MetricBlock label={t("investmentRisk.indicators.avgEquityBalance")} value={money(indicators.data.equity_turnover?.average_equity_balance)} />
                  </div>
                  <p className="text-muted-foreground mt-4 text-xs">{t("investmentRisk.indicators.turnoverMethodHint", { method: indicators.data.equity_turnover?.method ?? "—" })}</p>
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

          <RiskMetricBoardSection fundId={fundId} startDate={startDate} endDate={endDate} />
        </TabsContent>

        {/* 六大業務域：卡片铺满，风格对齐组合概况 */}
        {RISK_DOMAINS.map(({ key, Component }) => (
          <TabsContent key={key} value={key} className="mt-0">
            <Card>
              <CardContent className="pt-6">
                <Component fundId={fundId} asOfDate={endDate} startDate={startDate} endDate={endDate} />
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className="mt-1 text-xl font-semibold">{value}</p>
        {detail ? (
          <p className="text-muted-foreground mt-1 truncate text-xs" title={detail}>{detail}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function MetricBlock({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border p-3"><p className="text-muted-foreground text-xs">{label}</p><p className="mt-1 font-mono text-lg">{value}</p></div>
}

function EmptyRow({ columns }: { columns: number }) {
  const { t } = useTranslation()
  return <TableRow><TableCell colSpan={columns} className="h-20 text-center text-muted-foreground">{t("investmentRisk.common.empty")}</TableCell></TableRow>
}

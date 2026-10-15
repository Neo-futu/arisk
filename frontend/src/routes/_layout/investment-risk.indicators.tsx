/**
 * 投资风险 · 风险指标页（/investment-risk/indicators）
 *
 * 开发步骤（step-by-step）：
 * 1. 参数栏 + PageContext（fund / date）绑定，供 Ask AI 注入
 * 2. 组合信息 / KPI / 核心风险指标（含 VaR 三方法）用 WorkbenchTable 统一交互
 * 3. 六大类指标看板（metric-board）与持仓明细分区展示
 * 4. riskMetrics 写入 PageContext，Ask AI 回答 VaR 等时优先用页面真实数
 */
import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fsiApi, type PortfolioBasicInfo } from "@/fsiClient"
import { TrendLineChart } from "@/modules/investment-risk/dashboard-kit"
import { EngineKpiPanel } from "@/modules/investment-risk/EngineKpiPanel"
import { HoldingsDetailSection } from "@/modules/investment-risk/HoldingsDetailSection"
import { RiskMetricBoardSection } from "@/modules/investment-risk/RiskMetricBoardSection"
import { RISK_DOMAINS } from "@/modules/investment-risk/RiskDomainTabs"
import { SqlViewButton } from "@/modules/investment-risk/SqlViewButton"
import { useBindPageContext } from "@/platform/page-context"
import { WorkbenchTable, type WorkbenchColumn } from "@/platform/WorkbenchTable"

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

  // 供 AI Copilot / Agent 注入页面已展示的风险指标（含 VaR 三方法）
  useBindPageContext({
    portfolio: fundId,
    date: endDate,
    result: varCompare.data
      ? `max_var_pct_nav=${varCompare.data.max_var_pct_nav}`
      : indicators.data
        ? `interval_return_pct=${indicators.data.interval_return_pct}`
        : undefined,
    chart: activeTab === "core" ? "rolling-volatility / var-compare" : activeTab,
    riskMetrics: {
      fund_id: fundId,
      as_of_date: endDate,
      period: { start: startDate, end: endDate },
      indicators: indicators.data
        ? {
            interval_return_pct: indicators.data.interval_return_pct,
            annualized_volatility_pct: indicators.data.annualized_volatility_pct,
            max_drawdown_pct: indicators.data.max_drawdown_pct,
            equity_turnover_pct: indicators.data.equity_turnover?.annualized_turnover_pct ?? null,
            equity_beta: indicators.data.equity_beta?.value ?? null,
          }
        : null,
      var_compare: varCompare.data
        ? {
            confidence: varCompare.data.confidence,
            horizon_days: varCompare.data.horizon_days,
            max_var_pct_nav: varCompare.data.max_var_pct_nav,
            methods: (varCompare.data.results ?? []).map((row) => ({
              method: row.method_requested ?? row.method,
              var_hkd: row.var_hkd,
              var_pct_nav: row.var_pct_nav,
              cvar_hkd: row.cvar_hkd,
              sample_size: row.sample_size,
            })),
          }
        : null,
    },
  })

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

                <ManagersWorkbenchTable
                  fundId={fundId}
                  asOfDate={endDate}
                  managers={basicInfo.data.managers}
                />
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
          <Card className="min-h-[280px]">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">{t("investmentRisk.overview.exposureTitle")}</CardTitle>
                <SqlViewButton sqlIds={["SQL-RI-01"]} />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <EngineKpiPanel
                domain="overview"
                fundId={fundId}
                asOfDate={endDate}
                variant="metrics"
                title={t("investmentRisk.overview.exposureTitle")}
                embed
              />
              {indicators.data ? (
                <div className="grid min-h-[112px] gap-4 md:grid-cols-2 xl:grid-cols-5">
                  <div className="rounded-lg border px-4 py-3">
                    <p className="text-muted-foreground text-xs">{t("investmentRisk.indicators.intervalReturn")}</p>
                    <p className="mt-1 text-xl font-semibold font-mono">{percent(indicators.data.interval_return_pct)}</p>
                  </div>
                  <div className="rounded-lg border px-4 py-3">
                    <p className="text-muted-foreground text-xs">{t("investmentRisk.indicators.annualizedVol")}</p>
                    <p className="mt-1 text-xl font-semibold font-mono">{percent(indicators.data.annualized_volatility_pct)}</p>
                  </div>
                  <div className="rounded-lg border px-4 py-3">
                    <p className="text-muted-foreground text-xs">{t("investmentRisk.indicators.maxDrawdown")}</p>
                    <p className="mt-1 text-xl font-semibold font-mono">{percent(indicators.data.max_drawdown_pct)}</p>
                  </div>
                  <div className="rounded-lg border px-4 py-3">
                    <p className="text-muted-foreground text-xs">{t("investmentRisk.indicators.equityTurnover")}</p>
                    <p className="mt-1 text-xl font-semibold font-mono">{percent(indicators.data.equity_turnover?.annualized_turnover_pct)}</p>
                  </div>
                  <div className="rounded-lg border px-4 py-3">
                    <p className="text-muted-foreground text-xs">{t("investmentRisk.indicators.equityBeta")}</p>
                    <p className="mt-1 text-xl font-semibold font-mono">
                      {indicators.data.equity_beta?.value == null ? "—" : indicators.data.equity_beta.value.toFixed(3)}
                    </p>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>

          {indicators.data ? (
            <>
              {(indicators.data.message || indicatorSeries.data?.message) ? (
                <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                  {indicators.data.message || indicatorSeries.data?.message}
                </p>
              ) : null}

              <Card className="min-h-[520px]">
                <CardHeader>
                  <ModuleHeader title={t("investmentRisk.indicators.rollingVol")} sqlIds={["SQL-RI-02"]} applicable={ALL_CATEGORIES} />
                </CardHeader>
                <CardContent>
                  <Tabs defaultValue="chart" className="space-y-3">
                    <TabsList>
                      <TabsTrigger value="chart">{t("investmentRisk.indicators.tabChart")}</TabsTrigger>
                      <TabsTrigger value="table">{t("investmentRisk.indicators.tabTable")}</TabsTrigger>
                    </TabsList>
                    <div className="h-[360px]">
                      <TabsContent value="chart" className="mt-0 h-full">
                        <div className="h-full rounded-lg border p-3">
                          <TrendLineChart
                            values={(indicatorSeries.data?.points ?? []).map((row) => row.rolling_volatility_pct ?? 0)}
                            labels={(indicatorSeries.data?.points ?? []).map((row) => String(row.date).slice(5))}
                            lineColor="#dc2626"
                            pointColor="#fb7185"
                            className="h-full w-full"
                            height={360}
                            valueFormatter={(value) =>
                              Math.abs(value) >= 1 ? `${value.toFixed(2)}%` : `${value.toFixed(4)}%`
                            }
                          />
                        </div>
                      </TabsContent>
                      <TabsContent value="table" className="mt-0 h-full">
                        <IndicatorSeriesWorkbenchTable
                          fundId={fundId}
                          startDate={startDate}
                          endDate={endDate}
                          points={indicatorSeries.data?.points ?? []}
                          mode="full"
                          embedded
                        />
                      </TabsContent>
                    </div>
                  </Tabs>
                </CardContent>
              </Card>

              <IndicatorSeriesWorkbenchTable
                fundId={fundId}
                startDate={startDate}
                endDate={endDate}
                points={(indicatorSeries.data?.points ?? []).slice(-10)}
                mode="drawdown"
                title={t("investmentRisk.indicators.drawdownVarSummary")}
                toolbarExtra={<SqlViewButton sqlIds={["SQL-RI-02", "SQL-VAR-01"]} />}
                bodyClassName="h-[280px] overflow-auto rounded-lg border"
              />

              <Card className="min-h-[220px]">
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

              {varCompare.data ? (
                <VarCompareWorkbenchTable
                  fundId={fundId}
                  asOfDate={endDate}
                  maxVarPct={varCompare.data.max_var_pct_nav}
                  results={varCompare.data.results}
                  methodLabels={methodLabels}
                />
              ) : null}
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

function ManagersWorkbenchTable({
  fundId,
  asOfDate,
  managers,
}: {
  fundId: string
  asOfDate: string
  managers: PortfolioBasicInfo["managers"]
}) {
  const { t } = useTranslation()
  const columns = useMemo<WorkbenchColumn<PortfolioBasicInfo["managers"][number]>[]>(() => [
    {
      key: "person_name",
      header: t("investmentRisk.indicators.managerName"),
      accessor: (row) => row.person_name,
      cell: (row) => (
        <span className="font-medium">
          {row.person_name}
          {row.person_name_en ? <span className="ml-1 text-xs text-muted-foreground">{row.person_name_en}</span> : null}
        </span>
      ),
      exportValue: (row) => row.person_name,
    },
    {
      key: "role",
      header: t("investmentRisk.indicators.managerRole"),
      filterable: true,
      accessor: (row) => PERSON_ROLE_LABELS[row.role] ?? row.role,
    },
    {
      key: "tenure",
      header: t("investmentRisk.indicators.managerTenure"),
      accessor: (row) => `${row.begin_date ?? "—"} ~ ${row.end_date ?? t("investmentRisk.indicators.present")}`,
      cell: (row) => (
        <span className="font-mono text-xs">
          {row.begin_date ?? "—"} ~ {row.end_date ?? t("investmentRisk.indicators.present")}
        </span>
      ),
    },
  ], [t])

  return (
    <WorkbenchTable
      title={t("investmentRisk.indicators.managers")}
      rows={managers}
      columns={columns}
      rowId={(row) => `${row.person_id}-${row.role}-${row.begin_date}`}
      exportFilename={`managers-${fundId}-${asOfDate}.csv`}
      initialSortKey="person_name"
    />
  )
}

type SeriesPoint = {
  date: string
  nav: number
  daily_return_pct: number | null
  cumulative_return_pct: number | null
  rolling_volatility_pct: number | null
  drawdown_pct: number | null
  rolling_var_95_pct: number | null
}

function IndicatorSeriesWorkbenchTable({
  fundId,
  startDate,
  endDate,
  points,
  mode,
  title,
  toolbarExtra,
  bodyClassName,
  embedded = false,
}: {
  fundId: string
  startDate: string
  endDate: string
  points: SeriesPoint[]
  mode: "full" | "drawdown"
  title?: string
  toolbarExtra?: ReactNode
  bodyClassName?: string
  embedded?: boolean
}) {
  const { t } = useTranslation()
  const columns = useMemo<WorkbenchColumn<SeriesPoint>[]>(() => {
    const base: WorkbenchColumn<SeriesPoint>[] = [
      { key: "date", header: t("investmentRisk.indicators.date"), accessor: (row) => row.date },
    ]
    if (mode === "full") {
      base.push(
        {
          key: "nav",
          header: t("investmentRisk.indicators.unitNav"),
          align: "right",
          accessor: (row) => row.nav,
          cell: (row) => <span className="font-mono">{row.nav == null ? "—" : Number(row.nav).toFixed(4)}</span>,
        },
        {
          key: "daily_return_pct",
          header: t("investmentRisk.indicators.dailyReturn"),
          align: "right",
          accessor: (row) => row.daily_return_pct,
          cell: (row) => <span className="font-mono">{percent(row.daily_return_pct, 3)}</span>,
        },
        {
          key: "cumulative_return_pct",
          header: t("investmentRisk.indicators.cumulativeReturn"),
          align: "right",
          accessor: (row) => row.cumulative_return_pct,
          cell: (row) => <span className="font-mono">{percent(row.cumulative_return_pct, 3)}</span>,
        },
        {
          key: "rolling_volatility_pct",
          header: t("investmentRisk.indicators.rollingVolPct"),
          align: "right",
          accessor: (row) => row.rolling_volatility_pct,
          cell: (row) => <span className="font-mono">{percent(row.rolling_volatility_pct, 3)}</span>,
        },
      )
    } else {
      base.push({
        key: "daily_return_pct",
        header: t("investmentRisk.indicators.dailyReturn"),
        align: "right",
        accessor: (row) => row.daily_return_pct,
        cell: (row) => <span className="font-mono">{percent(row.daily_return_pct, 3)}</span>,
      })
    }
    base.push(
      {
        key: "drawdown_pct",
        header: t("investmentRisk.indicators.drawdown"),
        align: "right",
        accessor: (row) => row.drawdown_pct,
        cell: (row) => <span className="font-mono">{percent(row.drawdown_pct, 3)}</span>,
      },
      {
        key: "rolling_var_95_pct",
        header: t("investmentRisk.indicators.rollingVar95"),
        align: "right",
        accessor: (row) => row.rolling_var_95_pct,
        cell: (row) => <span className="font-mono">{percent(row.rolling_var_95_pct, 3)}</span>,
      },
    )
    return base
  }, [mode, t])

  return (
    <WorkbenchTable
      title={title ?? t("investmentRisk.indicators.rollingVol")}
      rows={points}
      columns={columns}
      rowId={(row) => row.date}
      exportFilename={`${mode === "full" ? "rolling-volatility" : "drawdown-var"}-${fundId}-${startDate}-${endDate}.csv`}
      initialSortKey="date"
      toolbarExtra={toolbarExtra}
      bodyClassName={bodyClassName}
      embedded={embedded}
    />
  )
}

function VarCompareWorkbenchTable({
  fundId,
  asOfDate,
  maxVarPct,
  results,
  methodLabels,
}: {
  fundId: string
  asOfDate: string
  maxVarPct: number | null | undefined
  results: Array<{
    method?: string
    method_requested?: string
    var_hkd?: number | null
    var_pct_nav?: number | null
    cvar_hkd?: number | null
    sample_size?: number | null
  }>
  methodLabels: Record<string, string>
}) {
  const { t } = useTranslation()
  const columns = useMemo<WorkbenchColumn<(typeof results)[number]>[]>(() => [
    {
      key: "method",
      header: t("investmentRisk.indicators.method"),
      filterable: true,
      accessor: (row) => methodLabels[row.method_requested ?? ""] ?? row.method ?? "",
    },
    {
      key: "var_hkd",
      header: t("investmentRisk.indicators.varHkd"),
      align: "right",
      accessor: (row) => row.var_hkd,
      cell: (row) => <span className="font-mono">{money(row.var_hkd)}</span>,
    },
    {
      key: "var_pct_nav",
      header: t("investmentRisk.indicators.varPctNav"),
      align: "right",
      accessor: (row) => row.var_pct_nav,
      cell: (row) => <span className="font-mono">{percent(row.var_pct_nav, 4)}</span>,
    },
    {
      key: "cvar_hkd",
      header: t("investmentRisk.indicators.cvarHkd"),
      align: "right",
      accessor: (row) => row.cvar_hkd,
      cell: (row) => <span className="font-mono">{money(row.cvar_hkd)}</span>,
    },
    {
      key: "sample_size",
      header: t("investmentRisk.indicators.sampleSize"),
      align: "right",
      accessor: (row) => row.sample_size,
    },
  ], [methodLabels, t])

  return (
    <WorkbenchTable
      title={t("investmentRisk.indicators.varTitle")}
      rows={results}
      columns={columns}
      rowId={(row) => row.method_requested ?? row.method ?? "method"}
      exportFilename={`var-compare-${fundId}-${asOfDate}.csv`}
      initialSortKey="var_pct_nav"
      bodyClassName="h-[240px] overflow-auto rounded-lg border"
      toolbarExtra={(
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{t("investmentRisk.indicators.varMax", { value: percent(maxVarPct, 4) })}</Badge>
          <SqlViewButton sqlIds={["SQL-VAR-01"]} />
        </div>
      )}
    />
  )
}

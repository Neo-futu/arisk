import { useQuery } from "@tanstack/react-query"
import { useMemo, type ReactElement } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fsiApi } from "@/fsiClient"
import { HorizontalBarList } from "@/modules/investment-risk/dashboard-kit"
import { EquityBetaContributionCard } from "@/modules/investment-risk/EquityBetaContributionCard"
import { SqlViewButton } from "@/modules/investment-risk/SqlViewButton"
import { WorkbenchTable, type WorkbenchColumn } from "@/platform/WorkbenchTable"

function pct(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${Number(value).toFixed(digits)}%`
}
function money(value: number | null | undefined) {
  return value == null ? "—" : Number(value).toLocaleString("zh-HK", { maximumFractionDigits: 0 })
}
function num(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : Number(value).toFixed(digits)
}

function Kpi({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
      {detail ? <p className="text-muted-foreground mt-1 truncate text-xs" title={detail}>{detail}</p> : null}
    </div>
  )
}

function DomainState({ loading, error, empty }: { loading: boolean; error: boolean; empty?: boolean }) {
  const { t } = useTranslation()
  if (loading) return <p className="text-muted-foreground animate-pulse text-sm">{t("investmentRisk.domains.loading")}</p>
  if (error) return <p className="text-destructive text-sm">{t("investmentRisk.domains.error")}</p>
  if (empty) return <p className="text-muted-foreground text-sm">{t("investmentRisk.domains.empty")}</p>
  return null
}

export interface DomainProps {
  fundId: string
  asOfDate: string
  startDate: string
  endDate: string
}

function AttributionDomain({ fundId, startDate, endDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-attribution", fundId, startDate, endDate],
    queryFn: () => fsiApi.getPerformanceAttribution(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const betaQuery = useQuery({
    queryKey: ["domain-attribution-equity-beta", fundId, startDate, endDate],
    queryFn: () => fsiApi.getRiskIndicators(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const data = query.data
  const equityBeta = betaQuery.data?.equity_beta
  const contributionColumns = useMemo<WorkbenchColumn<{ asset_class: string; net_pnl: number; contribution_pct: number | null }>[]>(() => [
    { key: "asset_class", header: t("investmentRisk.domains.assetClass"), filterable: true, accessor: (row) => row.asset_class },
    {
      key: "net_pnl",
      header: t("investmentRisk.domains.netPnl"),
      align: "right",
      accessor: (row) => row.net_pnl,
      cell: (row) => <span className={`font-mono ${row.net_pnl < 0 ? "text-destructive" : "text-emerald-600"}`}>{money(row.net_pnl)}</span>,
    },
    {
      key: "contribution_pct",
      header: t("investmentRisk.domains.contributionPct"),
      align: "right",
      accessor: (row) => row.contribution_pct,
      cell: (row) => <span className="font-mono">{pct(row.contribution_pct, 2)}</span>,
    },
  ], [t])
  const pnlColumns = useMemo<WorkbenchColumn<{ security_code: string | null; security_name: string; sector: string; net_pnl: number; _rowKey?: string }>[]>(() => [
    {
      key: "security_name",
      header: t("investmentRisk.domains.security"),
      accessor: (row) => row.security_name,
      cell: (row) => (
        <span className="font-medium">
          {row.security_name}
          <span className="ml-1 text-xs text-muted-foreground">{row.security_code}</span>
        </span>
      ),
      exportValue: (row) => `${row.security_name} ${row.security_code ?? ""}`.trim(),
    },
    { key: "sector", header: t("investmentRisk.domains.sector"), filterable: true, accessor: (row) => row.sector },
    {
      key: "net_pnl",
      header: t("investmentRisk.domains.netPnl"),
      align: "right",
      accessor: (row) => row.net_pnl,
      cell: (row) => <span className={`font-mono ${row.net_pnl < 0 ? "text-destructive" : "text-emerald-600"}`}>{money(row.net_pnl)}</span>,
    },
  ], [t])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("investmentRisk.domains.attributionTitle")}</h3>
        <SqlViewButton sqlIds={["SQL-AT-01", "SQL-AT-04", "SQL-AT-05", "SQL-AT-06"]} />
      </div>
      <DomainState loading={query.isFetching && !data} error={query.isError} empty={!!data && !data.summary} />
      {data && (
        <>
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label={t("investmentRisk.domains.fundReturn")} value={pct(data.summary.fund_return_pct, 3)} />
            <Kpi label={t("investmentRisk.domains.benchmarkReturn")} value={pct(data.summary.benchmark_return_pct, 3)} detail={`${t("investmentRisk.domains.benchmarkReturn")} ${data.benchmark_id ?? t("investmentRisk.domains.benchmarkUnset")}`} />
            <Kpi label={t("investmentRisk.domains.activeReturn")} value={pct(data.summary.active_return_pct, 3)} />
            <Kpi label={t("investmentRisk.domains.allocationEffect")} value={pct(data.summary.allocation_effect_pct, 3)} />
            <Kpi label={t("investmentRisk.domains.selectionEffect")} value={pct(data.summary.selection_effect_pct, 3)} />
            <Kpi label={t("investmentRisk.domains.interactionEffect")} value={pct(data.summary.interaction_effect_pct, 3)} />
          </div>
          <WorkbenchTable
            title={t("investmentRisk.domains.assetContribution")}
            rows={data.asset_contribution}
            columns={contributionColumns}
            rowId={(row) => row.asset_class}
            exportFilename={`attribution-asset-${fundId}-${endDate}.csv`}
            initialSortKey="contribution_pct"
          />
          <div className="grid gap-4 xl:grid-cols-2">
            <WorkbenchTable
              title={t("investmentRisk.domains.topWinners")}
              rows={data.top_winners.map((row, index) => ({ ...row, _rowKey: `winner-${row.security_code ?? row.security_name}-${index}` }))}
              columns={pnlColumns}
              rowId={(row) => row._rowKey ?? row.security_code ?? row.security_name}
              exportFilename={`attribution-winners-${fundId}-${endDate}.csv`}
              initialSortKey="net_pnl"
            />
            <WorkbenchTable
              title={t("investmentRisk.domains.topLosers")}
              rows={data.top_losers.map((row, index) => ({ ...row, _rowKey: `loser-${row.security_code ?? row.security_name}-${index}` }))}
              columns={pnlColumns}
              rowId={(row) => row._rowKey ?? row.security_code ?? row.security_name}
              exportFilename={`attribution-losers-${fundId}-${endDate}.csv`}
              initialSortKey="net_pnl"
            />
          </div>
        </>
      )}
      {equityBeta ? (
        <EquityBetaContributionCard
          fundId={fundId}
          asOfDate={endDate}
          portfolioBeta={equityBeta.value}
          benchmarkId={equityBeta.benchmark_id}
          constituents={equityBeta.constituents ?? []}
          applicable={(equityBeta.constituents?.length ?? 0) > 0 || equityBeta.value != null}
        />
      ) : betaQuery.isFetching ? (
        <p className="text-muted-foreground animate-pulse text-sm">{t("investmentRisk.domains.loading")}</p>
      ) : null}
    </div>
  )
}

function RatesCreditDomain({ fundId, asOfDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-rates-credit", fundId, asOfDate],
    queryFn: () => fsiApi.getRatesCredit(fundId, asOfDate).then((r) => r.data),
    retry: 1,
  })
  const data = query.data
  const issuerColumns = useMemo<WorkbenchColumn<{ issuer: string; market_value: number; weight_pct: number }>[]>(() => [
    { key: "issuer", header: t("investmentRisk.domains.issuer"), accessor: (row) => row.issuer },
    {
      key: "market_value",
      header: t("investmentRisk.domains.marketValue"),
      align: "right",
      accessor: (row) => row.market_value,
      cell: (row) => <span className="font-mono">{money(row.market_value)}</span>,
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.domains.weight"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{pct(row.weight_pct)}</span>,
    },
  ], [t])
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("investmentRisk.domains.ratesCreditTitle")}</h3>
        <SqlViewButton sqlIds={["SQL-RC-01", "SQL-RC-02", "SQL-RC-03", "SQL-RC-04"]} />
      </div>
      <DomainState loading={query.isFetching && !data} error={query.isError} empty={!!data && data.bond_count === 0} />
      {data && (
        <>
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
            <Kpi label={t("investmentRisk.domains.bondHoldings")} value={money(data.total_bond_market_value)} detail={t("investmentRisk.domains.bondHoldingsDetail", { count: data.bond_count, pct: pct(data.bond_exposure_pct_nav) })} />
            <Kpi label={t("investmentRisk.domains.weightedDuration")} value={num(data.weighted_duration_years, 2) + " 年"} />
            <Kpi label="DV01" value={money(data.portfolio_dv01)} />
            <Kpi label="CS01" value={money(data.portfolio_cs01)} />
            <Kpi label={t("investmentRisk.domains.issuerHhi")} value={num(data.issuer_concentration.hhi, 3)} />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.tsdBuckets")}</CardTitle></CardHeader>
              <CardContent>
                <HorizontalBarList items={data.krd_buckets.map((b) => ({ label: b.bucket, value: b.weight_pct_bond }))} formatter={(v) => pct(v, 2)} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.ratingDist")}</CardTitle></CardHeader>
              <CardContent>
                <HorizontalBarList items={data.rating_distribution.map((r) => ({ label: r.rating, value: r.weight_pct }))} formatter={(v) => pct(v, 2)} />
              </CardContent>
            </Card>
          </div>
          <WorkbenchTable
            title={t("investmentRisk.domains.issuerConcentration")}
            rows={data.issuer_concentration.top_issuers}
            columns={issuerColumns}
            rowId={(row) => row.issuer}
            exportFilename={`rates-issuers-${fundId}-${asOfDate}.csv`}
            initialSortKey="weight_pct"
          />
        </>
      )}
    </div>
  )
}

function LiquidityDomain({ fundId, asOfDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-liquidity", fundId, asOfDate],
    queryFn: () => fsiApi.getLiquidityStress(fundId, asOfDate, { redemptionPct: 20, rateShockBps: 50 }).then((r) => r.data),
    retry: 1,
  })
  const data = query.data
  const ladderColumns = useMemo<WorkbenchColumn<{ asset_class: string; market_value: number; ttl_days: number; cumulative_pct_nav: number | null }>[]>(() => [
    { key: "asset_class", header: t("investmentRisk.domains.assetClass"), filterable: true, accessor: (row) => row.asset_class },
    {
      key: "market_value",
      header: t("investmentRisk.domains.marketValue"),
      align: "right",
      accessor: (row) => row.market_value,
      cell: (row) => <span className="font-mono">{money(row.market_value)}</span>,
    },
    {
      key: "ttl_days",
      header: t("investmentRisk.domains.ttlDays"),
      align: "right",
      accessor: (row) => row.ttl_days,
      cell: (row) => <span className="font-mono">{num(row.ttl_days, 1)}</span>,
    },
    {
      key: "cumulative_pct_nav",
      header: t("investmentRisk.domains.cumulativePctNav"),
      align: "right",
      accessor: (row) => row.cumulative_pct_nav,
      cell: (row) => <span className="font-mono">{pct(row.cumulative_pct_nav)}</span>,
    },
  ], [t])
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("investmentRisk.domains.liquidityTitle")}</h3>
        <SqlViewButton sqlIds={["SQL-LS-01", "SQL-LS-02", "SQL-LS-03"]} />
      </div>
      <DomainState loading={query.isFetching && !data} error={query.isError} />
      {data && (
        <>
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
            <Kpi label={t("investmentRisk.domains.ttl10")} value={num(data.ttl_snapshot.ttl_10pct_days, 1) + " 天"} />
            <Kpi label={t("investmentRisk.domains.ttl25")} value={num(data.ttl_snapshot.ttl_25pct_days, 1) + " 天"} />
            <Kpi label={t("investmentRisk.domains.ttl50")} value={num(data.ttl_snapshot.ttl_50pct_days, 1) + " 天"} />
            <Kpi label={t("investmentRisk.domains.lcr")} value={num(data.stress_summary.liquidity_coverage_ratio, 2)} />
            <Kpi label={t("investmentRisk.domains.stressedNav")} value={money(data.stress_summary.projected_stressed_nav)} />
          </div>
          {data.breach_flags.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {data.breach_flags.map((flag) => <Badge key={flag} variant="destructive">{flag}</Badge>)}
            </div>
          ) : null}
          <WorkbenchTable
            title={t("investmentRisk.domains.liquidityLadder")}
            rows={data.liquidity_ladder}
            columns={ladderColumns}
            rowId={(row) => row.asset_class}
            exportFilename={`liquidity-ladder-${fundId}-${asOfDate}.csv`}
            initialSortKey="ttl_days"
          />
        </>
      )}
    </div>
  )
}

function MacroDomain({ fundId, startDate, endDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-macro", fundId, startDate, endDate],
    queryFn: () => fsiApi.getMacroDynamics(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const data = query.data
  const macroColumns = useMemo<WorkbenchColumn<{ index_code: string; period_return_pct: number | null; annualized_volatility_pct: number | null }>[]>(() => [
    { key: "index_code", header: t("investmentRisk.domains.index"), accessor: (row) => row.index_code, cell: (row) => <span className="font-mono">{row.index_code}</span> },
    {
      key: "period_return_pct",
      header: t("investmentRisk.domains.periodReturn"),
      align: "right",
      accessor: (row) => row.period_return_pct,
      cell: (row) => <span className="font-mono">{pct(row.period_return_pct, 3)}</span>,
    },
    {
      key: "annualized_volatility_pct",
      header: t("investmentRisk.domains.fundVol"),
      align: "right",
      accessor: (row) => row.annualized_volatility_pct,
      cell: (row) => <span className="font-mono">{pct(row.annualized_volatility_pct, 2)}</span>,
    },
  ], [t])
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("investmentRisk.domains.macroTitle")}</h3>
        <SqlViewButton sqlIds={["SQL-MA-01", "SQL-MA-02", "SQL-MA-03"]} />
      </div>
      <DomainState loading={query.isFetching && !data} error={query.isError} />
      {data && (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <Kpi label={t("investmentRisk.domains.regime")} value={String(data.fund_regime.regime)} detail={t("investmentRisk.domains.regimeSamples", { count: data.fund_regime.sample_size })} />
            <Kpi label={t("investmentRisk.domains.fundVol")} value={pct(data.fund_regime.annualized_volatility_pct, 2)} />
            <Kpi label={t("investmentRisk.domains.macroCount")} value={String(data.macro_indicators.length)} />
          </div>
          <WorkbenchTable
            title={t("investmentRisk.domains.macroQuotes")}
            rows={data.macro_indicators}
            columns={macroColumns}
            rowId={(row) => row.index_code}
            exportFilename={`macro-quotes-${fundId}-${endDate}.csv`}
            initialSortKey="period_return_pct"
          />
          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.fundVsMarket")}</CardTitle></CardHeader>
            <CardContent>
              <HorizontalBarList items={data.fund_vs_market_correlations.map((c) => ({ label: c.index_code, value: c.correlation }))} formatter={(v) => num(v, 3)} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function FactorDomain({ fundId, startDate, endDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-factor", fundId, startDate, endDate],
    queryFn: () => fsiApi.getFactorBehavior(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const data = query.data
  const crowdingColumns = useMemo<WorkbenchColumn<{ security_code: string; security_name: string; weight_pct: number; crowding_ratio: number | null }>[]>(() => [
    {
      key: "security_name",
      header: t("investmentRisk.domains.security"),
      accessor: (row) => row.security_name,
      cell: (row) => (
        <span className="font-medium">
          {row.security_name}
          <span className="ml-1 text-xs text-muted-foreground">{row.security_code}</span>
        </span>
      ),
      exportValue: (row) => `${row.security_name} ${row.security_code}`,
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.domains.weight"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{pct(row.weight_pct, 2)}</span>,
    },
    {
      key: "crowding_ratio",
      header: t("investmentRisk.domains.crowdingRatio"),
      align: "right",
      accessor: (row) => row.crowding_ratio,
      cell: (row) => <span className="font-mono">{num(row.crowding_ratio, 3)}</span>,
    },
  ], [t])
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("investmentRisk.domains.factorTitle")}</h3>
        <SqlViewButton sqlIds={["SQL-FB-01", "SQL-FB-02", "SQL-FB-03"]} />
      </div>
      <DomainState loading={query.isFetching && !data} error={query.isError} />
      {data && (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Kpi label={t("investmentRisk.domains.momentum")} value={num(data.style_exposure.momentum_exposure, 3)} />
            <Kpi label={t("investmentRisk.domains.lowVol")} value={num(data.style_exposure.low_volatility_exposure, 3)} />
            <Kpi label={t("investmentRisk.domains.size")} value={num(data.style_exposure.size_exposure, 3)} />
            <Kpi label="行業 HHI" value={num(data.sector_concentration.hhi, 3)} detail={t("investmentRisk.domains.turnoverShort", { value: pct(data.trading_behavior.turnover_pct, 2) })} />
          </div>
          {data.warnings.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {data.warnings.map((w) => <Badge key={w} variant="outline" className="text-muted-foreground">{w}</Badge>)}
            </div>
          ) : null}
          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.sectorConcentration")}</CardTitle></CardHeader>
              <CardContent>
                <HorizontalBarList items={data.sector_concentration.weights.map((w) => ({ label: w.sector, value: w.weight_pct }))} formatter={(v) => pct(v, 2)} />
              </CardContent>
            </Card>
            <WorkbenchTable
              title={t("investmentRisk.domains.crowdingTop")}
              rows={data.trading_behavior.crowding_top}
              columns={crowdingColumns}
              rowId={(row) => row.security_code}
              exportFilename={`factor-crowding-${fundId}-${endDate}.csv`}
              initialSortKey="weight_pct"
            />
          </div>
        </>
      )}
    </div>
  )
}

function PretradeDomain({ fundId, asOfDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-pretrade", fundId, asOfDate],
    queryFn: () => fsiApi.getPretradeCheck(fundId, asOfDate, {
      tradeAmount: 10_000_000, tradeSide: "BUY", assetClass: "BOND_CORP", durationYears: 2, issuerName: "UNKNOWN_ISSUER",
    }).then((r) => r.data),
    retry: 1,
  })
  const data = query.data
  const decisionVariant = data?.decision === "BLOCK" ? "destructive" : data?.decision === "ALLOW_WITH_WARNING" ? "secondary" : "default"
  const limitRows = data
    ? [
        {
          id: "duration",
          metric: t("investmentRisk.domains.durationRow"),
          current: num(data.current.duration_years, 2),
          projected: num(data.projected.duration_years, 2),
          limit: num(data.limits.duration_years, 2),
        },
        {
          id: "issuer",
          metric: t("investmentRisk.domains.issuerPctRow"),
          current: pct(data.current.issuer_pct_nav),
          projected: pct(data.projected.issuer_pct_nav),
          limit: pct(data.limits.issuer_pct_nav),
        },
        {
          id: "te",
          metric: t("investmentRisk.domains.trackingErrorRow"),
          current: "—",
          projected: pct(data.projected.tracking_error_proxy_pct),
          limit: pct(data.limits.tracking_error_proxy_pct),
        },
        {
          id: "dv01",
          metric: t("investmentRisk.domains.dv01Row"),
          current: money(data.current.portfolio_dv01),
          projected: money(data.projected.portfolio_dv01),
          limit: "—",
        },
      ]
    : []
  const limitColumns = useMemo<WorkbenchColumn<(typeof limitRows)[number]>[]>(() => [
    { key: "metric", header: t("investmentRisk.domains.metric"), accessor: (row) => row.metric },
    { key: "current", header: t("investmentRisk.domains.current"), align: "right", accessor: (row) => row.current, cell: (row) => <span className="font-mono">{row.current}</span> },
    { key: "projected", header: t("investmentRisk.domains.projected"), align: "right", accessor: (row) => row.projected, cell: (row) => <span className="font-mono">{row.projected}</span> },
    { key: "limit", header: t("investmentRisk.domains.limitCol"), align: "right", accessor: (row) => row.limit, cell: (row) => <span className="font-mono">{row.limit}</span> },
  ], [t])
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("investmentRisk.domains.pretradeTitle")}</h3>
        <SqlViewButton sqlIds={["SQL-PT-01", "SQL-PT-02"]} />
      </div>
      <DomainState loading={query.isFetching && !data} error={query.isError} />
      {data && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={decisionVariant}>{t("investmentRisk.domains.decision", { value: data.decision })}</Badge>
            {data.breach_flags.map((f) => <Badge key={f} variant="destructive">{f}</Badge>)}
          </div>
          <WorkbenchTable
            title={t("investmentRisk.domains.durationLimits")}
            rows={limitRows}
            columns={limitColumns}
            rowId={(row) => row.id}
            exportFilename={`pretrade-limits-${fundId}-${asOfDate}.csv`}
            selectable={false}
          />
        </>
      )}
    </div>
  )
}

export const RISK_DOMAINS: ReadonlyArray<{
  key: string
  label: string
  Component: (props: DomainProps) => ReactElement
}> = [
  { key: "attribution", label: "tabAttribution", Component: AttributionDomain },
  { key: "rates-credit", label: "tabRatesCredit", Component: RatesCreditDomain },
  { key: "liquidity", label: "tabLiquidity", Component: LiquidityDomain },
  { key: "macro", label: "tabMacro", Component: MacroDomain },
  { key: "factor", label: "tabFactor", Component: FactorDomain },
  { key: "pretrade", label: "tabPretrade", Component: PretradeDomain },
]
const DOMAINS = RISK_DOMAINS

export function RiskDomainTabs(props: DomainProps) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("investmentRisk.domainTabs.title")}</CardTitle>
        <p className="text-muted-foreground text-sm">
          {t("investmentRisk.domainTabs.subtitle")}
        </p>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue={DOMAINS[0].key}>
          <TabsList className="flex-wrap">
            {DOMAINS.map((domain) => (
              <TabsTrigger key={domain.key} value={domain.key}>{t(`investmentRisk.domains.${domain.label}`)}</TabsTrigger>
            ))}
          </TabsList>
          {DOMAINS.map(({ key, Component }) => (
            <TabsContent key={key} value={key} className="mt-4">
              <Component {...props} />
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  )
}

export default RiskDomainTabs

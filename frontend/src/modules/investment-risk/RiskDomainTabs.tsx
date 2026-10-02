import { useQuery } from "@tanstack/react-query"
import type { ReactElement } from "react"
import { useTranslation } from "react-i18next"

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
import { fsiApi } from "@/fsiClient"
import { HorizontalBarList } from "@/modules/investment-risk/dashboard-kit"
import { EquityBetaContributionCard } from "@/modules/investment-risk/EquityBetaContributionCard"
import { SqlViewButton } from "@/modules/investment-risk/SqlViewButton"

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

// ── 業績歸因 ────────────────────────────────────────────────────
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
          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.assetContribution")}</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.domains.assetClass")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.netPnl")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.contributionPct")}</TableHead></TableRow></TableHeader>
                <TableBody>
                  {data.asset_contribution.map((row) => (
                    <TableRow key={row.asset_class}>
                      <TableCell className="font-medium">{row.asset_class}</TableCell>
                      <TableCell className={`text-right font-mono ${row.net_pnl < 0 ? "text-destructive" : "text-emerald-600"}`}>{money(row.net_pnl)}</TableCell>
                      <TableCell className="text-right font-mono">{pct(row.contribution_pct, 2)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.asset_contribution.length && <EmptyRow columns={3} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.topWinners")}</CardTitle></CardHeader>
              <CardContent>
                <PnlTable rows={data.top_winners} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.topLosers")}</CardTitle></CardHeader>
              <CardContent>
                <PnlTable rows={data.top_losers} />
              </CardContent>
            </Card>
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

function PnlTable({ rows }: { rows: Array<{ security_code: string | null; security_name: string; sector: string; net_pnl: number; contribution_pct: number | null }> }) {
  const { t } = useTranslation()
  return (
    <Table>
      <TableHeader><TableRow><TableHead>{t("investmentRisk.domains.security")}</TableHead><TableHead>{t("investmentRisk.domains.sector")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.netPnl")}</TableHead></TableRow></TableHeader>
      <TableBody>
        {rows.map((row, index) => (
          <TableRow key={`${row.security_code ?? index}`}>
            <TableCell className="font-medium">{row.security_name}<span className="ml-1 text-xs text-muted-foreground">{row.security_code}</span></TableCell>
            <TableCell>{row.sector}</TableCell>
            <TableCell className={`text-right font-mono ${row.net_pnl < 0 ? "text-destructive" : "text-emerald-600"}`}>{money(row.net_pnl)}</TableCell>
          </TableRow>
        ))}
        {!rows.length && <EmptyRow columns={3} />}
      </TableBody>
    </Table>
  )
}

// ── 利率與信用 ──────────────────────────────────────────────────
function RatesCreditDomain({ fundId, asOfDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-rates-credit", fundId, asOfDate],
    queryFn: () => fsiApi.getRatesCredit(fundId, asOfDate).then((r) => r.data),
    retry: 1,
  })
  const data = query.data
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
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.krdBuckets")}</CardTitle></CardHeader>
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
          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.issuerConcentration")}</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.domains.issuer")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.marketValue")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.weight")}</TableHead></TableRow></TableHeader>
                <TableBody>
                  {data.issuer_concentration.top_issuers.map((row) => (
                    <TableRow key={row.issuer}>
                      <TableCell className="font-medium">{row.issuer}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.market_value)}</TableCell>
                      <TableCell className="text-right font-mono">{pct(row.weight_pct)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.issuer_concentration.top_issuers.length && <EmptyRow columns={3} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

// ── 流動性與壓力測試 ────────────────────────────────────────────
function LiquidityDomain({ fundId, asOfDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-liquidity", fundId, asOfDate],
    queryFn: () => fsiApi.getLiquidityStress(fundId, asOfDate, { redemptionPct: 20, rateShockBps: 50 }).then((r) => r.data),
    retry: 1,
  })
  const data = query.data
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
          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.liquidityLadder")}</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.domains.assetClass")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.marketValue")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.ttlDays")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.cumulativePctNav")}</TableHead></TableRow></TableHeader>
                <TableBody>
                  {data.liquidity_ladder.map((row) => (
                    <TableRow key={row.asset_class}>
                      <TableCell className="font-medium">{row.asset_class}</TableCell>
                      <TableCell className="text-right font-mono">{money(row.market_value)}</TableCell>
                      <TableCell className="text-right font-mono">{num(row.ttl_days, 1)}</TableCell>
                      <TableCell className="text-right font-mono">{pct(row.cumulative_pct_nav)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.liquidity_ladder.length && <EmptyRow columns={4} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

// ── 宏觀與市場動態 ──────────────────────────────────────────────
function MacroDomain({ fundId, startDate, endDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-macro", fundId, startDate, endDate],
    queryFn: () => fsiApi.getMacroDynamics(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const data = query.data
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
          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.macroQuotes")}</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.domains.index")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.periodReturn")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.fundVol")}</TableHead></TableRow></TableHeader>
                <TableBody>
                  {data.macro_indicators.map((row) => (
                    <TableRow key={row.index_code}>
                      <TableCell className="font-mono">{row.index_code}</TableCell>
                      <TableCell className="text-right font-mono">{pct(row.period_return_pct, 3)}</TableCell>
                      <TableCell className="text-right font-mono">{pct(row.annualized_volatility_pct, 2)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.macro_indicators.length && <EmptyRow columns={3} />}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
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

// ── 因子與行為風險 ──────────────────────────────────────────────
function FactorDomain({ fundId, startDate, endDate }: DomainProps) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["domain-factor", fundId, startDate, endDate],
    queryFn: () => fsiApi.getFactorBehavior(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const data = query.data
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
            <Card>
              <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.crowdingTop")}</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader><TableRow><TableHead>{t("investmentRisk.domains.security")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.weight")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.crowdingRatio")}</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {data.trading_behavior.crowding_top.map((row) => (
                      <TableRow key={row.security_code}>
                        <TableCell className="font-medium">{row.security_name}<span className="ml-1 text-xs text-muted-foreground">{row.security_code}</span></TableCell>
                        <TableCell className="text-right font-mono">{pct(row.weight_pct, 2)}</TableCell>
                        <TableCell className="text-right font-mono">{num(row.crowding_ratio, 3)}</TableCell>
                      </TableRow>
                    ))}
                    {!data.trading_behavior.crowding_top.length && <EmptyRow columns={3} />}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

// ── 前置試算 ────────────────────────────────────────────────────
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
          <Card>
            <CardHeader><CardTitle className="text-base">{t("investmentRisk.domains.durationLimits")}</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>{t("investmentRisk.domains.metric")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.current")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.projected")}</TableHead><TableHead className="text-right">{t("investmentRisk.domains.limitCol")}</TableHead></TableRow></TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell className="font-medium">{t("investmentRisk.domains.durationRow")}</TableCell>
                    <TableCell className="text-right font-mono">{num(data.current.duration_years, 2)}</TableCell>
                    <TableCell className="text-right font-mono">{num(data.projected.duration_years, 2)}</TableCell>
                    <TableCell className="text-right font-mono">{num(data.limits.duration_years, 2)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">{t("investmentRisk.domains.issuerPctRow")}</TableCell>
                    <TableCell className="text-right font-mono">{pct(data.current.issuer_pct_nav)}</TableCell>
                    <TableCell className="text-right font-mono">{pct(data.projected.issuer_pct_nav)}</TableCell>
                    <TableCell className="text-right font-mono">{pct(data.limits.issuer_pct_nav)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">{t("investmentRisk.domains.trackingErrorRow")}</TableCell>
                    <TableCell className="text-right font-mono">—</TableCell>
                    <TableCell className="text-right font-mono">{pct(data.projected.tracking_error_proxy_pct)}</TableCell>
                    <TableCell className="text-right font-mono">{pct(data.limits.tracking_error_proxy_pct)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">{t("investmentRisk.domains.dv01Row")}</TableCell>
                    <TableCell className="text-right font-mono">{money(data.current.portfolio_dv01)}</TableCell>
                    <TableCell className="text-right font-mono">{money(data.projected.portfolio_dv01)}</TableCell>
                    <TableCell className="text-right font-mono">—</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function EmptyRow({ columns }: { columns: number }) {
  const { t } = useTranslation()
  return <TableRow><TableCell colSpan={columns} className="h-16 text-center text-muted-foreground">{t("investmentRisk.common.empty")}</TableCell></TableRow>
}

/** 六大業務域，供風險指標頁組合進統一 Tab 使用。 */
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

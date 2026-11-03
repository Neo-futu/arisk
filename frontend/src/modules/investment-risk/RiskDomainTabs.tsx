import { useQuery } from "@tanstack/react-query"
import { useMemo, useState, type ReactElement } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fsiApi } from "@/fsiClient"
import { HorizontalBarList } from "@/modules/investment-risk/dashboard-kit"
import { AttributionModelPanel } from "@/modules/investment-risk/AttributionModelPanel"
import { EquityBetaContributionCard } from "@/modules/investment-risk/EquityBetaContributionCard"
import { LqapPortfolioLiquidity } from "@/modules/investment-risk/LqapPortfolioLiquidity"
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
      <AttributionModelPanel fundId={fundId} startDate={startDate} endDate={endDate} />
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

type BondAgencyFlatRow = {
  security_code: string
  security_name: string
  issuer_name: string
  market_value: number
  weight_pct: number
  csci: string
  lianhe: string
  sp: string
  moody: string
  fitch: string
  internal: string
}

type RatingScaleRow = {
  band: string
  grade: string
  domestic: string
  sp_fitch: string
  moody: string
}

function ratingCell(value: string | null | undefined) {
  const text = (value || "").trim()
  return text ? <span className="font-mono text-xs">{text}</span> : <span className="text-muted-foreground">—</span>
}

function RatesCreditDomain({ fundId, asOfDate }: DomainProps) {
  const { t } = useTranslation()
  const [ratingSource, setRatingSource] = useState("all")
  const query = useQuery({
    queryKey: ["domain-rates-credit", fundId, asOfDate, ratingSource],
    queryFn: () => fsiApi.getRatesCredit(fundId, asOfDate, ratingSource).then((r) => r.data),
    retry: 1,
  })
  const data = query.data
  const ratingSourceOptions = [
    { id: "all", label_zh: t("investmentRisk.ratingSecurities.sourceAll") },
    { id: "domestic", label_zh: t("investmentRisk.ratingSecurities.sourceDomestic") },
    { id: "csci", label_zh: t("investmentRisk.ratingSecurities.sourceCsci") },
    { id: "lianhe", label_zh: t("investmentRisk.ratingSecurities.sourceLianhe") },
    { id: "foreign", label_zh: t("investmentRisk.ratingSecurities.sourceForeign") },
    { id: "sp", label_zh: t("investmentRisk.ratingSecurities.sourceSp") },
    { id: "moody", label_zh: t("investmentRisk.ratingSecurities.sourceMoody") },
    { id: "fitch", label_zh: t("investmentRisk.ratingSecurities.sourceFitch") },
    { id: "internal", label_zh: t("investmentRisk.ratingSecurities.sourceInternal") },
  ]
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
  const ratingColumns = useMemo<WorkbenchColumn<{ rating: string; market_value: number; weight_pct: number; is_investment_grade?: boolean }>[]>(() => [
    {
      key: "rating",
      header: t("investmentRisk.ratingSecurities.colRating"),
      filterable: true,
      accessor: (row) => row.rating,
      cell: (row) => (
        <span className="inline-flex items-center gap-2 font-mono">
          {row.rating}
          {row.is_investment_grade ? (
            <Badge className="bg-emerald-600 hover:bg-emerald-600 text-[10px]">{t("investmentRisk.ratingSecurities.igBadge")}</Badge>
          ) : (
            <Badge variant="outline" className="text-[10px]">{t("investmentRisk.ratingSecurities.belowIgBadge")}</Badge>
          )}
        </span>
      ),
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.ratingSecurities.colWeight"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{pct(row.weight_pct)}</span>,
    },
    {
      key: "market_value",
      header: t("investmentRisk.ratingSecurities.colMarketValue"),
      align: "right",
      accessor: (row) => row.market_value,
      cell: (row) => <span className="font-mono">{money(row.market_value)}</span>,
    },
  ], [t])
  const bondAgencyColumns = useMemo<WorkbenchColumn<BondAgencyFlatRow>[]>(() => [
    {
      key: "security_code",
      header: t("investmentRisk.ratingSecurities.colSecurityCode"),
      filterable: true,
      accessor: (row) => row.security_code,
      cell: (row) => <span className="font-mono text-xs">{row.security_code}</span>,
    },
    {
      key: "security_name",
      header: t("investmentRisk.ratingSecurities.colSecurityName"),
      filterable: true,
      accessor: (row) => row.security_name,
    },
    {
      key: "market_value",
      header: t("investmentRisk.domains.marketValue"),
      align: "right",
      accessor: (row) => row.market_value,
      cell: (row) => <span className="font-mono">{money(row.market_value)}</span>,
    },
    {
      key: "csci",
      header: t("investmentRisk.ratingSecurities.colCsci"),
      accessor: (row) => row.csci,
      cell: (row) => ratingCell(row.csci),
    },
    {
      key: "lianhe",
      header: t("investmentRisk.ratingSecurities.colLianhe"),
      accessor: (row) => row.lianhe,
      cell: (row) => ratingCell(row.lianhe),
    },
    {
      key: "sp",
      header: t("investmentRisk.ratingSecurities.colSp"),
      accessor: (row) => row.sp,
      cell: (row) => ratingCell(row.sp),
    },
    {
      key: "moody",
      header: t("investmentRisk.ratingSecurities.colMoody"),
      accessor: (row) => row.moody,
      cell: (row) => ratingCell(row.moody),
    },
    {
      key: "fitch",
      header: t("investmentRisk.ratingSecurities.colFitch"),
      accessor: (row) => row.fitch,
      cell: (row) => ratingCell(row.fitch),
    },
    {
      key: "internal",
      header: t("investmentRisk.ratingSecurities.colInternal"),
      filterable: true,
      accessor: (row) => row.internal,
      cell: (row) => ratingCell(row.internal),
    },
  ], [t])

  const ratingScaleColumns = useMemo<WorkbenchColumn<RatingScaleRow>[]>(() => [
    {
      key: "grade",
      header: t("investmentRisk.ratingSecurities.colGradeClass"),
      filterable: true,
      accessor: (row) => row.grade,
      cell: (row) =>
        row.grade === "investment" ? (
          <Badge className="bg-emerald-600 hover:bg-emerald-600 text-[10px]">
            {t("investmentRisk.ratingSecurities.igBadge")}
          </Badge>
        ) : (
          <Badge variant="outline" className="text-[10px]">
            {t("investmentRisk.ratingSecurities.speculativeBadge")}
          </Badge>
        ),
    },
    {
      key: "band",
      header: t("investmentRisk.ratingSecurities.colBand"),
      accessor: (row) => row.band,
    },
    {
      key: "domestic",
      header: t("investmentRisk.ratingSecurities.colDomesticAgencies"),
      accessor: (row) => row.domestic,
      cell: (row) => <span className="font-mono text-xs">{row.domestic}</span>,
    },
    {
      key: "sp_fitch",
      header: t("investmentRisk.ratingSecurities.colSpFitch"),
      accessor: (row) => row.sp_fitch,
      cell: (row) => <span className="font-mono text-xs">{row.sp_fitch}</span>,
    },
    {
      key: "moody",
      header: t("investmentRisk.ratingSecurities.colMoody"),
      accessor: (row) => row.moody,
      cell: (row) => <span className="font-mono text-xs">{row.moody}</span>,
    },
  ], [t])

  const flattenAgencyRows = (kind: "issuer" | "debt"): BondAgencyFlatRow[] =>
    (data?.bond_agency_rating_rows ?? []).map((row) => {
      const ratings = kind === "issuer" ? row.issuer_ratings : row.debt_ratings
      return {
        security_code: row.security_code,
        security_name: row.security_name || "—",
        issuer_name: row.issuer_name || "—",
        market_value: row.market_value,
        weight_pct: row.weight_pct,
        csci: ratings?.csci || "",
        lianhe: ratings?.lianhe || "",
        sp: ratings?.sp || "",
        moody: ratings?.moody || "",
        fitch: ratings?.fitch || "",
        internal: ratings?.internal || "",
      }
    })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("investmentRisk.domains.ratesCreditTitle")}</h3>
        <SqlViewButton sqlIds={["SQL-RC-01", "SQL-RC-02", "SQL-RC-03", "SQL-RC-04"]} />
      </div>
      <DomainState loading={query.isFetching && !data} error={query.isError} empty={!!data && data.bond_count === 0} />
      {data && (
        <>
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label={t("investmentRisk.domains.bondHoldings")} value={money(data.total_bond_market_value)} detail={t("investmentRisk.domains.bondHoldingsDetail", { count: data.bond_count, pct: pct(data.bond_exposure_pct_nav) })} />
            <Kpi label={t("investmentRisk.domains.weightedDuration")} value={num(data.weighted_duration_years, 2) + " 年"} />
            <Kpi label="DV01" value={money(data.portfolio_dv01)} detail={t("investmentRisk.domains.dv01Hint")} />
            <Kpi
              label={t("investmentRisk.domains.cs01")}
              value={money(data.portfolio_cs01)}
              detail={t("investmentRisk.domains.cs01Hint")}
            />
            <Kpi label={t("investmentRisk.ratingSecurities.issuerIgPct")} value={pct(data.issuer_investment_grade_pct ?? data.investment_grade_pct)} detail={t("investmentRisk.ratingSecurities.igHint")} />
            <Kpi label={t("investmentRisk.ratingSecurities.debtIgPct")} value={pct(data.debt_investment_grade_pct ?? data.investment_grade_pct)} detail={t("investmentRisk.ratingSecurities.igHint")} />
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
                <HorizontalBarList
                  items={(data.debt_rating_distribution ?? data.rating_distribution).map((r) => ({ label: r.rating, value: r.weight_pct }))}
                  formatter={(v) => pct(v, 2)}
                />
              </CardContent>
            </Card>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-300/60 bg-sky-50/70 px-3 py-3 dark:border-sky-800 dark:bg-sky-950/30">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-sky-900 dark:text-sky-100">
                {t("investmentRisk.ratingSecurities.sourceLabel")}
              </p>
              <p className="text-muted-foreground text-xs">
                {query.isFetching
                  ? t("investmentRisk.domains.loading")
                  : t("investmentRisk.ratingSecurities.sourceHint", {
                      count: data.rating_matched_bond_count ?? data.bond_count,
                      total: data.bond_count,
                    })}
              </p>
            </div>
            <select
              aria-label={t("investmentRisk.ratingSecurities.sourceLabel")}
              className="min-w-[240px] rounded-md border border-sky-400 bg-background px-3 py-2 text-sm font-medium shadow-sm"
              value={ratingSource}
              onChange={(event) => setRatingSource(event.target.value)}
            >
              {ratingSourceOptions.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label_zh}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <WorkbenchTable
              title={t("investmentRisk.ratingSecurities.issuerTable")}
              rows={data.issuer_rating_distribution ?? data.rating_distribution}
              columns={ratingColumns}
              rowId={(row) => `issuer-${row.rating}`}
              exportFilename={`rates-issuer-ratings-${fundId}-${asOfDate}-${ratingSource}.csv`}
              initialSortKey="weight_pct"
              selectable={false}
            />
            <WorkbenchTable
              title={t("investmentRisk.ratingSecurities.debtTable")}
              rows={data.debt_rating_distribution ?? data.rating_distribution}
              columns={ratingColumns}
              rowId={(row) => `debt-${row.rating}`}
              exportFilename={`rates-debt-ratings-${fundId}-${asOfDate}-${ratingSource}.csv`}
              initialSortKey="weight_pct"
              selectable={false}
            />
          </div>
          <div className="space-y-2">
            <p className="text-muted-foreground text-xs">{t("investmentRisk.ratingSecurities.bondAgencyHint")}</p>
            <WorkbenchTable
              title={t("investmentRisk.ratingSecurities.bondAgencyIssuerTable")}
              rows={flattenAgencyRows("issuer")}
              columns={bondAgencyColumns}
              rowId={(row) => `agency-issuer-${row.security_code}`}
              exportFilename={`rates-bond-issuer-multi-agency-${fundId}-${asOfDate}.csv`}
              initialSortKey="market_value"
              selectable={false}
            />
            <WorkbenchTable
              title={t("investmentRisk.ratingSecurities.bondAgencyDebtTable")}
              rows={flattenAgencyRows("debt")}
              columns={bondAgencyColumns}
              rowId={(row) => `agency-debt-${row.security_code}`}
              exportFilename={`rates-bond-debt-multi-agency-${fundId}-${asOfDate}.csv`}
              initialSortKey="market_value"
              selectable={false}
            />
          </div>
          <div className="space-y-2">
            <p className="text-muted-foreground text-xs">
              {data.rating_scale_note || t("investmentRisk.ratingSecurities.scaleHint")}
            </p>
            <WorkbenchTable
              title={t("investmentRisk.ratingSecurities.scaleTable")}
              rows={(data.rating_scale_legend ?? []) as RatingScaleRow[]}
              columns={ratingScaleColumns}
              rowId={(row) => `scale-${row.grade}-${row.band}-${row.sp_fitch}`}
              exportFilename={`rates-rating-scale-legend-${fundId}-${asOfDate}.csv`}
              selectable={false}
            />
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
  return <LqapPortfolioLiquidity fundId={fundId} asOfDate={asOfDate} />
}

export const RISK_DOMAINS: ReadonlyArray<{
  key: string
  label: string
  Component: (props: DomainProps) => ReactElement
}> = [
  { key: "attribution", label: "tabAttribution", Component: AttributionDomain },
  { key: "rates-credit", label: "tabRatesCredit", Component: RatesCreditDomain },
  { key: "liquidity", label: "tabLiquidity", Component: LiquidityDomain },
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

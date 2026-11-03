import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
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
import { fsiApi, type InvestmentKpiReport } from "@/fsiClient"
import { AdapterStatusBar } from "@/platform/AdapterStatus"
import { HorizontalBarList } from "@/modules/investment-risk/dashboard-kit"

function isFactorExposureMap(result: Record<string, unknown>): boolean {
  const values = Object.values(result)
  return values.length > 0 && values.every(
    (item) => item && typeof item === "object" && typeof (item as { pct_nav?: unknown }).pct_nav === "number",
  )
}

export function formatKpiResult(result: unknown): string {
  if (result == null) return "—"
  if (typeof result === "number") {
    return Number.isFinite(result) ? result.toLocaleString("zh-HK", { maximumFractionDigits: 4 }) : "—"
  }
  if (typeof result === "object") {
    const row = result as Record<string, unknown>
    // Duration: { weighted_years, fixed_income_mv }
    if (typeof row.weighted_years === "number") {
      return `${row.weighted_years.toFixed(3)} yr`
    }
    // Factor Exposure: { RATE_CREDIT: {amount, pct_nav}, ... }
    if (isFactorExposureMap(row)) {
      return Object.entries(row)
        .map(([factor, payload]) => {
          const pct = Number((payload as { pct_nav: number }).pct_nav)
          return `${factor} ${pct.toFixed(1)}%`
        })
        .join(" · ")
    }
    // Leverage prefers pct when present (avoid showing ratio as amount)
    if (typeof row.pct === "number" && typeof row.amount !== "number") {
      return `${row.pct.toFixed(2)}%`
    }
    if (typeof row.amount === "number") {
      return row.amount.toLocaleString("zh-HK", { maximumFractionDigits: 0 })
    }
    if (typeof row.ratio === "number") {
      return `${(row.ratio * 100).toFixed(2)}%`
    }
    if (typeof row.return === "number") {
      return `${(row.return * 100).toFixed(3)}%`
    }
    if (typeof row.years === "number") {
      return `${row.years.toFixed(3)}`
    }
    if (typeof row.pct_nav === "number") {
      return `${row.pct_nav.toFixed(2)}% NAV`
    }
    if (typeof row.beta === "number" || row.beta === null) {
      return row.beta == null ? "—" : Number(row.beta).toFixed(4)
    }
    if (typeof row.annualized_pct === "number" || row.annualized_pct === null) {
      return row.annualized_pct == null ? "—" : `${Number(row.annualized_pct).toFixed(2)}%`
    }
  }
  try {
    return JSON.stringify(result)
  } catch {
    return String(result)
  }
}

function chartValue(report: InvestmentKpiReport): number {
  const result = report.result
  if (typeof result === "number") return Math.abs(result)
  if (result && typeof result === "object") {
    const row = result as Record<string, unknown>
    if (typeof row.weighted_years === "number") return Math.abs(row.weighted_years)
    if (typeof row.pct === "number") return Math.abs(row.pct)
    if (typeof row.amount === "number") return Math.abs(row.amount)
    if (typeof row.ratio === "number") return Math.abs(row.ratio) * 100
    if (typeof row.return === "number") return Math.abs(row.return) * 100
    if (typeof row.years === "number") return Math.abs(row.years)
    if (typeof row.pct_nav === "number") return Math.abs(row.pct_nav)
  }
  return 0
}

function kpiDetail(report: InvestmentKpiReport): string {
  const result = report.result
  if (result && typeof result === "object") {
    const row = result as Record<string, unknown>
    if (typeof row.weighted_years === "number" && typeof row.fixed_income_mv === "number") {
      return `FI MV ${row.fixed_income_mv.toLocaleString("zh-HK", { maximumFractionDigits: 0 })}`
    }
    if (typeof row.amount === "number" && typeof row.pct_nav === "number") {
      return `${row.pct_nav.toFixed(2)}% NAV`
    }
    if (typeof row.ratio === "number" && typeof row.pct === "number") {
      return `ratio ${row.ratio.toFixed(4)}`
    }
  }
  return report.formula || report.engine || "—"
}

/** 后端 KPI 英文名 → 界面本地化；缺映射时回退原文 */
export function localizeKpiName(
  kpi: string,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const names = t("engine.kpiNames", { returnObjects: true })
  if (names && typeof names === "object" && !Array.isArray(names)) {
    const label = (names as Record<string, string>)[kpi]
    if (label) return label
  }
  return kpi
}

export function EngineKpiPanel({
  domain,
  fundId,
  asOfDate,
  title,
  variant = "full",
  badgeLabel,
  embed = false,
  showAdapters = true,
  showEngineBadge = true,
}: {
  domain: string
  fundId: string
  asOfDate: string
  title?: string
  /** full = table+adapters；metrics = 与组合概况卡片一致的 KPI 水位 */
  variant?: "full" | "metrics"
  badgeLabel?: string
  /** 嵌入外层 Card 时不重复包一层 Card */
  embed?: boolean
  /** 是否展示 FinancePy / Riskfolio / ORE 适配状态条 */
  showAdapters?: boolean
  /** 是否展示「经 RiskEngine」角标 */
  showEngineBadge?: boolean
}) {
  const { t } = useTranslation()
  const useReportLayer = variant === "metrics" && domain === "overview"
  const catalog = useQuery({
    queryKey: ["investment-kpi-catalog"],
    queryFn: () => fsiApi.getInvestmentKpiCatalog().then((response) => response.data),
    staleTime: 300_000,
    enabled: !useReportLayer,
    retry: 1,
  })
  const reported = useQuery({
    queryKey: ["reported-exposure", fundId, asOfDate],
    queryFn: () => fsiApi.getReportedExposure(fundId, asOfDate).then((response) => response.data),
    enabled: useReportLayer,
    retry: 1,
    placeholderData: (previous) => previous,
  })
  const pack = useQuery({
    queryKey: ["investment-kpi-pack", fundId, asOfDate],
    queryFn: () => fsiApi.getInvestmentKpiPack(fundId, asOfDate).then((response) => response.data),
    enabled: !useReportLayer,
    retry: 1,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  })

  const reports = useMemo(() => {
    if (useReportLayer) return reported.data?.kpis ?? []
    const domainPack = pack.data?.domains?.[domain]
    if (domainPack?.kpis) return Object.values(domainPack.kpis)
    const ids = catalog.data?.domains?.[domain] ?? []
    return ids
      .map((kpiId) => pack.data?.kpis?.[kpiId])
      .filter((item): item is InvestmentKpiReport => Boolean(item))
  }, [catalog.data?.domains, domain, pack.data?.domains, pack.data?.kpis, reported.data?.kpis, useReportLayer])

  const chartItems = useMemo(() => {
    const items: Array<{ label: string; value: number }> = []
    for (const report of reports) {
      const result = report.result
      if (result && typeof result === "object" && isFactorExposureMap(result as Record<string, unknown>)) {
        for (const [factor, payload] of Object.entries(result as Record<string, { pct_nav: number }>)) {
          items.push({ label: factor, value: Math.abs(Number(payload.pct_nav) || 0) })
        }
        continue
      }
      items.push({ label: localizeKpiName(report.kpi, t), value: chartValue(report) })
    }
    return items
  }, [reports, t])

  const heading = title ?? t("engine.kpiPackTitle", { domain })
  const showBadge = showEngineBadge && (badgeLabel !== undefined ? Boolean(badgeLabel) : true)
  const badge = badgeLabel ?? t("engine.viaRiskEngine")
  const isFetching = useReportLayer ? reported.isFetching : pack.isFetching
  const isError = useReportLayer ? reported.isError : pack.isError

  if (variant === "metrics") {
    const body = (
      <div className="min-h-[7.5rem]">
        {isError ? (
          <p className="text-sm text-destructive">{t("engine.kpiLoadError")}</p>
        ) : null}
        {!isFetching && !isError && !reports.length ? (
          <p className="text-sm text-muted-foreground">{t("platform.empty")}</p>
        ) : null}
        {reports.length ? (
          <div className={`grid gap-4 md:grid-cols-2 xl:grid-cols-4 ${isFetching ? "opacity-70" : ""}`}>
            {reports.map((report) => (
              <div
                key={report.kpi}
                className="rounded-lg border px-4 py-3"
                data-testid={`engine-kpi-metric-${report.kpi}`}
              >
                <p className="text-muted-foreground text-xs">{localizeKpiName(report.kpi, t)}</p>
                <p className="mt-1 truncate text-xl font-semibold font-mono">
                  {formatKpiResult(report.result)}
                </p>
                <p className="text-muted-foreground mt-1 truncate text-xs" title={kpiDetail(report)}>
                  {kpiDetail(report)}
                </p>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    )

    if (embed) {
      return <div data-testid={`engine-kpi-${domain}`}>{body}</div>
    }

    return (
      <Card data-testid={`engine-kpi-${domain}`}>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="text-base">{heading}</CardTitle>
            {showBadge ? <Badge variant="outline">{badge}</Badge> : null}
          </div>
        </CardHeader>
        <CardContent>{body}</CardContent>
      </Card>
    )
  }

  return (
    <Card data-testid={`engine-kpi-${domain}`}>
      <CardHeader className={showAdapters ? "space-y-3" : undefined}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base">{heading}</CardTitle>
          {showBadge ? <Badge variant="outline">{badge}</Badge> : null}
        </div>
        {showAdapters ? (
          <AdapterStatusBar
            adapters={catalog.data?.adapters ?? pack.data?.adapters}
            engine={catalog.data?.engine ?? pack.data?.engine}
            engineVersion={catalog.data?.engine_version ?? pack.data?.engine_version}
          />
        ) : null}
      </CardHeader>
      <CardContent className="min-h-[14rem] space-y-4">
        {isError ? <p className="text-sm text-destructive">{t("engine.kpiLoadError")}</p> : null}
        {!isFetching && !isError && !reports.length ? (
          <p className="text-sm text-muted-foreground">{t("platform.empty")}</p>
        ) : null}
        {reports.length ? (
          <div className={`grid h-[12rem] gap-6 xl:grid-cols-[1.4fr_0.8fr] ${isFetching ? "opacity-70" : ""}`}>
            <div className="overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("engine.colKpi")}</TableHead>
                    <TableHead>{t("engine.colResult")}</TableHead>
                    <TableHead>{t("engine.colEngine")}</TableHead>
                    <TableHead>{t("engine.colFormula")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reports.map((report) => (
                    <TableRow key={report.kpi}>
                      <TableCell className="font-medium">{localizeKpiName(report.kpi, t)}</TableCell>
                      <TableCell className="max-w-[18rem] truncate font-mono text-xs" title={formatKpiResult(report.result)}>
                        {formatKpiResult(report.result)}
                      </TableCell>
                      <TableCell className="text-xs">{report.engine}</TableCell>
                      <TableCell className="max-w-[14rem] truncate text-xs text-muted-foreground" title={report.formula}>
                        {report.formula}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <div className="overflow-auto">
              <HorizontalBarList items={chartItems} formatter={(value) => value.toFixed(2)} />
            </div>
          </div>
        ) : (
          <div className="h-[12rem]" />
        )}
      </CardContent>
    </Card>
  )
}

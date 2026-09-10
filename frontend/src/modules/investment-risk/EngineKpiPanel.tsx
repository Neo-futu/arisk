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

export function formatKpiResult(result: unknown): string {
  if (result == null) return "—"
  if (typeof result === "number") {
    return Number.isFinite(result) ? result.toLocaleString("zh-HK", { maximumFractionDigits: 4 }) : "—"
  }
  if (typeof result === "object") {
    const row = result as Record<string, unknown>
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
    if (typeof row.amount === "number") return Math.abs(row.amount)
    if (typeof row.ratio === "number") return Math.abs(row.ratio) * 100
    if (typeof row.return === "number") return Math.abs(row.return) * 100
    if (typeof row.years === "number") return Math.abs(row.years)
    if (typeof row.pct_nav === "number") return Math.abs(row.pct_nav)
  }
  return 0
}

export function EngineKpiPanel({
  domain,
  fundId,
  asOfDate,
  title,
}: {
  domain: string
  fundId: string
  asOfDate: string
  title?: string
}) {
  const { t } = useTranslation()
  const catalog = useQuery({
    queryKey: ["investment-kpi-catalog"],
    queryFn: () => fsiApi.getInvestmentKpiCatalog().then((response) => response.data),
    staleTime: 300_000,
    retry: 1,
  })
  const pack = useQuery({
    queryKey: ["investment-kpi-pack", fundId, asOfDate],
    queryFn: () => fsiApi.getInvestmentKpiPack(fundId, asOfDate).then((response) => response.data),
    retry: 1,
  })

  const reports = useMemo(() => {
    const domainPack = pack.data?.domains?.[domain]
    if (domainPack?.kpis) return Object.values(domainPack.kpis)
    const ids = catalog.data?.domains?.[domain] ?? []
    return ids
      .map((kpiId) => pack.data?.kpis?.[kpiId])
      .filter((item): item is InvestmentKpiReport => Boolean(item))
  }, [catalog.data?.domains, domain, pack.data?.domains, pack.data?.kpis])

  const chartItems = reports.map((report) => ({
    label: report.kpi,
    value: chartValue(report),
  }))

  return (
    <Card data-testid={`engine-kpi-${domain}`}>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base">{title ?? t("engine.kpiPackTitle", { domain })}</CardTitle>
          <Badge variant="outline">{t("engine.viaRiskEngine")}</Badge>
        </div>
        <AdapterStatusBar
          adapters={catalog.data?.adapters ?? pack.data?.adapters}
          engine={catalog.data?.engine ?? pack.data?.engine}
          engineVersion={catalog.data?.engine_version ?? pack.data?.engine_version}
        />
      </CardHeader>
      <CardContent className="space-y-4">
        {pack.isFetching ? <p className="text-sm text-muted-foreground">{t("platform.loading")}</p> : null}
        {pack.isError ? <p className="text-sm text-destructive">{t("engine.kpiLoadError")}</p> : null}
        {!pack.isFetching && !pack.isError && !reports.length ? (
          <p className="text-sm text-muted-foreground">{t("platform.empty")}</p>
        ) : null}
        {reports.length ? (
          <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
            <div className="overflow-x-auto">
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
                      <TableCell className="font-medium">{report.kpi}</TableCell>
                      <TableCell className="font-mono text-xs">{formatKpiResult(report.result)}</TableCell>
                      <TableCell className="text-xs">{report.engine}</TableCell>
                      <TableCell className="max-w-md text-xs text-muted-foreground">{report.formula}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <HorizontalBarList items={chartItems} formatter={(value) => value.toFixed(2)} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

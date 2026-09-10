import { useQuery } from "@tanstack/react-query"
import { Scale } from "lucide-react"
import { useMemo, useState, type ReactNode } from "react"
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
import { fsiApi } from "@/fsiClient"
import { AdapterStatusBar } from "@/platform/AdapterStatus"
import { RISK_GOVERNANCE_NAV } from "@/platform/nav"
import { useBindPageContext } from "@/platform/page-context"

type LimitRow = {
  limit_id?: string
  name?: string
  state?: string
  utilization?: number
  threshold?: number
  value?: number
}

function asLimitRows(payload: unknown): LimitRow[] {
  if (!payload || typeof payload !== "object") return []
  const source = payload as Record<string, unknown>
  const items = source.items ?? source.results ?? source.limits
  if (Array.isArray(items)) {
    return items.filter((item): item is LimitRow => Boolean(item) && typeof item === "object")
  }
  if (source.by_id && typeof source.by_id === "object") {
    return Object.entries(source.by_id as Record<string, Record<string, unknown>>).map(([limit_id, row]) => ({
      limit_id,
      ...row,
    }))
  }
  return Object.entries(source)
    .filter(([, value]) => value && typeof value === "object")
    .map(([limit_id, value]) => ({ limit_id, ...(value as Record<string, unknown>) }))
}

function Section({
  id,
  title,
  detail,
  children,
}: {
  id: string
  title: string
  detail: string
  children: ReactNode
}) {
  return (
    <Card id={id} className="scroll-mt-20">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <p className="text-sm text-muted-foreground">{detail}</p>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export function RiskGovernancePage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const catalog = useQuery({
    queryKey: ["risk-governance-catalog"],
    queryFn: () => fsiApi.getLimitsCatalog().then((response) => response.data),
    staleTime: 300_000,
    retry: 1,
  })
  const pack = useQuery({
    queryKey: ["investment-kpi-pack", fundId, asOfDate],
    queryFn: () => fsiApi.getInvestmentKpiPack(fundId, asOfDate).then((response) => response.data),
    retry: 1,
  })

  const limitRows = useMemo(() => asLimitRows(pack.data?.limits), [pack.data?.limits])
  const states = (catalog.data?.states as string[] | undefined) ?? ["OK", "WARNING", "BREACH", "HARD_BREACH"]
  const limitIds = (catalog.data?.limit_ids as string[] | undefined) ?? limitRows.map((row) => String(row.limit_id ?? ""))
  const adapters = catalog.data?.adapters ?? pack.data?.adapters
  const breaches = limitRows.filter((row) => String(row.state ?? "").toUpperCase().includes("BREACH"))
  const warnings = limitRows.filter((row) => String(row.state ?? "").toUpperCase().includes("WARN"))

  useBindPageContext({
    portfolio: fundId,
    date: asOfDate,
    module: "risk-governance",
    result: pack.data?.engine,
    riskMetrics: pack.data?.limits && typeof pack.data.limits === "object"
      ? { limits: Object.keys(pack.data.limits as object).length }
      : undefined,
  })

  return (
    <div className="space-y-6" data-testid="platform-workbench">
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Scale className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold tracking-tight">{t("riskGovernance.title")}</h1>
          <Badge variant="outline">{t("riskGovernance.badge")}</Badge>
        </div>
        <p className="max-w-4xl text-sm text-muted-foreground">{t("riskGovernance.subtitle")}</p>
        <AdapterStatusBar
          adapters={adapters}
          engine={catalog.data?.engine ?? pack.data?.engine}
          engineVersion={catalog.data?.engine_version ?? pack.data?.engine_version}
        />
      </div>

      <div data-testid="platform-parameter">
        <FsiToolbar
          fundId={fundId}
          onFundChange={setFundId}
          asOfDate={asOfDate}
          onDateChange={setAsOfDate}
          onRefresh={() => { void catalog.refetch(); void pack.refetch() }}
          isFetching={catalog.isFetching || pack.isFetching}
        />
      </div>

      {pack.isError ? <p className="text-sm text-destructive">{t("engine.kpiLoadError")}</p> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">{t("riskGovernance.limitCount")}</div><div className="mt-1 text-2xl font-semibold">{limitIds.length || limitRows.length}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">{t("riskGovernance.warningCount")}</div><div className="mt-1 text-2xl font-semibold">{warnings.length}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">{t("riskGovernance.breachCount")}</div><div className="mt-1 text-2xl font-semibold">{breaches.length}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">{t("riskGovernance.policyId")}</div><div className="mt-1 text-lg font-semibold">{String(catalog.data?.policy_id ?? "default")}</div></CardContent></Card>
      </div>

      <Section id="limits" title={t("nav.riskLimits")} detail={t("riskGovernance.limitsHint")}>
        <div data-testid="platform-data" className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("riskGovernance.colLimit")}</TableHead>
                <TableHead>{t("riskGovernance.colState")}</TableHead>
                <TableHead>{t("engine.colResult")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {limitRows.length ? limitRows.map((row, index) => (
                <TableRow key={String(row.limit_id ?? index)}>
                  <TableCell className="font-mono text-xs">{String(row.limit_id ?? row.name ?? "—")}</TableCell>
                  <TableCell>{String(row.state ?? "—")}</TableCell>
                  <TableCell className="font-mono text-xs">{String(row.utilization ?? row.value ?? row.threshold ?? "—")}</TableCell>
                </TableRow>
              )) : (
                <TableRow>
                  <TableCell colSpan={3} className="h-16 text-center text-muted-foreground">
                    {(catalog.data?.limit_ids as string[] | undefined)?.join(" · ") || t("platform.empty")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section id="alerts" title={t("nav.riskAlerts")} detail={t("riskGovernance.alertsHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.alertsBody", { count: warnings.length })}</p>
      </Section>

      <Section id="breaches" title={t("nav.riskBreaches")} detail={t("riskGovernance.breachesHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.breachesBody", { count: breaches.length })}</p>
      </Section>

      <Section id="exceptions" title={t("nav.exceptionManagement")} detail={t("riskGovernance.exceptionsHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.hardBreachLock")}</p>
      </Section>

      <Section id="escalation" title={t("nav.escalationDisposition")} detail={t("riskGovernance.escalationHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.escalationBody")}</p>
      </Section>

      <Section id="policy" title={t("nav.riskPolicy")} detail={t("riskGovernance.policyHint")}>
        <div className="flex flex-wrap gap-2">
          {states.map((state) => <Badge key={state} variant="secondary">{state}</Badge>)}
        </div>
      </Section>

      <Section id="model-validation" title={t("nav.modelValidation")} detail={t("riskGovernance.modelHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.modelBody")}</p>
      </Section>

      <Section id="valuation-control" title={t("nav.valuationControl")} detail={t("riskGovernance.valuationHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.valuationBody")}</p>
      </Section>

      <Section id="liquidity" title={t("nav.liquidityGovernance")} detail={t("riskGovernance.liquidityHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.liquidityBody")}</p>
      </Section>

      <Section id="compliance" title={t("nav.compliance")} detail={t("riskGovernance.complianceHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.complianceBody")}</p>
      </Section>

      <Section id="reports" title={t("nav.riskReports")} detail={t("riskGovernance.reportsHint")}>
        <p className="text-sm text-muted-foreground">{t("riskGovernance.reportsBody")}</p>
      </Section>

      <p className="text-xs text-muted-foreground">
        {t("riskGovernance.navNote", { count: RISK_GOVERNANCE_NAV.length })}
      </p>
    </div>
  )
}

import { useQuery } from "@tanstack/react-query"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { Download, Scale } from "lucide-react"
import { useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent } from "@/components/ui/tabs"
import {
  fsiApi,
  type ExposureResult,
  type GovernanceLimitRow,
  type GovernancePack,
} from "@/fsiClient"
import { exportCsv } from "@/modules/investment-risk/dashboard-kit"
import { RISK_GOVERNANCE_NAV } from "@/platform/nav"
import { useBindPageContext } from "@/platform/page-context"

type SectionId = (typeof RISK_GOVERNANCE_NAV)[number]["id"] extends string
  ? "limits" | "alerts" | "breaches" | "exceptions" | "escalation" | "policy"
    | "model-validation" | "valuation-control" | "liquidity" | "compliance" | "reports"
  : never

const SECTION_BY_HASH: Record<string, SectionId> = {
  limits: "limits",
  alerts: "alerts",
  breaches: "breaches",
  exceptions: "exceptions",
  escalation: "escalation",
  policy: "policy",
  "model-validation": "model-validation",
  "valuation-control": "valuation-control",
  liquidity: "liquidity",
  compliance: "compliance",
  reports: "reports",
}

const HASH_BY_SECTION: Record<SectionId, string> = {
  limits: "limits",
  alerts: "alerts",
  breaches: "breaches",
  exceptions: "exceptions",
  escalation: "escalation",
  policy: "policy",
  "model-validation": "model-validation",
  "valuation-control": "valuation-control",
  liquidity: "liquidity",
  compliance: "compliance",
  reports: "reports",
}

function sectionFromHash(hash: string | undefined): SectionId {
  const key = (hash || "").replace(/^#/, "")
  return SECTION_BY_HASH[key] ?? "limits"
}

function money(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return "—"
  return value.toLocaleString("zh-HK", { maximumFractionDigits: digits })
}

function pctUtil(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—"
  return `${(value * 100).toFixed(1)}%`
}

function stateTone(state: string | undefined) {
  const s = (state || "").toUpperCase()
  if (s.includes("HARD")) return "destructive"
  if (s.includes("BREACH")) return "destructive"
  if (s.includes("WARN")) return "secondary"
  return "outline"
}

function stateClass(state: string | undefined) {
  const s = (state || "").toUpperCase()
  if (s.includes("HARD") || s.includes("BREACH")) return "text-destructive"
  if (s.includes("WARN")) return "text-amber-600 dark:text-amber-400"
  if (s.includes("GREEN") || s === "OK" || s === "PASS") return "text-emerald-600"
  return "text-muted-foreground"
}

function ZoneTitle({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <CardTitle className="text-base">{title}</CardTitle>
        {detail ? <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p> : null}
      </div>
      {action}
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-lg font-semibold ${tone ?? ""}`}>{value}</div>
    </div>
  )
}

function flattenLimits(pack?: GovernancePack): GovernanceLimitRow[] {
  const map = pack?.limits?.limits
  if (!map) return []
  return Object.entries(map).map(([limit_id, row]) => ({ ...row, limit_id }))
}

function LimitTable({
  rows,
  empty,
}: {
  rows: GovernanceLimitRow[]
  empty: string
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto" data-testid="platform-data">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("riskGovernance.colLimit")}</TableHead>
            <TableHead>{t("riskGovernance.colState")}</TableHead>
            <TableHead className="text-right">{t("riskGovernance.colValue")}</TableHead>
            <TableHead className="text-right">{t("riskGovernance.colThreshold")}</TableHead>
            <TableHead className="text-right">{t("riskGovernance.colUtilization")}</TableHead>
            <TableHead>{t("riskGovernance.colDetail")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length ? rows.map((row) => (
            <TableRow key={row.limit_id}>
              <TableCell className="font-mono text-xs">{row.limit_id}</TableCell>
              <TableCell>
                <Badge variant={stateTone(row.state)}>{String(row.state ?? "—")}</Badge>
              </TableCell>
              <TableCell className="text-right font-mono text-xs">{money(Number(row.value))}</TableCell>
              <TableCell className="text-right font-mono text-xs">{money(Number(row.limit))}</TableCell>
              <TableCell className={`text-right font-mono text-xs ${stateClass(row.state)}`}>
                {pctUtil(Number(row.utilization))}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {[row.direction, row.unit, row.worst_member].filter(Boolean).join(" · ") || "—"}
              </TableCell>
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={6} className="h-16 text-center text-muted-foreground">{empty}</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}

export function RiskGovernancePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const router = useRouterState()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const section = sectionFromHash(router.location.hash)

  const pack = useQuery({
    queryKey: ["risk-governance-pack", fundId, asOfDate],
    queryFn: () => fsiApi.getGovernancePack(fundId, asOfDate).then((response) => response.data),
    retry: 1,
    refetchOnWindowFocus: false,
  })

  const exposure = useQuery({
    queryKey: ["risk-governance-exposure", fundId, asOfDate],
    queryFn: () => fsiApi.getExposure(fundId, asOfDate).then((response) => response.data),
    enabled: section === "compliance" || section === "liquidity" || section === "reports",
    retry: 1,
    refetchOnWindowFocus: false,
  })

  const rulesSummary = useQuery({
    queryKey: ["risk-governance-rules-summary"],
    queryFn: () => fsiApi.getRiskRuleSummary().then((response) => response.data),
    enabled: section === "policy" || section === "compliance" || section === "reports",
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })

  const applications = useQuery({
    queryKey: ["risk-governance-applications", fundId],
    queryFn: () => fsiApi.listRuleApplications({ fundId, activeOnly: true }).then((response) => response.data),
    enabled: section === "policy" || section === "exceptions",
    retry: 1,
    refetchOnWindowFocus: false,
  })

  // Default section from hash without forcing a navigate loop (empty hash → limits).
  // A replace-navigate here previously deadlocked the router when hash failed to stick.
  function setSection(next: SectionId) {
    const hash = HASH_BY_SECTION[next]
    if (sectionFromHash(router.location.hash) === next) return
    void navigate({
      to: "/risk-governance",
      hash,
      replace: true,
    } as never)
  }

  const allLimits = useMemo(() => flattenLimits(pack.data), [pack.data])
  const alerts = pack.data?.alerts ?? allLimits.filter((row) => String(row.state).toUpperCase().includes("WARN"))
  const breaches = pack.data?.breaches ?? allLimits.filter((row) => String(row.state).toUpperCase().includes("BREACH"))
  const liquidityRows = pack.data?.liquidity ?? allLimits.filter((row) =>
    ["Liquidity", "WAM", "WAL", "Shadow NAV Deviation"].includes(row.limit_id))
  const summary = pack.data?.summary
  const softBreaches = breaches.filter((row) => String(row.state).toUpperCase() !== "HARD_BREACH")
  const hardBreaches = breaches.filter((row) => String(row.state).toUpperCase() === "HARD_BREACH")

  useBindPageContext({
    portfolio: fundId,
    date: asOfDate,
    module: "risk-governance",
    result: section,
    riskMetrics: {
      aggregate_state: summary?.aggregate_state,
      warning_count: summary?.warning_count,
      breach_count: summary?.breach_count,
    },
  })

  return (
    <div className="space-y-5" data-testid="platform-workbench">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Scale className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold tracking-tight">{t("riskGovernance.title")}</h1>
        </div>
        <p className="max-w-4xl text-sm text-muted-foreground">{t("riskGovernance.subtitle")}</p>
      </div>

      <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
        <CardContent className="pt-6" data-testid="platform-parameter">
          <FsiToolbar
            fundId={fundId}
            onFundChange={setFundId}
            asOfDate={asOfDate}
            onDateChange={setAsOfDate}
            onRefresh={() => {
              void pack.refetch()
              void exposure.refetch()
              void rulesSummary.refetch()
              void applications.refetch()
            }}
            isFetching={pack.isFetching || exposure.isFetching}
          />
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label={t("riskGovernance.limitCount")} value={String(summary?.limit_count ?? allLimits.length)} />
        <Kpi label={t("riskGovernance.warningCount")} value={String(summary?.warning_count ?? alerts.length)} tone={alerts.length ? "text-amber-600" : undefined} />
        <Kpi label={t("riskGovernance.breachCount")} value={String(summary?.breach_count ?? breaches.length)} tone={breaches.length ? "text-destructive" : undefined} />
        <Kpi
          label={t("riskGovernance.aggregateState")}
          value={String(summary?.aggregate_state ?? pack.data?.limits?.state ?? "—")}
          tone={stateClass(summary?.aggregate_state ?? pack.data?.limits?.state)}
        />
      </div>

      {pack.isError ? <p className="text-sm text-destructive">{t("riskGovernance.loadError")}</p> : null}
      {pack.data?.errors?.length ? (
        <p className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          {pack.data.errors.join(" · ")}
        </p>
      ) : null}
      {pack.isFetching && !pack.data ? <p className="text-sm text-muted-foreground">{t("riskGovernance.loading")}</p> : null}

      <Tabs value={section} onValueChange={(value) => setSection(value as SectionId)}>
        <TabsContent value="limits" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle
                title={t("nav.riskLimits")}
                detail={t("riskGovernance.limitsHint")}
                action={(
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!allLimits.length}
                    onClick={() => exportCsv(
                      `limits_${fundId}_${asOfDate}.csv`,
                      ["limit_id", "state", "value", "limit", "utilization", "direction", "unit"],
                      allLimits.map((row) => [row.limit_id, row.state, row.value, row.limit, row.utilization, row.direction, row.unit]),
                    )}
                  >
                    <Download className="mr-1 h-4 w-4" />{t("riskGovernance.exportCsv")}
                  </Button>
                )}
              />
            </CardHeader>
            <CardContent>
              <LimitTable rows={allLimits} empty={t("riskGovernance.emptyLimits")} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alerts" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle title={t("nav.riskAlerts")} detail={t("riskGovernance.alertsHint")} />
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{t("riskGovernance.alertsBody", { count: alerts.length })}</p>
              <LimitTable rows={alerts} empty={t("riskGovernance.emptyAlerts")} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="breaches" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle title={t("nav.riskBreaches")} detail={t("riskGovernance.breachesHint")} />
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{t("riskGovernance.breachesBody", { count: breaches.length })}</p>
              <LimitTable rows={breaches} empty={t("riskGovernance.emptyBreaches")} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="exceptions" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle title={t("nav.exceptionManagement")} detail={t("riskGovernance.exceptionsHint")} />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {t("riskGovernance.hardBreachLock")}
                {hardBreaches.length ? ` · ${hardBreaches.map((row) => row.limit_id).join(", ")}` : ""}
              </div>
              <p className="text-sm text-muted-foreground">
                {t("riskGovernance.exceptionEligible", { count: softBreaches.length })}
              </p>
              <LimitTable rows={softBreaches} empty={t("riskGovernance.emptyExceptions")} />
              <div>
                <h3 className="mb-2 text-sm font-medium">{t("riskGovernance.activeApplications")}</h3>
                <ApplicationsTable items={applications.data?.items ?? []} empty={t("riskGovernance.emptyApplications")} />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="escalation" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle title={t("nav.escalationDisposition")} detail={t("riskGovernance.escalationHint")} />
            </CardHeader>
            <CardContent className="space-y-4">
              <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                <li>{t("riskGovernance.escalationStep1")}</li>
                <li>{t("riskGovernance.escalationStep2")}</li>
                <li>{t("riskGovernance.escalationStep3")}</li>
                <li>{t("riskGovernance.escalationStep4")}</li>
              </ol>
              <LimitTable rows={[...alerts, ...breaches]} empty={t("riskGovernance.emptyEscalation")} />
              <AuditTable rows={pack.data?.audit ?? []} empty={t("riskGovernance.emptyAudit")} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="policy" className="mt-0">
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <ZoneTitle title={t("nav.riskPolicy")} detail={t("riskGovernance.policyHint")} />
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="grid gap-2 sm:grid-cols-2">
                  <Kpi label={t("riskGovernance.policyId")} value={String(pack.data?.policy?.policy_id ?? "default")} />
                  <Kpi label={t("riskGovernance.ruleBindings")} value={String(applications.data?.items?.length ?? rulesSummary.data?.total ?? "—")} />
                </div>
                <p>{pack.data?.policy?.name}</p>
                <p className="text-muted-foreground">{pack.data?.appetite?.statement ?? pack.data?.policy?.appetite}</p>
                <div className="flex flex-wrap gap-2">
                  {(pack.data?.states ?? ["GREEN", "WARNING", "BREACH", "HARD_BREACH"]).map((state) => (
                    <Badge key={state} variant={stateTone(state)}>{state}</Badge>
                  ))}
                </div>
                <div className="grid gap-2 sm:grid-cols-3">
                  <Kpi label={t("riskGovernance.warnUtil")} value={pctUtil(pack.data?.appetite?.warning_utilization)} />
                  <Kpi label={t("riskGovernance.breachUtil")} value={pctUtil(pack.data?.appetite?.breach_utilization)} />
                  <Kpi label={t("riskGovernance.hardUtil")} value={pctUtil(pack.data?.appetite?.hard_breach_utilization)} />
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <ZoneTitle title={t("riskGovernance.defaultLimits")} detail={t("riskGovernance.defaultLimitsHint")} />
              </CardHeader>
              <CardContent>
                <PolicyLimitsTable rows={(pack.data?.policy?.limits as Array<Record<string, unknown>> | undefined) ?? []} empty={t("riskGovernance.emptyPolicyLimits")} />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="model-validation" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle title={t("nav.modelValidation")} detail={t("riskGovernance.modelHint")} />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <Kpi
                  label={t("riskGovernance.controlStatus")}
                  value={String(pack.data?.model_validation?.status ?? "—")}
                  tone={stateClass(pack.data?.model_validation?.status)}
                />
                <Kpi label={t("riskGovernance.controlEngine")} value={String(pack.data?.model_validation?.engine ?? pack.data?.engine ?? "—")} />
                <Kpi label={t("riskGovernance.controlName")} value={String(pack.data?.model_validation?.control ?? "model_validation")} />
              </div>
              <ChecksView checks={pack.data?.model_validation?.checks} empty={t("riskGovernance.emptyChecks")} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="valuation-control" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle title={t("nav.valuationControl")} detail={t("riskGovernance.valuationHint")} />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <Kpi
                  label={t("riskGovernance.controlStatus")}
                  value={String(pack.data?.valuation_control?.status ?? "—")}
                  tone={stateClass(pack.data?.valuation_control?.status)}
                />
                <Kpi label={t("riskGovernance.basePv")} value={money(pack.data?.valuation_control?.base_pv, 0)} />
                <Kpi label={t("riskGovernance.controlEngine")} value={String(pack.data?.valuation_control?.engine ?? pack.data?.engine ?? "—")} />
              </div>
              <p className="text-sm text-muted-foreground">{t("riskGovernance.valuationBody")}</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="liquidity" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle title={t("nav.liquidityGovernance")} detail={t("riskGovernance.liquidityHint")} />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Kpi label="WAM" value={exposure.data ? `${exposure.data.wam_days.toFixed(1)} d` : "—"} />
                <Kpi label="WAL" value={exposure.data ? `${exposure.data.wal_days.toFixed(1)} d` : "—"} />
                <Kpi label={t("riskGovernance.dailyLiquid")} value={exposure.data ? `${exposure.data.daily_liquid_pct.toFixed(2)}%` : "—"} />
                <Kpi label={t("riskGovernance.weeklyLiquid")} value={exposure.data ? `${exposure.data.weekly_liquid_pct.toFixed(2)}%` : "—"} />
              </div>
              <LimitTable rows={liquidityRows} empty={t("riskGovernance.emptyLiquidity")} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="compliance" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle title={t("nav.compliance")} detail={t("riskGovernance.complianceHint")} />
            </CardHeader>
            <CardContent className="space-y-4">
              <CompliancePanel data={exposure.data} loading={exposure.isFetching} error={exposure.isError} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reports" className="mt-0">
          <Card>
            <CardHeader>
              <ZoneTitle
                title={t("nav.riskReports")}
                detail={t("riskGovernance.reportsHint")}
                action={(
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!allLimits.length}
                    onClick={() => exportCsv(
                      `governance_report_${fundId}_${asOfDate}.csv`,
                      ["limit_id", "state", "value", "limit", "utilization"],
                      allLimits.map((row) => [row.limit_id, row.state, row.value, row.limit, row.utilization]),
                    )}
                  >
                    <Download className="mr-1 h-4 w-4" />{t("riskGovernance.exportCsv")}
                  </Button>
                )}
              />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Kpi label={t("riskGovernance.aggregateState")} value={String(summary?.aggregate_state ?? "—")} tone={stateClass(summary?.aggregate_state)} />
                <Kpi label={t("riskGovernance.warningCount")} value={String(alerts.length)} />
                <Kpi label={t("riskGovernance.breachCount")} value={String(breaches.length)} />
                <Kpi label={t("riskGovernance.ruleBindings")} value={String(rulesSummary.data?.total ?? "—")} />
              </div>
              <p className="text-sm text-muted-foreground">{t("riskGovernance.reportsBody")}</p>
              <LimitTable rows={allLimits} empty={t("riskGovernance.emptyLimits")} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

function ApplicationsTable({
  items,
  empty,
}: {
  items: Array<{
    application_id: number
    rule_id?: string | number
    rule_type?: string
    rule_code?: string | null
    port_id?: string | null
    is_active?: boolean
  }>
  empty: string
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ID</TableHead>
            <TableHead>{t("riskGovernance.colRule")}</TableHead>
            <TableHead>{t("riskGovernance.colFund")}</TableHead>
            <TableHead>{t("riskGovernance.colState")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length ? items.map((item) => (
            <TableRow key={item.application_id}>
              <TableCell className="font-mono text-xs">{item.application_id}</TableCell>
              <TableCell className="font-mono text-xs">
                {item.rule_code || `${String(item.rule_type ?? "")}:${String(item.rule_id ?? "")}`}
              </TableCell>
              <TableCell className="font-mono text-xs">{item.port_id ?? t("riskGovernance.allFunds")}</TableCell>
              <TableCell>{item.is_active ? "ACTIVE" : "INACTIVE"}</TableCell>
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={4} className="h-16 text-center text-muted-foreground">{empty}</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}

function PolicyLimitsTable({
  rows,
  empty,
}: {
  rows: Array<Record<string, unknown>>
  empty: string
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("riskGovernance.colLimit")}</TableHead>
            <TableHead>{t("riskGovernance.colDirection")}</TableHead>
            <TableHead className="text-right">{t("riskGovernance.colThreshold")}</TableHead>
            <TableHead className="text-right">Warn</TableHead>
            <TableHead className="text-right">Hard</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length ? rows.map((row) => (
            <TableRow key={String(row.limit_id)}>
              <TableCell className="font-mono text-xs">{String(row.limit_id)}</TableCell>
              <TableCell className="text-xs">{String(row.direction ?? "—")}</TableCell>
              <TableCell className="text-right font-mono text-xs">{money(Number(row.limit))}</TableCell>
              <TableCell className="text-right font-mono text-xs">{pctUtil(Number(row.warning))}</TableCell>
              <TableCell className="text-right font-mono text-xs">{pctUtil(Number(row.hard))}</TableCell>
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={5} className="h-16 text-center text-muted-foreground">{empty}</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}

function AuditTable({
  rows,
  empty,
}: {
  rows: Array<{ event_id?: string; event_type?: string; actor?: string; at?: string }>
  empty: string
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <h3 className="mb-2 text-sm font-medium">{t("riskGovernance.auditTrail")}</h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ID</TableHead>
            <TableHead>{t("riskGovernance.colEvent")}</TableHead>
            <TableHead>{t("riskGovernance.colActor")}</TableHead>
            <TableHead>{t("riskGovernance.colTime")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length ? rows.slice().reverse().map((row) => (
            <TableRow key={row.event_id ?? `${row.event_type}-${row.at}`}>
              <TableCell className="font-mono text-xs">{row.event_id ?? "—"}</TableCell>
              <TableCell className="text-xs">{row.event_type ?? "—"}</TableCell>
              <TableCell className="text-xs">{row.actor ?? "—"}</TableCell>
              <TableCell className="font-mono text-xs">{row.at?.slice(0, 19) ?? "—"}</TableCell>
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={4} className="h-16 text-center text-muted-foreground">{empty}</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}

function ChecksView({ checks, empty }: { checks: unknown; empty: string }) {
  if (!checks) return <p className="text-sm text-muted-foreground">{empty}</p>
  if (Array.isArray(checks)) {
    return (
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Check</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {checks.map((item, index) => {
              const row = (item && typeof item === "object") ? item as Record<string, unknown> : { detail: item }
              return (
                <TableRow key={index}>
                  <TableCell className="font-mono text-xs">{String(row.name ?? row.check ?? index)}</TableCell>
                  <TableCell>{String(row.status ?? row.state ?? "—")}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{String(row.detail ?? row.message ?? JSON.stringify(row))}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    )
  }
  return (
    <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs">
      {JSON.stringify(checks, null, 2)}
    </pre>
  )
}

function CompliancePanel({
  data,
  loading,
  error,
}: {
  data?: ExposureResult
  loading: boolean
  error: boolean
}) {
  const { t } = useTranslation()
  if (loading && !data) return <p className="text-sm text-muted-foreground">{t("riskGovernance.loading")}</p>
  if (error) return <p className="text-sm text-destructive">{t("riskGovernance.complianceLoadError")}</p>
  if (!data) return <p className="text-sm text-muted-foreground">{t("riskGovernance.emptyCompliance")}</p>

  const details = data.compliance_details ?? []
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label={t("riskGovernance.complianceStatus")}
          value={data.is_compliant ? t("riskGovernance.compliant") : t("riskGovernance.nonCompliant")}
          tone={data.is_compliant ? "text-emerald-600" : "text-destructive"}
        />
        <Kpi label="NAV" value={money(data.total_nav_hkd, 0)} />
        <Kpi label={t("riskGovernance.breachCount")} value={String(data.breach_flags?.length ?? 0)} />
        <Kpi label="WAM / WAL" value={`${data.wam_days.toFixed(1)} / ${data.wal_days.toFixed(1)}`} />
      </div>
      {data.breach_flags?.length ? (
        <p className="text-sm text-destructive">{data.breach_flags.join(" · ")}</p>
      ) : null}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("riskGovernance.colRule")}</TableHead>
              <TableHead className="text-right">{t("riskGovernance.colValue")}</TableHead>
              <TableHead className="text-right">{t("riskGovernance.colThreshold")}</TableHead>
              <TableHead>{t("riskGovernance.colState")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {details.length ? details.map((detail, index) => (
              <TableRow key={`${detail.rule_code ?? index}`}>
                <TableCell className="text-sm">{String(detail.rule_name || detail.rule_code || "—")}</TableCell>
                <TableCell className="text-right font-mono text-xs">{money(Number(detail.current_value))}</TableCell>
                <TableCell className="text-right font-mono text-xs">{money(Number(detail.limit_value))}</TableCell>
                <TableCell>
                  <Badge variant={detail.is_breached ? "destructive" : "outline"}>
                    {detail.is_breached ? "BREACH" : "OK"}
                  </Badge>
                </TableCell>
              </TableRow>
            )) : (
              <TableRow>
                <TableCell colSpan={4} className="h-16 text-center text-muted-foreground">
                  {t("riskGovernance.emptyCompliance")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

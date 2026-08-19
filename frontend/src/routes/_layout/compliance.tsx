import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { CheckCircle2, XCircle } from "lucide-react"
import { useMemo } from "react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { fsiApi, type ExposureResult } from "@/fsiClient"

export const Route = createFileRoute("/_layout/compliance")({
  component: CompliancePage,
  head: () => ({ meta: [{ title: "SFC 合規 — ARISK" }] }),
})

const SFC_RULES = [
  {
    code: "WAM_BREACH",
    name: "WAM — 加權平均期限",
    limit: "≤ 60 天",
    getValue: (d: ExposureResult) => `${d.wam_days.toFixed(1)} 天`,
  },
  {
    code: "WAL_BREACH",
    name: "WAL — 加權平均有效期",
    limit: "≤ 120 天",
    getValue: (d: ExposureResult) => `${d.wal_days.toFixed(1)} 天`,
  },
  {
    code: "DAILY_LIQUID_BREACH",
    name: "每日流動資產比例",
    limit: "≥ 7.5% NAV",
    getValue: (d: ExposureResult) => `${d.daily_liquid_pct.toFixed(2)}%`,
  },
  {
    code: "WEEKLY_LIQUID_BREACH",
    name: "每週流動資產比例",
    limit: "≥ 15% NAV",
    getValue: (d: ExposureResult) => `${d.weekly_liquid_pct.toFixed(2)}%`,
  },
  {
    code: "SINGLE_ENTITY_BREACH",
    name: "單一發行人集中度",
    limit: "≤ 10% NAV（重要金融機構 ≤ 25%）",
    getValue: (d: ExposureResult) => {
      const top = d.top_issuers[0]
      return top ? `${top.pct.toFixed(2)}%（${top.issuer}）` : "—"
    },
  },
  {
    code: "GROUP_BREACH",
    name: "同集團合計敞口",
    limit: "≤ 20% NAV",
    getValue: () => "—",
  },
  {
    code: "MATURITY_BREACH",
    name: "工具剩餘期限",
    limit: "≤ 397 天",
    getValue: () => "—",
  },
  {
    code: "ABS_BREACH",
    name: "資產抵押證券（ABS）",
    limit: "≤ 15% NAV",
    getValue: (d: ExposureResult) => {
      const abs = d.by_asset_type["abs"]
      return abs ? `${abs.pct.toFixed(2)}%` : "0%"
    },
  },
]

function RuleRow({
  name,
  limit,
  value,
  breach,
  source,
}: {
  name: string
  limit: string
  value: string
  breach: boolean
  source?: string
}) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center justify-between py-3 border-b last:border-0">
      <div className="flex items-center gap-3">
        {breach
          ? <XCircle className="h-4 w-4 text-destructive shrink-0" />
          : <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />}
        <div>
          <p className="text-sm font-medium">{name}</p>
          <p className="text-xs text-muted-foreground">{limit}</p>
          {source ? <p className="text-xs text-muted-foreground">{source}</p> : null}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm font-mono">{value}</span>
        <Badge
          variant={breach ? "destructive" : "outline"}
          className="w-14 justify-center text-xs"
        >
          {breach ? t("compliance.breach") : t("compliance.compliant")}
        </Badge>
      </div>
    </div>
  )
}

function CompliancePage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)

  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["compliance", fundId, asOfDate],
    queryFn: () => fsiApi.getExposure(fundId, asOfDate).then((r) => r.data),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
  })

  const renderedRules = useMemo(() => {
    if (!data) return []
    if (data.compliance_details?.length) {
      return data.compliance_details.map((detail) => {
        const value = detail.unit === "PCT"
          ? `${detail.current_value.toFixed(2)}%`
          : t("compliance.dayUnit", { value: detail.current_value.toFixed(1) })
        const limitValue = detail.unit === "PCT"
          ? `${detail.limit_value}%`
          : t("compliance.dayUnit", { value: detail.limit_value })
        const trace = data.rule_trace?.[detail.rule_code]
        const source = trace
          ? `${trace.used_default ? "Default" : "Config"} (R:${trace.regulatory}/C:${trace.contract}/I:${trace.internal})`
          : undefined
        return {
          key: detail.breach_code,
          name: `${detail.rule_code} - ${detail.rule_name}`,
          limit: `${detail.operator} ${limitValue}`,
          value,
          breach: detail.is_breached,
          source,
        }
      })
    }

    return SFC_RULES.map((rule) => ({
      key: rule.code,
      name: rule.name,
      limit: rule.limit,
      value: rule.getValue(data),
      breach: data.breach_flags.includes(rule.code),
      source: undefined,
    }))
  }, [data, t])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("compliance.title")}</h1>
        <p className="text-muted-foreground text-sm">
          {t("compliance.subtitle")}
        </p>
      </div>

      <FsiToolbar
        fundId={fundId} onFundChange={setFundId}
        asOfDate={asOfDate} onDateChange={setAsOfDate}
        onRefresh={() => refetch()} isFetching={isFetching}
      />

      {isFetching && <p className="text-muted-foreground text-sm animate-pulse">{t("compliance.loading")}</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {t("compliance.loadError")}
          </CardContent>
        </Card>
      )}

      {data && (
        <div className="space-y-4">
          <Card className={data.is_compliant ? "border-green-500/50" : "border-destructive"}>
            <CardContent className="flex items-center gap-4 pt-4">
              {data.is_compliant
                ? <CheckCircle2 className="h-8 w-8 text-green-500" />
                : <XCircle className="h-8 w-8 text-destructive" />}
              <div>
                <p className="font-semibold text-lg">
                  {data.is_compliant
                    ? t("compliance.allCompliant")
                    : t("compliance.breachCount", { count: data.breach_flags.length })}
                </p>
                <p className="text-sm text-muted-foreground">
                  {data.fund_id} · {String(data.as_of_date)} ·{" "}
                  {t("compliance.navSummary", { value: (data.total_nav_hkd / 1e8).toFixed(2) })}
                </p>
                {!data.is_compliant && (
                  <p className="text-sm text-destructive mt-1">
                    {t("compliance.breachItems", { items: data.breach_flags.join("、") })}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("compliance.checklistTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              {renderedRules.map((rule) => (
                <RuleRow
                  key={rule.key}
                  name={rule.name}
                  limit={rule.limit}
                  value={rule.value}
                  breach={rule.breach}
                  source={rule.source}
                />
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

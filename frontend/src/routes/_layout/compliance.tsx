import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { CheckCircle2, XCircle } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fsiApi, type ExposureResult } from "@/fsiClient"

export const Route = createFileRoute("/_layout/compliance")({
  component: CompliancePage,
  head: () => ({ meta: [{ title: "SFC 合規 — ARISK" }] }),
})

const FUNDS = [
  { id: "BHMMF001", name: "博匯港元貨幣市場基金 I" },
  { id: "BHMMF002", name: "博匯港元貨幣市場基金 II" },
]

// SFC 第 8.2 章所有守則定義
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
  rule,
  data,
}: {
  rule: (typeof SFC_RULES)[number]
  data: ExposureResult
}) {
  const breach = data.breach_flags.includes(rule.code)
  return (
    <div className="flex items-center justify-between py-3 border-b last:border-0">
      <div className="flex items-center gap-3">
        {breach ? (
          <XCircle className="h-4 w-4 text-destructive shrink-0" />
        ) : (
          <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
        )}
        <div>
          <p className="text-sm font-medium">{rule.name}</p>
          <p className="text-xs text-muted-foreground">{rule.limit}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm font-mono text-right">
          {rule.getValue(data)}
        </span>
        <Badge
          variant={breach ? "destructive" : "outline"}
          className="w-14 justify-center text-xs"
        >
          {breach ? "違規" : "合規"}
        </Badge>
      </div>
    </div>
  )
}

function CompliancePage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 1)
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1)
    return d.toISOString().split("T")[0]
  })

  const { data, isLoading, isError } = useQuery({
    queryKey: ["compliance", fundId, asOfDate],
    queryFn: () => fsiApi.getExposure(fundId, asOfDate).then((r) => r.data),
    retry: 1,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">SFC 合規核查</h1>
        <p className="text-muted-foreground text-sm">
          《單位信託及互惠基金守則》第 8.2 章 — 貨幣市場基金合規要求
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select value={fundId} onValueChange={setFundId}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FUNDS.map((f) => (
              <SelectItem key={f.id} value={f.id}>
                {f.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Badge variant="outline" className="h-10 px-3 text-sm">
          {asOfDate}
        </Badge>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">載入中...</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            無法載入合規數據。請確認 Processing API 已啟動。
          </CardContent>
        </Card>
      )}

      {data && (
        <div className="space-y-4">
          {/* 總體狀態 */}
          <Card
            className={
              data.is_compliant ? "border-green-500/50" : "border-destructive"
            }
          >
            <CardContent className="flex items-center gap-4 pt-4">
              {data.is_compliant ? (
                <CheckCircle2 className="h-8 w-8 text-green-500" />
              ) : (
                <XCircle className="h-8 w-8 text-destructive" />
              )}
              <div>
                <p className="font-semibold text-lg">
                  {data.is_compliant
                    ? "全部合規"
                    : `${data.breach_flags.length} 項守則違規`}
                </p>
                <p className="text-sm text-muted-foreground">
                  {data.fund_id} · {data.as_of_date} · 總 NAV HKD{" "}
                  {(data.total_nav_hkd / 1e8).toFixed(2)} 億
                </p>
                {!data.is_compliant && (
                  <p className="text-sm text-destructive mt-1">
                    違規項：{data.breach_flags.join("、")}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* 逐條守則 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">第 8.2 章守則逐項核查</CardTitle>
            </CardHeader>
            <CardContent>
              {SFC_RULES.map((rule) => (
                <RuleRow key={rule.code} rule={rule} data={data} />
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

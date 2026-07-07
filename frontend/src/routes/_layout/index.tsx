import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { AlertTriangle, CheckCircle2, TrendingDown, Waves } from "lucide-react"
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
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [{ title: "儀表板 — ARISK" }],
  }),
})

const DEMO_FUNDS = [
  { id: "BHMMF001", name: "博匯港元貨幣市場基金 I" },
  { id: "BHMMF002", name: "博匯港元貨幣市場基金 II" },
]

function lastTradeDate(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1)
  return d.toISOString().split("T")[0]
}

function MetricCard({
  title,
  value,
  sub,
  limit,
  status,
  icon: Icon,
}: {
  title: string
  value: string
  sub?: string
  limit?: string
  status?: "ok" | "warn" | "breach"
  icon: React.ComponentType<{ className?: string }>
}) {
  const iconColor =
    status === "breach"
      ? "text-destructive"
      : status === "warn"
        ? "text-yellow-500"
        : "text-green-500"
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className={`h-4 w-4 ${iconColor}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        {limit && (
          <p className="text-xs text-muted-foreground mt-1">限額：{limit}</p>
        )}
      </CardContent>
    </Card>
  )
}

function ComplianceRow({
  rule,
  value,
  limit,
  breach,
}: {
  rule: string
  value: string
  limit: string
  breach: boolean
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b last:border-0">
      <span className="text-sm">{rule}</span>
      <div className="flex items-center gap-3">
        <span className="text-sm font-mono">{value}</span>
        <span className="text-xs text-muted-foreground">{limit}</span>
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

function ExposureDashboard({ data }: { data: ExposureResult }) {
  const nav = (data.total_nav_hkd / 1e8).toFixed(2)

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="總 NAV"
          value={`HKD ${nav} 億`}
          icon={Waves}
          status="ok"
        />
        <MetricCard
          title="WAM（加權平均期限）"
          value={`${data.wam_days.toFixed(1)} 天`}
          limit="≤ 60 天"
          status={
            data.wam_days > 60 ? "breach" : data.wam_days > 50 ? "warn" : "ok"
          }
          icon={TrendingDown}
        />
        <MetricCard
          title="WAL（加權平均有效期）"
          value={`${data.wal_days.toFixed(1)} 天`}
          limit="≤ 120 天"
          status={
            data.wal_days > 120
              ? "breach"
              : data.wal_days > 100
                ? "warn"
                : "ok"
          }
          icon={TrendingDown}
        />
        <MetricCard
          title="合規狀態"
          value={
            data.is_compliant
              ? "全部合規"
              : `${data.breach_flags.length} 項違規`
          }
          sub={
            data.is_compliant ? "SFC 第 8.2 章" : data.breach_flags.join(", ")
          }
          status={data.is_compliant ? "ok" : "breach"}
          icon={data.is_compliant ? CheckCircle2 : AlertTriangle}
        />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">SFC 合規明細（第 8.2 章）</CardTitle>
          </CardHeader>
          <CardContent>
            <ComplianceRow
              rule="WAM 加權平均期限"
              value={`${data.wam_days.toFixed(1)} 天`}
              limit="≤ 60 天"
              breach={data.breach_flags.includes("WAM_BREACH")}
            />
            <ComplianceRow
              rule="WAL 加權平均有效期"
              value={`${data.wal_days.toFixed(1)} 天`}
              limit="≤ 120 天"
              breach={data.breach_flags.includes("WAL_BREACH")}
            />
            <ComplianceRow
              rule="每日流動資產"
              value={`${data.daily_liquid_pct.toFixed(2)}%`}
              limit="≥ 7.5%"
              breach={data.breach_flags.includes("DAILY_LIQUID_BREACH")}
            />
            <ComplianceRow
              rule="每週流動資產"
              value={`${data.weekly_liquid_pct.toFixed(2)}%`}
              limit="≥ 15%"
              breach={data.breach_flags.includes("WEEKLY_LIQUID_BREACH")}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">資產配置（% NAV）</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(data.by_asset_type)
                .sort((a, b) => b[1].pct - a[1].pct)
                .map(([type, v]) => (
                  <div key={type} className="flex items-center gap-3">
                    <span className="w-20 text-xs text-muted-foreground truncate">
                      {type}
                    </span>
                    <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${Math.min(v.pct, 100)}%` }}
                      />
                    </div>
                    <span className="w-12 text-xs text-right font-mono">
                      {v.pct.toFixed(1)}%
                    </span>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Dashboard() {
  const { user } = useAuth()
  const [fundId, setFundId] = useState(DEMO_FUNDS[0].id)
  const [asOfDate] = useState(lastTradeDate)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["exposure", fundId, asOfDate],
    queryFn: () => fsiApi.getExposure(fundId, asOfDate).then((r) => r.data),
    retry: 1,
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">風控儀表板</h1>
          <p className="text-muted-foreground text-sm">
            歡迎，{user?.full_name || user?.email} · 估值日期：{asOfDate}
          </p>
        </div>
        <Select value={fundId} onValueChange={setFundId}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder="選擇基金" />
          </SelectTrigger>
          <SelectContent>
            {DEMO_FUNDS.map((f) => (
              <SelectItem key={f.id} value={f.id}>
                {f.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && (
        <p className="text-muted-foreground text-sm">載入中...</p>
      )}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            無法載入風控數據。請確認 Processing API 已啟動（port 8001）。
          </CardContent>
        </Card>
      )}
      {data && <ExposureDashboard data={data} />}
    </div>
  )
}

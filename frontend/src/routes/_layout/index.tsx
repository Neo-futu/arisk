import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { AlertTriangle, CheckCircle2, RefreshCw, TrendingDown, Waves } from "lucide-react"
import { useEffect, useState } from "react"

import { FUNDS, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DatePicker } from "@/components/DatePicker"
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

const LATEST_EXPOSURE_DATE_CACHE_TTL_MS = 60_000

type LatestExposureDateCacheEntry = {
  effectiveDate: string
  expiresAt: number
}

const latestExposureDateCache = new Map<string, LatestExposureDateCacheEntry>()

async function resolveLatestExposureDate(fundId: string, requestedDate: string) {
  const now = Date.now()
  const cached = latestExposureDateCache.get(fundId)

  // Reuse short-lived per-fund cache when requested date is not earlier than cached effective date.
  if (cached && cached.expiresAt > now && requestedDate >= cached.effectiveDate) {
    return {
      effectiveDate: cached.effectiveDate,
      fallbackUsed: cached.effectiveDate !== requestedDate,
    }
  }

  const response = await fsiApi.getExposureLatestDate(fundId, requestedDate)
  const latestDate = response.data.effective_date

  if (latestDate) {
    latestExposureDateCache.set(fundId, {
      effectiveDate: latestDate,
      expiresAt: now + LATEST_EXPOSURE_DATE_CACHE_TTL_MS,
    })
  }

  const effectiveDate = latestDate ?? requestedDate
  return {
    effectiveDate,
    fallbackUsed: effectiveDate !== requestedDate,
  }
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
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)

  const latestDateQuery = useQuery({
    queryKey: ["exposure-latest-date", fundId, asOfDate],
    queryFn: () => resolveLatestExposureDate(fundId, asOfDate),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 0,
  })

  const effectiveDate = latestDateQuery.data?.effectiveDate ?? asOfDate

  const exposureQuery = useQuery({
    queryKey: ["exposure", fundId, effectiveDate],
    queryFn: () => fsiApi.getExposure(fundId, effectiveDate).then((r) => r.data),
    enabled: !latestDateQuery.isFetching && !latestDateQuery.isError,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
  })

  const exposureData = exposureQuery.data
  const fallbackUsed = latestDateQuery.data?.fallbackUsed ?? false
  const isFetching = latestDateQuery.isFetching || exposureQuery.isFetching
  const isError = latestDateQuery.isError || exposureQuery.isError

  useEffect(() => {
    if (latestDateQuery.data?.effectiveDate && latestDateQuery.data.effectiveDate !== asOfDate) {
      setAsOfDate(latestDateQuery.data.effectiveDate)
    }
  }, [latestDateQuery.data?.effectiveDate, asOfDate])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">風控儀表板</h1>
          <p className="text-muted-foreground text-sm">
            歡迎，{user?.full_name || user?.email} · 實際數據日：{effectiveDate}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Select value={fundId} onValueChange={setFundId}>
            <SelectTrigger className="w-56">
              <SelectValue placeholder="選擇基金" />
            </SelectTrigger>
            <SelectContent>
              {FUNDS.map((f) => (
                <SelectItem key={f.id} value={f.id}>
                  {f.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <DatePicker value={asOfDate} onChange={setAsOfDate} />
          {fallbackUsed ? <Badge variant="secondary">已自動回退到最近有數據日</Badge> : null}
          <Button
            variant="outline"
            size="icon"
            onClick={() => {
              latestExposureDateCache.delete(fundId)
              void latestDateQuery.refetch()
              void exposureQuery.refetch()
            }}
            disabled={isFetching}
            title="重新加載"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {isFetching && (
        <p className="text-muted-foreground text-sm animate-pulse">載入中...</p>
      )}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            API 請求失敗或該基金在參考日期之前無可用數據。請確認 Processing API（port 8001）和 Backend（port 8000）均已啟動。
          </CardContent>
        </Card>
      )}
      {exposureData && exposureData.total_nav_hkd === 0 && !isFetching && (
        <Card className="border-yellow-500/50">
          <CardContent className="pt-4 text-sm text-yellow-600">
            查無數據：基金 <b>{fundId}</b> 在 <b>{asOfDate}</b> 無 NAV 記錄。
            請確認日期和基金 ID 與數據庫一致，或點擊重新加載。
          </CardContent>
        </Card>
      )}
      {exposureData && exposureData.total_nav_hkd > 0 && <ExposureDashboard data={exposureData} />}
    </div>
  )
}

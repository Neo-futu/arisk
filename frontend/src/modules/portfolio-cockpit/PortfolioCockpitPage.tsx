import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Download, Gauge, RefreshCw } from "lucide-react"
import { useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { FloatingAiChat } from "@/components/FloatingAiChat"
import { lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fsiApi, type PortfolioCockpitItem } from "@/fsiClient"
import { exportCsv, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"

const ALL = "__all__"

function money(value: number | null | undefined, currency = "HKD", digits = 0) {
  if (value == null) return "—"
  return new Intl.NumberFormat("zh-HK", { style: "currency", currency, maximumFractionDigits: digits, notation: value >= 1e8 ? "compact" : "standard" }).format(value)
}
function pct(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${Number(value).toFixed(digits)}%`
}
function signed(value: number | null | undefined) {
  return value == null ? "text-muted-foreground" : value < 0 ? "text-destructive" : "text-emerald-600"
}
function statusTone(status: string) {
  if (status === "breach") return { dot: "bg-destructive", text: "text-destructive", variant: "destructive" as const }
  if (status === "warn") return { dot: "bg-amber-500", text: "text-amber-600", variant: "secondary" as const }
  return { dot: "bg-emerald-500", text: "text-emerald-600", variant: "default" as const }
}

function ZoneTitle({ index, title, detail, action }: { index: string; title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-semibold text-primary">{index}</span>
        <div>
          <CardTitle className="text-base">{title}</CardTitle>
          {detail ? <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p> : null}
        </div>
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

function LimitBadge({ label, value, limit }: { label: string; value: number | null; limit: number | null }) {
  const { t } = useTranslation()
  if (value == null) return <Badge variant="outline" className="font-mono text-[11px]">{label} —</Badge>
  const over = limit != null && value > limit
  const near = limit != null && !over && value >= limit * 0.9
  const cls = over ? "border-destructive text-destructive" : near ? "border-amber-500 text-amber-600" : "border-emerald-500/50 text-emerald-600"
  return (
    <Badge variant="outline" className={`font-mono text-[11px] ${cls}`} title={t("portfolioCockpit.limitHint")}>
      {label} {value}{limit != null ? `/${limit}` : ""}
    </Badge>
  )
}

function CockpitCard({ p, onDrill }: { p: PortfolioCockpitItem; onDrill: (to: string) => void }) {
  const { t } = useTranslation()
  const tone = statusTone(p.status)
  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${tone.dot}`} title={p.status} />
              <CardTitle className="text-base">{p.port_name}</CardTitle>
            </div>
            <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">{p.port_type}</Badge>
              <span className="font-mono">{p.port_id}</span>
              <span>· {p.base_currency}</span>
              {p.as_of_date ? <span>· {p.as_of_date}</span> : null}
            </div>
          </div>
          <Badge variant={tone.variant}>{t(`portfolioCockpit.status_${p.status}`)}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div><div className="text-xs text-muted-foreground">{t("portfolioCockpit.aum")}</div><div className="font-mono font-semibold">{money(p.net_asset, p.base_currency)}</div></div>
          <div><div className="text-xs text-muted-foreground">{t("portfolioCockpit.unitNav")}</div><div className="font-mono font-semibold">{p.unit_nav == null ? "—" : Number(p.unit_nav).toFixed(6)}</div></div>
          <div><div className="text-xs text-muted-foreground">{t("portfolioCockpit.dayReturn")}</div><div className={`font-mono font-semibold ${signed(p.day_return)}`}>{p.day_return == null ? "—" : pct(p.day_return * 100, 4)}</div></div>
          <div><div className="text-xs text-muted-foreground">{t("portfolioCockpit.yield7d")}</div><div className="font-mono font-semibold">{pct(p.return_rate_7d)}</div></div>
        </div>
        {p.is_mmf ? (
          <div className="flex flex-wrap gap-2">
            <LimitBadge label="WAM" value={p.wam_days} limit={p.wam_limit_days} />
            <LimitBadge label="WAL" value={p.wal_days} limit={p.wal_limit_days} />
            <Badge variant="outline" className={`font-mono text-[11px] ${Math.abs(p.nav_deviation ?? 0) > 50 ? "border-destructive text-destructive" : "border-emerald-500/50 text-emerald-600"}`}>
              {t("portfolioCockpit.deviation")} {p.nav_deviation == null ? "—" : `${p.nav_deviation}bp`}
            </Badge>
          </div>
        ) : null}
        {p.sparkline.length > 1 ? (
          <TrendLineChart values={p.sparkline} labels={[]} lineColor="#2563eb" pointColor="#93c5fd" />
        ) : <div className="flex h-16 items-center justify-center text-xs text-muted-foreground">{t("portfolioCockpit.noSparkline")}</div>}
        <div className="flex flex-wrap gap-2 border-t pt-3">
          <Button size="sm" variant="ghost" onClick={() => onDrill("/valuation")}>{t("portfolioCockpit.drillValuation")}</Button>
          <Button size="sm" variant="ghost" onClick={() => onDrill("/positions")}>{t("portfolioCockpit.drillPositions")}</Button>
          <Button size="sm" variant="ghost" onClick={() => onDrill("/investment-risk")}>{t("portfolioCockpit.drillRisk")}</Button>
        </div>
      </CardContent>
    </Card>
  )
}

export function PortfolioCockpitPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [asOfDate, setAsOfDate] = useState<string>(lastTradeDate())
  const [typeFilter, setTypeFilter] = useState(ALL)
  const [statusFilter, setStatusFilter] = useState(ALL)

  const cockpit = useQuery({
    queryKey: ["portfolio-cockpit", asOfDate],
    queryFn: () => fsiApi.getPortfolioCockpit({ asOfDate }).then((r) => r.data),
    retry: 1,
  })

  const all = cockpit.data?.portfolios ?? []
  const summary = cockpit.data?.summary
  const types = Array.from(new Set(all.map((p) => p.port_type)))
  const filtered = all.filter((p) =>
    (typeFilter === ALL || p.port_type === typeFilter) &&
    (statusFilter === ALL || p.status === statusFilter),
  )

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge className="gap-1"><Gauge className="h-3.5 w-3.5" />{t("portfolioCockpit.badge")}</Badge>
            <Badge variant="outline">Module 2.1</Badge>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("portfolioCockpit.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("portfolioCockpit.subtitle")}</p>
        </div>
      </div>

      <div className="space-y-5">
          <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
            <CardHeader><ZoneTitle index="01" title={t("portfolioCockpit.parameters")} /></CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">{t("portfolioCockpit.asOfDate")}</Label>
                  <Input type="date" className="h-9 w-40" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{t("portfolioCockpit.type")}</Label>
                  <Select value={typeFilter} onValueChange={setTypeFilter}>
                    <SelectTrigger className="h-9 w-32"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value={ALL}>{t("portfolioCockpit.all")}</SelectItem>{types.map((ty) => <SelectItem key={ty} value={ty}>{ty}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{t("portfolioCockpit.statusFilter")}</Label>
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger className="h-9 w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>{t("portfolioCockpit.all")}</SelectItem>
                      <SelectItem value="ok">{t("portfolioCockpit.status_ok")}</SelectItem>
                      <SelectItem value="warn">{t("portfolioCockpit.status_warn")}</SelectItem>
                      <SelectItem value="breach">{t("portfolioCockpit.status_breach")}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button variant="outline" size="sm" onClick={() => void cockpit.refetch()} disabled={cockpit.isFetching}>
                  <RefreshCw className={`mr-2 h-4 w-4 ${cockpit.isFetching ? "animate-spin" : ""}`} />{t("portfolioCockpit.refresh")}
                </Button>
                <Button variant="outline" size="sm" disabled={!all.length} onClick={() => exportCsv(
                  `portfolio_cockpit_${asOfDate}.csv`,
                  ["port_id", "port_name", "port_type", "currency", "net_asset", "unit_nav", "day_return", "return_rate_7d", "wam_days", "wal_days", "nav_deviation", "status"],
                  all.map((p) => [p.port_id, p.port_name, p.port_type, p.base_currency, p.net_asset, p.unit_nav, p.day_return, p.return_rate_7d, p.wam_days, p.wal_days, p.nav_deviation, p.status]),
                )}><Download className="mr-1 h-4 w-4" />{t("portfolioCockpit.exportCsv")}</Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><ZoneTitle index="02" title={t("portfolioCockpit.summary")} /></CardHeader>
            <CardContent>
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <Kpi label={t("portfolioCockpit.totalPortfolios")} value={String(summary?.total_portfolios ?? 0)} />
                <Kpi label={t("portfolioCockpit.totalAum")} value={Object.entries(summary?.total_aum ?? {}).map(([c, v]) => money(v, c)).join(" ") || "—"} />
                <Kpi label={t("portfolioCockpit.mmfCount")} value={String(summary?.mmf_count ?? 0)} />
                <Kpi label={t("portfolioCockpit.warned")} value={String(summary?.warned ?? 0)} tone={summary?.warned ? "text-amber-600" : ""} />
                <Kpi label={t("portfolioCockpit.breached")} value={String(summary?.breached ?? 0)} tone={summary?.breached ? "text-destructive" : ""} />
              </div>
              {summary && Object.keys(summary.by_type).length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {Object.entries(summary.by_type).map(([ty, n]) => <Badge key={ty} variant="secondary">{ty} · {n}</Badge>)}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><ZoneTitle index="03" title={t("portfolioCockpit.cockpitList")} detail={t("portfolioCockpit.cardCount", { count: filtered.length })} /></CardHeader>
            <CardContent>
              {cockpit.isFetching ? <p className="py-10 text-center text-sm text-muted-foreground">{t("portfolioCockpit.loading")}</p> : null}
              {cockpit.isError ? <p className="py-10 text-center text-sm text-destructive">{t("portfolioCockpit.operationFailed")}</p> : null}
              <div className="grid gap-4 xl:grid-cols-2">
                {filtered.map((p) => <CockpitCard key={p.port_id} p={p} onDrill={(to) => navigate({ to })} />)}
              </div>
              {!cockpit.isFetching && !filtered.length ? <p className="py-10 text-center text-sm text-muted-foreground">{t("portfolioCockpit.empty")}</p> : null}
            </CardContent>
          </Card>
      </div>
      <FloatingAiChat
        title={t("portfolioCockpit.aiArea")}
        hint={t("portfolioCockpit.aiHint")}
        placeholder={t("portfolioCockpit.aiPlaceholder")}
        buildPrompt={(q) => [
          "你正在 ARISK 组合驾驶舱协助投资风控人员纵览所有组合的基本盘与状态。",
          `数据日期：${asOfDate}；组合摘要（只作分析，不得杜撰）：`,
          JSON.stringify(all.map((p) => ({ id: p.port_id, type: p.port_type, ccy: p.base_currency, aum: p.net_asset, day_return: p.day_return, yield_7d: p.return_rate_7d, wam: p.wam_days, wal: p.wal_days, deviation: p.nav_deviation, status: p.status }))),
          `用户问题：${q}`,
        ].join("\n")}
      />
    </div>
  )
}

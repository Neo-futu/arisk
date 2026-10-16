import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  fsiApi,
  type RiskMetricBoardCategory,
  type RiskMetricBoardResult,
  type RiskMetricItem,
} from "@/fsiClient"
import { WorkbenchTable, type WorkbenchColumn } from "@/platform/WorkbenchTable"

function formatValue(metric: RiskMetricItem): string {
  if (metric.value == null || metric.value === "") return "—"
  const num = typeof metric.value === "number" ? metric.value : Number(metric.value)
  if (Number.isFinite(num)) {
    const abs = Math.abs(num)
    const digits = abs >= 100 ? 1 : abs >= 10 ? 2 : 3
    const formatted = num.toLocaleString("zh-CN", {
      maximumFractionDigits: digits,
      minimumFractionDigits: 0,
    })
    return metric.unit ? `${formatted}${metric.unit}` : formatted
  }
  return String(metric.value)
}

function metricNote(metric: RiskMetricItem): string {
  return [metric.detail, metric.note].filter(Boolean).join(" · ")
}

function pct(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${Number(value).toFixed(digits)}%`
}

function money(value: number | null | undefined) {
  return value == null ? "—" : Number(value).toLocaleString("zh-HK", { maximumFractionDigits: 0 })
}

function groupMetrics(category: RiskMetricBoardCategory): Array<{ group: string; metrics: RiskMetricItem[] }> {
  const order: string[] = []
  const buckets = new Map<string, RiskMetricItem[]>()
  for (const metric of category.metrics) {
    const group = metric.group || "其他"
    const bucket = buckets.get(group)
    if (bucket) {
      bucket.push(metric)
    } else {
      buckets.set(group, [metric])
      order.push(group)
    }
  }
  return order.map((group) => ({ group, metrics: buckets.get(group) ?? [] }))
}

type RatingRow = {
  rating: string
  market_value: number
  weight_pct: number
  is_investment_grade?: boolean
}

const RATING_KPI_IDS = new Set([
  "issuer_rating_dist",
  "debt_rating_dist",
  "issuer_ig_pct",
  "issuer_below_ig_pct",
  "debt_ig_pct",
  "debt_below_ig_pct",
])

function RatingDistTable({
  title,
  fundId,
  endDate,
  rows,
}: {
  title: string
  fundId: string
  endDate: string
  rows: RatingRow[]
}) {
  const { t } = useTranslation()
  const columns = useMemo<WorkbenchColumn<RatingRow>[]>(() => [
    {
      key: "rating",
      header: t("investmentRisk.ratingSecurities.colRating"),
      filterable: true,
      accessor: (row) => row.rating,
      cell: (row) => (
        <span className="inline-flex items-center gap-2 font-mono font-medium">
          {row.rating}
          {row.is_investment_grade ? (
            <Badge className="bg-emerald-600 hover:bg-emerald-600 text-[10px]">
              {t("investmentRisk.ratingSecurities.igBadge")}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[10px]">
              {t("investmentRisk.ratingSecurities.belowIgBadge")}
            </Badge>
          )}
        </span>
      ),
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.ratingSecurities.colWeight"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono tabular-nums">{pct(row.weight_pct)}</span>,
    },
    {
      key: "market_value",
      header: t("investmentRisk.ratingSecurities.colMarketValue"),
      align: "right",
      accessor: (row) => row.market_value,
      cell: (row) => <span className="font-mono tabular-nums">{money(row.market_value)}</span>,
    },
  ], [t])

  return (
    <WorkbenchTable
      title={title}
      rows={rows}
      columns={columns}
      rowId={(row) => row.rating}
      exportFilename={`rating-${title}-${fundId}-${endDate}.csv`}
      initialSortKey="weight_pct"
      selectable={false}
      embedded
      bodyClassName="h-[260px] overflow-auto rounded-lg border"
    />
  )
}

/** 信用风险 · 评级与个券：单块合并（投资级 KPI + 主体/债项明细 + 个券指标） */
function RatingAndSecuritiesGroup({
  fundId,
  endDate,
  metrics,
  detail,
}: {
  fundId: string
  endDate: string
  metrics: RiskMetricItem[]
  detail: NonNullable<RiskMetricBoardResult["credit_rating_detail"]> | undefined
}) {
  const { t } = useTranslation()
  const securityMetrics = metrics.filter((m) => !RATING_KPI_IDS.has(m.id))

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <div>
        <h3 className="text-sm font-semibold">{t("investmentRisk.ratingSecurities.title")}</h3>
        <p className="text-muted-foreground mt-1 text-xs">
          {t("investmentRisk.ratingSecurities.subtitleSplit")}
        </p>
      </div>

      {detail ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-lg border px-3 py-2">
            <p className="text-muted-foreground text-[11px]">{t("investmentRisk.ratingSecurities.issuerIgPct")}</p>
            <p className="mt-1 font-mono text-lg font-semibold text-emerald-700 dark:text-emerald-400">
              {pct(detail.issuer_investment_grade_pct)}
            </p>
          </div>
          <div className="rounded-lg border px-3 py-2">
            <p className="text-muted-foreground text-[11px]">{t("investmentRisk.ratingSecurities.issuerBelowIgPct")}</p>
            <p className="mt-1 font-mono text-lg font-semibold">{pct(detail.issuer_below_investment_grade_pct)}</p>
          </div>
          <div className="rounded-lg border px-3 py-2">
            <p className="text-muted-foreground text-[11px]">{t("investmentRisk.ratingSecurities.debtIgPct")}</p>
            <p className="mt-1 font-mono text-lg font-semibold text-emerald-700 dark:text-emerald-400">
              {pct(detail.debt_investment_grade_pct)}
            </p>
          </div>
          <div className="rounded-lg border px-3 py-2">
            <p className="text-muted-foreground text-[11px]">{t("investmentRisk.ratingSecurities.debtBelowIgPct")}</p>
            <p className="mt-1 font-mono text-lg font-semibold">{pct(detail.debt_below_investment_grade_pct)}</p>
          </div>
        </div>
      ) : null}

      {securityMetrics.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {securityMetrics.map((metric) => (
            <div key={metric.id} className="rounded-lg border px-3 py-2">
              <p className="text-muted-foreground text-[11px]">{metric.name}</p>
              <p className="mt-1 font-mono text-lg font-semibold">{formatValue(metric)}</p>
              {metricNote(metric) ? (
                <p className="text-muted-foreground mt-1 truncate text-[11px]" title={metricNote(metric)}>
                  {metricNote(metric)}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="min-h-[300px] space-y-2">
          <p className="text-sm font-medium">{t("investmentRisk.ratingSecurities.issuerTable")}</p>
          <RatingDistTable
            title={t("investmentRisk.ratingSecurities.issuerTable")}
            fundId={fundId}
            endDate={endDate}
            rows={detail?.issuer_rating_distribution ?? []}
          />
        </div>
        <div className="min-h-[300px] space-y-2">
          <p className="text-sm font-medium">{t("investmentRisk.ratingSecurities.debtTable")}</p>
          <RatingDistTable
            title={t("investmentRisk.ratingSecurities.debtTable")}
            fundId={fundId}
            endDate={endDate}
            rows={detail?.debt_rating_distribution ?? []}
          />
        </div>
      </div>
    </div>
  )
}

function GroupTable({
  fundId,
  endDate,
  categoryName,
  group,
  metrics,
}: {
  fundId: string
  endDate: string
  categoryName: string
  group: string
  metrics: RiskMetricItem[]
}) {
  const { t } = useTranslation()
  const columns = useMemo<WorkbenchColumn<RiskMetricItem>[]>(() => [
    { key: "name", header: t("investmentRisk.metricBoard.colMetric"), accessor: (row) => row.name },
    {
      key: "value",
      header: t("investmentRisk.metricBoard.colValue"),
      align: "right",
      accessor: (row) => (typeof row.value === "number" ? row.value : String(row.value ?? "")),
      cell: (row) => <span className="font-mono tabular-nums">{formatValue(row)}</span>,
      exportValue: (row) => row.value ?? "",
    },
    {
      key: "note",
      header: t("investmentRisk.metricBoard.colNote"),
      accessor: (row) => metricNote(row) || "—",
      cell: (row) => <span className="text-muted-foreground text-xs">{metricNote(row) || "—"}</span>,
    },
  ], [t])

  return (
    <WorkbenchTable
      title={group}
      rows={metrics}
      columns={columns}
      rowId={(row) => row.id}
      exportFilename={`risk-metrics-${fundId}-${endDate}-${categoryName}-${group}.csv`}
      initialSortKey="name"
      selectable={false}
      bodyClassName="h-[320px] overflow-auto rounded-lg border"
    />
  )
}

function isRatingSecuritiesGroup(group: string): boolean {
  return group === "评级与个券" || group.includes("评级与个券")
}

export function RiskMetricBoardSection({
  fundId,
  startDate,
  endDate,
  categoryPanels,
}: {
  fundId: string
  startDate: string
  endDate: string
  /** 注入到对应风险类别面板内的明细（如市场风险：波动率/回撤/换手/VaR） */
  categoryPanels?: Partial<Record<string, ReactNode>>
}) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["investment-risk-metric-board", fundId, startDate, endDate],
    queryFn: () => fsiApi.getRiskMetricBoard(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const data = query.data
  /** 空字符串表示全部收起；默认不展开任何类别 */
  const [activeCategoryId, setActiveCategoryId] = useState<string>("")

  const visibleCategories = useMemo(
    () => (data?.categories ?? []).filter((category) => category.id !== "stress"),
    [data],
  )

  useEffect(() => {
    if (!visibleCategories.length) return
    if (activeCategoryId && !visibleCategories.some((category) => category.id === activeCategoryId)) {
      setActiveCategoryId("")
    }
  }, [visibleCategories, activeCategoryId])

  if (query.isFetching && !data) {
    return <p className="text-muted-foreground animate-pulse text-sm">{t("investmentRisk.common.loading")}</p>
  }
  if (query.isError) {
    return <p className="text-destructive text-sm">{t("investmentRisk.metricBoard.loadError")}</p>
  }
  if (!data) {
    return <p className="text-muted-foreground text-sm">{t("investmentRisk.metricBoard.empty")}</p>
  }

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-base font-semibold">{t("investmentRisk.metricBoard.title")}</h2>
        <p className="text-muted-foreground mt-1 text-xs">{t("investmentRisk.metricBoard.navHint")}</p>
      </div>
      {data.message ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          {data.message}
        </p>
      ) : null}

      {/* 手风琴分区：既非页面 Tab，也非左侧菜单；产品压力测试已并入同名 Tab */}
      <div className="space-y-2">
        {visibleCategories.map((category, index) => {
          const open = category.id === activeCategoryId
          const metricCount = category.metrics?.length ?? 0
          return (
            <section
              key={category.id}
              className={cn(
                "overflow-hidden rounded-xl border transition-colors",
                open ? "border-primary/40 bg-background shadow-sm" : "bg-muted/15 hover:bg-muted/30",
              )}
            >
              <button
                type="button"
                aria-expanded={open}
                onClick={() =>
                  setActiveCategoryId((prev) => (prev === category.id ? "" : category.id))
                }
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
              >
                <span
                  className={cn(
                    "flex size-8 shrink-0 items-center justify-center rounded-full font-mono text-xs tabular-nums",
                    open
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="min-w-0 flex-1">
                  <span className={cn("block text-sm", open ? "font-semibold" : "font-medium")}>
                    {category.name}
                  </span>
                  {category.name_en ? (
                    <span className="text-muted-foreground block truncate text-xs">{category.name_en}</span>
                  ) : null}
                </span>
                <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                  {t("investmentRisk.metricBoard.metricCount", { count: metricCount })}
                </span>
                <span
                  aria-hidden
                  className={cn(
                    "text-muted-foreground shrink-0 text-xs transition-transform",
                    open && "rotate-180",
                  )}
                >
                  ▾
                </span>
              </button>

              {open ? (
                <div className="space-y-4 border-t px-4 py-4">
                  {groupMetrics(category).map((section) =>
                    category.id === "credit" && isRatingSecuritiesGroup(section.group) ? (
                      <RatingAndSecuritiesGroup
                        key={section.group}
                        fundId={fundId}
                        endDate={endDate}
                        metrics={section.metrics}
                        detail={data.credit_rating_detail}
                      />
                    ) : (
                      <GroupTable
                        key={section.group}
                        fundId={fundId}
                        endDate={endDate}
                        categoryName={category.name}
                        group={section.group}
                        metrics={section.metrics}
                      />
                    ),
                  )}
                  {categoryPanels?.[category.id] ? (
                    <div className="space-y-4 border-t pt-4">{categoryPanels[category.id]}</div>
                  ) : null}
                </div>
              ) : null}
            </section>
          )
        })}
      </div>
    </div>
  )
}

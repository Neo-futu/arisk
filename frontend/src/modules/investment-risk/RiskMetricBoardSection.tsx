import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fsiApi, type RiskMetricBoardCategory, type RiskMetricItem } from "@/fsiClient"
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

export function RiskMetricBoardSection({
  fundId,
  startDate,
  endDate,
}: {
  fundId: string
  startDate: string
  endDate: string
}) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["investment-risk-metric-board", fundId, startDate, endDate],
    queryFn: () => fsiApi.getRiskMetricBoard(fundId, startDate, endDate).then((r) => r.data),
    enabled: startDate <= endDate,
    retry: 1,
  })
  const data = query.data

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
    <div className="space-y-4">
      <h2 className="text-base font-semibold">{t("investmentRisk.metricBoard.title")}</h2>
      {data.message ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          {data.message}
        </p>
      ) : null}

      <Tabs defaultValue={data.categories[0]?.id ?? "market"}>
        <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1 p-1">
          {data.categories.map((category) => (
            <TabsTrigger key={category.id} value={category.id}>
              {category.name}
            </TabsTrigger>
          ))}
        </TabsList>
        {data.categories.map((category) => (
          <TabsContent key={category.id} value={category.id} className="mt-4 space-y-4">
            {groupMetrics(category).map((section) => (
              <GroupTable
                key={section.group}
                fundId={fundId}
                endDate={endDate}
                categoryName={category.name}
                group={section.group}
                metrics={section.metrics}
              />
            ))}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}

import { useQuery } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { FloatingAiChat } from "@/components/FloatingAiChat"
import { lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { fsiApi, type PortfolioCockpitItem } from "@/fsiClient"
import { WorkbenchCharts, type WorkbenchChart } from "@/platform/WorkbenchCharts"
import { WorkbenchTable, type WorkbenchColumn } from "@/platform/WorkbenchTable"

function shiftDate(iso: string, days: number) {
  const date = new Date(`${iso}T00:00:00`)
  date.setDate(date.getDate() + days)
  return date.toISOString().split("T")[0]
}

function amount(value: number | null | undefined) {
  if (value == null) return "—"
  return new Intl.NumberFormat("zh-HK", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function pct(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${Number(value).toFixed(digits)}%`
}

function signed(value: number | null | undefined) {
  return value == null ? "text-muted-foreground" : value < 0 ? "text-destructive" : "text-emerald-600"
}

function navText(value: number | null | undefined) {
  return value == null ? "—" : Number(value).toFixed(6)
}

function chartsFor(rows: PortfolioCockpitItem[], labels: { aum: string; aumHint: string; type: string; ret: string; retHint: string; nav: string; navHint: string }): WorkbenchChart[] {
  const aum = rows
    .filter((row) => row.net_asset != null)
    .map((row) => ({
      id: row.port_id,
      label: row.port_name,
      value: row.net_asset ?? 0,
      display: amount(row.net_asset),
      group: row.base_currency,
    }))
  const byType = new Map<string, number>()
  for (const row of rows) byType.set(row.port_type, (byType.get(row.port_type) ?? 0) + (row.net_asset ?? 0))
  return [
    { id: "aum", label: labels.aum, hint: labels.aumHint, kind: "bar", points: aum },
    {
      id: "mix",
      label: labels.type,
      kind: "pie",
      points: [...byType.entries()].map(([type, value]) => ({ id: type, label: type, value, display: amount(value) })),
    },
    {
      id: "return",
      label: labels.ret,
      hint: labels.retHint,
      kind: "bar",
      points: rows
        .filter((row) => row.period_return != null || row.day_return != null)
        .map((row) => {
          const value = (row.period_return ?? row.day_return ?? 0) * 100
          return { id: row.port_id, label: row.port_name, value, display: pct(value) }
        }),
    },
    {
      id: "nav",
      label: labels.nav,
      hint: labels.navHint,
      kind: "line",
      lines: rows.map((row) => {
        const history = (row.history ?? []).filter((point) => point.date && point.unit_nav != null && point.unit_nav > 0)
        const base = history[0]?.unit_nav ?? 1
        return {
          id: row.port_id,
          name: row.port_name,
          points: history.map((point) => ({ x: point.date as string, y: ((point.unit_nav as number) / base) * 100 })),
        }
      }),
    },
  ]
}

export function PortfolioCockpitPage() {
  const { t } = useTranslation()
  const endDefault = lastTradeDate()
  const [startDate, setStartDate] = useState(shiftDate(endDefault, -180))
  const [endDate, setEndDate] = useState(endDefault)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [chartRows, setChartRows] = useState<PortfolioCockpitItem[]>([])

  const cockpit = useQuery({
    queryKey: ["portfolio-cockpit", startDate, endDate],
    queryFn: () => fsiApi.getPortfolioCockpit({ startDate, endDate }).then((response) => response.data),
    enabled: startDate <= endDate,
    retry: 1,
  })

  const rows = cockpit.data?.portfolios ?? []
  const columns = useMemo<WorkbenchColumn<PortfolioCockpitItem>[]>(() => [
    {
      key: "port_name",
      header: t("portfolioCockpit.name"),
      accessor: (row) => row.port_name,
      cell: (row) => (
        <div>
          <div className="font-medium">{row.port_name}</div>
          <div className="font-mono text-xs text-muted-foreground">{row.port_id}</div>
        </div>
      ),
      exportValue: (row) => row.port_name,
    },
    {
      key: "port_type",
      header: t("portfolioCockpit.type"),
      filterable: true,
      accessor: (row) => row.port_type,
      cell: (row) => <Badge variant="outline">{row.port_type}</Badge>,
    },
    { key: "base_currency", header: t("portfolioCockpit.currency"), accessor: (row) => row.base_currency },
    { key: "as_of_date", header: t("portfolioCockpit.asOf"), accessor: (row) => row.as_of_date },
    {
      key: "net_asset",
      header: t("portfolioCockpit.aum"),
      align: "right",
      accessor: (row) => row.net_asset,
      cell: (row) => <span className="font-mono">{amount(row.net_asset)}</span>,
    },
    {
      key: "unit_nav",
      header: t("portfolioCockpit.unitNav"),
      align: "right",
      accessor: (row) => row.unit_nav,
      cell: (row) => <span className="font-mono">{navText(row.unit_nav)}</span>,
    },
    {
      key: "acc_unit_nav",
      header: t("portfolioCockpit.accNav"),
      align: "right",
      accessor: (row) => row.acc_unit_nav,
      cell: (row) => <span className="font-mono">{navText(row.acc_unit_nav)}</span>,
    },
    {
      key: "day_return",
      header: t("portfolioCockpit.dayReturn"),
      align: "right",
      accessor: (row) => row.day_return,
      cell: (row) => <span className={`font-mono ${signed(row.day_return)}`}>{row.day_return == null ? "—" : pct(row.day_return * 100, 4)}</span>,
    },
    {
      key: "period_return",
      header: t("portfolioCockpit.periodReturn"),
      align: "right",
      accessor: (row) => row.period_return,
      cell: (row) => <span className={`font-mono ${signed(row.period_return)}`}>{pct(row.period_return == null ? null : row.period_return * 100)}</span>,
    },
    {
      key: "return_rate_7d",
      header: t("portfolioCockpit.yield7d"),
      align: "right",
      accessor: (row) => row.return_rate_7d,
      cell: (row) => <span className="font-mono">{pct(row.return_rate_7d)}</span>,
    },
  ], [t])

  const charts = chartsFor(chartRows.length ? chartRows : rows, {
    aum: t("portfolioCockpit.tabAum"),
    aumHint: t("portfolioCockpit.aumHint"),
    type: t("portfolioCockpit.type"),
    ret: t("portfolioCockpit.tabReturn"),
    retHint: t("portfolioCockpit.returnHint"),
    nav: t("portfolioCockpit.tabNav"),
    navHint: `${t("portfolioCockpit.navHint")} · ${t("portfolioCockpit.indexed")}`,
  })

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">{t("portfolioCockpit.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("portfolioCockpit.subtitle")}</p>
      </div>

      <WorkbenchTable
        title={t("portfolioCockpit.listTitle")}
        rows={rows}
        columns={columns}
        rowId={(row) => row.port_id}
        dateRange={{ startDate, endDate }}
        onDateRangeChange={(next) => {
          setStartDate(next.startDate)
          setEndDate(next.endDate)
        }}
        onRefresh={() => void cockpit.refetch()}
        refreshing={cockpit.isFetching}
        loading={cockpit.isFetching && !rows.length}
        error={cockpit.isError ? t("portfolioCockpit.operationFailed") : null}
        emptyText={t("portfolioCockpit.empty")}
        selectedIds={selectedIds}
        onSelectedIdsChange={setSelectedIds}
        onViewChange={(view) => setChartRows(view.selected)}
        exportFilename={`portfolio_cockpit_${startDate}_${endDate}.csv`}
        rowPicker={{
          label: t("portfolioCockpit.portfolioFilter"),
          text: (row) => `${row.port_id} ${row.port_name}`,
        }}
        initialSortKey="net_asset"
      />

      <WorkbenchCharts
        charts={charts}
        selectionActive={selectedIds.length > 0}
        onShowAll={() => setSelectedIds([])}
      />

      <FloatingAiChat
        title={t("portfolioCockpit.aiArea")}
        hint={t("portfolioCockpit.aiHint")}
        placeholder={t("portfolioCockpit.aiPlaceholder")}
        buildPrompt={(question) => [
          "你正在 ARISK 组合驾驶舱协助浏览组合基本信息（类型、AUM、净值、收益）。不要讨论合规、限额、WAM、WAL 或偏差。",
          `日期区间：${startDate} 至 ${endDate}；组合摘要（只作分析，不得杜撰）：`,
          JSON.stringify((chartRows.length ? chartRows : rows).map((item) => ({
            id: item.port_id,
            name: item.port_name,
            type: item.port_type,
            ccy: item.base_currency,
            aum: item.net_asset,
            unit_nav: item.unit_nav,
            day_return: item.day_return,
            period_return: item.period_return,
            yield_7d: item.return_rate_7d,
          }))),
          `用户问题：${question}`,
        ].join("\n")}
      />
    </div>
  )
}

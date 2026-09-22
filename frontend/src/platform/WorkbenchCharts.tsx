/** Framework charts: bar, pie, and line. Consumes the rows selected in WorkbenchTable. */
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const COLORS = ["#2563eb", "#0f766e", "#b45309", "#7c3aed", "#be123c", "#0369a1", "#4d7c0f", "#a16207"]

export type ChartPoint = {
  id: string
  label: string
  value: number
  display?: string
  group?: string
}

export type LineSeries = {
  id: string
  name: string
  points: { x: string; y: number }[]
}

export type WorkbenchChart = {
  id: string
  label: string
  hint?: string
  kind: "bar" | "pie" | "line"
  points?: ChartPoint[]
  lines?: LineSeries[]
}

function BarChart({ points }: { points: ChartPoint[] }) {
  const groups = new Map<string, ChartPoint[]>()
  for (const point of points) {
    const key = point.group ?? ""
    const bucket = groups.get(key) ?? []
    bucket.push(point)
    groups.set(key, bucket)
  }
  return (
    <div className="space-y-4">
      {[...groups.entries()].map(([group, rows]) => {
        const max = Math.max(...rows.map((row) => Math.abs(row.value)), 1)
        return (
          <div key={group || "all"} className="space-y-2">
            {group ? <div className="text-xs font-medium text-muted-foreground">{group}</div> : null}
            {rows.map((row) => (
              <div key={row.id} className="grid grid-cols-[9rem_1fr_7rem] items-center gap-3 text-sm">
                <div className="truncate font-medium" title={row.label}>{row.label}</div>
                <div className="h-2.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full rounded-full ${row.value < 0 ? "bg-destructive" : "bg-primary"}`}
                    style={{ width: `${Math.max(4, (Math.abs(row.value) / max) * 100)}%` }}
                  />
                </div>
                <div className={`text-right font-mono text-xs ${row.value < 0 ? "text-destructive" : ""}`}>{row.display ?? row.value}</div>
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function PieChart({ points }: { points: ChartPoint[] }) {
  const slices = points.filter((point) => point.value > 0)
  const total = slices.reduce((sum, point) => sum + point.value, 0)
  if (!slices.length || total <= 0) return <p className="py-10 text-center text-sm text-muted-foreground">—</p>
  let cursor = 0
  const arcs = slices.map((point, index) => {
    const start = cursor
    const sweep = point.value / total
    cursor += sweep
    return { ...point, start, end: cursor, color: COLORS[index % COLORS.length] }
  })
  const rings = arcs.map((arc) => {
    const a0 = arc.start * Math.PI * 2 - Math.PI / 2
    const a1 = arc.end * Math.PI * 2 - Math.PI / 2
    const large = arc.end - arc.start > 0.5 ? 1 : 0
    const x0 = 80 + Math.cos(a0) * 62
    const y0 = 80 + Math.sin(a0) * 62
    const x1 = 80 + Math.cos(a1) * 62
    const y1 = 80 + Math.sin(a1) * 62
    const path = slices.length === 1
      ? "M80,18 A62,62 0 1,1 79.9,18 Z"
      : `M80,80 L${x0},${y0} A62,62 0 ${large},1 ${x1},${y1} Z`
    return <path key={arc.id} d={path} fill={arc.color} />
  })
  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 160 160" className="h-44 w-44">{rings}</svg>
      <div className="space-y-1 text-sm">
        {arcs.map((arc) => (
          <div key={arc.id} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: arc.color }} />
            <span>{arc.label}</span>
            <span className="font-mono text-xs text-muted-foreground">{((arc.value / total) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function LineChart({ lines }: { lines: LineSeries[] }) {
  const series = lines.filter((line) => line.points.length > 1).slice(0, 8)
  if (!series.length) return <p className="py-10 text-center text-sm text-muted-foreground">—</p>
  const width = 720
  const height = 260
  const left = 44
  const right = 16
  const top = 16
  const bottom = 28
  const values = series.flatMap((line) => line.points.map((point) => point.y))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const axis = Array.from(new Set(series.flatMap((line) => line.points.map((point) => point.x)))).sort()
  const xOf = (x: string) => left + (Math.max(axis.indexOf(x), 0) / Math.max(axis.length - 1, 1)) * (width - left - right)
  const yOf = (y: number) => top + (1 - (y - min) / range) * (height - top - bottom)
  return (
    <div className="space-y-3">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-64 w-full">
        {[0, 0.5, 1].map((tick) => {
          const y = top + tick * (height - top - bottom)
          return (
            <g key={tick}>
              <line x1={left} x2={width - right} y1={y} y2={y} stroke="currentColor" strokeOpacity="0.12" />
              <text x={4} y={y + 4} className="fill-muted-foreground" fontSize="11">{(min + range * (1 - tick)).toFixed(1)}</text>
            </g>
          )
        })}
        {series.map((line, index) => (
          <polyline
            key={line.id}
            fill="none"
            stroke={COLORS[index % COLORS.length]}
            strokeWidth="2.4"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={line.points.map((point) => `${xOf(point.x)},${yOf(point.y)}`).join(" ")}
          />
        ))}
        <text x={left} y={height - 8} className="fill-muted-foreground" fontSize="11">{axis[0]}</text>
        <text x={width - right} y={height - 8} textAnchor="end" className="fill-muted-foreground" fontSize="11">{axis[axis.length - 1]}</text>
      </svg>
      <div className="flex flex-wrap gap-3 text-xs">
        {series.map((line, index) => (
          <span key={line.id} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-4 rounded-full" style={{ background: COLORS[index % COLORS.length] }} />
            {line.name}
          </span>
        ))}
      </div>
    </div>
  )
}

export function WorkbenchCharts({
  title,
  charts,
  selectionActive = false,
  onShowAll,
}: {
  title?: string
  charts: WorkbenchChart[]
  selectionActive?: boolean
  onShowAll?: () => void
}) {
  const { t } = useTranslation()
  const [tab, setTab] = useState(charts[0]?.id ?? "")
  const active = charts.some((chart) => chart.id === tab) ? tab : charts[0]?.id ?? ""
  if (!charts.length) return null
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">{title ?? t("platform.charts")}</CardTitle>
        {selectionActive && onShowAll ? (
          <Button size="sm" variant="ghost" onClick={onShowAll}>{t("platform.showAll")}</Button>
        ) : null}
      </CardHeader>
      <CardContent>
        <Tabs value={active} onValueChange={setTab}>
          <TabsList>
            {charts.map((chart) => <TabsTrigger key={chart.id} value={chart.id}>{chart.label}</TabsTrigger>)}
          </TabsList>
          {charts.map((chart) => (
            <TabsContent key={chart.id} value={chart.id} className="space-y-3 pt-3">
              {chart.hint ? <p className="text-xs text-muted-foreground">{chart.hint}</p> : null}
              {chart.kind === "bar" ? <BarChart points={chart.points ?? []} /> : null}
              {chart.kind === "pie" ? <PieChart points={chart.points ?? []} /> : null}
              {chart.kind === "line" ? <LineChart lines={chart.lines ?? []} /> : null}
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  )
}

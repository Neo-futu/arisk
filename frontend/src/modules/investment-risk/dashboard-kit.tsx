import type { ReactNode } from "react"

export type ChartPoint = {
  label: string
  value: number
}

export function exportCsv(filename: string, headers: string[], rows: Array<Array<string | number | null | undefined>>) {
  const csv = [headers, ...rows]
    .map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(","))
    .join("\n")

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

function buildLinePath(values: number[]) {
  const width = 360
  const height = 170
  const maxValue = Math.max(...values)
  const minValue = Math.min(...values)
  const range = maxValue - minValue || 1

  return values
    .map((value, index) => {
      const x = 20 + (index / Math.max(values.length - 1, 1)) * (width - 40)
      const normalized = (value - minValue) / range
      const y = height - 30 - normalized * (height - 60)
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
}

export function TrendLineChart({
  values,
  labels,
  lineColor = "#2563eb",
  pointColor = "#38bdf8",
}: {
  values: number[]
  labels: string[]
  lineColor?: string
  pointColor?: string
}) {
  if (!values.length) {
    return <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">暫無圖表數據</div>
  }

  const maxValue = Math.max(...values)
  const minValue = Math.min(...values)
  const range = maxValue - minValue || 1

  return (
    <div>
      <svg viewBox="0 0 360 170" className="h-48 w-full">
        <line x1="20" y1="140" x2="340" y2="140" stroke="currentColor" strokeOpacity="0.25" />
        <line x1="20" y1="95" x2="340" y2="95" stroke="currentColor" strokeOpacity="0.15" />
        <line x1="20" y1="50" x2="340" y2="50" stroke="currentColor" strokeOpacity="0.15" />
        <path d={buildLinePath(values)} fill="none" stroke={lineColor} strokeWidth="3" strokeLinecap="round" />
        {values.map((value, index) => {
          const x = 20 + (index / Math.max(values.length - 1, 1)) * 320
          const normalized = (value - minValue) / range
          const y = 140 - normalized * 90
          return <circle key={`${value}-${index}`} cx={x} cy={y} r="4.5" fill={pointColor} />
        })}
      </svg>
      <div className="mt-2 flex justify-between gap-2 text-xs text-muted-foreground">
        {labels.map((label) => (
          <span key={label} className="truncate">{label}</span>
        ))}
      </div>
    </div>
  )
}

export function HorizontalBarList({
  items,
  formatter,
  rightSlot,
}: {
  items: ChartPoint[]
  formatter?: (value: number) => string
  rightSlot?: (item: ChartPoint) => ReactNode
}) {
  if (!items.length) {
    return <div className="py-10 text-center text-sm text-muted-foreground">暫無圖表數據</div>
  }

  const maxValue = Math.max(...items.map((item) => item.value), 1)

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label}>
          <div className="mb-1 flex items-center justify-between gap-3 text-sm">
            <span className="truncate">{item.label}</span>
            <span className="shrink-0 text-muted-foreground">{rightSlot ? rightSlot(item) : formatter?.(item.value) ?? item.value}</span>
          </div>
          <div className="h-2 rounded-full bg-muted">
            <div className="h-2 rounded-full bg-primary" style={{ width: `${(item.value / maxValue) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}
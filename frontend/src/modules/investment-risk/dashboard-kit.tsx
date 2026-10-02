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

function buildLinePath(
  values: number[],
  opts: {
    width: number
    height: number
    padL: number
    padR: number
    padT: number
    padB: number
  },
) {
  const { width, height, padL, padR, padT, padB } = opts
  const maxValue = Math.max(...values)
  const minValue = Math.min(...values)
  const range = maxValue - minValue || 1
  const plotW = width - padL - padR
  const plotH = height - padT - padB

  return values
    .map((value, index) => {
      const x = padL + (index / Math.max(values.length - 1, 1)) * plotW
      const normalized = (value - minValue) / range
      const y = padT + plotH - normalized * plotH
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
}

function pickXTicks(labels: string[]): Array<{ index: number; label: string }> {
  if (!labels.length) return []
  if (labels.length === 1) return [{ index: 0, label: labels[0] }]
  if (labels.length === 2) {
    return [
      { index: 0, label: labels[0] },
      { index: 1, label: labels[1] },
    ]
  }
  const mid = Math.floor((labels.length - 1) / 2)
  return [
    { index: 0, label: labels[0] },
    { index: mid, label: labels[mid] },
    { index: labels.length - 1, label: labels[labels.length - 1] },
  ]
}

export function TrendLineChart({
  values,
  labels,
  lineColor = "#2563eb",
  pointColor = "#38bdf8",
  valueFormatter,
}: {
  values: number[]
  labels: string[]
  lineColor?: string
  pointColor?: string
  /** Y 轴刻度格式；默认保留 2 位小数 */
  valueFormatter?: (value: number) => string
}) {
  if (!values.length) {
    return <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">暫無圖表數據</div>
  }

  const width = 400
  const height = 200
  const padL = 52
  const padR = 12
  const padT = 14
  const padB = 28
  const plotW = width - padL - padR
  const plotH = height - padT - padB

  const maxValue = Math.max(...values)
  const minValue = Math.min(...values)
  const range = maxValue - minValue || 1
  const midValue = (maxValue + minValue) / 2
  const formatY = valueFormatter ?? ((value: number) => value.toFixed(2))
  const yTicks = [
    { value: maxValue, y: padT },
    { value: midValue, y: padT + plotH / 2 },
    { value: minValue, y: padT + plotH },
  ]
  const xTicks = pickXTicks(labels)
  const showPoints = values.length <= 40

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-52 w-full" role="img" aria-label="trend-line">
        {/* 网格 + Y 轴刻度 */}
        {yTicks.map((tick) => (
          <g key={`y-${tick.value}`}>
            <line
              x1={padL}
              y1={tick.y}
              x2={width - padR}
              y2={tick.y}
              stroke="currentColor"
              strokeOpacity={0.18}
            />
            <text
              x={padL - 6}
              y={tick.y + 3}
              textAnchor="end"
              className="fill-muted-foreground"
              fontSize="10"
            >
              {formatY(tick.value)}
            </text>
          </g>
        ))}
        {/* Y 轴线 */}
        <line
          x1={padL}
          y1={padT}
          x2={padL}
          y2={padT + plotH}
          stroke="currentColor"
          strokeOpacity={0.35}
        />
        {/* X 轴线 */}
        <line
          x1={padL}
          y1={padT + plotH}
          x2={width - padR}
          y2={padT + plotH}
          stroke="currentColor"
          strokeOpacity={0.35}
        />
        <path
          d={buildLinePath(values, {
            width,
            height,
            padL,
            padR,
            padT,
            padB,
          })}
          fill="none"
          stroke={lineColor}
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        {showPoints
          ? values.map((value, index) => {
              const x = padL + (index / Math.max(values.length - 1, 1)) * plotW
              const normalized = (value - minValue) / range
              const y = padT + plotH - normalized * plotH
              return <circle key={`${labels[index] ?? index}-${value}`} cx={x} cy={y} r="3.5" fill={pointColor} />
            })
          : null}
        {/* X 轴刻度 */}
        {xTicks.map((tick) => {
          const x = padL + (tick.index / Math.max(labels.length - 1, 1)) * plotW
          return (
            <text
              key={`x-${tick.index}-${tick.label}`}
              x={x}
              y={height - 8}
              textAnchor="middle"
              className="fill-muted-foreground"
              fontSize="10"
            >
              {tick.label}
            </text>
          )
        })}
      </svg>
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
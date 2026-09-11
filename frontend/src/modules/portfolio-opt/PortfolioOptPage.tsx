import { useMutation, useQuery } from "@tanstack/react-query"
import { Download, LineChart, PieChart, Play } from "lucide-react"
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { DatePicker } from "@/components/DatePicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  fsiApi,
  type OptimizeRequest,
  type OptimizeResult,
  type OptMetrics,
  type MarketQuote,
} from "@/fsiClient"
import { exportCsv } from "@/modules/investment-risk/dashboard-kit"
import { AdapterStatusBar } from "@/platform/AdapterStatus"
import { useBindPageContext } from "@/platform/page-context"

const PROFILE_COLORS: Record<string, string> = {
  conservative: "#2563eb", balanced: "#ef4444", aggressive: "#22c55e",
  hrp: "#f59e0b", target_return: "#a855f7", custom: "#ec4899", benchmark: "#0ea5e9",
}
const NONE = "__none__"

function pct(v: number | null | undefined, d = 2) {
  return v == null ? "—" : `${(v * 100).toFixed(d)}%`
}
function num(v: number | null | undefined, d = 2) {
  return v == null ? "—" : Number(v).toFixed(d)
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

function CorrelationHeatmap({ assets, matrix }: { assets: string[]; matrix: number[][] }) {
  const color = (v: number) => {
    const r = v < 0 ? 235 : Math.round(235 - v * 180)
    const g = v < 0 ? Math.round(235 + v * 40) : Math.round(215 + v * 40)
    return `rgb(${r},${g},110)`
  }
  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-[10px]">
        <tbody>
          {matrix.map((row, i) => (
            <tr key={assets[i]}>
              <td className="pr-2 text-right font-mono text-muted-foreground">{assets[i]}</td>
              {row.map((v, j) => (
                <td key={j} className="h-7 w-8 text-center font-mono" style={{ backgroundColor: color(v), color: "#111" }} title={`${assets[i]}/${assets[j]}: ${v.toFixed(2)}`}>{v.toFixed(1)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MarketQuoteSparkline({
  points,
  noDataText,
  xAxisLabel,
  yAxisLabel,
}: {
  points: Array<{ date: string; value: number }>
  noDataText: string
  xAxisLabel: string
  yAxisLabel: string
}) {
  if (!points.length) return <div className="flex h-44 items-center justify-center text-xs text-muted-foreground">{noDataText}</div>
  const width = 720
  const height = 220
  const padL = 58
  const padR = 24
  const padT = 18
  const padB = 48
  const values = points.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const scaleX = (i: number) => padL + (i / Math.max(points.length - 1, 1)) * (width - padL - padR)
  const scaleY = (v: number) => height - padB - ((v - min) / ((max - min) || 1)) * (height - padT - padB)
  const line = points.map((p, i) => `${scaleX(i)},${scaleY(p.value)}`).join(" ")
  const area = `${line} ${scaleX(points.length - 1)},${height - padB} ${scaleX(0)},${height - padB}`
  const yTicks = Array.from({ length: 5 }, (_, i) => min + ((4 - i) / 4) * ((max - min) || 1))
  const xTickIdx = Array.from(new Set([0, Math.floor((points.length - 1) * 0.33), Math.floor((points.length - 1) * 0.66), points.length - 1]))

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-64 w-full">
        <defs>
          <linearGradient id="quoteArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0" />
          </linearGradient>
        </defs>
        {yTicks.map((tick, i) => (
          <g key={`qy-${i}`}>
            <line x1={padL} y1={scaleY(tick)} x2={width - padR} y2={scaleY(tick)} stroke="currentColor" strokeOpacity="0.12" />
            <text x={padL - 8} y={scaleY(tick) + 3} fontSize="10" textAnchor="end" fill="currentColor" opacity="0.65">{tick.toFixed(2)}</text>
          </g>
        ))}
        {xTickIdx.map((idx) => (
          <g key={`qx-${idx}`}>
            <line x1={scaleX(idx)} y1={height - padB} x2={scaleX(idx)} y2={height - padB + 5} stroke="currentColor" strokeOpacity="0.45" />
            <text x={scaleX(idx)} y={height - padB + 18} fontSize="10" textAnchor="middle" fill="currentColor" opacity="0.65">{points[idx]?.date?.slice(5) ?? ""}</text>
          </g>
        ))}
        <line x1={padL} y1={height - padB} x2={width - padR} y2={height - padB} stroke="currentColor" strokeOpacity="0.45" />
        <line x1={padL} y1={padT} x2={padL} y2={height - padB} stroke="currentColor" strokeOpacity="0.45" />
        <polygon points={area} fill="url(#quoteArea)" />
        <polyline points={line} fill="none" stroke="#2563eb" strokeWidth="2.8" />
        {points.map((p, i) => (
          <circle key={`${p.date}-${i}`} cx={scaleX(i)} cy={scaleY(p.value)} r="3.3" fill="#2563eb" />
        ))}
        <text x={(padL + width - padR) / 2} y={height - 7} fontSize="11" textAnchor="middle" fill="currentColor" opacity="0.75">{xAxisLabel}</text>
        <text x="16" y={(padT + height - padB) / 2} fontSize="11" textAnchor="middle" fill="currentColor" opacity="0.75" transform={`rotate(-90 16 ${(padT + height - padB) / 2})`}>{yAxisLabel}</text>
      </svg>
    </div>
  )
}

/** Professional efficient-frontier chart: % axes + gridlines + CML + tangency. */
type HoverPt = { leftPct: number; topPct: number; title: string; vol: number; ret: number; color: string }

function FrontierScatter({ result, livePoint }: { result: OptimizeResult; livePoint?: { volatility: number; expected_return: number } | null }) {
  const { t } = useTranslation()
  const [hover, setHover] = useState<HoverPt | null>(null)
  const profilePts = Object.entries(result.profiles).map(([name, d]) => ({ name, ...d.metrics }))
  const allX = [...result.frontier.map((p) => p.volatility), ...result.asset_points.map((p) => p.volatility), ...profilePts.map((p) => p.volatility), 0]
  const allY = [...result.frontier.map((p) => p.expected_return), ...result.asset_points.map((p) => p.expected_return), ...profilePts.map((p) => p.expected_return), result.risk_free_rate]
  const xMin = 0, xMax = Math.max(...allX) * 1.08
  const yMin = Math.min(...allY, 0) * 1.1, yMax = Math.max(...allY) * 1.1
  const W = 780, H = 470, padL = 62, padB = 50, padT = 20, padR = 22
  const sx = (x: number) => padL + ((x - xMin) / (xMax - xMin || 1)) * (W - padL - padR)
  const sy = (y: number) => H - padB - ((y - yMin) / (yMax - yMin || 1)) * (H - padT - padB)
  const xticks = Array.from({ length: 6 }, (_, i) => xMin + (i / 5) * (xMax - xMin))
  const yticks = Array.from({ length: 6 }, (_, i) => yMin + (i / 5) * (yMax - yMin))
  const rf = result.risk_free_rate
  const tan = result.tangency

  const enter = (title: string, vol: number, ret: number, color: string) => () =>
    setHover({ leftPct: (sx(vol) / W) * 100, topPct: (sy(ret) / H) * 100, title, vol, ret, color })
  const leave = () => setHover(null)

  return (
    <div>
      <div className="relative w-full" style={{ aspectRatio: `${W} / ${H}` }}>
        <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full">
          <defs>
            <linearGradient id="frontierArea" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366f1" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
            </linearGradient>
          </defs>
          {xticks.map((xt) => (
            <g key={`x${xt}`}>
              <line x1={sx(xt)} y1={padT} x2={sx(xt)} y2={H - padB} stroke="currentColor" strokeOpacity="0.08" />
              <text x={sx(xt)} y={H - padB + 15} fontSize="10" textAnchor="middle" fill="currentColor" opacity="0.6">{(xt * 100).toFixed(0)}%</text>
            </g>
          ))}
          {yticks.map((yt) => (
            <g key={`y${yt}`}>
              <line x1={padL} y1={sy(yt)} x2={W - padR} y2={sy(yt)} stroke="currentColor" strokeOpacity="0.08" />
              <text x={padL - 8} y={sy(yt) + 3} fontSize="10" textAnchor="end" fill="currentColor" opacity="0.6">{(yt * 100).toFixed(0)}%</text>
            </g>
          ))}
          <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} stroke="currentColor" strokeOpacity="0.45" />
          <line x1={padL} y1={padT} x2={padL} y2={H - padB} stroke="currentColor" strokeOpacity="0.45" />
          {/* frontier area fill */}
          {result.frontier.length > 1 ? (
            <polygon points={`${result.frontier.map((p) => `${sx(p.volatility)},${sy(p.expected_return)}`).join(" ")} ${sx(result.frontier[result.frontier.length - 1].volatility)},${sy(yMin)} ${sx(result.frontier[0].volatility)},${sy(yMin)}`} fill="url(#frontierArea)" />
          ) : null}
          {/* Capital Market Line */}
          {tan && tan.volatility > 0 ? (
            <line x1={sx(0)} y1={sy(rf)} x2={sx(xMax)} y2={sy(rf + ((tan.expected_return - rf) / tan.volatility) * xMax)} stroke="#0891b2" strokeWidth="1.6" strokeDasharray="6 3" opacity="0.85" />
          ) : null}
          {/* efficient frontier */}
          {result.frontier.length > 1 ? (
            <polyline points={result.frontier.map((p) => `${sx(p.volatility)},${sy(p.expected_return)}`).join(" ")} fill="none" stroke="#6366f1" strokeWidth="3" />
          ) : null}
          {/* frontier hover dots */}
          {result.frontier.map((p, i) => i % 2 === 0 ? (
            <circle key={`f${i}`} cx={sx(p.volatility)} cy={sy(p.expected_return)} r="7" fill="transparent" style={{ cursor: "crosshair" }} onMouseEnter={enter(t("portfolioOpt.frontier"), p.volatility, p.expected_return, "#6366f1")} onMouseLeave={leave} />
          ) : null)}
          {/* risk-free point */}
          <circle cx={sx(0)} cy={sy(rf)} r="4.5" fill="#0891b2" onMouseEnter={enter("Rf", 0, rf, "#0891b2")} onMouseLeave={leave} style={{ cursor: "crosshair" }} />
          <text x={sx(0) + 7} y={sy(rf) - 5} fontSize="9" fill="#0891b2">Rf</text>
          {/* assets */}
          {result.asset_points.map((a) => (
            <g key={a.asset}>
              <circle cx={sx(a.volatility)} cy={sy(a.expected_return)} r="4" fill="#94a3b8" onMouseEnter={enter(a.asset, a.volatility, a.expected_return, "#64748b")} onMouseLeave={leave} style={{ cursor: "crosshair" }} />
              <text x={sx(a.volatility) + 5} y={sy(a.expected_return) + 3} fontSize="8" fill="currentColor" opacity="0.6">{a.asset}</text>
            </g>
          ))}
          {/* profiles */}
          {profilePts.map((p) => (
            <circle key={p.name} cx={sx(p.volatility)} cy={sy(p.expected_return)} r={p.name === "custom" ? 9 : 7} fill={PROFILE_COLORS[p.name] ?? "#666"} stroke="#fff" strokeWidth="1.8" onMouseEnter={enter(p.name, p.volatility, p.expected_return, PROFILE_COLORS[p.name] ?? "#666")} onMouseLeave={leave} style={{ cursor: "pointer" }} />
          ))}
          {/* live user point — non-interactive so the custom point underneath stays hoverable */}
          {livePoint ? <circle cx={sx(livePoint.volatility)} cy={sy(livePoint.expected_return)} r="9" fill="#ec4899" fillOpacity="0.45" stroke="#ec4899" strokeWidth="2" style={{ pointerEvents: "none" }} /> : null}
          {/* tangency star */}
          {tan ? (
            <g onMouseEnter={enter(t("portfolioOpt.tangency"), tan.volatility, tan.expected_return, "#f59e0b")} onMouseLeave={leave} style={{ cursor: "pointer" }}>
              <circle cx={sx(tan.volatility)} cy={sy(tan.expected_return)} r="8" fill="none" stroke="#f59e0b" strokeWidth="1.6" />
              <text x={sx(tan.volatility)} y={sy(tan.expected_return) + 4} fontSize="13" textAnchor="middle" fill="#f59e0b" fontWeight="bold">★</text>
            </g>
          ) : null}
          <text x={(padL + W - padR) / 2} y={H - 6} fontSize="12" textAnchor="middle" fill="currentColor" opacity="0.75">{t("portfolioOpt.axisVol")}</text>
          <text x="15" y={(padT + H - padB) / 2} fontSize="12" textAnchor="middle" fill="currentColor" opacity="0.75" transform={`rotate(-90 15 ${(padT + H - padB) / 2})`}>{t("portfolioOpt.axisRet")}</text>
        </svg>
        {/* ECharts-style hover tooltip */}
        {hover ? (
          <div className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[115%] whitespace-nowrap rounded-md border bg-popover px-2.5 py-1.5 text-xs shadow-lg" style={{ left: `${hover.leftPct}%`, top: `${hover.topPct}%` }}>
            <div className="mb-0.5 flex items-center gap-1.5 font-medium"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: hover.color }} />{hover.title}</div>
            <div className="font-mono text-muted-foreground">{t("portfolioOpt.vol")}: <span className="text-foreground">{(hover.vol * 100).toFixed(2)}%</span></div>
            <div className="font-mono text-muted-foreground">{t("portfolioOpt.return")}: <span className="text-foreground">{(hover.ret * 100).toFixed(2)}%</span></div>
          </div>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-xs">
        {profilePts.map((p) => <span key={p.name} className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: PROFILE_COLORS[p.name] ?? "#666" }} />{p.name}</span>)}
        <span className="flex items-center gap-1.5"><span className="text-[#f59e0b]">★</span>{t("portfolioOpt.tangency")}</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 bg-cyan-600" />CML</span>
      </div>
    </div>
  )
}

const BASE_UNIVERSE = ["GOOG", "AAPL", "META", "AMZN", "AMD", "WMT", "BAC", "XOM", "JPM", "PFE"]

export function PortfolioOptPage() {
  const { t } = useTranslation()
  const [userPortfolio, setUserPortfolio] = useState<string>(NONE)
  const [benchPortfolio, setBenchPortfolio] = useState<string>(NONE)
  const [universe, setUniverse] = useState<string[]>(BASE_UNIVERSE)
  const [names, setNames] = useState<Record<string, string>>({})
  const [userWeights, setUserWeights] = useState<Record<string, number>>({})
  const [benchWeights, setBenchWeights] = useState<Record<string, number>>({})
  const [dataSource, setDataSource] = useState<OptimizeRequest["data_source"]>("yfinance")
  const [lookback] = useState("500")  // fallback window when no explicit date range
  const [startDate, setStartDate] = useState(() => new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10))
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [rf, setRf] = useState("0.042")
  const [wLo, setWLo] = useState("0")
  const [wHi, setWHi] = useState("0.35")
  const [returnModel, setReturnModel] = useState<OptimizeRequest["return_model"]>("historical_mean")
  const [targetReturn, setTargetReturn] = useState("")
  const [quoteSecurity, setQuoteSecurity] = useState("")
  const [quoteSource, setQuoteSource] = useState<OptimizeRequest["data_source"]>("db")
  const [quotePriceType, setQuotePriceType] = useState("CLOSE")
  const [quoteDialogOpen, setQuoteDialogOpen] = useState(false)
  const [result, setResult] = useState<OptimizeResult | null>(null)
  const [liveMetrics, setLiveMetrics] = useState<OptMetrics | null>(null)
  const [livePoint, setLivePoint] = useState<{ volatility: number; expected_return: number } | null>(null)
  const [optMethod, setOptMethod] = useState("hrp")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const portfolios = useQuery({ queryKey: ["opt-portfolios"], queryFn: () => fsiApi.listOptPortfolios().then((r) => r.data.portfolios), staleTime: 60_000 })
  const rfOptions = useQuery({ queryKey: ["opt-rf-options"], queryFn: () => fsiApi.getRiskFreeOptions().then((r) => r.data.options), staleTime: 300_000 })
  const catalog = useQuery({ queryKey: ["portfolio-opt-catalog"], queryFn: () => fsiApi.getPortfolioOptCatalog().then((r) => r.data), staleTime: 300_000, retry: 1 })

  function buildReq(): OptimizeRequest {
    return {
      universe,
      data_source: dataSource,
      lookback_days: Number(lookback) || 500,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      risk_free_rate: Number(rf) || 0.04,
      weight_bounds: [Number(wLo) || 0, Number(wHi) || 1],
      return_model: returnModel,
      target_return: targetReturn.trim() ? Number(targetReturn) : null,
      custom_weights: userWeights,
      benchmark_weights: benchWeights,
    }
  }

  async function loadPortfolio(portId: string, role: "user" | "bench") {
    if (portId === NONE) return
    try {
      const h = await fsiApi.getOptHoldings(portId).then((r) => r.data)
      if (role === "user") {
        setUniverse(h.universe); setNames(h.names); setUserWeights(h.weights)
        setLiveMetrics(null); setLivePoint(null)
      } else {
        setBenchWeights(h.weights)
      }
    } catch {
      toast.error(t("portfolioOpt.operationFailed"))
    }
  }

  // Debounced live evaluation of the user portfolio while sliders move.
  function onWeightChange(code: string, value: number) {
    const next = { ...userWeights, [code]: value }
    setUserWeights(next)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const ev = await fsiApi.evaluatePortfolio({ ...buildReq(), custom_weights: next }).then((r) => r.data)
        setLiveMetrics(ev.metrics); setLivePoint(ev.point)
      } catch { /* ignore transient */ }
    }, 450)
  }

  const analyze = useMutation({
    mutationFn: () => fsiApi.analyzePortfolio(buildReq()).then((r) => r.data),
    onSuccess: (data) => { setResult(data); setLiveMetrics(null); setLivePoint(null) },
    onError: () => {
      setResult(null)
      setLiveMetrics(null)
      setLivePoint(null)
      toast.error(t("portfolioOpt.operationFailed"))
    },
  })

  const governed = useMutation({
    mutationFn: () => fsiApi.governedOptimize({
      method: optMethod,
      fund_id: userPortfolio === NONE ? undefined : userPortfolio,
      holdings: userPortfolio === NONE ? userWeights : undefined,
      universe,
      as_of_date: endDate,
      lookback_days: Number(lookback) || 500,
      constraints: { weight_bounds: [Number(wLo) || 0, Number(wHi) || 1] },
    }).then((response) => response.data),
    onError: () => toast.error(t("portfolioOpt.operationFailed")),
  })

  const quoteUniverse = useMemo(() => {
    const merged = new Set<string>([...universe, ...(result?.universe ?? [])])
    return Array.from(merged).filter(Boolean).sort()
  }, [result?.universe, universe])

  const quoteHistoryQuery = useQuery({
    queryKey: ["portfolio-opt-quote-history", quoteSecurity, startDate, endDate, quotePriceType, quoteSource],
    queryFn: async () => fsiApi.getPortfolioQuoteHistory(quoteSecurity, startDate, endDate, quotePriceType, quoteSource).then((r) => r.data),
    enabled: Boolean(quoteSecurity && startDate && endDate && quoteDialogOpen),
    staleTime: 60_000,
  })

  const quoteRows = quoteHistoryQuery.data?.items ?? []
  const quoteSourceUsed = quoteHistoryQuery.data?.source_used ?? quoteSource
  const quotePoints = useMemo(
    () => quoteRows.map((row) => ({ date: row.price_date, value: row.close_price })),
    [quoteRows],
  )
  const quoteSummary = quoteRows.length
    ? {
        first: quoteRows[0],
        last: quoteRows[quoteRows.length - 1],
        min: Math.min(...quoteRows.map((row) => row.close_price)),
        max: Math.max(...quoteRows.map((row) => row.close_price)),
      }
    : null

  function openQuoteDialog(code: string) {
    setQuoteSecurity(code)
    setQuoteSource(dataSource)
    setQuoteDialogOpen(true)
  }

  // Real-time: debounced auto-analysis whenever any parameter or weight changes.
  const reqSignature = JSON.stringify([universe, dataSource, lookback, startDate, endDate, rf, wLo, wHi, returnModel, targetReturn, userWeights, benchWeights])
  useEffect(() => {
    if (!universe.length) return
    const timer = setTimeout(() => analyze.mutate(), 700)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqSignature])

  async function downloadChart(name: string) {
    try {
      const res = await fsiApi.optChartBlob(name, buildReq())
      const url = window.URL.createObjectURL(res.data as Blob)
      const a = document.createElement("a"); a.href = url; a.download = `${name}.png`; a.click()
      window.URL.revokeObjectURL(url)
    } catch { toast.error(t("portfolioOpt.operationFailed")) }
  }

  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current) }, [])

  useEffect(() => {
    if (!window.location.hash) return
    const target = document.getElementById(window.location.hash.slice(1))
    target?.scrollIntoView({ block: "start" })
  }, [result])

  const profileNames = result ? Object.keys(result.profiles) : []
  useBindPageContext({
    portfolio: userPortfolio === NONE ? universe.join(",") : userPortfolio,
    date: endDate,
    module: "portfolio-optimization",
    result: result ? `tangency=${result.tangency ?? ""}` : undefined,
    chart: result ? "efficient-frontier" : undefined,
    riskMetrics: liveMetrics ? { ...liveMetrics } : undefined,
  })
  const weightAssets = useMemo(() => {
    if (!result) return []
    const set = new Set<string>()
    for (const p of Object.values(result.profiles)) for (const k of Object.keys(p.weights)) if (p.weights[k] > 0.0001) set.add(k)
    return Array.from(set).sort()
  }, [result])
  const userWeightSum = Object.values(userWeights).reduce((a, b) => a + b, 0)

  return (
    <div id="overview" className="space-y-5 scroll-mt-20">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight"><PieChart className="h-6 w-6 text-primary" />{t("portfolioOpt.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("portfolioOpt.subtitle")}</p>
          <div className="mt-3">
            <AdapterStatusBar
              adapters={catalog.data?.adapters}
              engine={catalog.data?.engine}
              engineVersion={catalog.data?.engine_version}
            />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{t("portfolioOpt.notTradeInstruction")}</p>
        </div>
      </div>

      <div className="space-y-5" data-testid="platform-workbench">
          <div id="construction" className="scroll-mt-20">
          <Card id="parameters" className="scroll-mt-20 border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent" data-testid="platform-parameter">
            <CardHeader><ZoneTitle index="01" title={t("portfolioOpt.parameters")} /></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.userPortfolio")}</Label>
                  <Select value={userPortfolio} onValueChange={(v) => { setUserPortfolio(v); loadPortfolio(v, "user") }}>
                    <SelectTrigger className="h-9"><SelectValue placeholder={t("portfolioOpt.selectPortfolio")} /></SelectTrigger>
                    <SelectContent><SelectItem value={NONE}>{t("portfolioOpt.manualUniverse")}</SelectItem>{(portfolios.data ?? []).map((p) => <SelectItem key={p.port_id} value={p.port_id}>{p.port_name} · {p.port_type}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.benchmarkPortfolio")}</Label>
                  <Select value={benchPortfolio} onValueChange={(v) => { setBenchPortfolio(v); if (v === NONE) setBenchWeights({}); else loadPortfolio(v, "bench") }}>
                    <SelectTrigger className="h-9"><SelectValue placeholder={t("portfolioOpt.selectBenchmark")} /></SelectTrigger>
                    <SelectContent><SelectItem value={NONE}>{t("portfolioOpt.none")}</SelectItem>{(portfolios.data ?? []).map((p) => <SelectItem key={p.port_id} value={p.port_id}>{p.port_name} · {p.port_type}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.dataSource")}</Label>
                  <Select value={dataSource} onValueChange={(v) => setDataSource(v as OptimizeRequest["data_source"])}>
                    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="yfinance">yfinance</SelectItem><SelectItem value="openbb">OpenBB</SelectItem><SelectItem value="db">{t("portfolioOpt.srcDb")}</SelectItem></SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.returnModel")}</Label>
                  <Select value={returnModel} onValueChange={(v) => setReturnModel(v as OptimizeRequest["return_model"])}>
                    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="historical_mean">Historical Mean</SelectItem><SelectItem value="real_cagr">Real CAGR</SelectItem><SelectItem value="capm">CAPM</SelectItem><SelectItem value="black_litterman">Black-Litterman</SelectItem><SelectItem value="backtest">{t("portfolioOpt.backtestModel")}</SelectItem></SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.riskFreePreset")}</Label>
                  <Select value={rf} onValueChange={setRf}>
                    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>{(rfOptions.data ?? []).map((o) => <SelectItem key={o.key} value={String(o.value)}>{o.label} · {(o.value * 100).toFixed(2)}%</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.riskFree")}</Label>
                  <div className="flex items-center gap-1">
                    <Button type="button" variant="outline" size="icon" className="h-9 w-9 shrink-0" onClick={() => setRf((Math.max(0, (Number(rf) || 0) - 0.0025)).toFixed(4))}>−</Button>
                    <Input className="h-9 text-center" type="number" step="0.0025" value={rf} onChange={(e) => setRf(e.target.value)} />
                    <Button type="button" variant="outline" size="icon" className="h-9 w-9 shrink-0" onClick={() => setRf(((Number(rf) || 0) + 0.0025).toFixed(4))}>+</Button>
                  </div>
                </div>
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.startDate")}</Label><DatePicker className="h-9 w-full" value={startDate} onChange={(next) => { setStartDate(next); if (next > endDate) setEndDate(next) }} /></div>
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.endDate")}</Label><DatePicker className="h-9 w-full" value={endDate} onChange={(next) => { setEndDate(next); if (next < startDate) setStartDate(next) }} /></div>
                <div id="constraints" className="grid scroll-mt-20 grid-cols-2 gap-2"><div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.weightMin")}</Label><Input className="h-9" type="number" step="0.05" value={wLo} onChange={(e) => setWLo(e.target.value)} /></div><div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.weightMax")}</Label><Input className="h-9" type="number" step="0.05" value={wHi} onChange={(e) => setWHi(e.target.value)} /></div></div>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                {userPortfolio === NONE ? (
                  <div className="min-w-[14rem] flex-1 space-y-1"><Label className="text-xs">{t("portfolioOpt.universe")}</Label>
                    <Textarea rows={1} className="min-h-9 py-2" value={universe.join(", ")} onChange={(e) => { const u = e.target.value.split(/[\n,\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean); setUniverse(u); setUserWeights(Object.fromEntries(u.map((c) => [c, 1 / (u.length || 1)]))) }} />
                  </div>
                ) : null}
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.targetReturn")}</Label>
                  <Input className="h-9 w-28" type="number" step="0.01" placeholder={t("portfolioOpt.targetReturnPh")} value={targetReturn} onChange={(e) => setTargetReturn(e.target.value)} title={t("portfolioOpt.targetReturnHint")} />
                </div>
                <span className="mb-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Play className={`h-3.5 w-3.5 ${analyze.isPending ? "animate-pulse text-primary" : ""}`} />
                  {analyze.isPending ? t("portfolioOpt.autoUpdating") : t("portfolioOpt.autoLive")}
                </span>
              </div>
            </CardContent>
          </Card>
          </div>

          <Card id="optimization-gate" className="scroll-mt-20">
            <CardHeader>
              <ZoneTitle
                index="01b"
                title={t("portfolioOpt.governedTitle")}
                detail={t("portfolioOpt.governedHint")}
                action={<Button size="sm" onClick={() => governed.mutate()} disabled={governed.isPending}><Play className="mr-1 h-4 w-4" />{t("portfolioOpt.runGoverned")}</Button>}
              />
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="space-y-1">
                  <Label className="text-xs">{t("portfolioOpt.riskfolioMethod")}</Label>
                  <Select value={optMethod} onValueChange={setOptMethod}>
                    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {(catalog.data?.methods ?? ["hrp", "risk_parity", "cvar", "black_litterman", "herc"]).map((method) => (
                        <SelectItem key={method} value={method}>{method}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="rounded-lg border bg-muted/30 p-3 text-xs">
                  {t("portfolioOpt.notTradeInstruction")}
                  {governed.data ? ` · ${governed.data.status ?? "PROPOSAL"}` : ""}
                </div>
              </div>
              {governed.data ? (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(governed.data.gate_status ?? {}).map(([gate, passed]) => (
                    <div key={gate} className="rounded-md border px-3 py-2 text-xs">
                      <span className="font-medium">{gate}</span>
                      <span className={passed ? "ml-2 text-emerald-600" : "ml-2 text-destructive"}>{passed ? "PASS" : "HOLD"}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="grid items-stretch gap-5 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <div id="simulation" className="scroll-mt-20">
          <Card id="user-weights" className="flex scroll-mt-20 flex-col">
            <CardHeader><ZoneTitle index="02" title={t("portfolioOpt.userWeights")} detail={t("portfolioOpt.weightHint", { sum: (userWeightSum * 100).toFixed(0) })} /></CardHeader>
            <CardContent className="flex flex-1 flex-col gap-3">
              {(() => {
                const um = liveMetrics ?? result?.profiles?.custom?.metrics ?? null
                return (
                  <div className="grid shrink-0 grid-cols-3 gap-2 rounded-lg border bg-muted/30 p-3 text-xs">
                    <div>{t("portfolioOpt.return")}: <span className="font-mono">{um ? pct(um.expected_return) : "—"}</span></div>
                    <div>{t("portfolioOpt.vol")}: <span className="font-mono">{um ? pct(um.volatility) : "—"}</span></div>
                    <div>{t("portfolioOpt.sharpe")}: <span className="font-mono">{um ? num(um.sharpe) : "—"}</span></div>
                    <div>{t("portfolioOpt.mdd")}: <span className="font-mono text-destructive">{um ? pct(um.max_drawdown) : "—"}</span></div>
                    <div>VaR95: <span className="font-mono">{um ? pct(um.var_95) : "—"}</span></div>
                    <div>CVaR95: <span className="font-mono">{um ? pct(um.cvar_95) : "—"}</span></div>
                  </div>
                )
              })()}
              <div className="grid min-h-[8rem] flex-1 content-start gap-2.5 overflow-y-auto overflow-x-hidden pr-1">
                {universe.map((code) => {
                  const raw = userWeights[code] ?? 0
                  const normalized = userWeightSum > 0 ? raw / userWeightSum : 0
                  return (
                    <div key={code} className="min-w-0 space-y-1 border-b pb-1.5 last:border-0">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <div className="flex min-w-0 items-center gap-1.5 truncate">
                          <Button type="button" variant="ghost" size="sm" className="h-6 gap-1 px-1.5 font-normal" onClick={() => openQuoteDialog(code)} title={t("portfolioOpt.quoteOpen")}>
                            <LineChart className="h-3.5 w-3.5" />
                            <span className="font-mono">{code}</span>
                          </Button>
                          {names[code] && names[code] !== code ? <span className="truncate text-muted-foreground" title={names[code]}>{names[code]}</span> : null}
                        </div>
                        <span className="shrink-0 font-mono text-primary" title={t("portfolioOpt.normalized")}>≈{(normalized * 100).toFixed(1)}%</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <input type="range" min={0} max={1} step={0.01} value={raw} onChange={(e) => onWeightChange(code, Number(e.target.value))} className="h-2 min-w-0 flex-1 cursor-pointer accent-pink-500" />
                        <Button type="button" variant="outline" size="icon" className="h-6 w-6 shrink-0" onClick={() => onWeightChange(code, Math.max(0, Number((raw - 0.05).toFixed(4))))}>−</Button>
                        <span className="w-9 shrink-0 text-center font-mono text-xs">{(raw * 100).toFixed(0)}%</span>
                        <Button type="button" variant="outline" size="icon" className="h-6 w-6 shrink-0" onClick={() => onWeightChange(code, Math.min(1, Number((raw + 0.05).toFixed(4))))}>+</Button>
                        <Button type="button" variant="ghost" size="icon" className="h-6 w-6 shrink-0" onClick={() => openQuoteDialog(code)} title={t("portfolioOpt.quoteOpen")}>
                          <LineChart className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>
          </div>
          <Card className="flex flex-col">
            <CardHeader><ZoneTitle index="03" title={t("portfolioOpt.frontier")} detail={t("portfolioOpt.frontierLiveHint")} action={result ? <Button size="sm" variant="ghost" onClick={() => downloadChart("efficient_frontier")}><Download className="mr-1 h-4 w-4" />PNG</Button> : undefined} /></CardHeader>
            <CardContent className="flex flex-1 items-center">
              {result ? <div className="w-full"><FrontierScatter result={result} livePoint={livePoint} /></div> : <div className="flex h-80 w-full items-center justify-center text-sm text-muted-foreground">{t("portfolioOpt.runPrompt")}</div>}
            </CardContent>
          </Card>
          </div>

          {result ? (
            <>
              <Card id="return-models" className="scroll-mt-20">
                <CardHeader><ZoneTitle index="04" title={t("portfolioOpt.returnModels")}
                  action={<Button size="sm" variant="outline" onClick={() => exportCsv("individual_assets_return_models.csv", ["asset", "historical_mean", "real_cagr", "capm", "black_litterman", "period_total_return"], result.return_models.map((r) => [r.asset, r.historical_mean, r.real_cagr, r.capm, r.black_litterman, r.period_total_return]))}><Download className="mr-1 h-4 w-4" />CSV</Button>} />
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <Table><TableHeader><TableRow>
                    <TableHead>{t("portfolioOpt.asset")}</TableHead><TableHead className="text-right">Hist. Mean</TableHead><TableHead className="text-right">Real CAGR</TableHead><TableHead className="text-right">CAPM</TableHead><TableHead className="text-right">Black-Litterman</TableHead><TableHead className="text-right">{t("portfolioOpt.periodReturn")}</TableHead>
                  </TableRow></TableHeader><TableBody>
                    {result.return_models.map((r) => <TableRow key={r.asset}><TableCell className="font-mono text-xs">{r.asset}</TableCell><TableCell className="text-right font-mono">{pct(r.historical_mean)}</TableCell><TableCell className="text-right font-mono">{pct(r.real_cagr)}</TableCell><TableCell className="text-right font-mono">{pct(r.capm)}</TableCell><TableCell className="text-right font-mono">{pct(r.black_litterman)}</TableCell><TableCell className="text-right font-mono">{pct(r.period_total_return)}</TableCell></TableRow>)}
                  </TableBody></Table>
                </CardContent>
              </Card>

              <Card id="asset-metrics" className="scroll-mt-20">
                <CardHeader><ZoneTitle index="05" title={t("portfolioOpt.assetMetrics")}
                  action={<Button size="sm" variant="outline" onClick={() => exportCsv("individual_assets_metrics.csv", ["asset", "expected_return", "volatility", "sharpe", "max_drawdown", "var_95", "cvar_95"], result.asset_metrics.map((r) => [r.asset, r.expected_return, r.volatility, r.sharpe, r.max_drawdown, r.var_95, r.cvar_95]))}><Download className="mr-1 h-4 w-4" />CSV</Button>} />
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <Table><TableHeader><TableRow>
                    <TableHead>{t("portfolioOpt.asset")}</TableHead><TableHead className="text-right">{t("portfolioOpt.return")}</TableHead><TableHead className="text-right">{t("portfolioOpt.vol")}</TableHead><TableHead className="text-right">{t("portfolioOpt.sharpe")}</TableHead><TableHead className="text-right">{t("portfolioOpt.mdd")}</TableHead><TableHead className="text-right">VaR95</TableHead><TableHead className="text-right">CVaR95</TableHead>
                  </TableRow></TableHeader><TableBody>
                    {result.asset_metrics.map((r) => <TableRow key={r.asset}><TableCell className="font-mono text-xs">{r.asset}</TableCell><TableCell className="text-right font-mono">{pct(r.expected_return)}</TableCell><TableCell className="text-right font-mono">{pct(r.volatility)}</TableCell><TableCell className="text-right font-mono">{num(r.sharpe)}</TableCell><TableCell className="text-right font-mono text-destructive">{pct(r.max_drawdown)}</TableCell><TableCell className="text-right font-mono">{pct(r.var_95)}</TableCell><TableCell className="text-right font-mono">{pct(r.cvar_95)}</TableCell></TableRow>)}
                  </TableBody></Table>
                </CardContent>
              </Card>

              <div id="optimization" className="scroll-mt-20">
              <Card id="portfolios" className="scroll-mt-20" data-testid="platform-data">
                <CardHeader><ZoneTitle index="06" title={t("portfolioOpt.portfolios")}
                  action={<Button size="sm" variant="outline" onClick={() => exportCsv("portfolio_profiles_weights.csv", ["asset", ...profileNames], weightAssets.map((a) => [a, ...profileNames.map((p) => result.profiles[p].weights[a] ?? 0)]))}><Download className="mr-1 h-4 w-4" />CSV</Button>} />
                </CardHeader>
                <CardContent className="space-y-4 overflow-x-auto">
                  <Table><TableHeader><TableRow><TableHead>{t("portfolioOpt.metric")}</TableHead>{profileNames.map((p) => <TableHead key={p} className="text-right capitalize">{p}</TableHead>)}</TableRow></TableHeader><TableBody>
                    {([["expected_return", t("portfolioOpt.return"), pct], ["volatility", t("portfolioOpt.vol"), pct], ["sharpe", t("portfolioOpt.sharpe"), num], ["max_drawdown", t("portfolioOpt.mdd"), pct], ["var_95", "VaR95", pct], ["cvar_95", "CVaR95", pct]] as const).map(([key, label, fmt]) => (
                      <TableRow key={key}><TableCell>{label}</TableCell>{profileNames.map((p) => <TableCell key={p} className="text-right font-mono">{fmt((result.profiles[p].metrics as unknown as Record<string, number>)[key])}</TableCell>)}</TableRow>
                    ))}
                  </TableBody></Table>
                  {result.efficiency ? (
                    <div className="rounded-lg border bg-muted/30 p-3 text-sm"><div className="mb-1 font-medium">{t("portfolioOpt.diagnosis")}</div><div className="flex flex-wrap gap-6 text-xs"><span>{t("portfolioOpt.alphaLoss")}: <span className="font-mono text-emerald-600">{pct(result.efficiency.alpha_loss)}</span></span><span>{t("portfolioOpt.excessVol")}: <span className="font-mono text-destructive">{pct(result.efficiency.excess_vol)}</span></span></div></div>
                  ) : null}
                </CardContent>
              </Card>
              </div>

              <div id="comparison" className="scroll-mt-20">
              <Card id="charts" className="scroll-mt-20" data-testid="platform-charts">
                <CardHeader><ZoneTitle index="07" title={t("portfolioOpt.charts")} detail={t("portfolioOpt.chartsHint")} /></CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <div className="mb-1 flex items-center justify-between"><span className="text-sm font-medium">{t("portfolioOpt.heatmap")}</span><Button size="sm" variant="ghost" onClick={() => downloadChart("covariance_heatmap")}><Download className="mr-1 h-4 w-4" />PNG</Button></div>
                    <p className="mb-2 text-xs text-muted-foreground">{t("portfolioOpt.heatmapMeaning")}</p>
                    <CorrelationHeatmap assets={result.correlation.assets} matrix={result.correlation.matrix} />
                  </div>
                  <div>
                    <div className="mb-2 flex items-center justify-between"><span className="text-sm font-medium">{t("portfolioOpt.allocation")}</span><Button size="sm" variant="ghost" onClick={() => downloadChart("asset_allocation")}><Download className="mr-1 h-4 w-4" />PNG</Button></div>
                    <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>{t("portfolioOpt.asset")}</TableHead>{profileNames.map((p) => <TableHead key={p} className="text-right capitalize">{p}</TableHead>)}</TableRow></TableHeader><TableBody>
                      {weightAssets.map((a) => <TableRow key={a}><TableCell className="font-mono text-xs">{a}</TableCell>{profileNames.map((p) => <TableCell key={p} className="text-right font-mono">{pct(result.profiles[p].weights[a] ?? 0, 1)}</TableCell>)}</TableRow>)}
                    </TableBody></Table></div>
                  </div>
                </CardContent>
              </Card>
              </div>
              <Card id="validation" className="scroll-mt-20">
                <CardHeader><ZoneTitle index="08" title={t("nav.portfolioValidation")} /></CardHeader>
                <CardContent className="text-sm text-muted-foreground" data-testid="platform-engine-note">
                  {t("platform.engineNote")}
                  {result.efficiency ? (
                    <div className="mt-2 flex flex-wrap gap-6 text-xs">
                      <span>{t("portfolioOpt.alphaLoss")}: <span className="font-mono">{pct(result.efficiency.alpha_loss)}</span></span>
                      <span>{t("portfolioOpt.excessVol")}: <span className="font-mono">{pct(result.efficiency.excess_vol)}</span></span>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </>
          ) : (
            <Card><CardContent className="py-16 text-center text-sm text-muted-foreground">{t("portfolioOpt.runPrompt")}</CardContent></Card>
          )}
      </div>
      <Dialog open={quoteDialogOpen} onOpenChange={setQuoteDialogOpen}>
        <DialogContent className="w-[96vw] max-w-6xl p-0">
          <div className="flex h-[86vh] min-h-[42rem] flex-col overflow-hidden">
            <DialogHeader className="shrink-0 border-b px-6 py-4 pr-12">
            <DialogTitle className="flex items-center gap-2">
              <LineChart className="h-4 w-4 text-primary" />
              {t("portfolioOpt.quoteTrace")}
            </DialogTitle>
            <DialogDescription>
              {quoteSecurity} · {t("portfolioOpt.quoteTraceHint")}
            </DialogDescription>
            </DialogHeader>
            <div className="w-full flex-1 space-y-4 overflow-y-auto px-6 py-4">
            <div className="grid w-full gap-3 lg:grid-cols-[minmax(0,1.5fr)_10rem_10rem]">
              <div className="space-y-1">
                <Label className="text-xs">{t("portfolioOpt.quoteSecurity")}</Label>
                <Input
                  className="h-9"
                  list="portfolio-opt-security-codes-dialog"
                  placeholder={t("portfolioOpt.quoteSecurityPh")}
                  value={quoteSecurity}
                  onChange={(e) => setQuoteSecurity(e.target.value.trim().toUpperCase())}
                />
                <datalist id="portfolio-opt-security-codes-dialog">
                  {quoteUniverse.map((code) => <option key={`dlg-${code}`} value={code} />)}
                </datalist>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("portfolioOpt.quotePriceType")}</Label>
                <Select value={quotePriceType} onValueChange={setQuotePriceType}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="OPEN">OPEN</SelectItem>
                    <SelectItem value="HIGH">HIGH</SelectItem>
                    <SelectItem value="LOW">LOW</SelectItem>
                    <SelectItem value="CLOSE">CLOSE</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("portfolioOpt.quoteSource")}</Label>
                <Select value={quoteSource} onValueChange={(v) => setQuoteSource(v as OptimizeRequest["data_source"]) }>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="db">db</SelectItem>
                    <SelectItem value="yfinance">yfinance</SelectItem>
                    <SelectItem value="openbb">openbb</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="w-full rounded-lg border bg-muted/30 p-3 text-xs">
              <div className="text-muted-foreground">{t("portfolioOpt.quoteRange")}</div>
              <div className="font-mono">{startDate || "—"} → {endDate || "—"}</div>
              <div className="text-muted-foreground">{t("portfolioOpt.quoteSourceCol")}: <span className="font-mono">{quoteSourceUsed.toUpperCase()}</span></div>
            </div>
            {quoteHistoryQuery.isFetching ? <div className="text-xs text-muted-foreground">{t("portfolioOpt.quoteLoading")}</div> : null}
            {quoteHistoryQuery.isError ? <div className="text-xs text-destructive">{t("portfolioOpt.quoteFailed")}</div> : null}
            {quoteSummary ? (
              <div className="grid w-full gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-lg border bg-muted/20 p-3 text-xs"><div className="text-muted-foreground">{t("portfolioOpt.quoteFirst")}</div><div className="font-mono">{quoteSummary.first.price_date}</div><div className="font-mono">{quoteSummary.first.close_price.toFixed(4)}</div></div>
                <div className="rounded-lg border bg-muted/20 p-3 text-xs"><div className="text-muted-foreground">{t("portfolioOpt.quoteLast")}</div><div className="font-mono">{quoteSummary.last.price_date}</div><div className="font-mono">{quoteSummary.last.close_price.toFixed(4)}</div></div>
                <div className="rounded-lg border bg-muted/20 p-3 text-xs"><div className="text-muted-foreground">{t("portfolioOpt.quoteMin")}</div><div className="font-mono">{quoteSummary.min.toFixed(4)}</div></div>
                <div className="rounded-lg border bg-muted/20 p-3 text-xs"><div className="text-muted-foreground">{t("portfolioOpt.quoteMax")}</div><div className="font-mono">{quoteSummary.max.toFixed(4)}</div></div>
              </div>
            ) : null}
            <div className="w-full rounded-lg border bg-background/70 p-3">
              {quotePoints.length ? (
                <MarketQuoteSparkline
                  points={quotePoints}
                  noDataText={t("portfolioOpt.quoteEmpty")}
                  xAxisLabel={t("portfolioOpt.quoteDate")}
                  yAxisLabel={t("dataManagement.unitPrice")}
                />
              ) : <div className="flex h-64 items-center justify-center text-xs text-muted-foreground">{t("portfolioOpt.quoteEmpty")}</div>}
            </div>
            <div className="w-full min-h-0 overflow-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("portfolioOpt.quoteDate")}</TableHead>
                    <TableHead className="text-right">Open</TableHead>
                    <TableHead className="text-right">High</TableHead>
                    <TableHead className="text-right">Low</TableHead>
                    <TableHead className="text-right">Close</TableHead>
                    <TableHead className="text-right">Vol</TableHead>
                    <TableHead className="text-right">Turnover</TableHead>
                    <TableHead>{t("portfolioOpt.quoteSourceCol")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {quoteRows.map((row: MarketQuote) => (
                    <TableRow key={`${row.price_date}-${row.security_code}-${row.price_type}`}>
                      <TableCell className="font-mono text-xs">{row.price_date}</TableCell>
                      <TableCell className="text-right font-mono">{row.open_price == null ? "—" : row.open_price.toFixed(4)}</TableCell>
                      <TableCell className="text-right font-mono">{row.high_price == null ? "—" : row.high_price.toFixed(4)}</TableCell>
                      <TableCell className="text-right font-mono">{row.low_price == null ? "—" : row.low_price.toFixed(4)}</TableCell>
                      <TableCell className="text-right font-mono">{row.close_price.toFixed(4)}</TableCell>
                      <TableCell className="text-right font-mono">{row.volume == null ? "—" : Number(row.volume).toLocaleString()}</TableCell>
                      <TableCell className="text-right font-mono">{row.turnover == null ? "—" : Number(row.turnover).toLocaleString()}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{row.data_source}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

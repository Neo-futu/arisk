import { useMutation, useQuery } from "@tanstack/react-query"
import { Download, PieChart, Play } from "lucide-react"
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { FloatingAiChat } from "@/components/FloatingAiChat"
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
} from "@/fsiClient"
import { exportCsv } from "@/modules/investment-risk/dashboard-kit"

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
  const [startDate, setStartDate] = useState(() => new Date(Date.now() - 730 * 864e5).toISOString().slice(0, 10))
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [rf, setRf] = useState("0.042")
  const [wLo, setWLo] = useState("0")
  const [wHi, setWHi] = useState("0.35")
  const [returnModel, setReturnModel] = useState<OptimizeRequest["return_model"]>("historical_mean")
  const [targetReturn, setTargetReturn] = useState("")
  const [result, setResult] = useState<OptimizeResult | null>(null)
  const [liveMetrics, setLiveMetrics] = useState<OptMetrics | null>(null)
  const [livePoint, setLivePoint] = useState<{ volatility: number; expected_return: number } | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const portfolios = useQuery({ queryKey: ["opt-portfolios"], queryFn: () => fsiApi.listOptPortfolios().then((r) => r.data.portfolios), staleTime: 60_000 })
  const rfOptions = useQuery({ queryKey: ["opt-rf-options"], queryFn: () => fsiApi.getRiskFreeOptions().then((r) => r.data.options), staleTime: 300_000 })

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
    onError: () => toast.error(t("portfolioOpt.operationFailed")),
  })

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

  const profileNames = result ? Object.keys(result.profiles) : []
  const weightAssets = useMemo(() => {
    if (!result) return []
    const set = new Set<string>()
    for (const p of Object.values(result.profiles)) for (const k of Object.keys(p.weights)) if (p.weights[k] > 0.0001) set.add(k)
    return Array.from(set).sort()
  }, [result])
  const userWeightSum = Object.values(userWeights).reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight"><PieChart className="h-6 w-6 text-primary" />{t("portfolioOpt.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("portfolioOpt.subtitle")}</p>
        </div>
      </div>

      <div className="space-y-5">
          <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
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
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.startDate")}</Label><Input className="h-9" type="date" value={startDate} max={endDate} onChange={(e) => setStartDate(e.target.value)} /></div>
                <div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.endDate")}</Label><Input className="h-9" type="date" value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-2"><div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.weightMin")}</Label><Input className="h-9" type="number" step="0.05" value={wLo} onChange={(e) => setWLo(e.target.value)} /></div><div className="space-y-1"><Label className="text-xs">{t("portfolioOpt.weightMax")}</Label><Input className="h-9" type="number" step="0.05" value={wHi} onChange={(e) => setWHi(e.target.value)} /></div></div>
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

          <div className="grid items-stretch gap-5 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <Card className="flex flex-col">
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
                        <span className="min-w-0 truncate" title={names[code] ?? code}><span className="font-mono">{code}</span>{names[code] && names[code] !== code ? <span className="ml-1 text-muted-foreground">{names[code]}</span> : null}</span>
                        <span className="shrink-0 font-mono text-primary" title={t("portfolioOpt.normalized")}>≈{(normalized * 100).toFixed(1)}%</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <input type="range" min={0} max={1} step={0.01} value={raw} onChange={(e) => onWeightChange(code, Number(e.target.value))} className="h-2 min-w-0 flex-1 cursor-pointer accent-pink-500" />
                        <Button type="button" variant="outline" size="icon" className="h-6 w-6 shrink-0" onClick={() => onWeightChange(code, Math.max(0, Number((raw - 0.05).toFixed(4))))}>−</Button>
                        <span className="w-9 shrink-0 text-center font-mono text-xs">{(raw * 100).toFixed(0)}%</span>
                        <Button type="button" variant="outline" size="icon" className="h-6 w-6 shrink-0" onClick={() => onWeightChange(code, Math.min(1, Number((raw + 0.05).toFixed(4))))}>+</Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>
          <Card className="flex flex-col">
            <CardHeader><ZoneTitle index="03" title={t("portfolioOpt.frontier")} detail={t("portfolioOpt.frontierLiveHint")} action={result ? <Button size="sm" variant="ghost" onClick={() => downloadChart("efficient_frontier")}><Download className="mr-1 h-4 w-4" />PNG</Button> : undefined} /></CardHeader>
            <CardContent className="flex flex-1 items-center">
              {result ? <div className="w-full"><FrontierScatter result={result} livePoint={livePoint} /></div> : <div className="flex h-80 w-full items-center justify-center text-sm text-muted-foreground">{t("portfolioOpt.runPrompt")}</div>}
            </CardContent>
          </Card>
          </div>

          {result ? (
            <>
              <Card>
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

              <Card>
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

              <Card>
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

              <Card>
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
            </>
          ) : (
            <Card><CardContent className="py-16 text-center text-sm text-muted-foreground">{t("portfolioOpt.runPrompt")}</CardContent></Card>
          )}
      </div>
      <FloatingAiChat
        title={t("portfolioOpt.aiArea")}
        hint={t("portfolioOpt.aiHint")}
        placeholder={t("portfolioOpt.aiPlaceholder")}
        buildPrompt={(q) => [
          "你正在 ARISK 组合优化模块协助投资经理解读有效前沿/CML/Black-Litterman/HRP 结果。",
          "以下是当前分析摘要（只作分析，不得杜撰数据）：",
          JSON.stringify(result ? { universe: result.universe, return_model: result.return_model, risk_free_rate: result.risk_free_rate, tangency: result.tangency, profiles: Object.fromEntries(Object.entries(result.profiles).map(([k, v]) => [k, v.metrics])), efficiency: result.efficiency } : null),
          `用户问题：${q}`,
        ].join("\n")}
      />
    </div>
  )
}

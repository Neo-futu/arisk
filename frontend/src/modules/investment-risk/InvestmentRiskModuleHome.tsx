import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowRight,
  BrainCircuit,
  Database,
  Download,
  Filter,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Workflow,
} from "lucide-react"
import { useMemo, useState } from "react"

import { FUNDS, lastTradeDate } from "@/components/FsiToolbar"
import { DatePicker } from "@/components/DatePicker"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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
import { fsiApi, type PortfolioOverviewResult } from "@/fsiClient"
import { INVESTMENT_RISK_TOPICS, type InvestmentRiskTopic } from "@/modules/investment-risk/content"

const integrationItems = [
  {
    title: "2_processing（計算引擎層）",
    description: "新增 inv-risk 專屬 API 路由，承載敏感度、壓測、風險預算等高頻計算任務。",
    icon: Workflow,
  },
  {
    title: "1_datastorage（存儲層）",
    description: "擴充敏感度快照、壓測結果與因子暴露時序表，支持歷史回溯與審計。",
    icon: Database,
  },
  {
    title: "5_deploy & 4_mcp（Agent 擴展層）",
    description: "部署 InvestmentRisk Subagent，將自然語言指令自動編排為底層風險計算鏈路。",
    icon: BrainCircuit,
  },
]

const riskTrend = [62, 68, 71, 66, 74, 81, 78]
const exposureMix = [
  { label: "利率", value: 74 },
  { label: "信用", value: 61 },
  { label: "流動性", value: 58 },
  { label: "因子", value: 49 },
]

const riskItems = [
  {
    id: "R-1021",
    name: "美元債信用利差擴張",
    bucket: "信用",
    severity: "高",
    score: 82,
    status: "需要加強監控",
    updatedAt: "2026-08-02",
  },
  {
    id: "R-1038",
    name: "流動性覆蓋比下降",
    bucket: "流動性",
    severity: "中",
    score: 67,
    status: "保持觀察",
    updatedAt: "2026-08-01",
  },
  {
    id: "R-1042",
    name: "利率曲線陡度飄移",
    bucket: "利率",
    severity: "高",
    score: 79,
    status: "即時提醒",
    updatedAt: "2026-08-02",
  },
  {
    id: "R-1051",
    name: "擁擠度上升與風格漂移",
    bucket: "因子",
    severity: "中",
    score: 61,
    status: "可接受",
    updatedAt: "2026-07-31",
  },
]

function shiftDate(dateText: string, offsetDays: number) {
  const date = new Date(`${dateText}T00:00:00`)
  date.setDate(date.getDate() + offsetDays)
  return date.toISOString().split("T")[0]
}

function hasOverviewData(data: PortfolioOverviewResult) {
  return (
    !!data.portfolio?.data_date
    && (data.asset_allocation.length > 0 || data.top_stocks.length > 0 || data.performance.length > 0)
  )
}

async function loadOverviewWithFallback(fundId: string, selectedDate: string, lookbackDays = 365) {
  for (let step = 0; step <= lookbackDays; step += 1) {
    const probeDate = shiftDate(selectedDate, -step)
    const response = await fsiApi.getPortfolioOverview(fundId, probeDate)
    if (hasOverviewData(response.data)) {
      return {
        payload: response.data,
        effectiveDate: probeDate,
        fallbackUsed: step > 0,
      }
    }
  }
  throw new Error("在回溯區間內未找到可用數據")
}

function money(value: number | null | undefined, currency = "HKD") {
  if (value == null) return "—"
  return new Intl.NumberFormat("zh-HK", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value))
}

function percent(value: number | null | undefined, digits = 2) {
  if (value == null) return "—"
  return `${Number(value).toFixed(digits)}%`
}

function buildLinePath(values: number[]) {
  const width = 360
  const height = 170
  const maxValue = Math.max(...values)
  const minValue = Math.min(...values)
  const range = maxValue - minValue || 1

  return values
    .map((value, index) => {
      const x = 20 + (index / (values.length - 1)) * (width - 40)
      const normalized = (value - minValue) / range
      const y = height - 30 - normalized * (height - 60)
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
}

export function InvestmentRiskModuleHome() {
  const [selectedTopic, setSelectedTopic] = useState<InvestmentRiskTopic["id"]>(INVESTMENT_RISK_TOPICS[0].id)
  const [selectedFundId, setSelectedFundId] = useState(FUNDS[0].id)
  const [analysisDate, setAnalysisDate] = useState(lastTradeDate)
  const [searchQuery, setSearchQuery] = useState("")
  const [severityFilter, setSeverityFilter] = useState("全部")
  const [timeWindow, setTimeWindow] = useState("30D")

  const selectedTopicMeta = INVESTMENT_RISK_TOPICS.find((topic) => topic.id === selectedTopic) ?? INVESTMENT_RISK_TOPICS[0]
  const dashboardQuery = useQuery({
    queryKey: ["investment-home-dashboard", selectedFundId, analysisDate],
    queryFn: () => loadOverviewWithFallback(selectedFundId, analysisDate),
    retry: 0,
  })

  const dashboardData = dashboardQuery.data?.payload
  const effectiveDate = dashboardQuery.data?.effectiveDate ?? analysisDate
  const fallbackUsed = dashboardQuery.data?.fallbackUsed ?? false

  const trendValues = useMemo(() => {
    const values = dashboardData?.performance.map((item) => item.return_pct) ?? []
    return values.length > 1 ? values : riskTrend
  }, [dashboardData?.performance])

  const trendLabels = useMemo(() => {
    const labels = dashboardData?.performance.map((item) => item.period) ?? []
    return labels.length > 1 ? labels : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
  }, [dashboardData?.performance])

  const exposureMixData = useMemo(() => {
    const items = (dashboardData?.asset_allocation ?? [])
      .slice(0, 4)
      .map((item) => ({ label: item.asset_class, value: Math.max(0, Math.min(100, item.weight_pct)) }))
    return items.length ? items : exposureMix
  }, [dashboardData?.asset_allocation])

  const dashboardRows = useMemo(() => {
    const dataDate = dashboardData?.portfolio.data_date ?? effectiveDate
    const top3Concentration = (dashboardData?.top_stocks ?? []).slice(0, 3).reduce((sum, item) => sum + item.weight_pct, 0)
    const dayReturnPct = dashboardData?.portfolio.day_return == null ? null : Number(dashboardData.portfolio.day_return) * 100
    return [
      {
        metric: `淨資產（${dataDate}）`,
        value: money(dashboardData?.portfolio.net_asset, dashboardData?.portfolio.base_currency ?? "HKD"),
        status: dashboardData ? "已更新" : "—",
      },
      {
        metric: "當日收益",
        value: percent(dayReturnPct, 3),
        status: dayReturnPct != null && dayReturnPct < 0 ? "波動" : "穩定",
      },
      {
        metric: "前3重倉集中度",
        value: percent(top3Concentration, 2),
        status: top3Concentration > 35 ? "待關注" : "正常",
      },
    ]
  }, [dashboardData, effectiveDate])

  const filteredItems = useMemo(() => {
    return riskItems.filter((item) => {
      const matchesSearch = `${item.id} ${item.name} ${item.bucket}`.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesSeverity = severityFilter === "全部" || item.severity === severityFilter
      return matchesSearch && matchesSeverity
    })
  }, [searchQuery, severityFilter])

  function handleExport() {
    const header = ["風險ID", "名稱", "類別", "等級", "分數", "狀態", "更新日"]
    const body = filteredItems.map((item) => [item.id, item.name, item.bucket, item.severity, item.score, item.status, item.updatedAt])
    const csv = [header, ...body]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
      .join("\n")

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `investment-risk-${timeWindow}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline">獨立模塊</Badge>
          <Badge variant="secondary">Investment Risk</Badge>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">投資風險模塊</h1>
        <p className="max-w-4xl text-sm text-muted-foreground">
          將 ARISK 覆蓋範圍從中後台合規風控延伸到前中台投資決策支持。這個頁面已整合儀表盤、圖表視覺化與可檢索的審查表格，支援實戰式風控分析流程。
        </p>
      </div>

      <Card className="border-primary/20 bg-gradient-to-br from-background to-primary/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" />
            實戰風控儀表盤
          </CardTitle>
          <CardDescription>覆蓋實時風險暴露、壓力情境與交易前置限額的雙視圖分析入口。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <Select value={selectedFundId} onValueChange={setSelectedFundId}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="選擇基金" />
              </SelectTrigger>
              <SelectContent>
                {FUNDS.map((fund) => (
                  <SelectItem key={fund.id} value={fund.id}>
                    {fund.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DatePicker value={analysisDate} onChange={setAnalysisDate} />
            <Badge variant="outline">實際數據日：{effectiveDate}</Badge>
            {fallbackUsed ? <Badge variant="secondary">已自動回退到最近有數據日</Badge> : null}
          </div>
          {dashboardQuery.isFetching ? <p className="text-sm text-muted-foreground">正在載入最新可用數據...</p> : null}
          {dashboardQuery.isError ? <p className="text-sm text-destructive">無法載入該基金近一年可用數據，請切換基金或日期。</p> : null}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border bg-background/80 p-4">
              <p className="text-xs text-muted-foreground">當前風險暴露</p>
              <p className="mt-2 text-2xl font-semibold">{percent((dashboardData?.asset_allocation ?? []).slice(0, 2).reduce((sum, item) => sum + item.weight_pct, 0), 2)}</p>
              <p className="mt-1 text-xs text-emerald-600">前兩大資產類別權重合計</p>
            </div>
            <div className="rounded-lg border bg-background/80 p-4">
              <p className="text-xs text-muted-foreground">壓力測試覆蓋</p>
              <p className="mt-2 text-2xl font-semibold">{dashboardData?.performance.length ?? 0}</p>
              <p className="mt-1 text-xs text-muted-foreground">已加載業績區間數</p>
            </div>
            <div className="rounded-lg border bg-background/80 p-4">
              <p className="text-xs text-muted-foreground">可用交易預算</p>
              <p className="mt-2 text-2xl font-semibold">{money(dashboardData?.portfolio.net_asset, dashboardData?.portfolio.base_currency ?? "HKD")}</p>
              <p className="mt-1 text-xs text-amber-600">基金資產規模（代理容量指標）</p>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.3fr_0.9fr]">
            <div className="rounded-lg border bg-background/70 p-4">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold">風險趨勢圖</p>
                  <p className="text-xs text-muted-foreground">近 7 個交易日的總體風險分數</p>
                </div>
                <Badge variant="outline">{timeWindow}</Badge>
              </div>
              <svg viewBox="0 0 360 170" className="h-48 w-full">
                <line x1="20" y1="140" x2="340" y2="140" stroke="currentColor" strokeOpacity="0.25" />
                <line x1="20" y1="95" x2="340" y2="95" stroke="currentColor" strokeOpacity="0.15" />
                <line x1="20" y1="50" x2="340" y2="50" stroke="currentColor" strokeOpacity="0.15" />
                <path d={buildLinePath(trendValues)} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinecap="round" />
                {trendValues.map((value, index) => {
                  const maxValue = Math.max(...trendValues)
                  const minValue = Math.min(...trendValues)
                  const range = maxValue - minValue || 1
                  const x = 20 + (index / (trendValues.length - 1)) * 320
                  const normalized = (value - minValue) / range
                  const y = 140 - normalized * 90
                  return <circle key={`${value}-${index}`} cx={x} cy={y} r="4.5" fill="#38bdf8" />
                })}
              </svg>
              <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                {trendLabels.map((label) => (
                  <span key={label}>{label}</span>
                ))}
              </div>
            </div>

            <div className="rounded-lg border bg-background/70 p-4">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold">風險因子構成</p>
                  <p className="text-xs text-muted-foreground">各類風險來源占比</p>
                </div>
                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                  <TrendingUp className="h-4 w-4" />
                  更新中
                </div>
              </div>
              <div className="space-y-3">
                {exposureMixData.map((item) => (
                  <div key={item.label}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span>{item.label}</span>
                      <span className="text-muted-foreground">{item.value}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-muted">
                      <div className="h-2 rounded-full bg-primary" style={{ width: `${item.value}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldAlert className="h-4 w-4" />
            完整分析清單
          </CardTitle>
          <CardDescription>提供搜尋、分級篩選與報表下載，適配投研與風控雙角色審閱。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 rounded-md border px-3 py-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Input
                className="h-8 border-0 p-0 shadow-none focus-visible:ring-0"
                placeholder="搜尋風險名稱或 ID"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <div className="flex items-center gap-2 rounded-md border px-3 py-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <Select value={severityFilter} onValueChange={setSeverityFilter}>
                <SelectTrigger className="h-8 w-32 border-0 p-0 shadow-none">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="全部">全部</SelectItem>
                  <SelectItem value="高">高</SelectItem>
                  <SelectItem value="中">中</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Select value={timeWindow} onValueChange={setTimeWindow}>
              <SelectTrigger className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7D">7D</SelectItem>
                <SelectItem value="30D">30D</SelectItem>
                <SelectItem value="90D">90D</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={handleExport}>
              <Download className="mr-2 h-4 w-4" />
              匯出 CSV
            </Button>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>風險ID</TableHead>
                <TableHead>名稱</TableHead>
                <TableHead>類別</TableHead>
                <TableHead>等級</TableHead>
                <TableHead>分數</TableHead>
                <TableHead>狀態</TableHead>
                <TableHead>更新日</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredItems.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-mono">{item.id}</TableCell>
                  <TableCell>{item.name}</TableCell>
                  <TableCell>{item.bucket}</TableCell>
                  <TableCell>{item.severity}</TableCell>
                  <TableCell>{item.score}</TableCell>
                  <TableCell>{item.status}</TableCell>
                  <TableCell>{item.updatedAt}</TableCell>
                </TableRow>
              ))}
              {!filteredItems.length && (
                <TableRow>
                  <TableCell colSpan={7} className="h-16 text-center text-muted-foreground">
                    暫無符合條件的風險項目。
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" />
            快速分析入口
          </CardTitle>
          <CardDescription>使用下拉選擇、日期控件與操作按鈕直接進入對應分析頁。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Select value={selectedTopic} onValueChange={(value) => setSelectedTopic(value as InvestmentRiskTopic["id"])}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder="選擇分析主題" />
              </SelectTrigger>
              <SelectContent>
                {INVESTMENT_RISK_TOPICS.map((topic) => (
                  <SelectItem key={topic.id} value={topic.id}>
                    {topic.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DatePicker value={analysisDate} onChange={setAnalysisDate} />
            <Button asChild>
              <Link to={`/investment-risk/${selectedTopicMeta.id}`}>
                打開功能頁
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>

          <div className="rounded-lg border p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
              <ShieldAlert className="h-4 w-4" />
              {selectedTopicMeta.title} · {effectiveDate}
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>指标</TableHead>
                  <TableHead>当前值</TableHead>
                  <TableHead>狀態</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dashboardRows.map((row) => (
                  <TableRow key={row.metric}>
                    <TableCell>{row.metric}</TableCell>
                    <TableCell>{row.value}</TableCell>
                    <TableCell>{row.status}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {INVESTMENT_RISK_TOPICS.map((topic) => (
          <Card key={topic.id} className="h-full">
            <CardHeader>
              <CardTitle className="text-base">{topic.title}</CardTitle>
              <CardDescription>{topic.subtitle}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">{topic.summary}</p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {topic.capabilities.slice(0, 3).map((capability) => (
                  <li key={capability}>{capability}</li>
                ))}
              </ul>
              <Button asChild variant="outline" size="sm">
                <Link to={`/investment-risk/${topic.id}`}>
                  打開功能頁
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">系統架構整合與數據流</CardTitle>
          <CardDescription>投資風險模塊融合非同步計算與 Agent 智能調度。</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 lg:grid-cols-3">
          {integrationItems.map((item) => (
            <div key={item.title} className="rounded-lg border p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <item.icon className="h-4 w-4" />
                {item.title}
              </div>
              <p className="text-sm text-muted-foreground">{item.description}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

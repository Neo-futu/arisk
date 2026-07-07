import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useState } from "react"

import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { fsiApi, type VarCompareResult } from "@/fsiClient"

export const Route = createFileRoute("/_layout/risk")({
  component: RiskPage,
  head: () => ({ meta: [{ title: "風控分析 — ARISK" }] }),
})

const METHOD_LABELS: Record<string, string> = {
  historical: "歷史模擬法",
  monte_carlo: "蒙特卡洛法",
  distribution: "參數法",
}

function VarTable({ data }: { data: VarCompareResult }) {
  const maxMethod = data.results.find(
    (r) => r.var_pct_nav === data.max_var_pct_nav,
  )?.method_requested

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>方法</TableHead>
          <TableHead className="text-right">VaR（HKD）</TableHead>
          <TableHead className="text-right">VaR（% NAV）</TableHead>
          <TableHead className="text-right">CVaR（HKD）</TableHead>
          <TableHead className="text-right">樣本數</TableHead>
          <TableHead className="text-right">備注</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.results.map((r) => {
          const isMax = r.method_requested === maxMethod
          return (
            <TableRow key={r.method_requested} className={isMax ? "bg-muted/50" : ""}>
              <TableCell className="font-medium">
                {METHOD_LABELS[r.method_requested ?? ""] ?? r.method_requested}
              </TableCell>
              <TableCell className="text-right font-mono">
                {Number(r.var_hkd).toLocaleString("zh-HK", { maximumFractionDigits: 0 })}
              </TableCell>
              <TableCell className="text-right font-mono">
                {Number(r.var_pct_nav).toFixed(4)}%
              </TableCell>
              <TableCell className="text-right font-mono">
                {Number(r.cvar_hkd).toLocaleString("zh-HK", { maximumFractionDigits: 0 })}
              </TableCell>
              <TableCell className="text-right">{r.sample_size}</TableCell>
              <TableCell className="text-right">
                {isMax && <Badge variant="secondary" className="text-xs">最保守</Badge>}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

function RiskPage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [confidence, setConfidence] = useState("0.99")

  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["var-compare", fundId, asOfDate, confidence],
    queryFn: () =>
      fsiApi.getVarCompare(fundId, asOfDate, { confidence: Number(confidence) }).then((r) => r.data),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
  })

  const confidenceSelect = (
    <Select value={confidence} onValueChange={setConfidence}>
      <SelectTrigger className="w-28">
        <SelectValue placeholder="置信度" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="0.95">95%</SelectItem>
        <SelectItem value="0.99">99%</SelectItem>
      </SelectContent>
    </Select>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">風控分析</h1>
        <p className="text-muted-foreground text-sm">
          VaR 三方法對比（歷史模擬 / 蒙特卡洛 / 參數法）
        </p>
      </div>

      <FsiToolbar
        fundId={fundId} onFundChange={setFundId}
        asOfDate={asOfDate} onDateChange={setAsOfDate}
        onRefresh={() => refetch()} isFetching={isFetching}
        extra={confidenceSelect}
      />

      {isFetching && <p className="text-muted-foreground text-sm animate-pulse">計算中...</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            無法載入 VaR 數據。請確認 Processing API 已啟動。
          </CardContent>
        </Card>
      )}
      {data && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                {fundId} · {asOfDate} · 置信度 {(Number(confidence) * 100).toFixed(0)}%
              </CardTitle>
              <Badge variant="outline">
                最大 VaR：{data.max_var_pct_nav.toFixed(4)}%
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <VarTable data={data} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

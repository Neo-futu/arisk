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
import { fsiApi, type Position } from "@/fsiClient"

export const Route = createFileRoute("/_layout/positions")({
  component: PositionsPage,
  head: () => ({ meta: [{ title: "持倉明細 — ARISK" }] }),
})

const ASSET_TYPES = [
  { value: "", label: "全部資產類別" },
  { value: "bond", label: "債券" },
  { value: "cd", label: "存款證（CD）" },
  { value: "deposit", label: "定期存款" },
  { value: "repo", label: "回購" },
]

/** 安全格式化數字，null/undefined 顯示 — */
function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null || isNaN(Number(v))) return "—"
  return Number(v).toFixed(decimals)
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return "—"
  return Number(v).toLocaleString("zh-HK", { maximumFractionDigits: 0 })
}

function PositionRow({ p }: { p: Position }) {
  return (
    <TableRow>
      <TableCell className="font-mono text-xs max-w-24 truncate" title={p.asset_id}>
        {p.asset_id}
      </TableCell>
      <TableCell className="max-w-48 truncate" title={p.asset_name}>
        {p.asset_name}
      </TableCell>
      <TableCell>
        <Badge variant="secondary" className="text-xs">
          {p.asset_type}
        </Badge>
      </TableCell>
      <TableCell>{p.currency}</TableCell>
      <TableCell className="text-right font-mono">
        {fmtMoney(p.market_value_hkd ?? p.market_value)}
      </TableCell>
      <TableCell className="text-right font-mono">
        {fmt(p.weight_pct)}%
      </TableCell>
      <TableCell className="text-sm">{p.maturity_date ?? "—"}</TableCell>
      <TableCell>
        {p.credit_rating
          ? <Badge variant="outline" className="text-xs">{p.credit_rating}</Badge>
          : "—"}
      </TableCell>
    </TableRow>
  )
}

function PositionsPage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [assetType, setAssetType] = useState("")

  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["positions", fundId, asOfDate, assetType],
    queryFn: () =>
      fsiApi.getPositions(fundId, asOfDate, assetType || undefined).then((r) => r.data),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
  })

  const positions = data?.positions ?? []

  const assetFilter = (
    <Select value={assetType} onValueChange={setAssetType}>
      <SelectTrigger className="w-40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ASSET_TYPES.map((t) => (
          <SelectItem key={t.value} value={t.value}>
            {t.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">持倉明細</h1>
        <p className="text-muted-foreground text-sm">當日持倉列表，按市值降序排列</p>
      </div>

      <FsiToolbar
        fundId={fundId} onFundChange={setFundId}
        asOfDate={asOfDate} onDateChange={setAsOfDate}
        onRefresh={() => refetch()} isFetching={isFetching}
        extra={assetFilter}
      />

      {isFetching && (
        <p className="text-muted-foreground text-sm animate-pulse">載入中...</p>
      )}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            無法載入持倉數據。請確認 Processing API 已啟動。
          </CardContent>
        </Card>
      )}

      {data && !isFetching && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {fundId} · {asOfDate}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                共 {data.count} 筆
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {positions.length === 0 ? (
              <p className="text-center text-muted-foreground py-8 text-sm">
                {asOfDate} 無持倉數據
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>資產代碼</TableHead>
                    <TableHead>名稱</TableHead>
                    <TableHead>類別</TableHead>
                    <TableHead>幣種</TableHead>
                    <TableHead className="text-right">市值（HKD）</TableHead>
                    <TableHead className="text-right">佔 NAV</TableHead>
                    <TableHead>到期日</TableHead>
                    <TableHead>評級</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {positions.map((p, i) => (
                    <PositionRow key={`${p.asset_id}-${i}`} p={p} />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

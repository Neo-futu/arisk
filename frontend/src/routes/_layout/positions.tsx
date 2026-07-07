import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useState } from "react"

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
import { fsiApi } from "@/fsiClient"

export const Route = createFileRoute("/_layout/positions")({
  component: PositionsPage,
  head: () => ({ meta: [{ title: "持倉明細 — ARISK" }] }),
})

const FUNDS = [
  { id: "BHMMF001", name: "博匯港元貨幣市場基金 I" },
  { id: "BHMMF002", name: "博匯港元貨幣市場基金 II" },
]

const ASSET_TYPES = [
  { value: "", label: "全部資產類別" },
  { value: "bond", label: "債券" },
  { value: "cd", label: "存款證（CD）" },
  { value: "deposit", label: "定期存款" },
  { value: "repo", label: "回購" },
]

const ASSET_TYPE_LABELS: Record<string, string> = {
  bond: "債券",
  cd: "存款證",
  deposit: "定期存款",
  repo: "回購",
  cash: "現金",
}

function PositionsPage() {
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 1)
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1)
    return d.toISOString().split("T")[0]
  })
  const [assetType, setAssetType] = useState("")

  const { data, isLoading, isError } = useQuery({
    queryKey: ["positions", fundId, asOfDate, assetType],
    queryFn: () =>
      fsiApi
        .getPositions(fundId, asOfDate, assetType || undefined)
        .then((r) => r.data),
    retry: 1,
  })

  const positions = data?.positions ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">持倉明細</h1>
        <p className="text-muted-foreground text-sm">
          當日持倉列表，按市值降序排列
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select value={fundId} onValueChange={setFundId}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FUNDS.map((f) => (
              <SelectItem key={f.id} value={f.id}>
                {f.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={assetType} onValueChange={setAssetType}>
          <SelectTrigger className="w-44">
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

        <Badge variant="outline" className="h-10 px-3 text-sm">
          {asOfDate}
        </Badge>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">載入中...</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            無法載入持倉數據。請確認 Processing API 已啟動。
          </CardContent>
        </Card>
      )}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {fundId} · {asOfDate}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                共 {data.total_count} 個持倉
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>證券 ID</TableHead>
                  <TableHead>名稱</TableHead>
                  <TableHead>資產類別</TableHead>
                  <TableHead>貨幣</TableHead>
                  <TableHead className="text-right">市值（HKD）</TableHead>
                  <TableHead className="text-right">佔 NAV</TableHead>
                  <TableHead>到期日</TableHead>
                  <TableHead>評級</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={8}
                      className="text-center text-muted-foreground py-8"
                    >
                      暫無持倉數據
                    </TableCell>
                  </TableRow>
                ) : (
                  positions
                    .sort((a, b) => b.market_value_hkd - a.market_value_hkd)
                    .map((p) => (
                      <TableRow key={p.security_id}>
                        <TableCell className="font-mono text-xs">
                          {p.security_id}
                        </TableCell>
                        <TableCell className="max-w-48 truncate">
                          {p.security_name}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="text-xs">
                            {ASSET_TYPE_LABELS[p.asset_type] ?? p.asset_type}
                          </Badge>
                        </TableCell>
                        <TableCell>{p.currency}</TableCell>
                        <TableCell className="text-right font-mono">
                          {p.market_value_hkd.toLocaleString("zh-HK", {
                            maximumFractionDigits: 0,
                          })}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {p.pct_nav.toFixed(2)}%
                        </TableCell>
                        <TableCell className="text-sm">
                          {p.maturity_date ?? "—"}
                        </TableCell>
                        <TableCell>
                          {p.rating ? (
                            <Badge variant="outline" className="text-xs">
                              {p.rating}
                            </Badge>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

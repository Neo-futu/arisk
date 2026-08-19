/**
 * FsiToolbar — 所有 FSI 頁面共用的基金選擇 + 日期選擇 + 刷新工具欄
 */
import { RefreshCw } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { useEffect, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { DatePicker } from "@/components/DatePicker"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fsiApi } from "@/fsiClient"

export const FUNDS = [
  { id: "BHMMF001", name: "博匯港元貨幣市場基金 I" },
  { id: "BHMMF002", name: "博匯港元貨幣市場基金 II" },
]

export function lastTradeDate(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1)
  return d.toISOString().split("T")[0]
}

interface FsiToolbarProps {
  fundId: string
  onFundChange: (id: string) => void
  asOfDate: string
  onDateChange: (date: string) => void
  onRefresh: () => void
  isFetching?: boolean
  extra?: ReactNode
}

export function FsiToolbar({
  fundId,
  onFundChange,
  asOfDate,
  onDateChange,
  onRefresh,
  isFetching = false,
  extra,
}: FsiToolbarProps) {
  const { t } = useTranslation()
  const accessQuery = useQuery({
    queryKey: ["my-access-context"],
    queryFn: () => fsiApi.getMyAccessContext().then((response) => response.data),
    staleTime: 30_000,
  })
  const authorizedFunds = accessQuery.data?.portfolios.map((portfolio) => ({
    id: portfolio.port_id,
    name: portfolio.port_name,
  }))
  const funds = authorizedFunds ?? FUNDS

  useEffect(() => {
    if (!authorizedFunds || authorizedFunds.length === 0) return
    if (!authorizedFunds.some((fund) => fund.id === fundId)) {
      onFundChange(authorizedFunds[0].id)
    }
  }, [authorizedFunds, fundId, onFundChange])

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select value={fundId} onValueChange={onFundChange}>
        <SelectTrigger className="w-56">
          <SelectValue placeholder={t("toolbar.selectFund")} />
        </SelectTrigger>
        <SelectContent>
          {funds.map((f) => (
            <SelectItem key={f.id} value={f.id}>
              {f.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <DatePicker value={asOfDate} onChange={onDateChange} />

      <Button
        variant="outline"
        size="icon"
        onClick={onRefresh}
        disabled={isFetching}
        title={t("toolbar.reload")}
      >
        <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
      </Button>

      {extra}
    </div>
  )
}

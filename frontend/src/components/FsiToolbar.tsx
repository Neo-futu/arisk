/**
 * FsiToolbar — 所有 FSI 頁面共用的基金選擇 + 日期選擇 + 刷新工具欄
 * 日期控件与组合驾驶舱一致：原生 date input，支持键盘输入与日历选择。
 */
import { RefreshCw } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { useEffect, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fsiApi } from "@/fsiClient"
import { usePageContext } from "@/platform/page-context"

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
  asOfDateLabel?: string
  startDate?: string
  onStartDateChange?: (date: string) => void
  startDateLabel?: string
  onRefresh: () => void
  isFetching?: boolean
  extra?: ReactNode
}

export function FsiToolbar({
  fundId,
  onFundChange,
  asOfDate,
  onDateChange,
  asOfDateLabel,
  startDate,
  onStartDateChange,
  startDateLabel,
  onRefresh,
  isFetching = false,
  extra,
}: FsiToolbarProps) {
  const { t } = useTranslation()
  const page = usePageContext()
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
    page.patch({ portfolio: fundId, date: asOfDate })
  }, [asOfDate, fundId, page.patch])

  useEffect(() => {
    if (!authorizedFunds || authorizedFunds.length === 0) return
    if (!authorizedFunds.some((fund) => fund.id === fundId)) {
      onFundChange(authorizedFunds[0].id)
    }
  }, [authorizedFunds, fundId, onFundChange])

  return (
    <div className="flex flex-wrap items-end gap-3">
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

      {startDate !== undefined && onStartDateChange ? (
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">
            {startDateLabel ?? t("platform.startDate")}
          </div>
          <Input
            type="date"
            className="h-9 w-40"
            value={startDate}
            onChange={(event) => onStartDateChange(event.target.value)}
          />
        </div>
      ) : null}

      <div className="space-y-1">
        {(asOfDateLabel || startDate !== undefined) ? (
          <div className="text-xs text-muted-foreground">
            {asOfDateLabel ?? t("platform.endDate")}
          </div>
        ) : null}
        <Input
          type="date"
          className="h-9 w-40"
          value={asOfDate}
          onChange={(event) => onDateChange(event.target.value)}
        />
      </div>

      <Button
        variant="outline"
        size="icon"
        className="h-9 w-9 shrink-0"
        onClick={onRefresh}
        disabled={isFetching}
        title={t("toolbar.reload")}
      >
        <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
      </Button>
      <span
        className={`inline-flex h-9 min-w-16 items-center text-sm text-muted-foreground ${isFetching ? "animate-pulse" : "invisible"}`}
        aria-live="polite"
      >
        {t("toolbar.loading")}
      </span>

      {extra}
    </div>
  )
}

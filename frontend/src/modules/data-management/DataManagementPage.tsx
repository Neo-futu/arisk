import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle2,
  Database,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react"
import { useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { FloatingAiChat } from "@/components/FloatingAiChat"
import { FsiToolbar, FUNDS, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import {
  fsiApi,
  PORTFOLIO_TYPES,
  type EditablePosition,
  type EditablePositionPayload,
  type MarketQuote,
  type MarketQuotePayload,
  type PortfolioMaster,
  type PortfolioMasterPayload,
  type PortfolioMasterType,
  type SimulatedOrder,
  type SimulatedOrderPayload,
  type SimulatedOrderStatus,
} from "@/fsiClient"
import { HorizontalBarList, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"

type WorkbenchSection = "positions" | "market" | "trades" | "portfolios"
type DialogState<T> = { open: boolean; item: T | null }

const EMPTY_DIALOG = { open: false, item: null }

function numberOrNull(value: string): number | null {
  return value.trim() ? Number(value) : null
}

function money(value: number | null | undefined, currency = "HKD") {
  if (value == null) return "—"
  return new Intl.NumberFormat("zh-HK", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value)
}

function numeric(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : Number(value).toLocaleString("zh-HK", { maximumFractionDigits: digits })
}

function dateMinus(value: string, days: number) {
  const result = new Date(`${value}T00:00:00`)
  result.setDate(result.getDate() - days)
  return result.toISOString().slice(0, 10)
}

function statusVariant(status: SimulatedOrderStatus) {
  if (status === "BLOCKED") return "destructive" as const
  if (status === "VALIDATED") return "default" as const
  if (status === "WARNING") return "secondary" as const
  return "outline" as const
}

function ZoneTitle({ index, title, detail, action }: { index: string; title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-semibold text-primary">
          {index}
        </span>
        <div>
          <CardTitle className="text-base">{title}</CardTitle>
          {detail ? <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p> : null}
        </div>
      </div>
      {action}
    </div>
  )
}

export function DataManagementPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [section, setSection] = useState<WorkbenchSection>("positions")
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [search, setSearch] = useState("")
  const [selectedQuoteCode, setSelectedQuoteCode] = useState<string | null>(null)
  const [positionDialog, setPositionDialog] = useState<DialogState<EditablePosition>>(EMPTY_DIALOG)
  const [quoteDialog, setQuoteDialog] = useState<DialogState<MarketQuote>>(EMPTY_DIALOG)
  const [orderDialog, setOrderDialog] = useState<DialogState<SimulatedOrder>>(EMPTY_DIALOG)
  const [portfolioDialog, setPortfolioDialog] = useState<DialogState<PortfolioMaster>>(EMPTY_DIALOG)

  const access = useQuery({
    queryKey: ["my-access-context"],
    queryFn: () => fsiApi.getMyAccessContext().then((response) => response.data),
    staleTime: 30_000,
  })
  const portfolioAccess = access.data?.portfolios.find((portfolio) => portfolio.port_id === fundId)
  const permissions = new Set(access.data?.permission_codes ?? [])
  const isSuperuser = Boolean(access.data?.is_superuser)
  const canManagePositions = isSuperuser || (
    portfolioAccess?.access_level === "MANAGE" && permissions.has("portfolio.manage")
  )
  const canManageTrades = isSuperuser || (
    portfolioAccess?.access_level === "MANAGE" && permissions.has("trade.manage")
  )
  const canManageMarket = isSuperuser || permissions.has("market_data.manage")
  const canManagePortfolios = isSuperuser || permissions.has("portfolio.admin")

  const positions = useQuery({
    queryKey: ["data-management", "positions", fundId, asOfDate, search],
    queryFn: () => fsiApi.listEditablePositions(fundId, asOfDate, search || undefined).then((response) => response.data),
    enabled: section === "positions",
    retry: 1,
  })
  const quotes = useQuery({
    queryKey: ["data-management", "market", asOfDate, search],
    queryFn: () => fsiApi.listMarketQuotes(asOfDate, search || undefined).then((response) => response.data),
    enabled: section === "market",
    retry: 1,
  })
  const orders = useQuery({
    queryKey: ["data-management", "trades", fundId, asOfDate],
    queryFn: () => fsiApi.listSimulatedOrders(fundId, asOfDate).then((response) => response.data),
    enabled: section === "trades",
    retry: 1,
  })
  const portfolios = useQuery({
    queryKey: ["data-management", "portfolios", search],
    queryFn: () => fsiApi.listPortfolios({ search: search || undefined }).then((response) => response.data),
    enabled: section === "portfolios",
    retry: 1,
  })

  const quoteItems = quotes.data?.items ?? []
  const selectedQuote = quoteItems.find((item) => item.security_code === selectedQuoteCode) ?? quoteItems[0]
  const quoteHistory = useQuery({
    queryKey: ["data-management", "market-history", selectedQuote?.security_code, asOfDate],
    queryFn: () => fsiApi.getMarketQuoteHistory(
      selectedQuote!.security_code,
      dateMinus(asOfDate, 90),
      asOfDate,
      selectedQuote!.price_type,
    ).then((response) => response.data),
    enabled: section === "market" && Boolean(selectedQuote),
    retry: 1,
  })

  const currentQuery = section === "positions" ? positions : section === "market" ? quotes : section === "trades" ? orders : portfolios
  const refresh = () => void currentQuery.refetch()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["data-management", section] })

  const chartItems = useMemo(() => {
    if (section === "positions") {
      const rows = positions.data?.items ?? []
      const total = rows.reduce((sum, row) => sum + Number(row.market_value ?? 0), 0)
      return rows.slice(0, 10).map((row) => ({
        label: row.subject_name || row.subject_code,
        value: row.weight_pct == null
          ? (total ? Number(row.market_value ?? 0) / total * 100 : 0)
          : Number(row.weight_pct),
      }))
    }
    if (section === "trades") {
      const totals = new Map<string, number>()
      for (const order of orders.data?.items ?? []) {
        totals.set(order.status, (totals.get(order.status) ?? 0) + Number(order.trade_amount))
      }
      return Array.from(totals, ([label, value]) => ({ label, value }))
    }
    if (section === "portfolios") {
      const totals = new Map<string, number>()
      for (const portfolio of portfolios.data?.items ?? []) {
        totals.set(portfolio.port_type, (totals.get(portfolio.port_type) ?? 0) + 1)
      }
      return Array.from(totals, ([label, value]) => ({ label, value }))
    }
    return []
  }, [orders.data?.items, portfolios.data?.items, positions.data?.items, section])

  const aiSummary = useMemo(() => {
    if (section === "positions") {
      return (positions.data?.items ?? []).slice(0, 12).map((row) => ({
        code: row.subject_code,
        name: row.subject_name,
        market_value: row.market_value,
        weight_pct: row.weight_pct,
      }))
    }
    if (section === "market") {
      return quoteItems.slice(0, 12).map((row) => ({
        code: row.security_code,
        market: row.market_id,
        close: row.close_price,
        change_pct: row.price_change_pct,
      }))
    }
    if (section === "portfolios") {
      return (portfolios.data?.items ?? []).slice(0, 20).map((row) => ({
        port_id: row.port_id,
        name: row.port_name,
        type: row.port_type,
        currency: row.base_currency,
        is_mmf: row.is_mmf,
        is_active: row.is_active,
      }))
    }
    return (orders.data?.items ?? []).slice(0, 12).map((row) => ({
      code: row.security_code,
      side: row.trade_side,
      amount: row.trade_amount,
      status: row.status,
      decision: row.decision,
      breaches: row.breach_flags,
    }))
  }, [orders.data?.items, portfolios.data?.items, positions.data?.items, quoteItems, section])

  async function deletePosition(row: EditablePosition) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deleteEditablePosition(fundId, asOfDate, row.subject_code)
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function deleteQuote(row: MarketQuote) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deleteMarketQuote(row)
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function validateOrder(row: SimulatedOrder) {
    try {
      await fsiApi.validateSimulatedOrder(fundId, row.order_id)
      await invalidate()
      toast.success(t("dataManagement.validated"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function cancelOrder(row: SimulatedOrder) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.cancelSimulatedOrder(fundId, row.order_id)
      await invalidate()
      toast.success(t("dataManagement.cancelled"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function deletePortfolio(row: PortfolioMaster) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deletePortfolio(row.port_id)
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status
      toast.error(status === 409 ? t("dataManagement.portfolioDeleteBlocked") : t("dataManagement.operationFailed"))
    }
  }

  const currentCanManage = section === "positions"
    ? canManagePositions
    : section === "market"
      ? canManageMarket
      : section === "trades"
        ? canManageTrades
        : canManagePortfolios

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge className="gap-1"><Database className="h-3.5 w-3.5" />Data Foundation</Badge>
            <Badge variant="outline">Phase 1</Badge>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("dataManagement.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("dataManagement.subtitle")}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="secondary"><Database className="mr-1 h-3 w-3" />{t("dataManagement.directDb")}</Badge>
          <Badge variant="secondary"><ShieldCheck className="mr-1 h-3 w-3" />{t("dataManagement.audited")}</Badge>
        </div>
      </div>

      <div className="space-y-5">
          <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
            <CardHeader>
              <ZoneTitle index="01" title={t("dataManagement.parameters")} detail={`${fundId} · ${asOfDate}`} />
            </CardHeader>
            <CardContent className="space-y-4">
              <Tabs value={section} onValueChange={(value) => {
                setSection(value as WorkbenchSection)
                setSearch("")
              }}>
                <TabsList className="grid w-full max-w-2xl grid-cols-4">
                  <TabsTrigger value="portfolios">{t("dataManagement.portfoliosTab")}</TabsTrigger>
                  <TabsTrigger value="positions">{t("dataManagement.positionsTab")}</TabsTrigger>
                  <TabsTrigger value="market">{t("dataManagement.marketTab")}</TabsTrigger>
                  <TabsTrigger value="trades">{t("dataManagement.tradesTab")}</TabsTrigger>
                </TabsList>
              </Tabs>
              <FsiToolbar
                fundId={fundId}
                onFundChange={setFundId}
                asOfDate={asOfDate}
                onDateChange={setAsOfDate}
                onRefresh={refresh}
                isFetching={currentQuery.isFetching}
                extra={section !== "trades" ? (
                  <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-3">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-7 w-52 border-0 p-0 shadow-none focus-visible:ring-0"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder={t("dataManagement.search")}
                    />
                  </div>
                ) : null}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <ZoneTitle
                index="02"
                title={t("dataManagement.dataArea")}
                detail={section === "positions"
                  ? t("dataManagement.positionCount", { count: positions.data?.count ?? 0 })
                  : section === "market"
                    ? t("dataManagement.quoteCount", { count: quotes.data?.count ?? 0 })
                    : section === "trades"
                      ? t("dataManagement.orderCount", { count: orders.data?.count ?? 0 })
                      : t("dataManagement.portfolioCount", { count: portfolios.data?.count ?? 0 })}
                action={<Button size="sm" disabled={!currentCanManage} onClick={() => {
                  if (section === "positions") setPositionDialog({ open: true, item: null })
                  else if (section === "market") setQuoteDialog({ open: true, item: null })
                  else if (section === "trades") setOrderDialog({ open: true, item: null })
                  else setPortfolioDialog({ open: true, item: null })
                }}><Plus className="mr-1 h-4 w-4" />{t("dataManagement.add")}</Button>}
              />
            </CardHeader>
            <CardContent>
              {!currentCanManage ? (
                <p className="mb-3 text-xs text-amber-600 dark:text-amber-400">{t("dataManagement.noPermission")}</p>
              ) : null}
              {currentQuery.isFetching ? <p className="py-10 text-center text-sm text-muted-foreground">{t("dataManagement.loading")}</p> : null}
              {currentQuery.isError ? <p className="py-10 text-center text-sm text-destructive">{t("dataManagement.operationFailed")}</p> : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "positions" ? (
                <PositionTable
                  rows={positions.data?.items ?? []}
                  canManage={canManagePositions}
                  onEdit={(item) => setPositionDialog({ open: true, item })}
                  onDelete={deletePosition}
                />
              ) : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "market" ? (
                <MarketTable
                  rows={quoteItems}
                  canManage={canManageMarket}
                  selectedCode={selectedQuote?.security_code}
                  onSelect={setSelectedQuoteCode}
                  onEdit={(item) => setQuoteDialog({ open: true, item })}
                  onDelete={deleteQuote}
                />
              ) : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "trades" ? (
                <OrderTable
                  rows={orders.data?.items ?? []}
                  canManage={canManageTrades}
                  onEdit={(item) => setOrderDialog({ open: true, item })}
                  onValidate={validateOrder}
                  onCancel={cancelOrder}
                />
              ) : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "portfolios" ? (
                <PortfolioTable
                  rows={portfolios.data?.items ?? []}
                  canManage={canManagePortfolios}
                  onEdit={(item) => setPortfolioDialog({ open: true, item })}
                  onDelete={deletePortfolio}
                />
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <ZoneTitle
                index="03"
                title={t("dataManagement.chartArea")}
                detail={section === "positions"
                  ? t("dataManagement.positionChart")
                  : section === "market"
                    ? t("dataManagement.marketChart")
                    : section === "trades"
                      ? t("dataManagement.tradeChart")
                      : t("dataManagement.portfolioChart")}
              />
            </CardHeader>
            <CardContent>
              {section === "market" ? (
                <div>
                  <div className="mb-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                    <span>{selectedQuote?.security_code ?? t("dataManagement.selectQuote")}</span>
                    {selectedQuote ? <Badge variant="outline">{selectedQuote.market_id}</Badge> : null}
                  </div>
                  <TrendLineChart
                    values={(quoteHistory.data?.items ?? []).map((row) => Number(row.close_price))}
                    labels={(quoteHistory.data?.items ?? []).map((row) => row.price_date.slice(5))}
                    lineColor="#8b5cf6"
                    pointColor="#c4b5fd"
                  />
                </div>
              ) : (
                <HorizontalBarList
                  items={chartItems}
                  formatter={(value) => section === "positions" ? `${value.toFixed(2)}%` : section === "portfolios" ? String(value) : money(value)}
                />
              )}
            </CardContent>
          </Card>
      </div>
      <FloatingAiChat
        title={t("dataManagement.aiArea")}
        hint={t("dataManagement.aiHint")}
        placeholder={t("dataManagement.aiPlaceholder")}
        context={{ fund_id: fundId, as_of_date: asOfDate }}
        buildPrompt={(q) => [
          "你正在 ARISK 數據管理中心協助投資風控人員。",
          `當前模塊：${section}；基金：${fundId}；數據日期：${asOfDate}。`,
          "以下是當前頁面可見數據摘要（只作分析，不得聲稱已執行交易）：",
          JSON.stringify(aiSummary),
          `用戶問題：${q}`,
        ].join("\n")}
      />

      {positionDialog.open ? (
        <PositionDialog
          fundId={fundId}
          asOfDate={asOfDate}
          item={positionDialog.item}
          onClose={() => setPositionDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setPositionDialog(EMPTY_DIALOG)
            await invalidate()
          }}
        />
      ) : null}
      {quoteDialog.open ? (
        <MarketQuoteDialog
          asOfDate={asOfDate}
          item={quoteDialog.item}
          onClose={() => setQuoteDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setQuoteDialog(EMPTY_DIALOG)
            await invalidate()
          }}
        />
      ) : null}
      {orderDialog.open ? (
        <SimulatedOrderDialog
          fundId={fundId}
          asOfDate={asOfDate}
          item={orderDialog.item}
          onClose={() => setOrderDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setOrderDialog(EMPTY_DIALOG)
            await invalidate()
          }}
        />
      ) : null}
      {portfolioDialog.open ? (
        <PortfolioDialog
          item={portfolioDialog.item}
          onClose={() => setPortfolioDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setPortfolioDialog(EMPTY_DIALOG)
            await invalidate()
          }}
        />
      ) : null}
    </div>
  )
}

function EmptyRow({ columns }: { columns: number }) {
  const { t } = useTranslation()
  return <TableRow><TableCell colSpan={columns} className="h-28 text-center text-muted-foreground">{t("dataManagement.empty")}</TableCell></TableRow>
}

function ActionButtons({ canManage, onEdit, onDelete }: { canManage: boolean; onEdit: () => void; onDelete: () => void }) {
  const { t } = useTranslation()
  if (!canManage) return <span className="text-muted-foreground">—</span>
  return (
    <div className="flex justify-end gap-1">
      <Button variant="ghost" size="icon" title={t("dataManagement.edit")} onClick={(event) => { event.stopPropagation(); onEdit() }}>
        <Pencil className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" title={t("dataManagement.delete")} onClick={(event) => { event.stopPropagation(); onDelete() }}>
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  )
}

function PositionTable({ rows, canManage, onEdit, onDelete }: {
  rows: EditablePosition[]
  canManage: boolean
  onEdit: (item: EditablePosition) => void
  onDelete: (item: EditablePosition) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow>
          <TableHead>{t("dataManagement.code")}</TableHead><TableHead>{t("dataManagement.name")}</TableHead>
          <TableHead>{t("dataManagement.currency")}</TableHead><TableHead className="text-right">{t("dataManagement.quantity")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.unitPrice")}</TableHead><TableHead className="text-right">{t("dataManagement.marketValue")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.weight")}</TableHead><TableHead>{t("dataManagement.source")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={row.subject_code}>
            <TableCell className="font-mono text-xs">{row.subject_code}</TableCell><TableCell className="font-medium">{row.subject_name}</TableCell>
            <TableCell>{row.currency}</TableCell><TableCell className="text-right font-mono">{numeric(row.quantity, 4)}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.unit_price, 6)}</TableCell><TableCell className="text-right font-mono">{money(row.market_value, row.currency)}</TableCell>
            <TableCell className="text-right font-mono">{row.weight_pct == null ? "—" : `${numeric(row.weight_pct)}%`}</TableCell>
            <TableCell><Badge variant="outline">{row.data_source ?? "—"}</Badge></TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={9} /> : null}
        </TableBody>
      </Table>
    </div>
  )
}

function MarketTable({ rows, canManage, selectedCode, onSelect, onEdit, onDelete }: {
  rows: MarketQuote[]
  canManage: boolean
  selectedCode?: string
  onSelect: (code: string) => void
  onEdit: (item: MarketQuote) => void
  onDelete: (item: MarketQuote) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow>
          <TableHead>{t("dataManagement.code")}</TableHead><TableHead>{t("dataManagement.market")}</TableHead>
          <TableHead>{t("dataManagement.priceType")}</TableHead><TableHead className="text-right">{t("dataManagement.open")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.high")}</TableHead><TableHead className="text-right">{t("dataManagement.low")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.close")}</TableHead><TableHead className="text-right">{t("dataManagement.change")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.volume")}</TableHead><TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow
            key={`${row.security_code}-${row.price_type}`}
            className={`cursor-pointer ${selectedCode === row.security_code ? "bg-primary/[0.06]" : ""}`}
            onClick={() => onSelect(row.security_code)}
          >
            <TableCell className="font-mono text-xs">{row.security_code}</TableCell><TableCell>{row.market_id}</TableCell>
            <TableCell><Badge variant="outline">{row.price_type}</Badge></TableCell><TableCell className="text-right font-mono">{numeric(row.open_price, 6)}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.high_price, 6)}</TableCell><TableCell className="text-right font-mono">{numeric(row.low_price, 6)}</TableCell>
            <TableCell className="text-right font-mono font-semibold">{numeric(row.close_price, 6)}</TableCell>
            <TableCell className={`text-right font-mono ${(row.price_change_pct ?? 0) < 0 ? "text-destructive" : "text-emerald-600"}`}>
              {row.price_change_pct == null ? "—" : `${numeric(row.price_change_pct, 3)}%`}
            </TableCell>
            <TableCell className="text-right font-mono">{numeric(row.volume, 0)}</TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={10} /> : null}
        </TableBody>
      </Table>
    </div>
  )
}

function OrderTable({ rows, canManage, onEdit, onValidate, onCancel }: {
  rows: SimulatedOrder[]
  canManage: boolean
  onEdit: (item: SimulatedOrder) => void
  onValidate: (item: SimulatedOrder) => void
  onCancel: (item: SimulatedOrder) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{t("dataManagement.simulationOnly")}</p>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead>{t("dataManagement.code")}</TableHead><TableHead>{t("dataManagement.side")}</TableHead>
            <TableHead>{t("dataManagement.assetClass")}</TableHead><TableHead>{t("dataManagement.issuer")}</TableHead>
            <TableHead className="text-right">{t("dataManagement.tradeAmount")}</TableHead><TableHead>{t("dataManagement.status")}</TableHead>
            <TableHead>{t("dataManagement.decision")}</TableHead><TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((row) => <TableRow key={row.order_id}>
              <TableCell><div className="font-mono text-xs">{row.security_code}</div><div className="max-w-40 truncate text-xs text-muted-foreground">{row.security_name}</div></TableCell>
              <TableCell><Badge variant={row.trade_side === "BUY" ? "default" : "secondary"}>{row.trade_side}</Badge></TableCell>
              <TableCell>{row.asset_class}</TableCell><TableCell className="max-w-40 truncate">{row.issuer_name ?? "—"}</TableCell>
              <TableCell className="text-right font-mono">{money(row.trade_amount, row.currency)}</TableCell>
              <TableCell><Badge variant={statusVariant(row.status)}>{row.status}</Badge></TableCell>
              <TableCell><span title={row.breach_flags.join("\n")}>{row.decision ?? "—"}{row.breach_flags.length ? ` (${row.breach_flags.length})` : ""}</span></TableCell>
              <TableCell><div className="flex justify-end gap-1">
                {canManage ? <>
                  <Button variant="ghost" size="icon" title={t("dataManagement.edit")} onClick={() => onEdit(row)}><Pencil className="h-4 w-4" /></Button>
                  <Button variant="ghost" size="icon" title={t("dataManagement.validate")} onClick={() => onValidate(row)}><CheckCircle2 className="h-4 w-4 text-emerald-600" /></Button>
                  <Button variant="ghost" size="icon" title={t("dataManagement.cancelOrder")} onClick={() => onCancel(row)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                </> : "—"}
              </div></TableCell>
            </TableRow>)}
            {!rows.length ? <EmptyRow columns={8} /> : null}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function PortfolioTable({ rows, canManage, onEdit, onDelete }: {
  rows: PortfolioMaster[]
  canManage: boolean
  onEdit: (item: PortfolioMaster) => void
  onDelete: (item: PortfolioMaster) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow>
          <TableHead>{t("dataManagement.code")}</TableHead><TableHead>{t("dataManagement.name")}</TableHead>
          <TableHead>{t("dataManagement.portType")}</TableHead><TableHead>{t("dataManagement.currency")}</TableHead>
          <TableHead>{t("dataManagement.isMmf")}</TableHead><TableHead>{t("dataManagement.inceptionDate")}</TableHead>
          <TableHead>{t("dataManagement.status")}</TableHead><TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={row.port_id}>
            <TableCell className="font-mono text-xs">{row.port_id}</TableCell>
            <TableCell className="font-medium">{row.port_name}</TableCell>
            <TableCell><Badge variant="outline">{row.port_type}</Badge></TableCell>
            <TableCell>{row.base_currency}</TableCell>
            <TableCell>{row.is_mmf ? "✓" : "—"}</TableCell>
            <TableCell className="font-mono text-xs">{row.inception_date ?? "—"}</TableCell>
            <TableCell><Badge variant={row.is_active ? "default" : "secondary"}>{row.is_active ? t("dataManagement.active") : t("dataManagement.inactive")}</Badge></TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={8} /> : null}
        </TableBody>
      </Table>
    </div>
  )
}

function PortfolioDialog({ item, onClose, onSaved }: {
  item: PortfolioMaster | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    port_id: item?.port_id ?? "",
    port_name: item?.port_name ?? "",
    port_name_en: item?.port_name_en ?? "",
    port_type: item?.port_type ?? "MMF",
    base_currency: item?.base_currency ?? "HKD",
    inception_date: item?.inception_date ?? new Date().toISOString().slice(0, 10),
    is_mmf: item?.is_mmf ?? true,
    is_active: item?.is_active ?? true,
    sfc_code: item?.sfc_code ?? "",
    mmf_wam_limit_days: item?.mmf_wam_limit_days?.toString() ?? "60",
    mmf_wal_limit_days: item?.mmf_wal_limit_days?.toString() ?? "120",
    mgmt_fee_bps: item?.mgmt_fee_bps?.toString() ?? "",
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    if (!form.port_id.trim() || !form.port_name.trim() || !form.inception_date) {
      toast.error(t("dataManagement.required")); return
    }
    const payload: PortfolioMasterPayload = {
      ...(item ? {} : { port_id: form.port_id.trim().toUpperCase() }),
      port_name: form.port_name.trim(),
      port_name_en: form.port_name_en.trim() || null,
      port_type: form.port_type as PortfolioMasterType,
      base_currency: form.base_currency.trim().toUpperCase(),
      inception_date: form.inception_date,
      is_mmf: form.is_mmf,
      is_active: form.is_active,
      sfc_code: form.sfc_code.trim() || null,
      mmf_wam_limit_days: form.mmf_wam_limit_days ? Number(form.mmf_wam_limit_days) : null,
      mmf_wal_limit_days: form.mmf_wal_limit_days ? Number(form.mmf_wal_limit_days) : null,
      mgmt_fee_bps: form.mgmt_fee_bps ? Number(form.mgmt_fee_bps) : null,
    }
    setSaving(true)
    try {
      if (item) await fsiApi.updatePortfolio(item.port_id, payload)
      else await fsiApi.createPortfolio(payload)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  const boolSelect = (value: boolean, onChange: (v: string) => void, label: string) => (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Select value={value ? "yes" : "no"} onValueChange={onChange}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value="yes">{t("dataManagement.yes")}</SelectItem><SelectItem value="no">{t("dataManagement.no")}</SelectItem></SelectContent>
      </Select>
    </div>
  )

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.portfoliosTab")}</DialogTitle><DialogDescription>{t("dataManagement.directDb")}</DialogDescription></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("dataManagement.code")} value={form.port_id} onChange={set("port_id")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.name")} value={form.port_name} onChange={set("port_name")} required />
      <FormField label={t("dataManagement.nameEn")} value={form.port_name_en} onChange={set("port_name_en")} />
      <div className="space-y-1.5">
        <Label>{t("dataManagement.portType")} *</Label>
        <Select value={form.port_type} onValueChange={set("port_type")}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>{PORTFOLIO_TYPES.map((ty) => <SelectItem key={ty} value={ty}>{ty}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <FormField label={t("dataManagement.currency")} value={form.base_currency} onChange={set("base_currency")} required />
      <FormField label={t("dataManagement.inceptionDate")} value={form.inception_date} onChange={set("inception_date")} type="date" required />
      {boolSelect(form.is_mmf, (v) => setForm((p) => ({ ...p, is_mmf: v === "yes" })), t("dataManagement.isMmf"))}
      {boolSelect(form.is_active, (v) => setForm((p) => ({ ...p, is_active: v === "yes" })), t("dataManagement.active"))}
      <FormField label={t("dataManagement.sfcCode")} value={form.sfc_code} onChange={set("sfc_code")} />
      <FormField label={t("dataManagement.wamLimit")} value={form.mmf_wam_limit_days} onChange={set("mmf_wam_limit_days")} type="number" />
      <FormField label={t("dataManagement.walLimit")} value={form.mmf_wal_limit_days} onChange={set("mmf_wal_limit_days")} type="number" />
      <FormField label={t("dataManagement.mgmtFee")} value={form.mgmt_fee_bps} onChange={set("mgmt_fee_bps")} type="number" />
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("dataManagement.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("dataManagement.saving") : t("dataManagement.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}


function FormField({ label, value, onChange, type = "text", required = false, disabled = false }: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  required?: boolean
  disabled?: boolean
}) {
  return <div className="space-y-1.5"><Label>{label}{required ? " *" : ""}</Label><Input type={type} value={value} onChange={(event) => onChange(event.target.value)} required={required} disabled={disabled} /></div>
}

function PositionDialog({ fundId, asOfDate, item, onClose, onSaved }: {
  fundId: string
  asOfDate: string
  item: EditablePosition | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    subject_code: item?.subject_code ?? "",
    subject_name: item?.subject_name ?? "",
    currency: item?.currency ?? "HKD",
    quantity: item?.quantity?.toString() ?? "",
    unit_price: item?.unit_price?.toString() ?? "",
    cost: item?.cost?.toString() ?? "",
    market_value: item?.market_value?.toString() ?? "",
    weight_pct: item?.weight_pct?.toString() ?? "",
    data_source: item?.data_source ?? "MANUAL",
    memo: item?.memo ?? "",
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    if (!form.subject_code.trim() || !form.subject_name.trim() || !form.currency.trim()) {
      toast.error(t("dataManagement.required")); return
    }
    const payload: EditablePositionPayload = {
      subject_code: form.subject_code.trim().toUpperCase(),
      subject_name: form.subject_name.trim(),
      currency: form.currency.trim().toUpperCase(),
      quantity: numberOrNull(form.quantity),
      unit_price: numberOrNull(form.unit_price),
      cost: numberOrNull(form.cost),
      market_value: numberOrNull(form.market_value),
      weight_pct: numberOrNull(form.weight_pct),
      data_source: form.data_source.trim().toUpperCase() || "MANUAL",
      memo: form.memo.trim() || null,
    }
    setSaving(true)
    try {
      if (item) await fsiApi.updateEditablePosition(fundId, asOfDate, item.subject_code, payload)
      else await fsiApi.createEditablePosition(fundId, asOfDate, payload)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.positionsTab")}</DialogTitle><DialogDescription>{fundId} · {asOfDate}</DialogDescription></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("dataManagement.code")} value={form.subject_code} onChange={set("subject_code")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.name")} value={form.subject_name} onChange={set("subject_name")} required />
      <FormField label={t("dataManagement.currency")} value={form.currency} onChange={set("currency")} required />
      <FormField label={t("dataManagement.quantity")} value={form.quantity} onChange={set("quantity")} type="number" />
      <FormField label={t("dataManagement.unitPrice")} value={form.unit_price} onChange={set("unit_price")} type="number" />
      <FormField label={t("dataManagement.cost")} value={form.cost} onChange={set("cost")} type="number" />
      <FormField label={t("dataManagement.marketValue")} value={form.market_value} onChange={set("market_value")} type="number" />
      <FormField label={t("dataManagement.weight")} value={form.weight_pct} onChange={set("weight_pct")} type="number" />
      <FormField label={t("dataManagement.source")} value={form.data_source} onChange={set("data_source")} required />
      <FormField label={t("dataManagement.memo")} value={form.memo} onChange={set("memo")} />
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("dataManagement.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("dataManagement.saving") : t("dataManagement.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}

function MarketQuoteDialog({ asOfDate, item, onClose, onSaved }: {
  asOfDate: string
  item: MarketQuote | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    price_date: item?.price_date ?? asOfDate,
    security_code: item?.security_code ?? "",
    market_id: item?.market_id ?? "HKEX",
    price_type: item?.price_type ?? "CLOSE",
    open_price: item?.open_price?.toString() ?? "",
    high_price: item?.high_price?.toString() ?? "",
    low_price: item?.low_price?.toString() ?? "",
    close_price: item?.close_price?.toString() ?? "",
    prev_close: item?.prev_close?.toString() ?? "",
    volume: item?.volume?.toString() ?? "",
    turnover: item?.turnover?.toString() ?? "",
    data_source: item?.data_source ?? "MANUAL",
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    if (!form.security_code.trim() || !form.market_id.trim() || !form.close_price.trim()) {
      toast.error(t("dataManagement.required")); return
    }
    const payload: MarketQuotePayload = {
      price_date: form.price_date,
      security_code: form.security_code.trim().toUpperCase(),
      market_id: form.market_id.trim().toUpperCase(),
      price_type: form.price_type.trim().toUpperCase(),
      open_price: numberOrNull(form.open_price),
      high_price: numberOrNull(form.high_price),
      low_price: numberOrNull(form.low_price),
      close_price: Number(form.close_price),
      prev_close: numberOrNull(form.prev_close),
      volume: numberOrNull(form.volume),
      turnover: numberOrNull(form.turnover),
      data_source: form.data_source.trim().toUpperCase() || "MANUAL",
    }
    setSaving(true)
    try {
      if (item) await fsiApi.updateMarketQuote(item, payload)
      else await fsiApi.createMarketQuote(payload)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.marketTab")}</DialogTitle><DialogDescription>{t("dataManagement.audited")}</DialogDescription></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("dataManagement.date")} value={form.price_date} onChange={set("price_date")} type="date" required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.code")} value={form.security_code} onChange={set("security_code")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.market")} value={form.market_id} onChange={set("market_id")} required />
      <FormField label={t("dataManagement.priceType")} value={form.price_type} onChange={set("price_type")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.open")} value={form.open_price} onChange={set("open_price")} type="number" />
      <FormField label={t("dataManagement.high")} value={form.high_price} onChange={set("high_price")} type="number" />
      <FormField label={t("dataManagement.low")} value={form.low_price} onChange={set("low_price")} type="number" />
      <FormField label={t("dataManagement.close")} value={form.close_price} onChange={set("close_price")} type="number" required />
      <FormField label={t("dataManagement.previousClose")} value={form.prev_close} onChange={set("prev_close")} type="number" />
      <FormField label={t("dataManagement.volume")} value={form.volume} onChange={set("volume")} type="number" />
      <FormField label={t("dataManagement.turnover")} value={form.turnover} onChange={set("turnover")} type="number" />
      <FormField label={t("dataManagement.source")} value={form.data_source} onChange={set("data_source")} required />
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("dataManagement.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("dataManagement.saving") : t("dataManagement.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}

function SimulatedOrderDialog({ fundId, asOfDate, item, onClose, onSaved }: {
  fundId: string
  asOfDate: string
  item: SimulatedOrder | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    as_of_date: item?.as_of_date ?? asOfDate,
    trade_date: item?.trade_date ?? asOfDate,
    trade_side: item?.trade_side ?? "BUY",
    asset_class: item?.asset_class ?? "BOND_CORP",
    security_code: item?.security_code ?? "",
    security_name: item?.security_name ?? "",
    issuer_name: item?.issuer_name ?? "",
    currency: item?.currency ?? "HKD",
    quantity: item?.quantity?.toString() ?? "",
    price: item?.price?.toString() ?? "",
    trade_amount: item?.trade_amount?.toString() ?? "",
    duration_years: item?.duration_years?.toString() ?? "0",
    notes: item?.notes ?? "",
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    if (!form.security_code.trim() || !form.asset_class.trim() || !form.currency.trim()) {
      toast.error(t("dataManagement.required")); return
    }
    const payload: SimulatedOrderPayload = {
      as_of_date: form.as_of_date,
      trade_date: form.trade_date,
      trade_side: form.trade_side as "BUY" | "SELL",
      asset_class: form.asset_class.trim().toUpperCase(),
      security_code: form.security_code.trim().toUpperCase(),
      security_name: form.security_name.trim() || null,
      issuer_name: form.issuer_name.trim() || null,
      currency: form.currency.trim().toUpperCase(),
      quantity: numberOrNull(form.quantity),
      price: numberOrNull(form.price),
      trade_amount: numberOrNull(form.trade_amount),
      duration_years: Number(form.duration_years || 0),
      notes: form.notes.trim() || null,
    }
    setSaving(true)
    try {
      if (item) await fsiApi.updateSimulatedOrder(fundId, item.order_id, payload)
      else await fsiApi.createSimulatedOrder(fundId, payload)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.tradesTab")}</DialogTitle><DialogDescription>{t("dataManagement.simulationOnly")}</DialogDescription></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("dataManagement.date")} value={form.as_of_date} onChange={set("as_of_date")} type="date" required />
      <FormField label={t("dataManagement.date")} value={form.trade_date} onChange={set("trade_date")} type="date" required />
      <div className="space-y-1.5"><Label>{t("dataManagement.side")} *</Label><Select value={form.trade_side} onValueChange={set("trade_side")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="BUY">BUY</SelectItem><SelectItem value="SELL">SELL</SelectItem></SelectContent></Select></div>
      <FormField label={t("dataManagement.assetClass")} value={form.asset_class} onChange={set("asset_class")} required />
      <FormField label={t("dataManagement.code")} value={form.security_code} onChange={set("security_code")} required />
      <FormField label={t("dataManagement.name")} value={form.security_name} onChange={set("security_name")} />
      <FormField label={t("dataManagement.issuer")} value={form.issuer_name} onChange={set("issuer_name")} />
      <FormField label={t("dataManagement.currency")} value={form.currency} onChange={set("currency")} required />
      <FormField label={t("dataManagement.quantity")} value={form.quantity} onChange={set("quantity")} type="number" />
      <FormField label={t("dataManagement.unitPrice")} value={form.price} onChange={set("price")} type="number" />
      <FormField label={t("dataManagement.tradeAmount")} value={form.trade_amount} onChange={set("trade_amount")} type="number" />
      <FormField label={t("dataManagement.duration")} value={form.duration_years} onChange={set("duration_years")} type="number" />
      <div className="space-y-1.5 sm:col-span-2"><Label>{t("dataManagement.memo")}</Label><Textarea value={form.notes} onChange={(event) => set("notes")(event.target.value)} /></div>
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("dataManagement.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("dataManagement.saving") : t("dataManagement.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  CheckCircle2,
  Download,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

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
  type PortfolioManagerPayload,
  type PortfolioManagerRecord,
  type PortfolioMaster,
  type PortfolioMasterPayload,
  type PortfolioMasterType,
  type PortfolioMmfPayload,
  type PortfolioMmfRow,
  type PortfolioNavPayload,
  type PortfolioNavRow,
  type ShareClassMaster,
  type ShareClassPayload,
  type SimulatedOrder,
  type SimulatedOrderPayload,
  type SimulatedOrderStatus,
  type ValuationSheetPayload,
  type ValuationSheetRow,
} from "@/fsiClient"
import { exportCsv, HorizontalBarList, TrendLineChart } from "@/modules/investment-risk/dashboard-kit"
import { useBindPageContext } from "@/platform/page-context"

type WorkbenchSection = "positions" | "market" | "trades" | "portfolios"
type DialogState<T> = { open: boolean; item: T | null }

const EMPTY_DIALOG = { open: false, item: null }
const PORTFOLIO_DATE_TABLES = new Set([
  "balance_valuation_sheet",
  "balance_portfolio_nav",
  "balance_portfolio_mmf",
])

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

export function DataManagementPage({
  initialSection = "positions",
  lockedSection,
  titleKey,
  subtitleKey,
  hideHeader = false,
  hideMarketTab = false,
}: {
  initialSection?: WorkbenchSection
  lockedSection?: WorkbenchSection
  titleKey?: string
  subtitleKey?: string
  /** 嵌入「市场数据与指标」等父页时隐藏本页标题 */
  hideHeader?: boolean
  /** 组合数据工作台不展示市场行情 Tab（行情改走市场数据与指标菜单） */
  hideMarketTab?: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [section, setSection] = useState<WorkbenchSection>(lockedSection ?? initialSection)
  const [selectedTable, setSelectedTable] = useState<string>("")
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(() => lastTradeDate())
  const [search, setSearch] = useState("")
  const [selectedQuoteCode, setSelectedQuoteCode] = useState<string | null>(null)
  const [positionDialog, setPositionDialog] = useState<DialogState<EditablePosition>>(EMPTY_DIALOG)
  const [quoteDialog, setQuoteDialog] = useState<DialogState<MarketQuote>>(EMPTY_DIALOG)
  const [orderDialog, setOrderDialog] = useState<DialogState<SimulatedOrder>>(EMPTY_DIALOG)
  const [portfolioDialog, setPortfolioDialog] = useState<DialogState<PortfolioMaster>>(EMPTY_DIALOG)
  const [shareClassDialog, setShareClassDialog] = useState<DialogState<ShareClassMaster>>(EMPTY_DIALOG)
  const [managerDialog, setManagerDialog] = useState<DialogState<PortfolioManagerRecord>>(EMPTY_DIALOG)
  const [valuationDialog, setValuationDialog] = useState<DialogState<ValuationSheetRow>>(EMPTY_DIALOG)
  const [navDialog, setNavDialog] = useState<DialogState<PortfolioNavRow>>(EMPTY_DIALOG)
  const [mmfDialog, setMmfDialog] = useState<DialogState<PortfolioMmfRow>>(EMPTY_DIALOG)

  useEffect(() => {
    setSection(lockedSection ?? initialSection)
    setSearch("")
    setSelectedTable("")
  }, [initialSection, lockedSection])

  const access = useQuery({
    queryKey: ["my-access-context"],
    queryFn: () => fsiApi.getMyAccessContext().then((response) => response.data),
    staleTime: 30_000,
  })
  const catalog = useQuery({
    queryKey: ["data-management", "catalog"],
    queryFn: () => fsiApi.getDataManagementCatalog().then((response) => response.data),
    staleTime: 300_000,
  })
  const workbenchEntities = (catalog.data?.entities ?? []).filter((entity) => {
    if (lockedSection) return entity.id === lockedSection
    if (entity.workbench_hidden) return false
    if (hideMarketTab && entity.id === "market") return false
    return true
  })
  const currentEntity = workbenchEntities.find((entity) => entity.id === section)
    ?? (catalog.data?.entities ?? []).find((entity) => entity.id === section)
  const tableOptions = currentEntity?.tables ?? []
  const resolvedTable = selectedTable || tableOptions[0]?.id || currentEntity?.table?.replace(/^fsi\./, "") || ""
  const selectedTableMeta = tableOptions.find((item) => item.id === resolvedTable) ?? null
  const lockedAssetClass = section === "positions" && selectedTableMeta?.asset_class
    ? String(selectedTableMeta.asset_class)
    : null

  useEffect(() => {
    if (!tableOptions.length) return
    if (!selectedTable || !tableOptions.some((item) => item.id === selectedTable)) {
      setSelectedTable(tableOptions[0].id)
    }
  }, [section, tableOptions, selectedTable])

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
    queryKey: ["data-management", "positions", fundId, asOfDate, search, resolvedTable],
    queryFn: () => fsiApi.listEditablePositions(fundId, asOfDate, search || undefined, resolvedTable || undefined).then((response) => response.data),
    enabled: section === "positions" && Boolean(resolvedTable),
    retry: 1,
  })
  const quotes = useQuery({
    queryKey: ["data-management", "market", asOfDate, search, resolvedTable],
    queryFn: () => fsiApi.listMarketQuotes(asOfDate, search || undefined, undefined, resolvedTable || undefined).then((response) => response.data),
    enabled: section === "market" && Boolean(resolvedTable),
    retry: 1,
  })
  const orders = useQuery({
    queryKey: ["data-management", "trades", fundId, asOfDate],
    queryFn: () => fsiApi.listSimulatedOrders(fundId, asOfDate).then((response) => response.data),
    enabled: section === "trades",
    retry: 1,
  })
  const portfolios = useQuery({
    queryKey: ["data-management", "portfolios", search, resolvedTable, fundId, asOfDate],
    queryFn: () => fsiApi.listPortfolios({
      search: search || undefined,
      table: resolvedTable || undefined,
      fundId: PORTFOLIO_DATE_TABLES.has(resolvedTable) ? fundId : undefined,
      asOfDate: PORTFOLIO_DATE_TABLES.has(resolvedTable) ? asOfDate : undefined,
    }).then((response) => response.data),
    enabled: section === "portfolios" && Boolean(resolvedTable),
    retry: 1,
  })

  useEffect(() => {
    if (section !== "positions") return
    const effective = positions.data?.effective_date
    if (effective && effective !== asOfDate && (positions.data?.count ?? 0) > 0) setAsOfDate(effective)
  }, [section, asOfDate, positions.data?.effective_date, positions.data?.count])

  useEffect(() => {
    if (section !== "market") return
    const effective = quotes.data?.effective_date
    if (effective && effective !== asOfDate && (quotes.data?.count ?? 0) > 0) setAsOfDate(effective)
  }, [section, asOfDate, quotes.data?.effective_date, quotes.data?.count])

  useEffect(() => {
    if (section !== "portfolios" || !PORTFOLIO_DATE_TABLES.has(resolvedTable)) return
    const effective = portfolios.data?.effective_date
    if (effective && effective !== asOfDate && (portfolios.data?.count ?? 0) > 0) setAsOfDate(effective)
  }, [section, resolvedTable, asOfDate, portfolios.data?.effective_date, portfolios.data?.count])

  const quoteItems = quotes.data?.items ?? []
  const selectedQuote = quoteItems.find((item) => item.security_code === selectedQuoteCode) ?? quoteItems[0]
  const quoteHistory = useQuery({
    queryKey: ["data-management", "market-history", selectedQuote?.security_code, asOfDate, resolvedTable],
    queryFn: () => fsiApi.getMarketQuoteHistory(
      selectedQuote!.security_code,
      dateMinus(asOfDate, 90),
      asOfDate,
      selectedQuote!.price_type,
      resolvedTable || undefined,
    ).then((response) => response.data),
    enabled: section === "market" && Boolean(selectedQuote) && Boolean(resolvedTable),
    retry: 1,
  })

  const currentQuery = section === "positions" ? positions : section === "market" ? quotes : section === "trades" ? orders : portfolios
  const requestedDate = section === "positions"
    ? positions.data?.requested_date
    : section === "market"
      ? quotes.data?.requested_date
      : section === "portfolios" && PORTFOLIO_DATE_TABLES.has(resolvedTable)
        ? portfolios.data?.requested_date
        : undefined
  const effectiveDate = section === "positions"
    ? positions.data?.effective_date
    : section === "market"
      ? quotes.data?.effective_date
      : section === "portfolios" && PORTFOLIO_DATE_TABLES.has(resolvedTable)
        ? portfolios.data?.effective_date
        : undefined
  const dateFallback = Boolean(requestedDate && effectiveDate && requestedDate !== effectiveDate)
  const refresh = () => void currentQuery.refetch()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["data-management", section] })

  function changeSection(next: WorkbenchSection) {
    if (lockedSection) return
    if (next === "trades") {
      void navigate({ to: "/trading" })
      return
    }
    if (hideMarketTab && next === "market") {
      void navigate({ to: "/indicator-explorer", search: { tab: "market" } as never })
      return
    }
    setSection(next)
    setSearch("")
    setSelectedTable("")
    void navigate({ to: "/data-management", search: { section: next } })
  }

  useEffect(() => {
    if (!lockedSection && section === "trades") {
      void navigate({ to: "/trading" })
    }
  }, [lockedSection, navigate, section])

  useEffect(() => {
    if (!hideMarketTab || lockedSection) return
    if (section === "market") {
      setSection("positions")
      void navigate({ to: "/data-management", search: { section: "positions" }, replace: true })
    }
  }, [hideMarketTab, lockedSection, navigate, section])

  function downloadCsv() {
    if (section === "positions") {
      const rows = positions.data?.items ?? []
      exportCsv(`positions-${fundId}-${asOfDate}.csv`,
        ["subject_code", "subject_name", "currency", "quantity", "unit_price", "market_value", "weight_pct", "data_source"],
        rows.map((row) => [row.subject_code, row.subject_name, row.currency, row.quantity ?? "", row.unit_price ?? "", row.market_value ?? "", row.weight_pct ?? "", row.data_source ?? ""]))
      return
    }
    if (section === "market") {
      const rows = quoteItems
      exportCsv(`market-quotes-${asOfDate}.csv`,
        ["price_date", "security_code", "market_id", "price_type", "close_price", "price_change_pct", "volume", "data_source"],
        rows.map((row) => [row.price_date, row.security_code, row.market_id, row.price_type, row.close_price, row.price_change_pct ?? "", row.volume ?? "", row.data_source ?? ""]))
      return
    }
    if (section === "trades") {
      const rows = orders.data?.items ?? []
      exportCsv(`simulated-orders-${fundId}-${asOfDate}.csv`,
        ["order_id", "security_code", "trade_side", "asset_class", "trade_amount", "status", "decision"],
        rows.map((row) => [row.order_id, row.security_code, row.trade_side, row.asset_class, row.trade_amount, row.status, row.decision ?? ""]))
      return
    }
    const rows = portfolios.data?.items ?? []
    exportCsv("portfolios.csv",
      ["port_id", "port_name", "port_type", "base_currency", "is_active", "inception_date"],
      rows.map((row) => [row.port_id, row.port_name, row.port_type, row.base_currency, row.is_active, row.inception_date ?? ""]))
  }

  useBindPageContext({
    portfolio: fundId,
    date: asOfDate,
    module: "data-management",
    result: section,
    riskMetrics: {
      section,
      table: currentEntity?.table,
      count: currentQuery.data && "count" in currentQuery.data ? currentQuery.data.count : undefined,
      effective_date: effectiveDate,
    },
  })

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
    if (section === "portfolios" && resolvedTable === "para_portfolio") {
      const totals = new Map<string, number>()
      for (const portfolio of (portfolios.data?.items ?? []) as PortfolioMaster[]) {
        totals.set(portfolio.port_type, (totals.get(portfolio.port_type) ?? 0) + 1)
      }
      return Array.from(totals, ([label, value]) => ({ label, value }))
    }
    return []
  }, [orders.data?.items, portfolios.data?.items, positions.data?.items, resolvedTable, section])

  async function deletePosition(row: EditablePosition) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deleteEditablePosition(fundId, asOfDate, row.subject_code, row.asset_class)
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function deleteQuote(row: MarketQuote) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deleteMarketQuote(row, resolvedTable || undefined)
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

  async function deleteShareClass(row: ShareClassMaster) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deleteShareClass(row.class_id)
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function deleteManager(row: PortfolioManagerRecord) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deletePortfolioManager({
        port_id: row.port_id,
        person_id: row.person_id,
        role: row.role,
        begin_date: row.begin_date,
      })
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function deleteValuation(row: ValuationSheetRow) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deleteValuationSheetRow(fundId, asOfDate, row.subject_code)
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function deleteNav(row: PortfolioNavRow) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deletePortfolioNav(fundId, asOfDate, row.currency)
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    }
  }

  async function deleteMmf(row: PortfolioMmfRow) {
    if (!window.confirm(t("dataManagement.confirmDelete"))) return
    try {
      await fsiApi.deletePortfolioMmf(fundId, asOfDate)
      await invalidate()
      toast.success(t("dataManagement.deleted"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
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
    <div className="space-y-5" data-testid="platform-workbench">
      {!hideHeader ? (
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t(titleKey ?? "dataManagement.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t(subtitleKey ?? "dataManagement.subtitle")}</p>
        </div>
      ) : null}

      {!lockedSection && workbenchEntities.length > 0 ? (
        <Card>
          <CardHeader>
            <ZoneTitle index="00" title={t("dataManagement.catalogTitle")} detail={t("dataManagement.catalogHint")} />
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {workbenchEntities.map((entity) => (
              <button
                key={entity.id}
                type="button"
                className={`rounded-lg border p-3 text-left transition hover:bg-muted/40 ${section === entity.id ? "border-primary bg-primary/5" : ""}`}
                onClick={() => changeSection(entity.id)}
              >
                <div className="text-sm font-medium">{entity.label}</div>
                <div className="mt-1 font-mono text-[11px] text-muted-foreground">{entity.table}</div>
                <p className="mt-2 text-xs text-muted-foreground">{entity.description}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {entity.ops.slice(0, 4).map((op) => <Badge key={op} variant="outline" className="text-[10px]">{op}</Badge>)}
                </div>
              </button>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-5">
          <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
            <CardHeader>
              <ZoneTitle index="01" title={t("dataManagement.parameters")} detail={`${fundId} · ${asOfDate}`} />
            </CardHeader>
            <CardContent className="space-y-4" data-testid="platform-parameter">
              {!lockedSection ? (
                <Tabs value={section} onValueChange={(value) => changeSection(value as WorkbenchSection)}>
                  <TabsList className={hideMarketTab ? "grid w-full max-w-md grid-cols-2" : "grid w-full max-w-xl grid-cols-3"}>
                    <TabsTrigger value="portfolios" data-testid="data-section-portfolios">{t("dataManagement.portfoliosTab")}</TabsTrigger>
                    <TabsTrigger value="positions" data-testid="data-section-positions">{t("dataManagement.positionsTab")}</TabsTrigger>
                    {!hideMarketTab ? (
                      <TabsTrigger value="market" data-testid="data-section-market">{t("dataManagement.marketTab")}</TabsTrigger>
                    ) : null}
                  </TabsList>
                </Tabs>
              ) : null}
              <FsiToolbar
                fundId={fundId}
                onFundChange={setFundId}
                asOfDate={asOfDate}
                onDateChange={setAsOfDate}
                onRefresh={refresh}
                isFetching={currentQuery.isFetching}
                extra={(
                  <div className="flex flex-wrap items-center gap-2">
                    {tableOptions.length > 1 ? (
                      <Select value={resolvedTable} onValueChange={setSelectedTable}>
                        <SelectTrigger className="h-9 w-56" data-testid="data-table-select">
                          <SelectValue placeholder={t("dataManagement.selectTable")} />
                        </SelectTrigger>
                        <SelectContent>
                          {tableOptions.map((option) => (
                            <SelectItem key={option.id} value={option.id}>
                              {option.label} · {option.table}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : null}
                    {section !== "trades" ? (
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
                  </div>
                )}
              />
              {dateFallback ? (
                <div className="rounded-md border border-amber-300 bg-amber-50/60 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/20 dark:text-amber-100">
                  {t("dataManagement.dateFallback", { requested: requestedDate, effective: effectiveDate })}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <ZoneTitle
                index="02"
                title={t("dataManagement.dataArea")}
                detail={[
                  section === "positions"
                    ? t("dataManagement.positionCount", { count: positions.data?.count ?? 0 })
                    : section === "market"
                      ? t("dataManagement.quoteCount", { count: quotes.data?.count ?? 0 })
                      : section === "trades"
                        ? t("dataManagement.orderCount", { count: orders.data?.count ?? 0 })
                        : t("dataManagement.portfolioCount", { count: portfolios.data?.count ?? 0 }),
                  `${t("dataManagement.underlyingTable")}: ${selectedTableMeta?.table ?? currentEntity?.table ?? "—"}`,
                ].filter(Boolean).join(" · ")}
                action={<div className="flex gap-2">
                  <Button size="sm" variant="outline" data-testid="platform-export" onClick={downloadCsv}>
                    <Download className="mr-1 h-4 w-4" />{t("dataManagement.exportCsv")}
                  </Button>
                  <Button size="sm" disabled={!currentCanManage || (section === "positions" && resolvedTable === "all")} onClick={() => {
                    if (section === "positions") setPositionDialog({ open: true, item: null })
                    else if (section === "market") setQuoteDialog({ open: true, item: null })
                    else if (section === "trades") setOrderDialog({ open: true, item: null })
                    else if (resolvedTable === "para_share_class") setShareClassDialog({ open: true, item: null })
                    else if (resolvedTable === "para_portfolio_manager") setManagerDialog({ open: true, item: null })
                    else if (resolvedTable === "balance_valuation_sheet") setValuationDialog({ open: true, item: null })
                    else if (resolvedTable === "balance_portfolio_nav") setNavDialog({ open: true, item: null })
                    else if (resolvedTable === "balance_portfolio_mmf") setMmfDialog({ open: true, item: null })
                    else setPortfolioDialog({ open: true, item: null })
                  }}><Plus className="mr-1 h-4 w-4" />{t("dataManagement.add")}</Button>
                </div>}
              />
            </CardHeader>
            <CardContent data-testid="platform-data">
              {!currentCanManage ? (
                <p className="mb-3 text-xs text-amber-600 dark:text-amber-400">{t("dataManagement.noPermission")}</p>
              ) : null}
              {section === "positions" && resolvedTable === "all" ? (
                <p className="mb-3 text-xs text-muted-foreground">{t("dataManagement.allTablesHint")}</p>
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
              {!currentQuery.isFetching && !currentQuery.isError && section === "portfolios" && resolvedTable === "para_portfolio" ? (
                <PortfolioTable
                  rows={(portfolios.data?.items ?? []) as PortfolioMaster[]}
                  canManage={canManagePortfolios}
                  onEdit={(item) => setPortfolioDialog({ open: true, item })}
                  onDelete={deletePortfolio}
                />
              ) : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "portfolios" && resolvedTable === "para_share_class" ? (
                <ShareClassTable
                  rows={(portfolios.data?.items ?? []) as ShareClassMaster[]}
                  canManage={canManagePortfolios}
                  onEdit={(item) => setShareClassDialog({ open: true, item })}
                  onDelete={deleteShareClass}
                />
              ) : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "portfolios" && resolvedTable === "para_portfolio_manager" ? (
                <PortfolioManagerTable
                  rows={(portfolios.data?.items ?? []) as PortfolioManagerRecord[]}
                  canManage={canManagePortfolios}
                  onEdit={(item) => setManagerDialog({ open: true, item })}
                  onDelete={deleteManager}
                />
              ) : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "portfolios" && resolvedTable === "balance_valuation_sheet" ? (
                <ValuationSheetTable
                  rows={(portfolios.data?.items ?? []) as ValuationSheetRow[]}
                  canManage={canManagePortfolios}
                  onEdit={(item) => setValuationDialog({ open: true, item })}
                  onDelete={deleteValuation}
                />
              ) : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "portfolios" && resolvedTable === "balance_portfolio_nav" ? (
                <PortfolioNavTable
                  rows={(portfolios.data?.items ?? []) as PortfolioNavRow[]}
                  canManage={canManagePortfolios}
                  onEdit={(item) => setNavDialog({ open: true, item })}
                  onDelete={deleteNav}
                />
              ) : null}
              {!currentQuery.isFetching && !currentQuery.isError && section === "portfolios" && resolvedTable === "balance_portfolio_mmf" ? (
                <PortfolioMmfTable
                  rows={(portfolios.data?.items ?? []) as PortfolioMmfRow[]}
                  canManage={canManagePortfolios}
                  onEdit={(item) => setMmfDialog({ open: true, item })}
                  onDelete={deleteMmf}
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
            <CardContent data-testid="platform-charts">
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
      {positionDialog.open ? (
        <PositionDialog
          fundId={fundId}
          asOfDate={asOfDate}
          item={positionDialog.item}
          lockedAssetClass={lockedAssetClass}
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
          table={resolvedTable}
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
      {shareClassDialog.open ? (
        <ShareClassDialog
          item={shareClassDialog.item}
          onClose={() => setShareClassDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setShareClassDialog(EMPTY_DIALOG)
            await invalidate()
          }}
        />
      ) : null}
      {managerDialog.open ? (
        <PortfolioManagerDialog
          item={managerDialog.item}
          onClose={() => setManagerDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setManagerDialog(EMPTY_DIALOG)
            await invalidate()
          }}
        />
      ) : null}
      {valuationDialog.open ? (
        <ValuationSheetDialog
          fundId={fundId}
          asOfDate={asOfDate}
          item={valuationDialog.item}
          onClose={() => setValuationDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setValuationDialog(EMPTY_DIALOG)
            await invalidate()
          }}
        />
      ) : null}
      {navDialog.open ? (
        <PortfolioNavDialog
          fundId={fundId}
          asOfDate={asOfDate}
          item={navDialog.item}
          onClose={() => setNavDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setNavDialog(EMPTY_DIALOG)
            await invalidate()
          }}
        />
      ) : null}
      {mmfDialog.open ? (
        <PortfolioMmfDialog
          fundId={fundId}
          asOfDate={asOfDate}
          item={mmfDialog.item}
          onClose={() => setMmfDialog(EMPTY_DIALOG)}
          onSaved={async () => {
            setMmfDialog(EMPTY_DIALOG)
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
          <TableHead>{t("dataManagement.assetClass")}</TableHead>
          <TableHead>{t("dataManagement.code")}</TableHead><TableHead>{t("dataManagement.name")}</TableHead>
          <TableHead>{t("dataManagement.currency")}</TableHead><TableHead className="text-right">{t("dataManagement.quantity")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.unitPrice")}</TableHead><TableHead className="text-right">{t("dataManagement.marketValue")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.weight")}</TableHead><TableHead>{t("dataManagement.source")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={`${row.asset_class ?? "NA"}:${row.subject_code}`}>
            <TableCell><Badge variant="secondary">{row.asset_class ?? "—"}</Badge></TableCell>
            <TableCell className="font-mono text-xs">{row.subject_code}</TableCell><TableCell className="font-medium">{row.subject_name}</TableCell>
            <TableCell>{row.currency}</TableCell><TableCell className="text-right font-mono">{numeric(row.quantity, 4)}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.unit_price, 6)}</TableCell><TableCell className="text-right font-mono">{money(row.market_value, row.currency)}</TableCell>
            <TableCell className="text-right font-mono">{row.weight_pct == null ? "—" : `${numeric(row.weight_pct)}%`}</TableCell>
            <TableCell><Badge variant="outline">{row.source_table ?? row.data_source ?? "—"}</Badge></TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={10} /> : null}
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

function ShareClassTable({ rows, canManage, onEdit, onDelete }: {
  rows: ShareClassMaster[]
  canManage: boolean
  onEdit: (item: ShareClassMaster) => void
  onDelete: (item: ShareClassMaster) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow>
          <TableHead>{t("dataManagement.code")}</TableHead><TableHead>{t("dataManagement.portfoliosTab")}</TableHead>
          <TableHead>{t("dataManagement.name")}</TableHead><TableHead>{t("dataManagement.currency")}</TableHead>
          <TableHead>{t("dataManagement.status")}</TableHead><TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={row.class_id}>
            <TableCell className="font-mono text-xs">{row.class_id}</TableCell>
            <TableCell className="font-mono text-xs">{row.port_id}</TableCell>
            <TableCell className="font-medium">{row.class_name}</TableCell>
            <TableCell>{row.currency}</TableCell>
            <TableCell><Badge variant={row.is_active ? "default" : "secondary"}>{row.is_active ? t("dataManagement.active") : t("dataManagement.inactive")}</Badge></TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={6} /> : null}
        </TableBody>
      </Table>
    </div>
  )
}

function PortfolioManagerTable({ rows, canManage, onEdit, onDelete }: {
  rows: PortfolioManagerRecord[]
  canManage: boolean
  onEdit: (item: PortfolioManagerRecord) => void
  onDelete: (item: PortfolioManagerRecord) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow>
          <TableHead>{t("dataManagement.portfoliosTab")}</TableHead><TableHead>{t("dataManagement.personId")}</TableHead>
          <TableHead>{t("dataManagement.role")}</TableHead><TableHead>{t("dataManagement.beginDate")}</TableHead>
          <TableHead>{t("dataManagement.endDate")}</TableHead><TableHead>{t("dataManagement.isLead")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={`${row.port_id}-${row.person_id}-${row.role}-${row.begin_date}`}>
            <TableCell className="font-mono text-xs">{row.port_id}</TableCell>
            <TableCell className="font-mono text-xs">{row.person_id}</TableCell>
            <TableCell><Badge variant="outline">{row.role}</Badge></TableCell>
            <TableCell className="font-mono text-xs">{row.begin_date}</TableCell>
            <TableCell className="font-mono text-xs">{row.end_date ?? "—"}</TableCell>
            <TableCell>{row.is_lead ? "✓" : "—"}</TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={7} /> : null}
        </TableBody>
      </Table>
    </div>
  )
}

function ValuationSheetTable({ rows, canManage, onEdit, onDelete }: {
  rows: ValuationSheetRow[]
  canManage: boolean
  onEdit: (item: ValuationSheetRow) => void
  onDelete: (item: ValuationSheetRow) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow>
          <TableHead>{t("dataManagement.code")}</TableHead><TableHead>{t("dataManagement.name")}</TableHead>
          <TableHead>{t("dataManagement.currency")}</TableHead><TableHead className="text-right">{t("dataManagement.quantity")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.unitPrice")}</TableHead><TableHead className="text-right">{t("dataManagement.marketValue")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.weight")}</TableHead><TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={row.subject_code}>
            <TableCell className="font-mono text-xs">{row.subject_code}</TableCell>
            <TableCell className="font-medium">{row.subject_name}</TableCell>
            <TableCell>{row.currency}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.quantity, 4)}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.unit_price, 6)}</TableCell>
            <TableCell className="text-right font-mono">{money(row.market_value, row.currency)}</TableCell>
            <TableCell className="text-right font-mono">{row.weight_pct == null ? "—" : `${numeric(row.weight_pct)}%`}</TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={8} /> : null}
        </TableBody>
      </Table>
    </div>
  )
}

function PortfolioNavTable({ rows, canManage, onEdit, onDelete }: {
  rows: PortfolioNavRow[]
  canManage: boolean
  onEdit: (item: PortfolioNavRow) => void
  onDelete: (item: PortfolioNavRow) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow>
          <TableHead>{t("dataManagement.currency")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.netAsset")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.unitNav")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.accUnitNav")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.dayReturn")}</TableHead>
          <TableHead>{t("dataManagement.shareClass")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={`${row.currency}-${row.class_id ?? "ALL"}`}>
            <TableCell className="font-mono text-xs">{row.currency}</TableCell>
            <TableCell className="text-right font-mono">{money(row.net_asset, row.currency)}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.unit_nav, 6)}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.acc_unit_nav, 6)}</TableCell>
            <TableCell className="text-right font-mono">{row.day_return == null ? "—" : numeric(Number(row.day_return) * 100, 4)}</TableCell>
            <TableCell className="font-mono text-xs">{row.class_id ?? "—"}</TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={7} /> : null}
        </TableBody>
      </Table>
    </div>
  )
}

function PortfolioMmfTable({ rows, canManage, onEdit, onDelete }: {
  rows: PortfolioMmfRow[]
  canManage: boolean
  onEdit: (item: PortfolioMmfRow) => void
  onDelete: (item: PortfolioMmfRow) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow>
          <TableHead className="text-right">{t("dataManagement.incomePer10k")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.return7d")}</TableHead>
          <TableHead className="text-right">{t("dataManagement.navDeviation")}</TableHead>
          <TableHead className="text-right">WAM</TableHead>
          <TableHead className="text-right">WAL</TableHead>
          <TableHead className="text-right">{t("dataManagement.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={`${row.port_id}-${row.evaluate_date}`}>
            <TableCell className="text-right font-mono">{numeric(row.income_per_10k, 4)}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.return_rate_7d, 3)}</TableCell>
            <TableCell className="text-right font-mono">{numeric(row.nav_deviation, 2)}</TableCell>
            <TableCell className="text-right font-mono">{row.wam_days ?? "—"}</TableCell>
            <TableCell className="text-right font-mono">{row.wal_days ?? "—"}</TableCell>
            <TableCell><ActionButtons canManage={canManage} onEdit={() => onEdit(row)} onDelete={() => onDelete(row)} /></TableCell>
          </TableRow>)}
          {!rows.length ? <EmptyRow columns={6} /> : null}
        </TableBody>
      </Table>
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

function ShareClassDialog({ item, onClose, onSaved }: {
  item: ShareClassMaster | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    class_id: item?.class_id ?? "",
    port_id: item?.port_id ?? FUNDS[0].id,
    class_name: item?.class_name ?? "",
    class_name_en: item?.class_name_en ?? "",
    currency: item?.currency ?? "HKD",
    isin: item?.isin ?? "",
    mgmt_fee_bps: item?.mgmt_fee_bps?.toString() ?? "",
    is_active: item?.is_active ?? true,
    inception_date: item?.inception_date ?? "",
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    if (!form.class_id.trim() || !form.port_id.trim() || !form.class_name.trim() || !form.currency.trim()) {
      toast.error(t("dataManagement.required")); return
    }
    const payload: ShareClassPayload = {
      ...(item ? {} : { class_id: form.class_id.trim().toUpperCase(), port_id: form.port_id.trim().toUpperCase() }),
      class_name: form.class_name.trim(),
      class_name_en: form.class_name_en.trim() || null,
      currency: form.currency.trim().toUpperCase(),
      isin: form.isin.trim() || null,
      mgmt_fee_bps: form.mgmt_fee_bps ? Number(form.mgmt_fee_bps) : null,
      is_active: form.is_active,
      inception_date: form.inception_date || null,
    }
    setSaving(true)
    try {
      if (item) await fsiApi.updateShareClass(item.class_id, payload)
      else await fsiApi.createShareClass(payload)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.shareClass")}</DialogTitle></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("dataManagement.code")} value={form.class_id} onChange={set("class_id")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.portfoliosTab")} value={form.port_id} onChange={set("port_id")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.name")} value={form.class_name} onChange={set("class_name")} required />
      <FormField label={t("dataManagement.nameEn")} value={form.class_name_en} onChange={set("class_name_en")} />
      <FormField label={t("dataManagement.currency")} value={form.currency} onChange={set("currency")} required />
      <FormField label="ISIN" value={form.isin} onChange={set("isin")} />
      <FormField label={t("dataManagement.mgmtFee")} value={form.mgmt_fee_bps} onChange={set("mgmt_fee_bps")} type="number" />
      <FormField label={t("dataManagement.inceptionDate")} value={form.inception_date} onChange={set("inception_date")} type="date" />
      <div className="space-y-1.5">
        <Label>{t("dataManagement.active")}</Label>
        <Select value={form.is_active ? "yes" : "no"} onValueChange={(value) => setForm((previous) => ({ ...previous, is_active: value === "yes" }))}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="yes">{t("dataManagement.yes")}</SelectItem><SelectItem value="no">{t("dataManagement.no")}</SelectItem></SelectContent>
        </Select>
      </div>
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("dataManagement.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("dataManagement.saving") : t("dataManagement.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}

function PortfolioManagerDialog({ item, onClose, onSaved }: {
  item: PortfolioManagerRecord | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    port_id: item?.port_id ?? FUNDS[0].id,
    person_id: item?.person_id ?? "",
    role: item?.role ?? "PM",
    begin_date: item?.begin_date ?? new Date().toISOString().slice(0, 10),
    end_date: item?.end_date ?? "",
    is_lead: item?.is_lead ?? false,
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    if (!form.port_id.trim() || !form.person_id.trim() || !form.role.trim() || !form.begin_date) {
      toast.error(t("dataManagement.required")); return
    }
    setSaving(true)
    try {
      if (item) {
        const payload: PortfolioManagerPayload = {
          end_date: form.end_date || null,
          is_lead: form.is_lead,
        }
        await fsiApi.updatePortfolioManager({
          port_id: item.port_id,
          person_id: item.person_id,
          role: item.role,
          begin_date: item.begin_date,
        }, payload)
      } else {
        const payload: PortfolioManagerPayload = {
          port_id: form.port_id.trim().toUpperCase(),
          person_id: form.person_id.trim().toUpperCase(),
          role: form.role.trim().toUpperCase(),
          begin_date: form.begin_date,
          end_date: form.end_date || null,
          is_lead: form.is_lead,
        }
        await fsiApi.createPortfolioManager(payload)
      }
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.portfolioManager")}</DialogTitle></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("dataManagement.portfoliosTab")} value={form.port_id} onChange={set("port_id")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.personId")} value={form.person_id} onChange={set("person_id")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.role")} value={form.role} onChange={set("role")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.beginDate")} value={form.begin_date} onChange={set("begin_date")} type="date" required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.endDate")} value={form.end_date} onChange={set("end_date")} type="date" />
      <div className="space-y-1.5">
        <Label>{t("dataManagement.isLead")}</Label>
        <Select value={form.is_lead ? "yes" : "no"} onValueChange={(value) => setForm((previous) => ({ ...previous, is_lead: value === "yes" }))}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="yes">{t("dataManagement.yes")}</SelectItem><SelectItem value="no">{t("dataManagement.no")}</SelectItem></SelectContent>
        </Select>
      </div>
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("dataManagement.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("dataManagement.saving") : t("dataManagement.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}


function ValuationSheetDialog({ fundId, asOfDate, item, onClose, onSaved }: {
  fundId: string
  asOfDate: string
  item: ValuationSheetRow | null
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
    const payload: ValuationSheetPayload = {
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
      if (item) await fsiApi.updateValuationSheetRow(fundId, asOfDate, item.subject_code, payload)
      else await fsiApi.createValuationSheetRow(fundId, asOfDate, payload)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.valuationSheet")}</DialogTitle><DialogDescription>{fundId} · {asOfDate}</DialogDescription></DialogHeader>
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

function PortfolioNavDialog({ fundId, asOfDate, item, onClose, onSaved }: {
  fundId: string
  asOfDate: string
  item: PortfolioNavRow | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    currency: item?.currency ?? "HKD",
    total_asset: item?.total_asset?.toString() ?? "",
    total_liability: item?.total_liability?.toString() ?? "",
    net_asset: item?.net_asset?.toString() ?? "",
    shares_outstanding: item?.shares_outstanding?.toString() ?? "",
    unit_nav: item?.unit_nav?.toString() ?? "",
    acc_unit_nav: item?.acc_unit_nav?.toString() ?? "",
    day_return: item?.day_return?.toString() ?? "",
    class_id: item?.class_id ?? "",
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    if (!form.currency.trim() || !form.net_asset.trim()) {
      toast.error(t("dataManagement.required")); return
    }
    const payload: PortfolioNavPayload = {
      currency: form.currency.trim().toUpperCase(),
      total_asset: numberOrNull(form.total_asset),
      total_liability: numberOrNull(form.total_liability),
      net_asset: Number(form.net_asset),
      shares_outstanding: numberOrNull(form.shares_outstanding),
      unit_nav: numberOrNull(form.unit_nav),
      acc_unit_nav: numberOrNull(form.acc_unit_nav),
      day_return: numberOrNull(form.day_return),
      class_id: form.class_id.trim().toUpperCase() || null,
    }
    setSaving(true)
    try {
      if (item) await fsiApi.updatePortfolioNav(fundId, asOfDate, item.currency, payload)
      else await fsiApi.createPortfolioNav(fundId, asOfDate, payload)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.portfolioNav")}</DialogTitle><DialogDescription>{fundId} · {asOfDate}</DialogDescription></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("dataManagement.currency")} value={form.currency} onChange={set("currency")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.netAsset")} value={form.net_asset} onChange={set("net_asset")} type="number" required />
      <FormField label={t("dataManagement.totalAsset")} value={form.total_asset} onChange={set("total_asset")} type="number" />
      <FormField label={t("dataManagement.totalLiability")} value={form.total_liability} onChange={set("total_liability")} type="number" />
      <FormField label={t("dataManagement.unitNav")} value={form.unit_nav} onChange={set("unit_nav")} type="number" />
      <FormField label={t("dataManagement.accUnitNav")} value={form.acc_unit_nav} onChange={set("acc_unit_nav")} type="number" />
      <FormField label={t("dataManagement.sharesOutstanding")} value={form.shares_outstanding} onChange={set("shares_outstanding")} type="number" />
      <FormField label={t("dataManagement.dayReturn")} value={form.day_return} onChange={set("day_return")} type="number" />
      <FormField label={t("dataManagement.shareClass")} value={form.class_id} onChange={set("class_id")} />
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("dataManagement.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("dataManagement.saving") : t("dataManagement.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}

function PortfolioMmfDialog({ fundId, asOfDate, item, onClose, onSaved }: {
  fundId: string
  asOfDate: string
  item: PortfolioMmfRow | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    income_per_10k: item?.income_per_10k?.toString() ?? "",
    return_rate_7d: item?.return_rate_7d?.toString() ?? "",
    nav_deviation: item?.nav_deviation?.toString() ?? "",
    nav_deviation_amount: item?.nav_deviation_amount?.toString() ?? "",
    wam_days: item?.wam_days?.toString() ?? "",
    wal_days: item?.wal_days?.toString() ?? "",
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    const payload: PortfolioMmfPayload = {
      income_per_10k: numberOrNull(form.income_per_10k),
      return_rate_7d: numberOrNull(form.return_rate_7d),
      nav_deviation: numberOrNull(form.nav_deviation),
      nav_deviation_amount: numberOrNull(form.nav_deviation_amount),
      wam_days: form.wam_days ? Number(form.wam_days) : null,
      wal_days: form.wal_days ? Number(form.wal_days) : null,
    }
    setSaving(true)
    try {
      if (item) await fsiApi.updatePortfolioMmf(fundId, asOfDate, payload)
      else await fsiApi.createPortfolioMmf(fundId, asOfDate, payload)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.portfolioMmf")}</DialogTitle><DialogDescription>{fundId} · {asOfDate}</DialogDescription></DialogHeader>
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={t("dataManagement.incomePer10k")} value={form.income_per_10k} onChange={set("income_per_10k")} type="number" />
      <FormField label={t("dataManagement.return7d")} value={form.return_rate_7d} onChange={set("return_rate_7d")} type="number" />
      <FormField label={t("dataManagement.navDeviation")} value={form.nav_deviation} onChange={set("nav_deviation")} type="number" />
      <FormField label={t("dataManagement.navDeviationAmount")} value={form.nav_deviation_amount} onChange={set("nav_deviation_amount")} type="number" />
      <FormField label="WAM" value={form.wam_days} onChange={set("wam_days")} type="number" />
      <FormField label="WAL" value={form.wal_days} onChange={set("wal_days")} type="number" />
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

function PositionDialog({ fundId, asOfDate, item, lockedAssetClass, onClose, onSaved }: {
  fundId: string
  asOfDate: string
  item: EditablePosition | null
  lockedAssetClass?: string | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    asset_class: item?.asset_class ?? lockedAssetClass ?? "BOND",
    subject_code: item?.subject_code ?? "",
    subject_name: item?.subject_name ?? "",
    currency: item?.currency ?? "HKD",
    quantity: item?.quantity?.toString() ?? "",
    unit_price: item?.unit_price?.toString() ?? "",
    cost: item?.cost?.toString() ?? "",
    market_value: item?.market_value?.toString() ?? "",
    weight_pct: item?.weight_pct?.toString() ?? "",
    maturity_date: item?.maturity_date ?? "",
    issuer_name: item?.issuer_name ?? "",
    data_source: item?.data_source ?? "MANUAL",
    memo: item?.memo ?? "",
  })
  const set = (key: keyof typeof form) => (value: string) => setForm((previous) => ({ ...previous, [key]: value }))

  async function save() {
    if (!form.subject_code.trim() || !form.subject_name.trim() || !form.currency.trim() || !form.asset_class.trim()) {
      toast.error(t("dataManagement.required")); return
    }
    const payload: EditablePositionPayload = {
      asset_class: form.asset_class.trim().toUpperCase(),
      subject_code: form.subject_code.trim().toUpperCase(),
      subject_name: form.subject_name.trim(),
      currency: form.currency.trim().toUpperCase(),
      quantity: numberOrNull(form.quantity),
      unit_price: numberOrNull(form.unit_price),
      cost: numberOrNull(form.cost),
      market_value: numberOrNull(form.market_value),
      weight_pct: numberOrNull(form.weight_pct),
      maturity_date: form.maturity_date.trim() || null,
      issuer_name: form.issuer_name.trim() || null,
      data_source: form.data_source.trim().toUpperCase() || "MANUAL",
      memo: form.memo.trim() || null,
    }
    setSaving(true)
    try {
      if (item) await fsiApi.updateEditablePosition(fundId, asOfDate, item.subject_code, payload, item.asset_class)
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
      <FormField label={t("dataManagement.assetClass")} value={form.asset_class} onChange={set("asset_class")} required disabled={Boolean(item) || Boolean(lockedAssetClass)} />
      <FormField label={t("dataManagement.code")} value={form.subject_code} onChange={set("subject_code")} required disabled={Boolean(item)} />
      <FormField label={t("dataManagement.name")} value={form.subject_name} onChange={set("subject_name")} required />
      <FormField label={t("dataManagement.currency")} value={form.currency} onChange={set("currency")} required />
      <FormField label={t("dataManagement.quantity")} value={form.quantity} onChange={set("quantity")} type="number" />
      <FormField label={t("dataManagement.unitPrice")} value={form.unit_price} onChange={set("unit_price")} type="number" />
      <FormField label={t("dataManagement.cost")} value={form.cost} onChange={set("cost")} type="number" />
      <FormField label={t("dataManagement.marketValue")} value={form.market_value} onChange={set("market_value")} type="number" />
      <FormField label={t("dataManagement.weight")} value={form.weight_pct} onChange={set("weight_pct")} type="number" />
      <FormField label={t("dataManagement.maturityDate")} value={form.maturity_date} onChange={set("maturity_date")} type="date" />
      <FormField label={t("dataManagement.issuer")} value={form.issuer_name} onChange={set("issuer_name")} />
      <FormField label={t("dataManagement.source")} value={form.data_source} onChange={set("data_source")} required />
      <FormField label={t("dataManagement.memo")} value={form.memo} onChange={set("memo")} />
    </div>
    <DialogFooter><Button variant="outline" onClick={onClose}>{t("dataManagement.cancel")}</Button><Button disabled={saving} onClick={save}>{saving ? t("dataManagement.saving") : t("dataManagement.save")}</Button></DialogFooter>
  </DialogContent></Dialog>
}

function MarketQuoteDialog({ asOfDate, item, table, onClose, onSaved }: {
  asOfDate: string
  item: MarketQuote | null
  table?: string
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
      if (item) await fsiApi.updateMarketQuote(item, payload, table)
      else await fsiApi.createMarketQuote(payload, table)
      await onSaved()
      toast.success(t(item ? "dataManagement.updated" : "dataManagement.created"))
    } catch {
      toast.error(t("dataManagement.operationFailed"))
    } finally { setSaving(false) }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader><DialogTitle>{item ? t("dataManagement.edit") : t("dataManagement.add")} · {t("dataManagement.marketTab")}{table ? ` · ${table}` : ""}</DialogTitle><DialogDescription>{t("dataManagement.audited")}</DialogDescription></DialogHeader>
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
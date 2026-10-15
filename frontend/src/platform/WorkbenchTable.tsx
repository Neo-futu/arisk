/** Framework data grid: optional date range/refresh, sort, filter, selection, export. */
import { ChevronDown, ChevronUp, Download, RefreshCw, Search } from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
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
import { exportCsv } from "@/modules/investment-risk/dashboard-kit"

const ALL = "__all__"

export type WorkbenchColumn<T> = {
  key: string
  header: string
  align?: "left" | "right"
  sortable?: boolean
  filterable?: boolean
  accessor: (row: T) => string | number | null | undefined
  cell?: (row: T) => ReactNode
  exportValue?: (row: T) => string | number | null | undefined
}

export type WorkbenchDateRange = {
  startDate: string
  endDate: string
}

export type WorkbenchView<T> = {
  visible: T[]
  selected: T[]
}

function compare(left: string | number | null | undefined, right: string | number | null | undefined) {
  if (left == null && right == null) return 0
  if (left == null || left === "") return 1
  if (right == null || right === "") return -1
  const leftNumber = typeof left === "number" ? left : Number(left)
  const rightNumber = typeof right === "number" ? right : Number(right)
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && String(left).trim() !== "" && String(right).trim() !== "") {
    return leftNumber - rightNumber
  }
  return String(left).localeCompare(String(right), "zh-Hans-CN", { numeric: true })
}

export function WorkbenchTable<T>({
  title,
  rows,
  columns,
  rowId,
  dateRange,
  onDateRangeChange,
  onRefresh,
  refreshing = false,
  loading = false,
  error,
  emptyText,
  selectedIds: controlledSelectedIds,
  onSelectedIdsChange,
  onViewChange,
  exportFilename = "export.csv",
  rowPicker,
  initialSortKey = null,
  selectable = true,
  toolbarExtra,
  /** 表体容器 class；默认固定高度，筛选后也不改变页面布局 */
  bodyClassName,
  /** 嵌入外层固定高度容器：铺满父级、隐藏标题，表体 flex 填满剩余空间 */
  embedded = false,
}: {
  title: string
  rows: T[]
  columns: WorkbenchColumn<T>[]
  rowId: (row: T) => string
  dateRange?: WorkbenchDateRange
  onDateRangeChange?: (next: WorkbenchDateRange) => void
  onRefresh?: () => void
  refreshing?: boolean
  loading?: boolean
  error?: string | null
  emptyText?: string
  selectedIds?: string[]
  onSelectedIdsChange?: (ids: string[]) => void
  onViewChange?: (view: WorkbenchView<T>) => void
  exportFilename?: string
  rowPicker?: { label: string; text: (row: T) => string }
  initialSortKey?: string | null
  selectable?: boolean
  toolbarExtra?: ReactNode
  bodyClassName?: string
  embedded?: boolean
}) {
  const resolvedBodyClassName =
    bodyClassName ??
    (embedded
      ? "min-h-0 flex-1 overflow-auto rounded-lg border"
      : "h-[360px] overflow-auto rounded-lg border")
  const { t } = useTranslation()
  const [query, setQuery] = useState("")
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({})
  const [pickedIds, setPickedIds] = useState<string[]>([])
  const [sortKey, setSortKey] = useState<string | null>(initialSortKey)
  const [sortDesc, setSortDesc] = useState(true)
  const [internalSelectedIds, setInternalSelectedIds] = useState<string[]>([])
  const selectedIds = controlledSelectedIds ?? internalSelectedIds
  const setSelectedIds = onSelectedIdsChange ?? setInternalSelectedIds
  const rangeInvalid = dateRange ? dateRange.startDate > dateRange.endDate : false
  const filterable = columns.filter((column) => column.filterable)
  const showDateRange = Boolean(dateRange && onDateRangeChange)

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const matched = rows.filter((row) => {
      if (needle) {
        const haystack = columns.map((column) => String(column.accessor(row) ?? "")).join(" ").toLowerCase()
        if (!haystack.includes(needle)) return false
      }
      return filterable.every((column) => {
        const chosen = columnFilters[column.key]
        if (!chosen || chosen === ALL) return true
        return String(column.accessor(row) ?? "") === chosen
      }) && (pickedIds.length === 0 || pickedIds.includes(rowId(row)))
    })
    if (!sortKey) return matched
    const column = columns.find((item) => item.key === sortKey)
    if (!column) return matched
    return [...matched].sort((left, right) => {
      const order = compare(column.accessor(left), column.accessor(right))
      return sortDesc ? -order : order
    })
  }, [columnFilters, columns, filterable, pickedIds, query, rowId, rows, sortDesc, sortKey])

  const selected = visible.filter((row) => selectedIds.includes(rowId(row)))
  const allChecked = visible.length > 0 && visible.every((row) => selectedIds.includes(rowId(row)))
  const viewKey = `${visible.map(rowId).join(",")}#${selected.map(rowId).join(",")}`

  useEffect(() => {
    onViewChange?.({ visible, selected: selected.length ? selected : visible })
  }, [viewKey]) // eslint-disable-line react-hooks/exhaustive-deps -- fire when the visible/selected identity changes

  function toggleSort(key: string) {
    if (sortKey === key) setSortDesc((current) => !current)
    else {
      setSortKey(key)
      setSortDesc(true)
    }
  }

  function exportRows() {
    const source = selected.length ? selected : visible
    exportCsv(
      exportFilename,
      columns.map((column) => column.header),
      source.map((row) => columns.map((column) => (column.exportValue ?? column.accessor)(row))),
    )
  }

  return (
    <Card className={embedded ? "flex h-full flex-col border-0 shadow-none" : undefined}>
      <CardHeader className={embedded ? "shrink-0 space-y-2 p-0 pb-3" : "space-y-3"}>
        {embedded ? null : <CardTitle className="text-base">{title}</CardTitle>}
        <div className="flex flex-wrap items-end gap-2">
          {showDateRange && dateRange && onDateRangeChange ? (
            <>
              <div className="space-y-1">
                <Label className="text-xs">{t("platform.startDate")}</Label>
                <Input
                  type="date"
                  className="h-9 w-40"
                  value={dateRange.startDate}
                  onChange={(event) => onDateRangeChange({ ...dateRange, startDate: event.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("platform.endDate")}</Label>
                <Input
                  type="date"
                  className="h-9 w-40"
                  value={dateRange.endDate}
                  onChange={(event) => onDateRangeChange({ ...dateRange, endDate: event.target.value })}
                />
              </div>
            </>
          ) : null}
          {rowPicker ? (
            <div className="space-y-1">
              <Label className="text-xs">{rowPicker.label}</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="h-9 w-52 justify-between font-normal">
                    <span className="truncate">
                      {pickedIds.length === 0 ? t("platform.all") : t("platform.pickedCount", { count: pickedIds.length })}
                    </span>
                    <ChevronDown className="h-4 w-4 opacity-60" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="start" className="w-72 p-2">
                  <button
                    type="button"
                    className="mb-1 w-full rounded px-2 py-1.5 text-left text-sm hover:bg-muted"
                    onClick={() => setPickedIds([])}
                  >
                    {t("platform.all")}
                  </button>
                  <div className="max-h-64 space-y-1 overflow-auto">
                    {rows.map((row) => {
                      const id = rowId(row)
                      const checked = pickedIds.includes(id)
                      return (
                        <label key={id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted">
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(next) => setPickedIds((current) => next === true ? [...current, id] : current.filter((item) => item !== id))}
                          />
                          <span className="truncate">{rowPicker.text(row)}</span>
                        </label>
                      )
                    })}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          ) : null}
          {filterable.map((column) => {
            const options = Array.from(new Set(rows.map((row) => String(column.accessor(row) ?? "")).filter(Boolean))).sort()
            return (
              <div key={column.key} className="space-y-1">
                <Label className="text-xs">{column.header}</Label>
                <Select
                  value={columnFilters[column.key] ?? ALL}
                  onValueChange={(value) => setColumnFilters((current) => ({ ...current, [column.key]: value }))}
                >
                  <SelectTrigger className="h-9 w-36"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>{t("platform.all")}</SelectItem>
                    {options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )
          })}
          {toolbarExtra}
          <div className="relative min-w-48 flex-1">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input className="h-9 pl-8" value={query} placeholder={t("platform.search")} onChange={(event) => setQuery(event.target.value)} />
          </div>
          <div className="ml-auto flex items-end gap-2">
            <Button variant="outline" size="sm" disabled={!visible.length} onClick={exportRows}>
              <Download className="mr-1 h-4 w-4" />{t("platform.export")}
            </Button>
            {onRefresh ? (
              <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing || rangeInvalid}>
                <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
                {t("platform.refresh")}
              </Button>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className={embedded ? "flex min-h-0 flex-1 flex-col p-0" : undefined}>
        {error ? <p className="mb-3 text-sm text-destructive">{error}</p> : null}
        <div className={resolvedBodyClassName}>
          {loading ? (
            <p className="flex h-full items-center justify-center text-sm text-muted-foreground">{t("platform.loading")}</p>
          ) : !visible.length ? (
            <p className="flex h-full items-center justify-center text-sm text-muted-foreground">{emptyText ?? t("platform.empty")}</p>
          ) : (
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-background">
                <TableRow>
                  {selectable ? (
                    <TableHead className="w-10">
                      <Checkbox
                        checked={allChecked}
                        onCheckedChange={(checked) => setSelectedIds(checked === true ? visible.map(rowId) : [])}
                        aria-label={title}
                      />
                    </TableHead>
                  ) : null}
                  {columns.map((column) => {
                    const active = sortKey === column.key
                    const Icon = active && !sortDesc ? ChevronUp : ChevronDown
                    return (
                      <TableHead key={column.key} className={column.align === "right" ? "text-right" : ""} aria-sort={active ? (sortDesc ? "descending" : "ascending") : "none"}>
                        {column.sortable === false ? column.header : (
                          <button
                            type="button"
                            className={`inline-flex items-center gap-1 font-medium hover:text-primary ${column.align === "right" ? "ml-auto" : ""}`}
                            onClick={(event) => {
                              event.stopPropagation()
                              toggleSort(column.key)
                            }}
                          >
                            {column.header}
                            <Icon className={`h-3.5 w-3.5 ${active ? "text-primary" : "text-muted-foreground/50"}`} />
                          </button>
                        )}
                      </TableHead>
                    )
                  })}
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((row) => {
                  const id = rowId(row)
                  const checked = selectedIds.includes(id)
                  return (
                    <TableRow
                      key={id}
                      data-state={checked ? "selected" : undefined}
                      className={selectable ? "cursor-pointer" : undefined}
                      onClick={selectable ? () => setSelectedIds(checked ? selectedIds.filter((item) => item !== id) : [...selectedIds, id]) : undefined}
                    >
                      {selectable ? (
                        <TableCell onClick={(event) => event.stopPropagation()}>
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(next) => setSelectedIds(next === true ? [...selectedIds, id] : selectedIds.filter((item) => item !== id))}
                            aria-label={id}
                          />
                        </TableCell>
                      ) : null}
                      {columns.map((column) => (
                        <TableCell key={column.key} className={column.align === "right" ? "text-right" : ""}>
                          {column.cell ? column.cell(row) : String(column.accessor(row) ?? "—")}
                        </TableCell>
                      ))}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

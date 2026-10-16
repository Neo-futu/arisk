import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import type { SecurityHolding, SecurityHoldingsResult } from "@/fsiClient"
import { WorkbenchTable, type WorkbenchColumn } from "@/platform/WorkbenchTable"

/** 固定資產類別順序；未命中一律歸入最後一類「衍生品及其他」。 */
const FIXED_ASSET_CLASSES = [
  "BOND",
  "EQUITY",
  "CD",
  "DEPOSIT",
  "CASH",
  "REPO",
  "FUND",
  "DERIVATIVE_OTHER",
] as const

type FixedAssetClass = (typeof FIXED_ASSET_CLASSES)[number]
type HoldingRow = SecurityHolding & { _rowKey: string }

const ASSET_CLASS_ALIASES: Record<string, FixedAssetClass> = {
  BOND: "BOND",
  BOND_GOVT: "BOND",
  BOND_CORP: "BOND",
  BOND_CONVERT: "BOND",
  BOND_ABS: "BOND",
  EQUITY: "EQUITY",
  STOCK: "EQUITY",
  CD: "CD",
  DEPOSIT: "DEPOSIT",
  CASH: "CASH",
  REPO: "REPO",
  REV_REPO: "REPO",
  FUND: "FUND",
  FUND_PUBLIC: "FUND",
  FUND_ETF: "FUND",
  CP: "DERIVATIVE_OTHER",
  FUTURES: "DERIVATIVE_OTHER",
  OPTIONS: "DERIVATIVE_OTHER",
  OTHER: "DERIVATIVE_OTHER",
  UNKNOWN: "DERIVATIVE_OTHER",
  UNMAPPED_CASH: "DERIVATIVE_OTHER",
}

function normalizeAssetClass(type: string | null | undefined): FixedAssetClass {
  if (!type) return "DERIVATIVE_OTHER"
  const key = type.trim().toUpperCase()
  return ASSET_CLASS_ALIASES[key] ?? "DERIVATIVE_OTHER"
}

function assetClassLabel(type: string, t: (key: string) => string) {
  const normalized = normalizeAssetClass(type)
  return t(`investmentRisk.indicators.assetClass.${normalized}`)
}

const BOND_SUBTYPE_ALIASES: Record<string, string> = {
  BOND_GOVT: "BOND_GOVT",
  GOVT: "BOND_GOVT",
  TREASURY: "BOND_GOVT",
  GOVERNMENT: "BOND_GOVT",
  BOND_CORP: "BOND_CORP",
  CORP: "BOND_CORP",
  CREDIT: "BOND_CORP",
  BOND_CONVERT: "BOND_CONVERT",
  CONVERT: "BOND_CONVERT",
  CONVERTIBLE: "BOND_CONVERT",
  BOND_ABS: "BOND_ABS",
  ABS: "BOND_ABS",
  BOND_OTHER: "BOND_OTHER",
  OTHER: "BOND_OTHER",
}

function normalizeBondSubtype(type: string | null | undefined): string {
  if (!type) return "BOND_OTHER"
  const key = type.trim().toUpperCase()
  return BOND_SUBTYPE_ALIASES[key] ?? "BOND_OTHER"
}

function bondSubtypeLabel(type: string | null | undefined, t: (key: string) => string) {
  return t(`investmentRisk.indicators.bondSubtype.${normalizeBondSubtype(type)}`)
}

function fmtPct(v: number | null | undefined, digits = 3) {
  if (v == null || Number.isNaN(Number(v))) return "0.000%"
  return `${Number(v).toFixed(digits)}%`
}

function fmtMoney(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return "0"
  return Number(v).toLocaleString("zh-HK", { maximumFractionDigits: 0 })
}

function fmtRate(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return "—"
  const n = Number(v)
  return `${(Math.abs(n) <= 1 ? n * 100 : n).toFixed(3)}%`
}

function fmtNum(v: number | null | undefined, digits = 2) {
  if (v == null || Number.isNaN(Number(v))) return "—"
  return Number(v).toFixed(digits)
}

function emptyGroup(assetClass: FixedAssetClass) {
  return {
    asset_class: assetClass,
    count: 0,
    market_value_base: 0,
    weight_pct: 0,
    holdings: [] as SecurityHolding[],
  }
}

function buildFixedGroups(rows: SecurityHolding[]) {
  const buckets = Object.fromEntries(
    FIXED_ASSET_CLASSES.map((assetClass) => [assetClass, emptyGroup(assetClass)]),
  ) as Record<FixedAssetClass, ReturnType<typeof emptyGroup>>

  for (const row of rows) {
    const assetClass = normalizeAssetClass(row.asset_class)
    const bucket = buckets[assetClass]
    bucket.holdings.push({ ...row, asset_class: assetClass })
    bucket.count += 1
    bucket.market_value_base += row.market_value_base || 0
    bucket.weight_pct += row.weight_pct || 0
  }

  return FIXED_ASSET_CLASSES.map((assetClass) => buckets[assetClass])
}

function subtypeDisplay(row: SecurityHolding, t: (key: string) => string) {
  if (normalizeAssetClass(row.asset_class) === "BOND" || row.sub_asset_class) {
    return bondSubtypeLabel(row.sub_asset_class, t)
  }
  return "—"
}

function holdingRowId(row: SecurityHolding, index = 0) {
  return `${row.asset_class}|${row.security_code}|${row.issuer_name ?? ""}|${row.maturity_date ?? ""}|${row.market_value_base ?? 0}|${index}`
}

function useHoldingColumns(t: (key: string) => string) {
  return useMemo<WorkbenchColumn<HoldingRow>[]>(() => [
    {
      key: "security_code",
      header: t("investmentRisk.overview.code"),
      accessor: (row) => row.security_code,
      cell: (row) => <span className="font-mono text-xs">{row.security_code}</span>,
    },
    {
      key: "security_name",
      header: t("investmentRisk.overview.name"),
      accessor: (row) => row.security_name,
      cell: (row) => (
        <span className="max-w-48 truncate font-medium" title={row.security_name}>
          {row.security_name}
        </span>
      ),
    },
    {
      key: "asset_class",
      header: t("positions.colType"),
      filterable: true,
      accessor: (row) => assetClassLabel(row.asset_class, t),
      cell: (row) => (
        <Badge variant="secondary" className="text-xs">
          {assetClassLabel(row.asset_class, t)}
        </Badge>
      ),
    },
    {
      key: "sub_asset_class",
      header: t("investmentRisk.indicators.subAssetClassCol"),
      filterable: true,
      accessor: (row) => subtypeDisplay(row, t),
      cell: (row) => {
        const subtype = subtypeDisplay(row, t)
        return subtype === "—" ? "—" : <Badge variant="outline" className="text-xs">{subtype}</Badge>
      },
    },
    { key: "issuer_name", header: t("investmentRisk.overview.issuer"), accessor: (row) => row.issuer_name ?? "—" },
    { key: "sector", header: t("investmentRisk.overview.sector"), filterable: true, accessor: (row) => row.sector ?? "—" },
    { key: "rating", header: t("investmentRisk.overview.rating"), filterable: true, accessor: (row) => row.rating ?? "—" },
    {
      key: "market_value_base",
      header: t("investmentRisk.overview.marketValue"),
      align: "right",
      accessor: (row) => row.market_value_base,
      cell: (row) => <span className="font-mono">{fmtMoney(row.market_value_base)}</span>,
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.overview.pctNav"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{fmtPct(row.weight_pct)}</span>,
    },
    {
      key: "ytm",
      header: t("investmentRisk.overview.ytm"),
      align: "right",
      accessor: (row) => row.ytm,
      cell: (row) => <span className="font-mono">{fmtRate(row.ytm)}</span>,
    },
    {
      key: "duration",
      header: t("investmentRisk.overview.duration"),
      align: "right",
      accessor: (row) => row.duration,
      cell: (row) => <span className="font-mono">{fmtNum(row.duration)}</span>,
    },
    {
      key: "coupon_rate",
      header: t("investmentRisk.overview.coupon"),
      align: "right",
      accessor: (row) => row.coupon_rate,
      cell: (row) => <span className="font-mono">{fmtRate(row.coupon_rate)}</span>,
    },
    { key: "maturity_date", header: t("investmentRisk.overview.maturity"), accessor: (row) => row.maturity_date ?? "—" },
    {
      key: "unrealized_pnl",
      header: t("investmentRisk.overview.unrealizedPnl"),
      align: "right",
      accessor: (row) => row.unrealized_pnl,
      cell: (row) => <span className="font-mono">{fmtMoney(row.unrealized_pnl)}</span>,
    },
  ], [t])
}

export function HoldingsDetailSection({
  fundId,
  asOfDate,
  data,
  isFetching,
  isError,
}: {
  fundId: string
  asOfDate: string
  data?: SecurityHoldingsResult
  isFetching: boolean
  isError: boolean
}) {
  const { t } = useTranslation()
  const holdings = useMemo(
    () => (data?.holdings ?? []).map((row, index) => ({ ...row, _rowKey: holdingRowId(row, index) })),
    [data?.holdings],
  )
  const byAssetClass = useMemo(
    () =>
      buildFixedGroups(holdings).map((group) => ({
        ...group,
        holdings: group.holdings.map((row, index) => ({ ...row, _rowKey: holdingRowId(row, index) })),
      })),
    [holdings],
  )
  const holdingColumns = useHoldingColumns(t)

  const summaryColumns = useMemo<WorkbenchColumn<(typeof byAssetClass)[number]>[]>(() => [
    {
      key: "asset_class",
      header: t("positions.colType"),
      filterable: true,
      accessor: (row) => assetClassLabel(row.asset_class, t),
    },
    {
      key: "count",
      header: t("investmentRisk.overview.positionCount"),
      align: "right",
      accessor: (row) => row.count,
    },
    {
      key: "market_value_base",
      header: t("investmentRisk.overview.marketValue"),
      align: "right",
      accessor: (row) => row.market_value_base,
      cell: (row) => <span className="font-mono">{fmtMoney(row.market_value_base)}</span>,
    },
    {
      key: "weight_pct",
      header: t("investmentRisk.overview.pctNav"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => <span className="font-mono">{fmtPct(row.weight_pct)}</span>,
    },
  ], [t])

  if (isFetching && !data) {
    return <p className="text-muted-foreground animate-pulse text-sm">{t("investmentRisk.common.loading")}</p>
  }

  if (isError) {
    return (
      <Card className="border-destructive">
        <CardContent className="text-destructive pt-4 text-sm">
          {t("positions.loadError")}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold">{t("investmentRisk.indicators.holdingsAllTitle")}</h2>
        <p className="text-muted-foreground text-sm">
          {fundId} · {asOfDate} · {t("positions.countLabel", { count: holdings.length })}
        </p>
      </div>

      <WorkbenchTable
        title={t("investmentRisk.indicators.holdingsTypeSummary")}
        rows={byAssetClass}
        columns={summaryColumns}
        rowId={(row) => row.asset_class}
        exportFilename={`holdings-type-summary-${fundId}-${asOfDate}.csv`}
        initialSortKey="weight_pct"
      />

      <WorkbenchTable
        title={t("investmentRisk.indicators.holdingsAllTitle")}
        rows={holdings}
        columns={holdingColumns}
        rowId={(row) => row._rowKey}
        exportFilename={`security-holdings-${fundId}-${asOfDate}.csv`}
        initialSortKey="weight_pct"
      />

      <div className="space-y-4">
        <h2 className="text-base font-semibold">{t("investmentRisk.indicators.holdingsByTypeTitle")}</h2>
        {byAssetClass.map((group) => (
          <WorkbenchTable
            key={group.asset_class}
            title={`${assetClassLabel(group.asset_class, t)} · ${t("positions.countLabel", { count: group.count })} · ${fmtPct(group.weight_pct)}`}
            rows={group.holdings}
            columns={holdingColumns}
            rowId={(row) => row._rowKey}
            exportFilename={`holdings-${group.asset_class}-${fundId}-${asOfDate}.csv`}
            initialSortKey="weight_pct"
            emptyText={t("investmentRisk.indicators.holdingsEmptyCategory")}
          />
        ))}
      </div>
    </div>
  )
}

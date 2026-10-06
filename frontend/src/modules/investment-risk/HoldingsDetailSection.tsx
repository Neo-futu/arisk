import { Download, Search } from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { SecurityHolding, SecurityHoldingsResult } from "@/fsiClient"
import { exportCsv } from "@/modules/investment-risk/dashboard-kit"

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

/** 債券子類別映射（來自 fsi.asset_class ENUM / balance_bond.asset_subtype） */
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

function SecurityHoldingsTable({ rows }: { rows: SecurityHolding[] }) {
  const { t } = useTranslation()
  if (!rows.length) {
    return (
      <p className="text-muted-foreground py-6 text-center text-sm">
        {t("investmentRisk.indicators.holdingsEmptyCategory")}
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("investmentRisk.overview.code")}</TableHead>
            <TableHead>{t("investmentRisk.overview.name")}</TableHead>
            <TableHead>{t("positions.colType")}</TableHead>
            <TableHead>{t("investmentRisk.indicators.subAssetClassCol")}</TableHead>
            <TableHead>{t("investmentRisk.overview.issuer")}</TableHead>
            <TableHead>{t("investmentRisk.overview.sector")}</TableHead>
            <TableHead>{t("investmentRisk.overview.rating")}</TableHead>
            <TableHead className="text-right">{t("investmentRisk.overview.marketValue")}</TableHead>
            <TableHead className="text-right">{t("investmentRisk.overview.pctNav")}</TableHead>
            <TableHead className="text-right">{t("investmentRisk.overview.ytm")}</TableHead>
            <TableHead className="text-right">{t("investmentRisk.overview.duration")}</TableHead>
            <TableHead className="text-right">{t("investmentRisk.overview.coupon")}</TableHead>
            <TableHead>{t("investmentRisk.overview.maturity")}</TableHead>
            <TableHead className="text-right">{t("investmentRisk.overview.unrealizedPnl")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => {
            const subtype = subtypeDisplay(row, t)
            return (
            <TableRow key={`${row.asset_class}-${row.security_code}-${index}`}>
              <TableCell className="font-mono text-xs">{row.security_code}</TableCell>
              <TableCell className="max-w-48 truncate font-medium" title={row.security_name}>
                {row.security_name}
              </TableCell>
              <TableCell>
                <Badge variant="secondary" className="text-xs">
                  {assetClassLabel(row.asset_class, t)}
                </Badge>
              </TableCell>
              <TableCell>
                {subtype === "—" ? (
                  "—"
                ) : (
                  <Badge variant="outline" className="text-xs">
                    {subtype}
                  </Badge>
                )}
              </TableCell>
              <TableCell className="max-w-36 truncate" title={row.issuer_name ?? undefined}>
                {row.issuer_name ?? "—"}
              </TableCell>
              <TableCell>{row.sector ?? "—"}</TableCell>
              <TableCell>{row.rating ?? "—"}</TableCell>
              <TableCell className="text-right font-mono">{fmtMoney(row.market_value_base)}</TableCell>
              <TableCell className="text-right font-mono">{fmtPct(row.weight_pct)}</TableCell>
              <TableCell className="text-right font-mono">{fmtRate(row.ytm)}</TableCell>
              <TableCell className="text-right font-mono">{fmtNum(row.duration)}</TableCell>
              <TableCell className="text-right font-mono">{fmtRate(row.coupon_rate)}</TableCell>
              <TableCell className="font-mono text-xs">{row.maturity_date ?? "—"}</TableCell>
              <TableCell className="text-right font-mono">{fmtMoney(row.unrealized_pnl)}</TableCell>
            </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
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
  const [query, setQuery] = useState("")
  const holdings = data?.holdings ?? []

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return holdings
    return holdings.filter((row) => {
      const haystack = [
        row.security_code,
        row.security_name,
        row.asset_class,
        row.sub_asset_class,
        row.issuer_name,
        row.sector,
        row.rating,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      return haystack.includes(keyword)
    })
  }, [holdings, query])

  const byAssetClass = useMemo(() => buildFixedGroups(filtered), [filtered])

  function exportAll() {
    exportCsv(
      `investment-risk-security-holdings-${fundId}-${asOfDate}.csv`,
      [
        t("investmentRisk.overview.code"),
        t("investmentRisk.overview.name"),
        t("positions.colType"),
        t("investmentRisk.indicators.subAssetClassCol"),
        t("investmentRisk.overview.issuer"),
        t("investmentRisk.overview.sector"),
        t("investmentRisk.overview.rating"),
        t("investmentRisk.overview.marketValue"),
        t("investmentRisk.overview.pctNav"),
        t("investmentRisk.overview.ytm"),
        t("investmentRisk.overview.duration"),
        t("investmentRisk.overview.coupon"),
        t("investmentRisk.overview.maturity"),
        t("investmentRisk.overview.unrealizedPnl"),
      ],
      filtered.map((row) => [
        row.security_code,
        row.security_name,
        assetClassLabel(row.asset_class, t),
        subtypeDisplay(row, t),
        row.issuer_name,
        row.sector,
        row.rating,
        row.market_value_base,
        row.weight_pct,
        row.ytm,
        row.duration,
        row.coupon_rate,
        row.maturity_date,
        row.unrealized_pnl,
      ]),
    )
  }

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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("investmentRisk.indicators.holdingsAllTitle")}</h2>
          <p className="text-muted-foreground text-sm">
            {fundId} · {asOfDate} · {t("positions.countLabel", { count: filtered.length })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 rounded-md border px-3 py-2">
            <Search className="text-muted-foreground h-4 w-4" />
            <Input
              className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
              placeholder={t("investmentRisk.indicators.holdingsSearch")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <Button variant="outline" size="sm" onClick={exportAll}>
            <Download className="mr-2 h-4 w-4" />
            {t("investmentRisk.common.export")}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("investmentRisk.indicators.holdingsTypeSummary")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("positions.colType")}</TableHead>
                <TableHead className="text-right">{t("investmentRisk.overview.positionCount")}</TableHead>
                <TableHead className="text-right">{t("investmentRisk.overview.marketValue")}</TableHead>
                <TableHead className="text-right">{t("investmentRisk.overview.pctNav")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {byAssetClass.map((group) => (
                <TableRow key={group.asset_class}>
                  <TableCell className="font-medium">{assetClassLabel(group.asset_class, t)}</TableCell>
                  <TableCell className="text-right">{group.count}</TableCell>
                  <TableCell className="text-right font-mono">{fmtMoney(group.market_value_base)}</TableCell>
                  <TableCell className="text-right font-mono">{fmtPct(group.weight_pct)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("investmentRisk.indicators.holdingsAllTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <SecurityHoldingsTable rows={filtered} />
        </CardContent>
      </Card>

      <div className="space-y-4">
        <h2 className="text-base font-semibold">{t("investmentRisk.indicators.holdingsByTypeTitle")}</h2>
        {byAssetClass.map((group) => (
          <Card key={group.asset_class}>
            <CardHeader>
              <CardTitle className="text-base">
                {assetClassLabel(group.asset_class, t)}
                <span className="text-muted-foreground ml-2 text-sm font-normal">
                  {t("positions.countLabel", { count: group.count })} · {fmtPct(group.weight_pct)}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <SecurityHoldingsTable rows={group.holdings} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

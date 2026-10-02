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
import { exportCsv } from "@/modules/investment-risk/dashboard-kit"
import { SqlViewButton } from "@/modules/investment-risk/SqlViewButton"

export type EquityBetaConstituent = {
  security_code: string
  security_name: string
  weight_pct: number
  beta: number
  sample_size: number
}

export function EquityBetaContributionCard({
  fundId,
  asOfDate,
  portfolioBeta,
  benchmarkId,
  constituents,
  applicable,
}: {
  fundId: string
  asOfDate: string
  portfolioBeta?: number | null
  benchmarkId?: string | null
  constituents: EquityBetaConstituent[]
  applicable?: boolean
}) {
  const { t } = useTranslation()
  const [query, setQuery] = useState("")
  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return constituents
    return constituents.filter((row) => {
      const haystack = `${row.security_code} ${row.security_name}`.toLowerCase()
      return haystack.includes(keyword)
    })
  }, [constituents, query])

  function exportRows() {
    exportCsv(
      `equity-beta-contribution-${fundId}-${asOfDate}.csv`,
      [
        t("investmentRisk.overview.code"),
        t("investmentRisk.overview.name"),
        t("investmentRisk.overview.weight"),
        t("investmentRisk.indicators.betaValue"),
        t("investmentRisk.indicators.sampleSize"),
      ],
      filtered.map((row) => [row.security_code, row.security_name, row.weight_pct, row.beta, row.sample_size]),
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">{t("investmentRisk.indicators.betaTitle")}</CardTitle>
            {applicable === true ? (
              <Badge className="bg-emerald-600 hover:bg-emerald-600">{t("investmentRisk.common.applicableSuggested")}</Badge>
            ) : applicable === false ? (
              <Badge variant="outline" className="text-muted-foreground" title={t("investmentRisk.indicators.betaNotApplicable")}>
                {t("investmentRisk.common.notApplicable")}
              </Badge>
            ) : null}
            {portfolioBeta != null ? (
              <Badge variant="secondary">
                {t("investmentRisk.indicators.equityBeta")} {portfolioBeta.toFixed(3)}
              </Badge>
            ) : null}
            {benchmarkId ? <Badge variant="outline">{benchmarkId}</Badge> : null}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 rounded-md border px-3 py-2">
              <Search className="text-muted-foreground h-4 w-4" />
              <Input
                className="h-8 w-56 border-0 p-0 shadow-none focus-visible:ring-0"
                placeholder={t("investmentRisk.indicators.searchConstituent")}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <Button variant="outline" size="sm" onClick={exportRows}>
              <Download className="mr-2 h-4 w-4" />
              {t("investmentRisk.common.export")}
            </Button>
            <SqlViewButton sqlIds={["SQL-RI-04"]} />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("investmentRisk.overview.code")}</TableHead>
              <TableHead>{t("investmentRisk.overview.name")}</TableHead>
              <TableHead className="text-right">{t("investmentRisk.overview.weight")}</TableHead>
              <TableHead className="text-right">{t("investmentRisk.indicators.betaValue")}</TableHead>
              <TableHead className="text-right">{t("investmentRisk.indicators.sampleSize")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((row) => (
              <TableRow key={row.security_code}>
                <TableCell className="font-mono">{row.security_code}</TableCell>
                <TableCell>{row.security_name}</TableCell>
                <TableCell className="text-right font-mono">
                  {row.weight_pct == null ? "—" : `${Number(row.weight_pct).toFixed(2)}%`}
                </TableCell>
                <TableCell className="text-right font-mono">{row.beta.toFixed(3)}</TableCell>
                <TableCell className="text-right">{row.sample_size}</TableCell>
              </TableRow>
            ))}
            {!filtered.length ? (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground h-20 text-center">
                  {t("investmentRisk.common.empty")}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

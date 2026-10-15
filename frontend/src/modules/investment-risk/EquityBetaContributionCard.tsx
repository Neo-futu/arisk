import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { WorkbenchTable, type WorkbenchColumn } from "@/platform/WorkbenchTable"
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
  const columns = useMemo<WorkbenchColumn<EquityBetaConstituent>[]>(() => [
    {
      key: "security_code",
      header: t("investmentRisk.overview.code"),
      accessor: (row) => row.security_code,
      cell: (row) => <span className="font-mono">{row.security_code}</span>,
    },
    { key: "security_name", header: t("investmentRisk.overview.name"), accessor: (row) => row.security_name },
    {
      key: "weight_pct",
      header: t("investmentRisk.overview.weight"),
      align: "right",
      accessor: (row) => row.weight_pct,
      cell: (row) => (
        <span className="font-mono">
          {row.weight_pct == null ? "—" : `${Number(row.weight_pct).toFixed(2)}%`}
        </span>
      ),
    },
    {
      key: "beta",
      header: t("investmentRisk.indicators.betaValue"),
      align: "right",
      accessor: (row) => row.beta,
      cell: (row) => <span className="font-mono">{row.beta.toFixed(3)}</span>,
    },
    {
      key: "sample_size",
      header: t("investmentRisk.indicators.sampleSize"),
      align: "right",
      accessor: (row) => row.sample_size,
    },
  ], [t])

  return (
    <WorkbenchTable
      title={t("investmentRisk.indicators.betaTitle")}
      rows={constituents}
      columns={columns}
      rowId={(row) => row.security_code}
      exportFilename={`equity-beta-contribution-${fundId}-${asOfDate}.csv`}
      initialSortKey="weight_pct"
      toolbarExtra={(
        <div className="flex flex-wrap items-center gap-2">
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
          <SqlViewButton sqlIds={["SQL-RI-04"]} />
        </div>
      )}
    />
  )
}

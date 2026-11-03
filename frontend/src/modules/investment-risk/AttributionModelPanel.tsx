import { useMutation, useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { DatePicker } from "@/components/DatePicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi, type PerformanceAttributionResult } from "@/fsiClient"

type BrinsonGroupBy = "asset" | "industry" | "symbol" | "portfolio"
type CampisiGroupBy = "industry" | "symbol" | "portfolio" | "asset"
type ContributionMode = "single" | "average" | "daily|carino" | "pnl"
type ContributionGroupBy = "symbol" | "asset" | "industry" | "portfolio"

function percent(value: number | null | undefined, digits = 3) {
  return value == null ? "—" : `${Number(value).toFixed(digits)}%`
}

export function AttributionModelPanel({
  fundId,
  startDate,
  endDate,
}: {
  fundId: string
  startDate: string
  endDate: string
}) {
  const { t } = useTranslation()
  const [brinsonStart, setBrinsonStart] = useState(startDate)
  const [brinsonEnd, setBrinsonEnd] = useState(endDate)
  const [brinsonBenchmarkId, setBrinsonBenchmarkId] = useState("")
  const [campisiStart, setCampisiStart] = useState(startDate)
  const [campisiEnd, setCampisiEnd] = useState(endDate)
  const [campisiBenchmarkId, setCampisiBenchmarkId] = useState("")
  const [brinsonMethod, setBrinsonMethod] = useState<"BHB" | "BF">("BHB")
  const [brinsonMode, setBrinsonMode] = useState<"single" | "grap">("grap")
  const [brinsonGroup, setBrinsonGroup] = useState<BrinsonGroupBy>("asset")
  const [campisiBenchmark, setCampisiBenchmark] = useState<"absolute" | "bench">("bench")
  const [campisiMode, setCampisiMode] = useState<"single" | "multi">("multi")
  const [campisiGroup, setCampisiGroup] = useState<CampisiGroupBy>("industry")
  const [contribStart, setContribStart] = useState(startDate)
  const [contribEnd, setContribEnd] = useState(endDate)
  const [contribMode, setContribMode] = useState<ContributionMode>("daily|carino")
  const [contribGroup, setContribGroup] = useState<ContributionGroupBy>("symbol")

  useEffect(() => {
    setBrinsonStart(startDate)
    setBrinsonEnd(endDate)
    setCampisiStart(startDate)
    setCampisiEnd(endDate)
    setContribStart(startDate)
    setContribEnd(endDate)
  }, [startDate, endDate])

  const benchmarks = useQuery({
    queryKey: ["attribution-benchmarks", fundId, endDate],
    queryFn: () => fsiApi.getAttributionBenchmarks(fundId, endDate).then((response) => response.data),
    enabled: Boolean(fundId && endDate),
  })
  useEffect(() => {
    const assigned = benchmarks.data?.benchmarks.find((item) => item.assigned && item.benchmark_role === "PRIMARY")
      ?? benchmarks.data?.benchmarks.find((item) => item.assigned)
    if (!assigned) return
    if (!brinsonBenchmarkId) setBrinsonBenchmarkId(assigned.benchmark_id)
    if (!campisiBenchmarkId) setCampisiBenchmarkId(assigned.benchmark_id)
  }, [benchmarks.data, brinsonBenchmarkId, campisiBenchmarkId])

  const brinsonCalc = useMutation({
    mutationFn: () => fsiApi.getAttributionModels(fundId, brinsonStart, brinsonEnd, brinsonBenchmarkId || undefined).then((response) => response.data),
  })
  const campisiCalc = useMutation({
    mutationFn: () => fsiApi.getAttributionModels(fundId, campisiStart, campisiEnd, campisiBenchmarkId || undefined).then((response) => response.data),
  })
  const contribCalc = useMutation({
    mutationFn: () => fsiApi.getAttributionModels(fundId, contribStart, contribEnd).then((response) => response.data),
  })
  const brinsonResult = brinsonCalc.data
  const campisiResult = campisiCalc.data
  const contribResult = contribCalc.data
  const brinson = brinsonResult?.brinson_model?.views?.[`${brinsonMethod}|${brinsonMode}|${brinsonGroup}`]
  const campisi = campisiResult?.campisi_model?.views?.[`${campisiBenchmark}|${campisiMode}|${campisiGroup}`]
  const contribViewKey = contribMode === "daily|carino" ? `daily|carino|${contribGroup}` : `${contribMode}|${contribGroup}`
  const contrib = contribResult?.contribution_model?.views?.[contribViewKey]
  const benchmarkOptions = (benchmarks.data?.benchmarks ?? []).map((item) => [
    item.benchmark_id,
    `${item.assigned ? "★ " : ""}${item.benchmark_name} (${item.benchmark_id})`,
  ] as [string, string])
  const contribModeOptions: Array<[ContributionMode, string]> = [
    ["single", t("investmentRisk.attribution.contribSingle")],
    ["average", t("investmentRisk.attribution.contribAverage")],
    ["daily|carino", t("investmentRisk.attribution.contribDaily")],
  ]
  if (contribResult?.contribution_model?.has_pnl) {
    contribModeOptions.push(["pnl", t("investmentRisk.attribution.contribPnl")])
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("investmentRisk.attribution.modelContributionTitle")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("investmentRisk.attribution.modelContributionHint")}</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 dark:border-emerald-900 dark:bg-emerald-950/20">
            <ModelRunBar
              start={contribStart}
              end={contribEnd}
              onStart={setContribStart}
              onEnd={setContribEnd}
              pending={contribCalc.isPending}
              canExport={Boolean(contribResult?.contribution_model)}
              onCalc={() => contribCalc.mutate()}
              onExport={() => contribResult?.contribution_model && exportContributionExcel(fundId, contribStart, contribEnd, contribResult.contribution_model)}
            />
            <div className="flex flex-wrap gap-2">
              <Select
                label={t("investmentRisk.attribution.modelHorizon")}
                value={contribMode}
                onChange={(value) => setContribMode(value as ContributionMode)}
                options={contribModeOptions}
              />
              <Select
                label={t("investmentRisk.attribution.modelGroup")}
                value={contribGroup}
                onChange={(value) => setContribGroup(value as ContributionGroupBy)}
                options={[
                  ["symbol", t("investmentRisk.attribution.groupSymbol")],
                  ["asset", t("investmentRisk.attribution.groupAsset")],
                  ["industry", t("investmentRisk.attribution.groupIndustry")],
                  ["portfolio", t("investmentRisk.attribution.groupPortfolio")],
                ]}
              />
            </div>
          </div>
          {contribResult?.contribution_model ? (
            <p className="text-muted-foreground text-xs">
              {t("investmentRisk.attribution.contribLive", {
                ms: contribResult.elapsed_ms,
                periods: contribResult.contribution_model.period_count ?? 0,
                holdings: contribResult.contribution_model.holding_count ?? 0,
              })}
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">{t("investmentRisk.attribution.contribReady")}</p>
          )}
          {contribCalc.isError ? <p className="text-destructive text-sm">{t("investmentRisk.attribution.loadError")}</p> : null}
          {contrib ? (
            <>
              <div className="grid gap-2 md:grid-cols-3">
                <Mini label={t("investmentRisk.attribution.contribPortfolioReturn")} value={percent(contrib.portfolio_return_pct)} />
                <Mini label={t("investmentRisk.attribution.contribTotal")} value={percent(contrib.contribution_total_pct)} />
                <Mini label={t("investmentRisk.attribution.contribResidual")} value={percent(contrib.residual_pct)} />
              </div>
              <div className="max-h-80 overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("investmentRisk.attribution.modelGroup")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.colFundWeight")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.contribSecurityReturn")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.colContribution")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {contrib.groups.map((row) => (
                      <TableRow key={row.group}>
                        <TableCell className="font-medium">{row.security_name || row.group}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.weight_pct, 2)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.return_pct)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.contribution_pct)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : contribResult?.contribution_model ? (
            <p className="text-muted-foreground text-sm">{t("investmentRisk.attribution.modelEmpty")}</p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("investmentRisk.attribution.modelBrinsonTitle")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("investmentRisk.attribution.modelBrinsonHint")}</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-3 rounded-lg border border-sky-200 bg-sky-50/50 p-3 dark:border-sky-900 dark:bg-sky-950/20">
            <ModelRunBar
              start={brinsonStart}
              end={brinsonEnd}
              onStart={setBrinsonStart}
              onEnd={setBrinsonEnd}
              benchmarkId={brinsonBenchmarkId}
              onBenchmark={setBrinsonBenchmarkId}
              benchmarkOptions={benchmarkOptions}
              pending={brinsonCalc.isPending}
              canExport={Boolean(brinsonResult)}
              onCalc={() => brinsonCalc.mutate()}
              onExport={() => brinsonResult && exportBrinsonExcel(fundId, brinsonStart, brinsonEnd, brinsonResult.brinson_model)}
            />
            <div className="flex flex-wrap gap-2">
              <Select
                label={t("investmentRisk.attribution.modelMethod")}
                value={brinsonMethod}
                onChange={(value) => setBrinsonMethod(value as "BHB" | "BF")}
                options={[
                  ["BHB", "BHB"],
                  ["BF", "BF"],
                ]}
              />
              <Select
                label={t("investmentRisk.attribution.modelHorizon")}
                value={brinsonMode}
                onChange={(value) => setBrinsonMode(value as "single" | "grap")}
                options={[
                  ["single", t("investmentRisk.attribution.modelSingle")],
                  ["grap", t("investmentRisk.attribution.modelMulti")],
                ]}
              />
              <Select
                label={t("investmentRisk.attribution.modelGroup")}
                value={brinsonGroup}
                onChange={(value) => setBrinsonGroup(value as BrinsonGroupBy)}
                options={[
                  ["asset", t("investmentRisk.attribution.groupAsset")],
                  ["industry", t("investmentRisk.attribution.groupIndustry")],
                  ["symbol", t("investmentRisk.attribution.groupSymbol")],
                  ["portfolio", t("investmentRisk.attribution.groupPortfolio")],
                ]}
              />
            </div>
          </div>
          {brinsonResult ? (
            <p className="text-muted-foreground text-xs">
              {t("investmentRisk.attribution.modelLive", {
                ms: brinsonResult.elapsed_ms,
                benchmark: benchmarkOptions.find(([id]) => id === brinsonBenchmarkId)?.[1] ?? brinsonResult.brinson_model?.benchmark_id ?? "—",
                source: brinsonResult.brinson_model?.benchmark_source === "index_component"
                  ? t("investmentRisk.attribution.modelSourceIndex")
                  : t("investmentRisk.attribution.modelSourceProxy"),
                periods: brinsonResult.brinson_model?.period_count ?? 0,
              })}
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">{t("investmentRisk.attribution.modelReady")}</p>
          )}
          {brinsonCalc.isError ? <p className="text-destructive text-sm">{t("investmentRisk.attribution.loadError")}</p> : null}
          {brinson ? (
            <>
              <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
                <Mini label={t("investmentRisk.attribution.fundReturn")} value={percent(brinson.portfolio_return_pct)} />
                <Mini label={t("investmentRisk.attribution.benchmarkReturn")} value={percent(brinson.benchmark_return_pct)} />
                <Mini label={t("investmentRisk.attribution.activeReturn")} value={percent(brinson.active_return_pct)} />
                <Mini label={t("investmentRisk.attribution.allocationEffect")} value={percent(brinson.allocation_effect_pct)} />
                <Mini label={t("investmentRisk.attribution.selectionEffect")} value={percent(brinson.selection_effect_pct)} />
                <Mini label={t("investmentRisk.attribution.interactionEffect")} value={percent(brinson.interaction_effect_pct)} />
              </div>
              <div className="max-h-80 overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("investmentRisk.attribution.modelGroup")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.colFundWeight")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.colBenchmarkWeight")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.colAllocationEffect")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.colSelectionEffect")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.colInteractionEffect")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.activeReturn")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {brinson.groups.map((row) => (
                      <TableRow key={row.group}>
                        <TableCell className="font-medium">{row.group}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.portfolio_weight_pct, 2)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.benchmark_weight_pct, 2)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.allocation_effect_pct)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.selection_effect_pct)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.interaction_effect_pct)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.active_return_pct)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : brinsonResult ? (
            <p className="text-muted-foreground text-sm">{t("investmentRisk.attribution.modelEmpty")}</p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("investmentRisk.attribution.modelCampisiTitle")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("investmentRisk.attribution.modelCampisiHint")}</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-900 dark:bg-amber-950/20">
            <ModelRunBar
              start={campisiStart}
              end={campisiEnd}
              onStart={setCampisiStart}
              onEnd={setCampisiEnd}
              benchmarkId={campisiBenchmarkId}
              onBenchmark={setCampisiBenchmarkId}
              benchmarkOptions={benchmarkOptions}
              pending={campisiCalc.isPending}
              canExport={Boolean(campisiResult)}
              onCalc={() => campisiCalc.mutate()}
              onExport={() => campisiResult && exportCampisiExcel(fundId, campisiStart, campisiEnd, campisiResult.campisi_model)}
            />
            <div className="flex flex-wrap gap-2">
              <Select
                label={t("investmentRisk.attribution.modelBenchmark")}
                value={campisiBenchmark}
                onChange={(value) => setCampisiBenchmark(value as "absolute" | "bench")}
                options={[
                  ["absolute", t("investmentRisk.attribution.campisiAbsolute")],
                  ["bench", t("investmentRisk.attribution.campisiBenchmark")],
                ]}
              />
              <Select
                label={t("investmentRisk.attribution.modelHorizon")}
                value={campisiMode}
                onChange={(value) => setCampisiMode(value as "single" | "multi")}
                options={[
                  ["single", t("investmentRisk.attribution.modelSingle")],
                  ["multi", t("investmentRisk.attribution.modelMultiCampisi")],
                ]}
              />
              <Select
                label={t("investmentRisk.attribution.modelGroup")}
                value={campisiGroup}
                onChange={(value) => setCampisiGroup(value as CampisiGroupBy)}
                options={[
                  ["asset", t("investmentRisk.attribution.groupAsset")],
                  ["industry", t("investmentRisk.attribution.groupIndustry")],
                  ["symbol", t("investmentRisk.attribution.groupSymbol")],
                  ["portfolio", t("investmentRisk.attribution.groupPortfolio")],
                ]}
              />
            </div>
          </div>
          {campisiResult ? (
            <p className="text-muted-foreground text-xs">
              {t("investmentRisk.attribution.modelLive", {
                ms: campisiResult.elapsed_ms,
                benchmark: benchmarkOptions.find(([id]) => id === campisiBenchmarkId)?.[1] ?? campisiResult.brinson_model?.benchmark_id ?? "—",
                source: campisiResult.brinson_model?.benchmark_source === "index_component"
                  ? t("investmentRisk.attribution.modelSourceIndex")
                  : t("investmentRisk.attribution.modelSourceProxy"),
                periods: campisiResult.campisi_model?.period_count ?? 0,
              })}
              {campisiBenchmark === "absolute"
                ? ` · ${t("investmentRisk.attribution.campisiSelectionAbsoluteHint")}`
                : ` · ${t("investmentRisk.attribution.campisiSelectionBenchHint")}`}
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">{t("investmentRisk.attribution.modelReady")}</p>
          )}
          {campisiCalc.isError ? <p className="text-destructive text-sm">{t("investmentRisk.attribution.loadError")}</p> : null}
          {campisi ? (
            <>
              <div className="grid gap-2 md:grid-cols-5">
                <Mini label={t("investmentRisk.attribution.campisiTotal")} value={percent(campisi.total_return_pct)} />
                <Mini label={t("investmentRisk.attribution.campisiIncome")} value={percent(campisi.income_effect_pct)} />
                <Mini label={t("investmentRisk.attribution.campisiTreasury")} value={percent(campisi.treasury_effect_pct)} />
                <Mini label={t("investmentRisk.attribution.campisiSpread")} value={percent(campisi.spread_effect_pct)} />
                <Mini label={t("investmentRisk.attribution.campisiSelection")} value={percent(campisi.selection_effect_pct)} />
              </div>
              <div className="max-h-80 overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("investmentRisk.attribution.modelGroup")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.colFundWeight")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.campisiTotal")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.campisiIncome")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.campisiTreasury")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.campisiSpread")}</TableHead>
                      <TableHead className="text-right">{t("investmentRisk.attribution.campisiSelection")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {campisi.groups.map((row) => (
                      <TableRow key={row.group}>
                        <TableCell className="font-medium">{row.group}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.weight_pct, 2)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.total_return_pct)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.income_effect_pct)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.treasury_effect_pct)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.spread_effect_pct)}</TableCell>
                        <TableCell className="text-right font-mono">{percent(row.selection_effect_pct)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : campisiResult ? (
            <p className="text-muted-foreground text-sm">{t("investmentRisk.attribution.modelEmpty")}</p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}

function ModelRunBar({
  start,
  end,
  onStart,
  onEnd,
  benchmarkId,
  onBenchmark,
  benchmarkOptions,
  pending,
  canExport,
  onCalc,
  onExport,
}: {
  start: string
  end: string
  onStart: (value: string) => void
  onEnd: (value: string) => void
  benchmarkId?: string
  onBenchmark?: (value: string) => void
  benchmarkOptions?: Array<[string, string]>
  pending: boolean
  canExport: boolean
  onCalc: () => void
  onExport: () => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">{t("investmentRisk.attribution.start")}</span>
        <DatePicker value={start} onChange={onStart} />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">{t("investmentRisk.attribution.modelEnd")}</span>
        <DatePicker value={end} onChange={onEnd} />
      </label>
      {onBenchmark && benchmarkOptions ? (
        <label className="flex min-w-[220px] flex-col gap-1 text-xs">
          <span className="text-muted-foreground">{t("investmentRisk.attribution.modelBenchmarkPick")}</span>
          <select
            className="rounded-md border bg-background px-2 py-2 text-sm"
            value={benchmarkId ?? ""}
            onChange={(event) => onBenchmark(event.target.value)}
          >
            <option value="">{t("investmentRisk.attribution.benchmarkUnset")}</option>
            {benchmarkOptions.map(([id, text]) => (
              <option key={id} value={id}>{text}</option>
            ))}
          </select>
        </label>
      ) : null}
      <Button size="sm" disabled={pending || start > end} onClick={onCalc}>
        {pending ? t("investmentRisk.attribution.calculating") : t("investmentRisk.attribution.modelCalc")}
      </Button>
      <Button size="sm" variant="outline" disabled={!canExport} onClick={onExport}>
        {t("investmentRisk.attribution.modelExport")}
      </Button>
    </div>
  )
}

function exportBrinsonExcel(
  fundId: string,
  start: string,
  end: string,
  model: PerformanceAttributionResult["brinson_model"],
) {
  const rows = Object.entries(model?.views ?? {}).flatMap(([key, view]) =>
    (view?.groups ?? []).map((row) => [
      key, view.method, row.group, row.portfolio_weight_pct, row.benchmark_weight_pct,
      row.allocation_effect_pct, row.selection_effect_pct, row.interaction_effect_pct, row.active_return_pct,
    ]),
  )
  downloadSheet(
    `brinson-${fundId}-${start}-${end}.xls`,
    "Brinson",
    ["视图", "方案", "分组", "组合权重%", "基准权重%", "配置%", "选择%", "交互%", "超额%"],
    rows,
    3,
  )
}

function exportCampisiExcel(
  fundId: string,
  start: string,
  end: string,
  model: PerformanceAttributionResult["campisi_model"],
) {
  const rows = Object.entries(model?.views ?? {}).flatMap(([key, view]) =>
    (view?.groups ?? []).map((row) => [
      key, row.group, row.weight_pct, row.total_return_pct, row.income_effect_pct,
      row.treasury_effect_pct, row.spread_effect_pct, row.selection_effect_pct,
    ]),
  )
  downloadSheet(
    `campisi-${fundId}-${start}-${end}.xls`,
    "Campisi",
    ["视图", "分组", "权重%", "总收益%", "收入%", "国债%", "利差%", "择券%"],
    rows,
    2,
  )
}

function exportContributionExcel(
  fundId: string,
  start: string,
  end: string,
  model: NonNullable<PerformanceAttributionResult["contribution_model"]>,
) {
  const rows = Object.entries(model.views ?? {}).flatMap(([key, view]) =>
    (view?.groups ?? []).map((row) => [
      key, row.group, row.security_name ?? "", row.weight_pct, row.return_pct, row.contribution_pct,
    ]),
  )
  downloadSheet(
    `contribution-${fundId}-${start}-${end}.xls`,
    "Contribution",
    ["视图", "分组", "名称", "权重%", "收益率%", "贡献%"],
    rows,
    3,
  )
}

function downloadSheet(
  filename: string,
  sheet: string,
  headers: string[],
  rows: Array<Array<string | number>>,
  textColumns: number,
) {
  const xml = `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<Worksheet ss:Name="${sheet}"><Table>
<Row>${headers.map((cell) => `<Cell><Data ss:Type="String">${cell}</Data></Cell>`).join("")}</Row>
${rows.map((row) => `<Row>${row.map((cell, index) => `<Cell><Data ss:Type="${index < textColumns ? "String" : "Number"}">${escapeXml(cell)}</Data></Cell>`).join("")}</Row>`).join("")}
</Table></Worksheet>
</Workbook>`
  const blob = new Blob([xml], { type: "application/vnd.ms-excel" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function escapeXml(value: string | number | null | undefined) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: Array<[string, string]>
}) {
  return (
    <label className="flex items-center gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <select
        className="rounded-md border bg-background px-2 py-1 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map(([id, text]) => (
          <option key={id} value={id}>
            {text}
          </option>
        ))}
      </select>
    </label>
  )
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-2">
      <p className="text-muted-foreground text-[11px]">{label}</p>
      <p className="font-mono text-sm font-semibold">{value}</p>
    </div>
  )
}

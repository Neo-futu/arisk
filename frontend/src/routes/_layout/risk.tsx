import { useQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { FUNDS, FsiToolbar, lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { fsiApi, type VarCompareResult } from "@/fsiClient"

export const Route = createFileRoute("/_layout/risk")({
  component: RiskPage,
  beforeLoad: () => {
    throw redirect({ to: "/investment-risk/indicators" })
  },
  head: () => ({ meta: [{ title: "投資風險分析 — ARISK" }] }),
})

const METHOD_LABEL_KEYS: Record<string, string> = {
  historical: "riskPage.methodHistorical",
  monte_carlo: "riskPage.methodMonteCarlo",
  distribution: "riskPage.methodDistribution",
}

function VarTable({ data }: { data: VarCompareResult }) {
  const { t } = useTranslation()
  const maxMethod = data.results.find(
    (r) => r.var_pct_nav === data.max_var_pct_nav,
  )?.method_requested

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("riskPage.colMethod")}</TableHead>
          <TableHead className="text-right">{t("riskPage.colVarHkd")}</TableHead>
          <TableHead className="text-right">{t("riskPage.colVarPct")}</TableHead>
          <TableHead className="text-right">{t("riskPage.colCvarHkd")}</TableHead>
          <TableHead className="text-right">{t("riskPage.colSampleSize")}</TableHead>
          <TableHead className="text-right">{t("riskPage.colNote")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.results.map((r) => {
          const isMax = r.method_requested === maxMethod
          return (
            <TableRow key={r.method_requested} className={isMax ? "bg-muted/50" : ""}>
              <TableCell className="font-medium">
                {METHOD_LABEL_KEYS[r.method_requested ?? ""]
                  ? t(METHOD_LABEL_KEYS[r.method_requested ?? ""])
                  : r.method_requested}
              </TableCell>
              <TableCell className="text-right font-mono">
                {Number(r.var_hkd).toLocaleString("zh-HK", { maximumFractionDigits: 0 })}
              </TableCell>
              <TableCell className="text-right font-mono">
                {Number(r.var_pct_nav).toFixed(4)}%
              </TableCell>
              <TableCell className="text-right font-mono">
                {Number(r.cvar_hkd).toLocaleString("zh-HK", { maximumFractionDigits: 0 })}
              </TableCell>
              <TableCell className="text-right">{r.sample_size}</TableCell>
              <TableCell className="text-right">
                {isMax && <Badge variant="secondary" className="text-xs">{t("riskPage.mostConservative")}</Badge>}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

function RiskPage() {
  const { t } = useTranslation()
  const [fundId, setFundId] = useState(FUNDS[0].id)
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)
  const [confidence, setConfidence] = useState("0.99")

  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["var-compare", fundId, asOfDate, confidence],
    queryFn: () =>
      fsiApi.getVarCompare(fundId, asOfDate, { confidence: Number(confidence) }).then((r) => r.data),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
  })

  const confidenceSelect = (
    <Select value={confidence} onValueChange={setConfidence}>
      <SelectTrigger className="w-28">
        <SelectValue placeholder={t("riskPage.confidencePlaceholder")} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="0.95">95%</SelectItem>
        <SelectItem value="0.99">99%</SelectItem>
      </SelectContent>
    </Select>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("riskPage.title")}</h1>
        <p className="text-muted-foreground text-sm">
          {t("riskPage.subtitle")}
        </p>
      </div>

      <FsiToolbar
        fundId={fundId} onFundChange={setFundId}
        asOfDate={asOfDate} onDateChange={setAsOfDate}
        onRefresh={() => refetch()} isFetching={isFetching}
        extra={confidenceSelect}
      />

      {isFetching && <p className="text-muted-foreground text-sm animate-pulse">{t("riskPage.calculating")}</p>}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {t("riskPage.loadError")}
          </CardContent>
        </Card>
      )}
      {data && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                {fundId} · {asOfDate} · {t("riskPage.confidenceLabel", { value: (Number(confidence) * 100).toFixed(0) })}
              </CardTitle>
              <Badge variant="outline">
                {t("riskPage.maxVar", { value: data.max_var_pct_nav.toFixed(4) })}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <VarTable data={data} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

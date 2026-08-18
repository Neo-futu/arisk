import { useQuery } from "@tanstack/react-query"
import { Check, Code2, Copy } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fsiApi, type IndicatorSql } from "@/fsiClient"

interface SqlViewButtonProps {
  /** SQL 片段 ID（來自驗證文檔，如 "SQL-RI-01"），支持多個 */
  sqlIds: string[]
  label?: string
  className?: string
}

function CopyButton({ sql }: { sql: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        void navigator.clipboard?.writeText(sql)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
    >
      {copied ? <Check className="mr-1 h-3.5 w-3.5" /> : <Copy className="mr-1 h-3.5 w-3.5" />}
      {copied ? t("investmentRisk.sqlView.copied") : t("investmentRisk.sqlView.copy")}
    </Button>
  )
}

function SqlBlock({ id, entry }: { id: string; entry: IndicatorSql | undefined }) {
  const { t } = useTranslation()
  if (!entry) {
    return (
      <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        {t("investmentRisk.sqlView.notFound", { id })}
      </div>
    )
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono text-[11px]">{entry.id}</Badge>
          <span className="text-sm font-medium">{entry.title}</span>
        </div>
        <CopyButton sql={entry.sql} />
      </div>
      <pre className="max-h-[52vh] overflow-auto rounded-md bg-muted p-3 font-mono text-xs leading-relaxed">
        {entry.sql}
      </pre>
    </div>
  )
}

export function SqlViewButton({ sqlIds, label, className }: SqlViewButtonProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const catalogQuery = useQuery({
    queryKey: ["indicator-sql-catalog"],
    queryFn: () => fsiApi.getIndicatorSqlCatalog().then((response) => response.data.items),
    enabled: open,
    staleTime: 5 * 60_000,
  })

  const byId = new Map((catalogQuery.data ?? []).map((item) => [item.id, item]))

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className={className}>
          <Code2 className="mr-1 h-3.5 w-3.5" />
          {label ?? t("investmentRisk.common.viewSql")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("investmentRisk.sqlView.title")}</DialogTitle>
          <DialogDescription>
            {t("investmentRisk.sqlView.description")}
          </DialogDescription>
        </DialogHeader>

        {catalogQuery.isLoading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t("investmentRisk.sqlView.loading")}</p>
        ) : sqlIds.length === 1 ? (
          <SqlBlock id={sqlIds[0]} entry={byId.get(sqlIds[0])} />
        ) : (
          <Tabs defaultValue={sqlIds[0]}>
            <TabsList className="flex-wrap">
              {sqlIds.map((id) => (
                <TabsTrigger key={id} value={id} className="font-mono text-xs">{id}</TabsTrigger>
              ))}
            </TabsList>
            {sqlIds.map((id) => (
              <TabsContent key={id} value={id} className="mt-3">
                <SqlBlock id={id} entry={byId.get(id)} />
              </TabsContent>
            ))}
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default SqlViewButton

import { useQuery } from "@tanstack/react-query"
import { Bot, Copy, Download, Search } from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fsiApi } from "@/fsiClient"
import { useBindPageContext } from "@/platform/page-context"

const ALL = "__all__"

function ZoneTitle({ index, title, detail, action }: { index: string; title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-semibold text-primary">{index}</span>
        <div>
          <CardTitle className="text-base">{title}</CardTitle>
          {detail ? <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p> : null}
        </div>
      </div>
      {action}
    </div>
  )
}

function downloadText(filename: string, content: string, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type: mime })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

export function SqlLibraryPage() {
  const { t } = useTranslation()
  const [group, setGroup] = useState(ALL)
  const [category, setCategory] = useState(ALL)
  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [aiContext, setAiContext] = useState<{ markdown: string; asset_count: number; truncated: boolean } | null>(null)
  const [loadingContext, setLoadingContext] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [search])

  const catalog = useQuery({
    queryKey: ["sql-catalog", group, category, debouncedSearch],
    queryFn: () => fsiApi.getSqlAssetCatalog({
      group: group === ALL ? undefined : group,
      category: category === ALL ? undefined : category,
      search: debouncedSearch || undefined,
    }).then((r) => r.data),
    retry: 1,
  })

  const items = catalog.data?.items ?? []
  const effectiveId = selectedId && items.some((i) => i.id === selectedId) ? selectedId : items[0]?.id ?? null

  const asset = useQuery({
    queryKey: ["sql-asset", effectiveId],
    queryFn: () => fsiApi.getSqlAsset(effectiveId!).then((r) => r.data),
    enabled: Boolean(effectiveId),
    retry: 1,
  })

  const currentSqlSnippet = useMemo(() => {
    if (!asset.data?.sql) return null
    const body = asset.data.sql.length > 12_000
      ? `${asset.data.sql.slice(0, 12_000)}\n\n-- … truncated for AI page context …`
      : asset.data.sql
    return {
      id: asset.data.id,
      title: asset.data.title,
      category: asset.data.category,
      group: asset.data.group,
      description: asset.data.description,
      sql: body,
    }
  }, [asset.data])

  useBindPageContext({
    module: "sql-library",
    result: effectiveId ?? undefined,
    riskMetrics: {
      sql_asset: currentSqlSnippet,
      sql_ai_context: aiContext
        ? {
            asset_count: aiContext.asset_count,
            truncated: aiContext.truncated,
            markdown_preview: aiContext.markdown.slice(0, 8_000),
          }
        : null,
      catalog_filter: {
        group: group === ALL ? null : group,
        category: category === ALL ? null : category,
        search: debouncedSearch || null,
        matched: catalog.data?.count ?? 0,
      },
    },
  })

  async function copySql() {
    if (!asset.data?.sql) return
    try {
      await navigator.clipboard.writeText(asset.data.sql)
      toast.success(t("sqlLibrary.copied"))
    } catch {
      toast.error(t("sqlLibrary.operationFailed"))
    }
  }

  function downloadSql() {
    if (!asset.data?.sql) return
    const name = asset.data.filename || `${asset.data.id.replace(/\//g, "_")}`
    downloadText(name.endsWith(".sql") ? name : `${name}.sql`, asset.data.sql, "application/sql;charset=utf-8")
  }

  async function loadAiContext() {
    setLoadingContext(true)
    try {
      const { data } = await fsiApi.getSqlAssetContext({
        group: group === ALL ? undefined : group,
        category: category === ALL ? undefined : category,
      })
      setAiContext(data)
      toast.success(t("sqlLibrary.contextLoaded", { count: data.asset_count }))
    } catch {
      toast.error(t("sqlLibrary.operationFailed"))
    } finally {
      setLoadingContext(false)
    }
  }

  function downloadContext() {
    if (!aiContext?.markdown) return
    downloadText("sql-assets-context.md", aiContext.markdown, "text/markdown;charset=utf-8")
  }

  return (
    <div className="space-y-5" data-testid="sql-library-workbench">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("sqlLibrary.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("sqlLibrary.subtitle")}</p>
        </div>
      </div>

      <div className="space-y-5">
        <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
          <CardHeader>
            <ZoneTitle index="01" title={t("sqlLibrary.parameters")} detail={t("sqlLibrary.assetCount", { count: catalog.data?.count ?? 0 })} />
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <Label className="text-xs">{t("sqlLibrary.group")}</Label>
                <Select value={group} onValueChange={(value) => { setGroup(value); setCategory(ALL); setSelectedId(null); setAiContext(null) }}>
                  <SelectTrigger className="h-9 w-36"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>{t("sqlLibrary.all")}</SelectItem>
                    {(catalog.data?.groups ?? []).map((g) => <SelectItem key={g} value={g}>{g}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("sqlLibrary.category")}</Label>
                <Select value={category} onValueChange={(value) => { setCategory(value); setSelectedId(null); setAiContext(null) }}>
                  <SelectTrigger className="h-9 w-52"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>{t("sqlLibrary.all")}</SelectItem>
                    {(catalog.data?.categories ?? []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-3">
                <Search className="h-4 w-4 text-muted-foreground" />
                <Input
                  className="h-7 w-52 border-0 p-0 shadow-none focus-visible:ring-0"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("sqlLibrary.search")}
                />
              </div>
              <Button size="sm" variant="outline" disabled={loadingContext} onClick={() => void loadAiContext()}>
                <Bot className="mr-1 h-4 w-4" />
                {aiContext ? t("sqlLibrary.contextReloaded") : t("sqlLibrary.loadContext")}
              </Button>
              {aiContext ? (
                <Button size="sm" variant="ghost" onClick={downloadContext}>
                  <Download className="mr-1 h-4 w-4" />{t("sqlLibrary.downloadContext")}
                </Button>
              ) : null}
            </div>
            {aiContext ? (
              <p className="mt-3 text-xs text-muted-foreground">
                {t("sqlLibrary.contextLoaded", { count: aiContext.asset_count })}
                {aiContext.truncated ? ` · ${t("sqlLibrary.contextTruncated")}` : ""}
              </p>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">{t("sqlLibrary.aiHint")}</p>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <Card>
            <CardHeader><ZoneTitle index="02" title={t("sqlLibrary.assetList")} /></CardHeader>
            <CardContent className="p-0">
              <div className="max-h-[36rem] overflow-y-auto">
                {catalog.isFetching ? <p className="py-8 text-center text-sm text-muted-foreground">{t("sqlLibrary.loading")}</p> : null}
                {items.map((it) => (
                  <button
                    key={it.id}
                    type="button"
                    onClick={() => setSelectedId(it.id)}
                    className={`block w-full border-b px-4 py-2.5 text-left transition hover:bg-muted/50 ${effectiveId === it.id ? "bg-primary/[0.06]" : ""}`}
                  >
                    <div className="truncate text-sm font-medium">{it.title}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <Badge variant="outline" className="px-1 py-0 text-[10px]">{it.group}</Badge>
                      <span className="truncate">{it.category}</span>
                      <span>· {it.line_count} {t("sqlLibrary.lines")}</span>
                    </div>
                  </button>
                ))}
                {!catalog.isFetching && !items.length ? <p className="py-8 text-center text-sm text-muted-foreground">{t("sqlLibrary.empty")}</p> : null}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <ZoneTitle
                index="03"
                title={asset.data?.title ?? t("sqlLibrary.detail")}
                detail={asset.data?.id}
                action={(
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" disabled={!asset.data?.sql} onClick={copySql}>
                      <Copy className="mr-1 h-4 w-4" />{t("sqlLibrary.copy")}
                    </Button>
                    <Button size="sm" variant="outline" disabled={!asset.data?.sql} onClick={downloadSql}>
                      <Download className="mr-1 h-4 w-4" />{t("sqlLibrary.downloadSql")}
                    </Button>
                  </div>
                )}
              />
            </CardHeader>
            <CardContent className="space-y-3">
              {asset.data?.description ? <p className="text-sm text-muted-foreground">{asset.data.description}</p> : null}
              {asset.data ? (
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline">{asset.data.group}</Badge>
                  <Badge variant="secondary">{asset.data.category}</Badge>
                  <span>{asset.data.line_count} {t("sqlLibrary.lines")}</span>
                </div>
              ) : null}
              {asset.isFetching ? <p className="py-8 text-center text-sm text-muted-foreground">{t("sqlLibrary.loading")}</p> : null}
              {asset.data?.sql ? (
                <pre className="max-h-[32rem] overflow-auto rounded-lg border bg-muted/40 p-4 text-xs leading-relaxed"><code>{asset.data.sql}</code></pre>
              ) : !asset.isFetching ? <p className="py-8 text-center text-sm text-muted-foreground">{t("sqlLibrary.selectPrompt")}</p> : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

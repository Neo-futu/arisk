import { useQuery } from "@tanstack/react-query"
import { Code2, Copy, Search } from "lucide-react"
import { useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { FloatingAiChat } from "@/components/FloatingAiChat"
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

export function SqlLibraryPage() {
  const { t } = useTranslation()
  const [group, setGroup] = useState(ALL)
  const [category, setCategory] = useState(ALL)
  const [search, setSearch] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const catalog = useQuery({
    queryKey: ["sql-catalog", group, category, search],
    queryFn: () => fsiApi.getSqlAssetCatalog({
      group: group === ALL ? undefined : group,
      category: category === ALL ? undefined : category,
      search: search || undefined,
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

  async function copySql() {
    if (!asset.data?.sql) return
    try {
      await navigator.clipboard.writeText(asset.data.sql)
      toast.success(t("sqlLibrary.copied"))
    } catch {
      toast.error(t("sqlLibrary.operationFailed"))
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge className="gap-1"><Code2 className="h-3.5 w-3.5" />{t("sqlLibrary.badge")}</Badge>
            <Badge variant="outline">feature 11</Badge>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("sqlLibrary.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("sqlLibrary.subtitle")}</p>
        </div>
      </div>

      <div className="space-y-5">
          <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.06] to-transparent">
            <CardHeader><ZoneTitle index="01" title={t("sqlLibrary.parameters")} detail={t("sqlLibrary.assetCount", { count: catalog.data?.count ?? 0 })} /></CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">{t("sqlLibrary.group")}</Label>
                  <Select value={group} onValueChange={setGroup}>
                    <SelectTrigger className="h-9 w-36"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>{t("sqlLibrary.all")}</SelectItem>
                      {(catalog.data?.groups ?? []).map((g) => <SelectItem key={g} value={g}>{g}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{t("sqlLibrary.category")}</Label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger className="h-9 w-40"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>{t("sqlLibrary.all")}</SelectItem>
                      {(catalog.data?.categories ?? []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-3">
                  <Search className="h-4 w-4 text-muted-foreground" />
                  <Input className="h-7 w-52 border-0 p-0 shadow-none focus-visible:ring-0" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("sqlLibrary.search")} />
                </div>
              </div>
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
                      <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant="outline" className="px-1 py-0 text-[10px]">{it.group}</Badge>
                        <span>{it.category}</span>
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
                <ZoneTitle index="03" title={asset.data?.title ?? t("sqlLibrary.detail")} detail={asset.data?.id}
                  action={<Button size="sm" variant="outline" disabled={!asset.data?.sql} onClick={copySql}><Copy className="mr-1 h-4 w-4" />{t("sqlLibrary.copy")}</Button>} />
              </CardHeader>
              <CardContent className="space-y-3">
                {asset.data?.description ? <p className="text-sm text-muted-foreground">{asset.data.description}</p> : null}
                {asset.isFetching ? <p className="py-8 text-center text-sm text-muted-foreground">{t("sqlLibrary.loading")}</p> : null}
                {asset.data?.sql ? (
                  <pre className="max-h-[32rem] overflow-auto rounded-lg border bg-muted/40 p-4 text-xs leading-relaxed"><code>{asset.data.sql}</code></pre>
                ) : !asset.isFetching ? <p className="py-8 text-center text-sm text-muted-foreground">{t("sqlLibrary.selectPrompt")}</p> : null}
              </CardContent>
            </Card>
          </div>
      </div>
      <FloatingAiChat
        title={t("sqlLibrary.aiArea")}
        hint={t("sqlLibrary.aiHint")}
        placeholder={t("sqlLibrary.aiPlaceholder")}
        buildPrompt={(q) => [
          "你正在 ARISK SQL 资产库协助分析人员理解与运用风控/业绩计算 SQL。",
          "以下是所选 SQL 资产（作为参考上下文，勿杜撰表结构）：",
          asset.data?.sql ? `### ${asset.data.title}\n\n\`\`\`sql\n${asset.data.sql}\n\`\`\`` : "（未选择 SQL）",
          `用户问题：${q}`,
        ].join("\n")}
      />
    </div>
  )
}


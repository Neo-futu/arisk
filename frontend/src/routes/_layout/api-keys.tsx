import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Check, Copy, KeyRound, Loader2, Plus, ShieldCheck, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi } from "@/fsiClient"

export const Route = createFileRoute("/_layout/api-keys")({
  component: ApiKeysPage,
  head: () => ({ meta: [{ title: "API Key Management — ARISK" }] }),
})

function ApiKeysPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState(() => t("apiKeys.defaultKeyName"))
  const [expiresDays, setExpiresDays] = useState("90")
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const keys = useQuery({
    queryKey: ["user-api-keys"],
    queryFn: () => fsiApi.listApiKeys().then((response) => response.data),
  })
  const localConfig = useQuery({
    queryKey: ["local-api-config"],
    queryFn: () => fsiApi.getLocalApiConfig().then((response) => response.data),
  })
  const createKey = useMutation({
    mutationFn: () => fsiApi.createApiKey({
      name: name.trim(),
      expires_days: expiresDays === "never" ? null : Number(expiresDays),
    }),
    onSuccess: (response) => {
      setCreatedKey(response.data.key)
      queryClient.invalidateQueries({ queryKey: ["user-api-keys"] })
      toast.success(t("apiKeys.createdToast"))
    },
    onError: () => toast.error(t("apiKeys.createFailedToast")),
  })
  const revokeKey = useMutation({
    mutationFn: (id: string) => fsiApi.revokeApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-api-keys"] })
      toast.success(t("apiKeys.revokedToast"))
    },
    onError: () => toast.error(t("apiKeys.revokeFailedToast")),
  })

  async function copyKey() {
    if (!createdKey) return
    await navigator.clipboard.writeText(createdKey)
    setCopied(true)
    toast.success(t("apiKeys.copiedToast"))
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-primary" />
          <span className="text-muted-foreground text-sm">{t("apiKeys.breadcrumb")}</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{t("apiKeys.title")}</h1>
        <p className="text-muted-foreground text-sm">
          {t("apiKeys.subtitle")}
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">{t("apiKeys.localConfigTitle")}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {localConfig.data ? (
            <div className="grid gap-4 md:grid-cols-2">
              <ConfigItem label={t("apiKeys.apiBaseUrl")} value={localConfig.data.api_base_url} />
              <ConfigItem label={t("apiKeys.authHeader")} value={localConfig.data.header_name} />
              <ConfigItem label={t("apiKeys.keyPrefix")} value={localConfig.data.key_prefix} />
              <ConfigItem label={t("apiKeys.processingApi")} value={localConfig.data.processing_api.url} />
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">{t("apiKeys.loadingConfig")}</p>
          )}
          {localConfig.data && (
            <Alert>
              <ShieldCheck className="h-4 w-4" />
              <AlertTitle>{t("apiKeys.internalKeyIsolation")}</AlertTitle>
              <AlertDescription>
                {localConfig.data.note} {localConfig.data.processing_api.secret_source}。
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">{t("apiKeys.createTitle")}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-[1fr_220px_auto] md:items-end">
            <div className="space-y-2">
              <Label htmlFor="api-key-name">{t("apiKeys.nameLabel")}</Label>
              <Input id="api-key-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} placeholder={t("apiKeys.namePlaceholder")} />
            </div>
            <div className="space-y-2">
              <Label>{t("apiKeys.expiryLabel")}</Label>
              <Select value={expiresDays} onValueChange={setExpiresDays}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">{t("apiKeys.expiry30")}</SelectItem>
                  <SelectItem value="90">{t("apiKeys.expiry90")}</SelectItem>
                  <SelectItem value="365">{t("apiKeys.expiry365")}</SelectItem>
                  <SelectItem value="never">{t("apiKeys.expiryNever")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={() => createKey.mutate()} disabled={!name.trim() || createKey.isPending}>
              {createKey.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {t("apiKeys.createButton")}
            </Button>
          </div>

          {createdKey && (
            <Alert className="border-amber-500/50 bg-amber-500/5">
              <KeyRound className="h-4 w-4" />
              <AlertTitle>{t("apiKeys.saveKeyTitle")}</AlertTitle>
              <AlertDescription className="space-y-3">
                <p>{t("apiKeys.saveKeyWarning")}</p>
                <div className="flex items-center gap-2 rounded-md border bg-background p-2">
                  <code className="min-w-0 flex-1 break-all text-xs">{createdKey}</code>
                  <Button variant="outline" size="icon" onClick={copyKey} title={t("apiKeys.copyKey")}>
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setCreatedKey(null)}>{t("apiKeys.savedClose")}</Button>
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">{t("apiKeys.myKeysTitle")}</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow><TableHead>{t("apiKeys.colName")}</TableHead><TableHead>{t("apiKeys.colKey")}</TableHead><TableHead>{t("apiKeys.colCreated")}</TableHead><TableHead>{t("apiKeys.colExpires")}</TableHead><TableHead>{t("apiKeys.colLastUsed")}</TableHead><TableHead>{t("apiKeys.colStatus")}</TableHead><TableHead className="text-right">{t("apiKeys.colActions")}</TableHead></TableRow></TableHeader>
            <TableBody>
              {keys.data?.map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-medium">{key.name}</TableCell>
                  <TableCell className="font-mono text-xs">{key.masked_key}</TableCell>
                  <TableCell>{formatDate(key.created_at)}</TableCell>
                  <TableCell>{formatDate(key.expires_at)}</TableCell>
                  <TableCell>{formatDate(key.last_used_at)}</TableCell>
                  <TableCell><Badge variant={key.is_active ? "default" : "secondary"}>{key.is_active ? t("apiKeys.statusActive") : t("apiKeys.statusRevoked")}</Badge></TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" disabled={!key.is_active || revokeKey.isPending} onClick={() => revokeKey.mutate(key.id)}>
                      <Trash2 className="h-4 w-4" />{t("apiKeys.revoke")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!keys.isLoading && !keys.data?.length && (
                <TableRow><TableCell colSpan={7} className="h-20 text-center text-muted-foreground">{t("apiKeys.emptyKeys")}</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

function ConfigItem({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border p-3"><p className="text-muted-foreground text-xs">{label}</p><code className="mt-1 block break-all text-sm">{value}</code></div>
}

function formatDate(value: string | null) {
  if (!value) return "—"
  return new Intl.DateTimeFormat("zh-HK", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
}

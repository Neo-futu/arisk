import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Check, Copy, KeyRound, Loader2, Plus, ShieldCheck, Trash2 } from "lucide-react"
import { useState } from "react"
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
  head: () => ({ meta: [{ title: "API Key 管理 — ARISK" }] }),
})

function ApiKeysPage() {
  const queryClient = useQueryClient()
  const [name, setName] = useState("本地開發")
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
      toast.success("API Key 已建立")
    },
    onError: () => toast.error("API Key 建立失敗"),
  })
  const revokeKey = useMutation({
    mutationFn: (id: string) => fsiApi.revokeApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-api-keys"] })
      toast.success("API Key 已撤銷")
    },
    onError: () => toast.error("API Key 撤銷失敗"),
  })

  async function copyKey() {
    if (!createdKey) return
    await navigator.clipboard.writeText(createdKey)
    setCopied(true)
    toast.success("已複製到剪貼簿")
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-primary" />
          <span className="text-muted-foreground text-sm">系統管理</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">API Key 管理</h1>
        <p className="text-muted-foreground text-sm">
          為本地腳本和外部客戶端建立個人 API Key；密鑰只會顯示一次。
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">本地 API 配置</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {localConfig.data ? (
            <div className="grid gap-4 md:grid-cols-2">
              <ConfigItem label="API Base URL" value={localConfig.data.api_base_url} />
              <ConfigItem label="認證 Header" value={localConfig.data.header_name} />
              <ConfigItem label="用戶 Key 前綴" value={localConfig.data.key_prefix} />
              <ConfigItem label="內部 Processing API" value={localConfig.data.processing_api.url} />
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">載入本地配置中...</p>
          )}
          {localConfig.data && (
            <Alert>
              <ShieldCheck className="h-4 w-4" />
              <AlertTitle>內部 Key 隔離</AlertTitle>
              <AlertDescription>
                {localConfig.data.note} {localConfig.data.processing_api.secret_source}。
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">建立 API Key</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-[1fr_220px_auto] md:items-end">
            <div className="space-y-2">
              <Label htmlFor="api-key-name">名稱</Label>
              <Input id="api-key-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} placeholder="例如：本地 Python 報表" />
            </div>
            <div className="space-y-2">
              <Label>有效期</Label>
              <Select value={expiresDays} onValueChange={setExpiresDays}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">30 天</SelectItem>
                  <SelectItem value="90">90 天</SelectItem>
                  <SelectItem value="365">1 年</SelectItem>
                  <SelectItem value="never">永不過期</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={() => createKey.mutate()} disabled={!name.trim() || createKey.isPending}>
              {createKey.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              建立
            </Button>
          </div>

          {createdKey && (
            <Alert className="border-amber-500/50 bg-amber-500/5">
              <KeyRound className="h-4 w-4" />
              <AlertTitle>請立即保存此 Key</AlertTitle>
              <AlertDescription className="space-y-3">
                <p>關閉後無法再次查看明文。如遺失，請撤銷並重新建立。</p>
                <div className="flex items-center gap-2 rounded-md border bg-background p-2">
                  <code className="min-w-0 flex-1 break-all text-xs">{createdKey}</code>
                  <Button variant="outline" size="icon" onClick={copyKey} title="複製 API Key">
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setCreatedKey(null)}>我已保存，關閉</Button>
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">我的 API Keys</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow><TableHead>名稱</TableHead><TableHead>Key</TableHead><TableHead>建立時間</TableHead><TableHead>到期時間</TableHead><TableHead>最後使用</TableHead><TableHead>狀態</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader>
            <TableBody>
              {keys.data?.map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-medium">{key.name}</TableCell>
                  <TableCell className="font-mono text-xs">{key.masked_key}</TableCell>
                  <TableCell>{formatDate(key.created_at)}</TableCell>
                  <TableCell>{formatDate(key.expires_at)}</TableCell>
                  <TableCell>{formatDate(key.last_used_at)}</TableCell>
                  <TableCell><Badge variant={key.is_active ? "default" : "secondary"}>{key.is_active ? "有效" : "已撤銷"}</Badge></TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" disabled={!key.is_active || revokeKey.isPending} onClick={() => revokeKey.mutate(key.id)}>
                      <Trash2 className="h-4 w-4" />撤銷
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!keys.isLoading && !keys.data?.length && (
                <TableRow><TableCell colSpan={7} className="h-20 text-center text-muted-foreground">尚未建立 API Key</TableCell></TableRow>
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

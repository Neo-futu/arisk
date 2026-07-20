import { useMutation, useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Bell, Building2, Loader2, Mail, MessageSquare, Send } from "lucide-react"
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
import { Textarea } from "@/components/ui/textarea"
import { fsiApi, type NotificationChannel } from "@/fsiClient"

export const Route = createFileRoute("/_layout/notifications")({
  component: NotificationsPage,
  head: () => ({ meta: [{ title: "通知中心 — ARISK" }] }),
})

const CHANNELS: Array<{
  id: NotificationChannel
  name: string
  icon: typeof Mail
  env: string
}> = [
  { id: "email", name: "郵件", icon: Mail, env: "SMTP_HOST / EMAILS_FROM_EMAIL" },
  { id: "feishu", name: "飛書", icon: MessageSquare, env: "FEISHU_WEBHOOK_URL" },
  { id: "wecom", name: "企業微信", icon: Building2, env: "WECOM_WEBHOOK_URL" },
]

function NotificationsPage() {
  const [channel, setChannel] = useState<NotificationChannel>("email")
  const [recipient, setRecipient] = useState("")
  const [title, setTitle] = useState("ARISK 投資風險分析通知")
  const [content, setContent] = useState("")

  const channels = useQuery({
    queryKey: ["notification-channels"],
    queryFn: () => fsiApi.getNotificationChannels().then((response) => response.data),
  })
  const send = useMutation({
    mutationFn: () => fsiApi.sendNotification(channel, {
      title: title.trim(),
      content: content.trim(),
      ...(channel === "email" ? { recipient: recipient.trim() } : {}),
    }),
    onSuccess: (response) => toast.success(response.data.message),
    onError: () => toast.error("通知發送失敗，請檢查渠道配置和接口狀態"),
  })

  const configured = channels.data?.[channel].configured ?? false
  const canSend = configured && title.trim() && content.trim() && (channel !== "email" || recipient.trim())

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <Bell className="h-5 w-5 text-primary" />
          <span className="text-muted-foreground text-sm">系統服務</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">通知中心</h1>
        <p className="text-muted-foreground text-sm">
          統一對接郵件、飛書和企業微信；各接口可由其他查詢頁面的發送按鈕直接複用。
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {CHANNELS.map((item) => {
          const Icon = item.icon
          const status = channels.data?.[item.id]
          return (
            <Card key={item.id} className={channel === item.id ? "border-primary" : ""}>
              <CardContent className="flex items-start justify-between gap-3 pt-5">
                <div className="flex gap-3">
                  <div className="rounded-lg bg-muted p-2"><Icon className="h-5 w-5" /></div>
                  <div>
                    <p className="font-medium">{item.name}</p>
                    <p className="text-muted-foreground mt-1 text-xs">{status?.description ?? "載入中..."}</p>
                    <code className="text-muted-foreground mt-2 block text-[11px]">{item.env}</code>
                  </div>
                </div>
                <Badge variant={status?.configured ? "default" : "secondary"}>{status?.configured ? "已配置" : "未配置"}</Badge>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">發送通知</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>通知渠道</Label>
              <Select value={channel} onValueChange={(value) => setChannel(value as NotificationChannel)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CHANNELS.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {channel === "email" && (
              <div className="space-y-2">
                <Label htmlFor="notification-recipient">收件人</Label>
                <Input id="notification-recipient" type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="risk@example.com" />
              </div>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="notification-title">標題</Label>
            <Input id="notification-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="notification-content">內容</Label>
            <Textarea id="notification-content" value={content} onChange={(event) => setContent(event.target.value)} rows={8} maxLength={10000} placeholder="輸入需要發送的查詢結果摘要或風險提示..." />
            <p className="text-muted-foreground text-right text-xs">{content.length} / 10000</p>
          </div>

          {!channels.isLoading && !configured && (
            <Alert>
              <Bell className="h-4 w-4" />
              <AlertTitle>渠道尚未配置</AlertTitle>
              <AlertDescription>
                請在伺服器 .env 中設置 {CHANNELS.find((item) => item.id === channel)?.env}，重啟 Backend 後即可發送。
              </AlertDescription>
            </Alert>
          )}

          <Button onClick={() => send.mutate()} disabled={!canSend || send.isPending}>
            {send.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            發送{CHANNELS.find((item) => item.id === channel)?.name}通知
          </Button>
        </CardContent>
      </Card>

      <Alert>
        <Send className="h-4 w-4" />
        <AlertTitle>獨立接口</AlertTitle>
        <AlertDescription>
          POST /api/v1/notifications/email、/feishu、/wecom 均接受標題和內容；郵件接口另需 recipient。所有接口支持 JWT 或用戶 X-API-Key 認證。
        </AlertDescription>
      </Alert>
    </div>
  )
}

import { useMutation, useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Bell, Building2, Loader2, Mail, MessageSquare, Send } from "lucide-react"
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
import { Textarea } from "@/components/ui/textarea"
import { fsiApi, type NotificationChannel } from "@/fsiClient"

export const Route = createFileRoute("/_layout/notifications")({
  component: NotificationsPage,
  head: () => ({ meta: [{ title: "Notification Center — ARISK" }] }),
})

const CHANNELS: Array<{
  id: NotificationChannel
  nameKey: string
  icon: typeof Mail
  env: string
}> = [
  { id: "email", nameKey: "notifications.channelEmail", icon: Mail, env: "SMTP_HOST / EMAILS_FROM_EMAIL" },
  { id: "feishu", nameKey: "notifications.channelFeishu", icon: MessageSquare, env: "FEISHU_WEBHOOK_URL" },
  { id: "wecom", nameKey: "notifications.channelWecom", icon: Building2, env: "WECOM_WEBHOOK_URL" },
]

function NotificationsPage() {
  const { t } = useTranslation()
  const [channel, setChannel] = useState<NotificationChannel>("email")
  const [recipient, setRecipient] = useState("")
  const [title, setTitle] = useState(() => t("notifications.defaultTitle"))
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
    onError: () => toast.error(t("notifications.sendFailedToast")),
  })

  const configured = channels.data?.[channel].configured ?? false
  const canSend = configured && title.trim() && content.trim() && (channel !== "email" || recipient.trim())

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <Bell className="h-5 w-5 text-primary" />
          <span className="text-muted-foreground text-sm">{t("notifications.breadcrumb")}</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{t("notifications.title")}</h1>
        <p className="text-muted-foreground text-sm">
          {t("notifications.subtitle")}
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
                    <p className="font-medium">{t(item.nameKey)}</p>
                    <p className="text-muted-foreground mt-1 text-xs">{status?.description ?? t("notifications.channelLoading")}</p>
                    <code className="text-muted-foreground mt-2 block text-[11px]">{item.env}</code>
                  </div>
                </div>
                <Badge variant={status?.configured ? "default" : "secondary"}>{status?.configured ? t("notifications.configured") : t("notifications.notConfigured")}</Badge>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">{t("notifications.sendTitle")}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>{t("notifications.channelLabel")}</Label>
              <Select value={channel} onValueChange={(value) => setChannel(value as NotificationChannel)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CHANNELS.map((item) => <SelectItem key={item.id} value={item.id}>{t(item.nameKey)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {channel === "email" && (
              <div className="space-y-2">
                <Label htmlFor="notification-recipient">{t("notifications.recipientLabel")}</Label>
                <Input id="notification-recipient" type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="risk@example.com" />
              </div>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="notification-title">{t("notifications.titleLabel")}</Label>
            <Input id="notification-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="notification-content">{t("notifications.contentLabel")}</Label>
            <Textarea id="notification-content" value={content} onChange={(event) => setContent(event.target.value)} rows={8} maxLength={10000} placeholder={t("notifications.contentPlaceholder")} />
            <p className="text-muted-foreground text-right text-xs">{content.length} / 10000</p>
          </div>

          {!channels.isLoading && !configured && (
            <Alert>
              <Bell className="h-4 w-4" />
              <AlertTitle>{t("notifications.channelNotConfiguredTitle")}</AlertTitle>
              <AlertDescription>
                {t("notifications.channelNotConfiguredDesc", { env: CHANNELS.find((item) => item.id === channel)?.env })}
              </AlertDescription>
            </Alert>
          )}

          <Button onClick={() => send.mutate()} disabled={!canSend || send.isPending}>
            {send.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {t("notifications.sendButton", { channel: t(CHANNELS.find((item) => item.id === channel)?.nameKey ?? "notifications.channelEmail") })}
          </Button>
        </CardContent>
      </Card>

      <Alert>
        <Send className="h-4 w-4" />
        <AlertTitle>{t("notifications.independentApiTitle")}</AlertTitle>
        <AlertDescription>
          {t("notifications.independentApiDesc")}
        </AlertDescription>
      </Alert>
    </div>
  )
}

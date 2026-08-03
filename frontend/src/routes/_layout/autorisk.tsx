import { createFileRoute } from "@tanstack/react-router"
import { ExternalLink, Sparkles } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export const Route = createFileRoute("/_layout/autorisk")({
  component: AutoRiskPage,
  head: () => ({ meta: [{ title: "自動風控 — ARISK" }] }),
})

function AutoRiskPage() {
  const autoriskBaseUrl = (
    (import.meta.env.VITE_AUTORISK_URL as string | undefined)?.trim() || "http://localhost:8100"
  ).replace(/\/$/, "")

  const demoUrl = `${autoriskBaseUrl}/demo`
  const docsUrl = `${autoriskBaseUrl}/docs`
  const healthUrl = `${autoriskBaseUrl}/health`

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold tracking-tight">自動風控</h1>
          <Badge variant="secondary">AutoRisk 模塊</Badge>
        </div>
        <p className="max-w-3xl text-sm text-muted-foreground">
          將 AutoRisk 智能風控評估服務接入前端平台，提供可視化風控評估、雙級覆核與審計回溯入口，後續可以作為新的功能模塊快速接入。
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_0.8fr]">
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base">AutoRisk 互動演示</CardTitle>
            <CardDescription>
              在平台內直接打開 AutoRisk 的可視化風控審核頁，便於檢查評估流程與決策結果。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <a href={demoUrl} target="_blank" rel="noreferrer">
                  打開演示頁
                  <ExternalLink className="ml-2 h-4 w-4" />
                </a>
              </Button>
              <Button variant="outline" asChild>
                <a href={docsUrl} target="_blank" rel="noreferrer">
                  打開 API 文檔
                </a>
              </Button>
            </div>

            <div className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">本地服務地址</p>
              <p className="mt-1 break-all">{autoriskBaseUrl}</p>
              <p className="mt-2">可用端點：{healthUrl}</p>
              <p className="mt-3 text-amber-600">
                若點擊演示頁失敗，請先在另一個終端啟動 AutoRisk：<span className="font-mono">cd autorisk && python run.py</span>
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">模塊能力</CardTitle>
            <CardDescription>這個入口可作為後續擴展的標準模板。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <div className="rounded-md border p-3">
              <p className="font-medium text-foreground">風控評估</p>
              <p className="mt-1">支援交易/持倉/事件等多場景評估。</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="font-medium text-foreground">雙級覆核</p>
              <p className="mt-1">AI Risk Officer 與 AI MIC 共同完成審核。</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="font-medium text-foreground">審計與回執</p>
              <p className="mt-1">保存簽名、審計鏈與決策回執結果。</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

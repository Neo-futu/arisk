import { useMutation, useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Loader2, MessageSquare, PlayCircle } from "lucide-react"
import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { fsiApi } from "@/fsiClient"

export const Route = createFileRoute("/_layout/chat")({
  component: ChatPage,
  head: () => ({ meta: [{ title: "Agent Chat — ARISK" }] }),
})

function ChatPage() {
  const [task, setTask] = useState("請總結 BHMMF001 最近一日的 VaR 與主要風險點")
  const [fundId, setFundId] = useState("BHMMF001")
  const [asOfDate, setAsOfDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 1)
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1)
    return d.toISOString().split("T")[0]
  })
  const [chatReply, setChatReply] = useState<string | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)

  const chatMutation = useMutation({
    mutationFn: () =>
      fsiApi.chat({
        task,
        fund_id: fundId,
        date: asOfDate,
        mode: "chat",
      }),
    onSuccess: (response) => {
      setChatReply(response.data.reply)
    },
  })

  const runMutation = useMutation({
    mutationFn: () =>
      fsiApi.runAgentTask({
        task,
        fund_id: fundId,
        date: asOfDate,
        mode: "agent",
      }),
    onSuccess: (response) => {
      setTaskId(response.data.task_id)
    },
  })

  const statusQuery = useQuery({
    queryKey: ["agent-task-status", taskId],
    queryFn: () => fsiApi.getAgentTaskStatus(taskId!).then((r) => r.data),
    enabled: Boolean(taskId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === "queued" || status === "running" ? 2000 : false
    },
  })

  useEffect(() => {
    if (runMutation.isSuccess && taskId) {
      void statusQuery.refetch()
    }
  }, [runMutation.isSuccess, taskId, statusQuery])

  const taskStatus = statusQuery.data?.status

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Agent Chat 工作台</h1>
        <p className="text-muted-foreground text-sm">
          根目錄 frontend 為唯一 Web 入口。同步 Chat 與異步 Agent 任務都經由 backend 統一代理。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>任務輸入</CardTitle>
          <CardDescription>可先即時對話，再提交完整 Agent 任務。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <input
              type="text"
              value={fundId}
              onChange={(e) => setFundId(e.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="基金 ID"
            />
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            />
            <Badge variant="outline" className="h-10 justify-center text-sm">
              backend → 6_entry → processing
            </Badge>
          </div>
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={6}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            placeholder="輸入風控分析問題或任務指令"
          />
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => chatMutation.mutate()} disabled={chatMutation.isPending || runMutation.isPending} className="gap-2">
              {chatMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}
              即時 Chat
            </Button>
            <Button variant="outline" onClick={() => runMutation.mutate()} disabled={chatMutation.isPending || runMutation.isPending} className="gap-2">
              {runMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              提交 Agent 任務
            </Button>
          </div>
          {(chatMutation.isError || runMutation.isError) && (
            <p className="text-sm text-destructive">
              {(chatMutation.error || runMutation.error)?.message ?? "請求失敗"}
            </p>
          )}
        </CardContent>
      </Card>

      {chatReply && (
        <Card>
          <CardHeader>
            <CardTitle>Chat 回覆</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="whitespace-pre-wrap text-sm leading-6">{chatReply}</div>
          </CardContent>
        </Card>
      )}

      {taskId && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>Agent 任務</CardTitle>
              <Badge variant={taskStatus === "completed" ? "default" : "secondary"}>
                {taskStatus ?? "queued"}
              </Badge>
            </div>
            <CardDescription>Task ID: {taskId}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {statusQuery.isLoading && <p className="text-sm text-muted-foreground">讀取任務狀態中...</p>}
            {statusQuery.data?.result && (
              <div className="whitespace-pre-wrap rounded-md border bg-muted/30 p-4 text-sm leading-6">
                {statusQuery.data.result}
              </div>
            )}
            {statusQuery.data?.error && (
              <p className="text-sm text-destructive">{statusQuery.data.error}</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
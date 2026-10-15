import { Bot, Loader2, MessageSquareText, Sparkles, X } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { fsiApi } from "@/fsiClient"
import { FALLBACK_MODELS, MODEL_GROUPS } from "@/components/Chat/constants"
import { agentForModule } from "@/platform/nav"
import { formatPageContext, usePageContext } from "@/platform/page-context"

type CopilotMsg = {
  id: string
  role: "user" | "assistant"
  content: string
  status?: string
  error?: string
  streaming?: boolean
}

type SseEvent = {
  type: string
  content?: string
  message?: string
  name?: string
}

type ModelOption = {
  id: string
  label: string
  provider: string
  default?: boolean
}

/** Ask AI 优先展示 Cursor / OpenAI；其余 Provider 仍可选 */
const COPILOT_PROVIDER_ORDER = ["cursor", "openai", "anthropic", "openrouter", "gemini", "moonshot", "deepseek"] as const

/**
 * Layout 级 Ask AI 浮窗（原 AI Copilot）。
 *
 * 接入步骤：
 * 1. 读取 PageContext（portfolio / date / riskMetrics）
 * 2. 缺 VaR 时预取 var-compare + risk-indicators 写入上下文
 * 3. SSE → backend → 6_entry/aiagent（Cursor Composer 默认；工具走 processing）
 * 4. 超时与状态提示，避免长期停在「思考中」
 */
export function FloatingAiChat({
  title,
  hint,
  placeholder,
  buildPrompt,
  agent,
  context,
}: {
  title?: string
  hint?: string
  placeholder?: string
  buildPrompt?: (question: string) => string
  agent?: string
  context?: { fund_id?: string; as_of_date?: string }
}) {
  const { t } = useTranslation()
  const page = usePageContext()
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState("")
  const [messages, setMessages] = useState<CopilotMsg[]>([])
  const [asking, setAsking] = useState(false)
  // Composer 比 Auto Router 更稳，避免 Ask AI 长期卡在「思考中」
  const [modelId, setModelId] = useState<string>("composer-2.5")
  const [models, setModels] = useState<ModelOption[]>([])
  const listRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const pageAgent = agent ?? agentForModule(page.context.module)
  const pageCtx = {
    fund_id: context?.fund_id ?? page.context.portfolio,
    as_of_date: context?.as_of_date ?? page.context.date,
    module: page.context.module,
    result: page.context.result,
    chart: page.context.chart,
    risk_metrics: page.context.riskMetrics,
  }

  useEffect(() => {
    fsiApi.listModels()
      .then((response) => {
        const list = (response.data ?? []).map((item) => ({
          id: item.id,
          label: item.label,
          provider: item.provider,
          default: item.default,
        }))
        if (list.length) {
          setModels(list)
          const preferred =
            list.find((item) => item.id === "composer-2.5")?.id
            ?? list.find((item) => item.provider === "cursor" && item.id !== "auto-smart")?.id
            ?? list.find((item) => item.provider === "openai")?.id
            ?? list.find((item) => item.default)?.id
            ?? list[0]?.id
          if (preferred) setModelId(preferred)
          return
        }
        throw new Error("empty")
      })
      .catch(() => {
        const fallback = FALLBACK_MODELS.map((item) => ({
          id: item.id,
          label: item.label,
          provider: item.provider,
          default: item.default,
        }))
        setModels(fallback)
        const preferred =
          fallback.find((item) => item.id === "composer-2.5")?.id
          ?? "composer-2.5"
        setModelId(preferred)
      })
  }, [])

  const modelGroups = useMemo(() => {
    const byProvider = new Map<string, ModelOption[]>()
    for (const model of models) {
      const bucket = byProvider.get(model.provider) ?? []
      bucket.push(model)
      byProvider.set(model.provider, bucket)
    }
    return COPILOT_PROVIDER_ORDER
      .filter((key) => (byProvider.get(key)?.length ?? 0) > 0)
      .map((key) => {
        const meta = MODEL_GROUPS.find((group) => group.key === key)
        return {
          key,
          label: meta ? t(meta.labelKey, { defaultValue: meta.label }) : key,
          icon: meta?.icon ?? "•",
          models: byProvider.get(key) ?? [],
        }
      })
  }, [models, t])

  const selectedModel = models.find((item) => item.id === modelId)

  useEffect(() => {
    const list = listRef.current
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: "smooth" })
  }, [messages, asking])

  function updateLastAssistant(fn: (msg: CopilotMsg) => CopilotMsg) {
    setMessages((prev) => {
      const next = [...prev]
      for (let i = next.length - 1; i >= 0; i -= 1) {
        if (next[i].role === "assistant") {
          next[i] = fn(next[i])
          break
        }
      }
      return next
    })
  }

  async function enrichRiskContext(): Promise<Record<string, unknown> | undefined> {
    const existing = page.context.riskMetrics
    const hasVar = Boolean(
      existing
      && typeof existing === "object"
      && (existing as { var_compare?: unknown }).var_compare,
    )
    if (hasVar) return existing

    const fundId = pageCtx.fund_id
    const asOfDate = pageCtx.as_of_date
    if (!fundId || !asOfDate) return existing

    try {
      const [varRes, indRes] = await Promise.all([
        fsiApi.getVarCompare(fundId, asOfDate).catch(() => null),
        fsiApi.getRiskIndicators(fundId, asOfDate, asOfDate).catch(() => null),
      ])
      const varData = varRes?.data
      const indData = indRes?.data
      if (!varData && !indData) return existing
      return {
        ...(existing ?? {}),
        fund_id: fundId,
        as_of_date: asOfDate,
        source: "copilot-prefetch",
        indicators: indData
          ? {
              interval_return_pct: indData.interval_return_pct,
              annualized_volatility_pct: indData.annualized_volatility_pct,
              max_drawdown_pct: indData.max_drawdown_pct,
            }
          : (existing as { indicators?: unknown } | undefined)?.indicators ?? null,
        var_compare: varData
          ? {
              confidence: varData.confidence,
              horizon_days: varData.horizon_days,
              max_var_pct_nav: varData.max_var_pct_nav,
              methods: (varData.results ?? []).map((row) => ({
                method: row.method_requested ?? row.method,
                var_hkd: row.var_hkd,
                var_pct_nav: row.var_pct_nav,
                cvar_hkd: row.cvar_hkd,
                sample_size: row.sample_size,
              })),
            }
          : null,
      }
    } catch {
      return existing
    }
  }

  async function ask() {
    const userText = question.trim()
    if (!userText || asking) return
    setQuestion("")
    setAsking(true)

    const riskMetrics = await enrichRiskContext()
    const pageSnapshot = {
      ...page.context,
      portfolio: pageCtx.fund_id ?? page.context.portfolio,
      date: pageCtx.as_of_date ?? page.context.date,
      riskMetrics,
      result: page.context.result
        ?? (riskMetrics && typeof riskMetrics === "object" && "var_compare" in riskMetrics
          ? `max_var_pct_nav=${(riskMetrics.var_compare as { max_var_pct_nav?: number } | null)?.max_var_pct_nav ?? "—"}`
          : page.context.result),
    }

    const userContent = buildPrompt
      ? buildPrompt(userText)
      : [
          "你是 ARISK Ask AI。",
          "优先使用下方 Page context / Risk Metrics 中的真实数字回答（含 VaR 三方法对比）。",
          "数字已在上下文中则直接引用，不要声称需要再查系统。",
          "不要编造 NAV / VaR / PnL / 压力损失 / 估值 / 限额；上下文确实没有时才说明缺失项。",
          "回答 VaR 时请给出：方法、var_pct_nav、var_hkd、置信度、持有期，并可用 max_var_pct_nav 作汇总。",
          "Page context:",
          formatPageContext(pageSnapshot),
          `User question: ${userText}`,
        ].join("\n")

    const historyForApi = [
      ...messages
        .filter((msg) => !msg.streaming && !msg.error)
        .map((msg) => ({ role: msg.role, content: msg.content })),
      { role: "user" as const, content: userContent },
    ]

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content: userText },
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        status: t("ai.thinking", { defaultValue: "思考中…" }),
        streaming: true,
      },
    ])

    const controller = new AbortController()
    const timeoutMs = 75_000
    const timer = window.setTimeout(() => controller.abort(), timeoutMs)

    try {
      const response = await fsiApi.streamAgentChat(
        historyForApi,
        pageAgent,
        {
          fund_id: pageCtx.fund_id,
          as_of_date: pageCtx.as_of_date,
        },
        modelId,
        undefined,
        undefined,
        controller.signal,
      )
      if (!response.ok) {
        const err = await response.text()
        updateLastAssistant((msg) => ({
          ...msg,
          streaming: false,
          status: undefined,
          error: t("ai.failed") + (err ? `：${err.slice(0, 180)}` : ""),
        }))
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        updateLastAssistant((msg) => ({
          ...msg,
          streaming: false,
          status: undefined,
          error: t("ai.failed"),
        }))
        return
      }

      const decoder = new TextDecoder()
      let buffer = ""
      let gotText = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          let ev: SseEvent
          try {
            ev = JSON.parse(line.slice(6))
          } catch {
            continue
          }
          if (ev.type === "text" && ev.content) {
            gotText = true
            updateLastAssistant((msg) => ({
              ...msg,
              content: msg.content + ev.content!,
              status: undefined,
            }))
          } else if (ev.type === "tool_call") {
            updateLastAssistant((msg) => ({
              ...msg,
              status: t("ai.callingTool", {
                defaultValue: "调用工具：{{name}}",
                name: ev.name ?? "tool",
              }),
            }))
          } else if (ev.type === "tool_result") {
            updateLastAssistant((msg) => ({
              ...msg,
              status: t("ai.thinking", { defaultValue: "思考中…" }),
            }))
          } else if (ev.type === "error") {
            updateLastAssistant((msg) => ({
              ...msg,
              streaming: false,
              status: undefined,
              error: ev.message ?? t("ai.failed"),
            }))
          } else if (ev.type === "done") {
            updateLastAssistant((msg) => ({
              ...msg,
              streaming: false,
              status: undefined,
            }))
          }
        }
      }
      updateLastAssistant((msg) => ({
        ...msg,
        streaming: false,
        status: undefined,
        error: !gotText && !msg.error && !msg.content
          ? t("ai.timeout", { defaultValue: "响应超时，请改选 Composer 2.5 或稍后重试。" })
          : msg.error,
      }))
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError"
      updateLastAssistant((msg) => ({
        ...msg,
        streaming: false,
        status: undefined,
        error: aborted
          ? t("ai.timeout", { defaultValue: "响应超时，请改选 Composer 2.5 或稍后重试。" })
          : err instanceof Error ? err.message : t("ai.failed"),
      }))
    } finally {
      window.clearTimeout(timer)
      setAsking(false)
    }
  }

  if (!open) {
    return (
      <Button
        className="fixed bottom-6 right-6 z-40 gap-2 rounded-full px-4 shadow-lg"
        data-testid="platform-copilot"
        onClick={() => setOpen(true)}
      >
        <Sparkles className="h-4 w-4" />{title ?? t("ai.assistant")}
      </Button>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 z-40 w-[28rem] max-w-[calc(100vw-2rem)]" data-testid="platform-copilot-panel">
      <Card className="border-violet-500/30 shadow-2xl">
        <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 py-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Bot className="h-4 w-4 text-violet-500" />
            {title ?? t("platform.copilot")}
          </CardTitle>
          <Button variant="ghost" size="icon" className="h-7 w-7" title={t("ai.close")} onClick={() => setOpen(false)}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md border bg-muted/40 p-2 text-[11px] text-muted-foreground" data-testid="platform-ai-context">
            <div>Portfolio: {pageCtx.fund_id ?? "—"}</div>
            <div>Date: {pageCtx.as_of_date ?? "—"}</div>
            <div>Module: {page.context.module}</div>
          </div>

          <div className="space-y-1">
            <p className="text-[11px] text-muted-foreground">{t("ai.model", { defaultValue: "模型" })}</p>
            <Select value={modelId} onValueChange={setModelId} disabled={asking}>
              <SelectTrigger className="h-9 w-full text-xs" data-testid="copilot-model-selector">
                <SelectValue placeholder={t("ai.model", { defaultValue: "模型" })} />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                {modelGroups.map((group) => (
                  <div key={group.key}>
                    <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {group.icon} {group.label}
                    </div>
                    {group.models.map((model) => (
                      <SelectItem key={model.id} value={model.id} className="text-xs">
                        {model.label}
                      </SelectItem>
                    ))}
                  </div>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[10px] text-muted-foreground">
              {selectedModel?.provider ?? "—"} · {modelId}
            </p>
          </div>

          <div
            ref={listRef}
            className="flex max-h-[48vh] min-h-40 flex-col gap-2 overflow-y-auto overscroll-contain rounded-lg border bg-background/80 p-3 text-sm"
          >
            {messages.length === 0 ? (
              <div className="flex min-h-32 flex-col items-center justify-center text-center text-muted-foreground">
                <Bot className="mb-2 h-8 w-8 text-violet-500" />
                <p className="text-xs">{hint ?? t("platform.copilotHint")}</p>
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`rounded-lg px-3 py-2 text-sm ${
                    msg.role === "user"
                      ? "ml-6 bg-primary text-primary-foreground"
                      : "mr-6 border bg-muted/50"
                  }`}
                >
                  {msg.role === "user" ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <div className="space-y-1">
                      {msg.status ? (
                        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          {msg.status}
                        </p>
                      ) : null}
                      {msg.error ? (
                        <p className="text-xs text-destructive">{msg.error}</p>
                      ) : null}
                      {msg.content ? (
                        <div className="prose prose-sm dark:prose-invert max-w-none">
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={bottomRef} />
          </div>

          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={placeholder ?? t("platform.copilotPlaceholder")}
            rows={3}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                void ask()
              }
            }}
          />
          <Button className="w-full" disabled={asking || !question.trim()} onClick={() => void ask()}>
            {asking ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <MessageSquareText className="mr-2 h-4 w-4" />}
            {asking ? t("ai.asking") : t("ai.ask")}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

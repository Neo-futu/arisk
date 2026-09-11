import { Bot, MessageSquareText, Sparkles, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { fsiApi } from "@/fsiClient"
import { agentForModule } from "@/platform/nav"
import { formatPageContext, usePageContext } from "@/platform/page-context"

const KERNEL_AGENTS: Record<string, string> = {
  "risk-analyst": "risk_agent",
  "fund-reporter": "portfolio_agent",
  "valuation-reviewer": "valuation_agent",
  "month-end-closer": "workflow_agent",
  "market-researcher": "investment_agent",
  general: "investment_agent",
}

/**
 * Layout-level Copilot. Page context (portfolio / date / module / result / chart / metrics)
 * is injected so the Agent can call the matching Business API. Frontend never calculates.
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
  const [answer, setAnswer] = useState("")
  const [asking, setAsking] = useState(false)
  const pageAgent = agent ?? agentForModule(page.context.module)
  const pageCtx = {
    fund_id: context?.fund_id ?? page.context.portfolio,
    as_of_date: context?.as_of_date ?? page.context.date,
    module: page.context.module,
    result: page.context.result,
    chart: page.context.chart,
    risk_metrics: page.context.riskMetrics,
  }

  async function ask() {
    if (!question.trim()) return
    setAsking(true)
    const prompt = buildPrompt
      ? buildPrompt(question.trim())
      : [
          "You are the ARISK AI Copilot. Use the page context to call the matching Business / RiskEngine API.",
          "Do not invent NAV, VaR, PnL, stress loss, valuation, or limit numbers.",
          "Page context:",
          formatPageContext(page.context),
          `User question: ${question.trim()}`,
        ].join("\n")
    try {
      try {
        const kernel = await fsiApi.invokeAgents({
          message: prompt,
          agent: KERNEL_AGENTS[pageAgent] ?? "risk_agent",
          fund_id: pageCtx.fund_id ?? "TEST001",
        })
        const explanation = kernel.data.explanation || kernel.data.result
        if (kernel.data.ok && explanation) {
          setAnswer(typeof explanation === "string" ? explanation : JSON.stringify(explanation, null, 2))
          return
        }
      } catch {
        /* fall through to chat */
      }
      const response = await fsiApi.chatV2(prompt, pageAgent, pageCtx)
      setAnswer(response.data.reply)
    } catch {
      setAnswer(t("ai.failed"))
    } finally {
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
    <div className="fixed bottom-6 right-6 z-40 w-[26rem] max-w-[calc(100vw-2rem)]" data-testid="platform-copilot-panel">
      <Card className="border-violet-500/30 shadow-2xl">
        <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 py-3">
          <CardTitle className="flex items-center gap-2 text-sm"><Bot className="h-4 w-4 text-violet-500" />{title ?? t("platform.copilot")}</CardTitle>
          <Button variant="ghost" size="icon" className="h-7 w-7" title={t("ai.close")} onClick={() => setOpen(false)}><X className="h-4 w-4" /></Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md border bg-muted/40 p-2 text-[11px] text-muted-foreground" data-testid="platform-ai-context">
            <div>Portfolio: {pageCtx.fund_id ?? "—"}</div>
            <div>Date: {pageCtx.as_of_date ?? "—"}</div>
            <div>Module: {page.context.module}</div>
            <div>Result: {page.context.result ?? "—"}</div>
            <div>Chart: {page.context.chart ?? "—"}</div>
          </div>
          <div className="max-h-[52vh] min-h-40 overflow-y-auto rounded-lg border bg-background/80 p-3 text-sm">
            {answer ? (
              <div className="prose prose-sm dark:prose-invert"><ReactMarkdown>{answer}</ReactMarkdown></div>
            ) : (
              <div className="flex min-h-32 flex-col items-center justify-center text-center text-muted-foreground">
                <Bot className="mb-2 h-8 w-8 text-violet-500" />
                <p className="text-xs">{hint ?? t("platform.copilotHint")}</p>
              </div>
            )}
          </div>
          <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={placeholder ?? t("platform.copilotPlaceholder")} rows={3} />
          <Button className="w-full" disabled={asking || !question.trim()} onClick={ask}>
            <MessageSquareText className="mr-2 h-4 w-4" />{asking ? t("ai.asking") : t("ai.ask")}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

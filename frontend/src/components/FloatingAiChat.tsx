import { Bot, MessageSquareText, Sparkles, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { fsiApi } from "@/fsiClient"

/**
 * Floating, popup contextual AI assistant. Rendered once per page at the root; it
 * shows a floating action button and expands into an overlay chat window, so the
 * main page content always uses full width and the assistant never steals layout.
 */
export function FloatingAiChat({
  title,
  hint,
  placeholder,
  buildPrompt,
  agent = "risk-analyst",
  context,
}: {
  title: string
  hint: string
  placeholder: string
  buildPrompt: (question: string) => string
  agent?: string
  context?: { fund_id?: string; as_of_date?: string }
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState("")
  const [answer, setAnswer] = useState("")
  const [asking, setAsking] = useState(false)

  async function ask() {
    if (!question.trim()) return
    setAsking(true)
    try {
      const response = await fsiApi.chatV2(buildPrompt(question.trim()), agent, context)
      setAnswer(response.data.reply)
    } catch {
      setAnswer(t("ai.failed"))
    } finally {
      setAsking(false)
    }
  }

  if (!open) {
    return (
      <Button className="fixed bottom-6 right-6 z-40 gap-2 rounded-full px-4 shadow-lg" onClick={() => setOpen(true)}>
        <Sparkles className="h-4 w-4" />{t("ai.assistant")}
      </Button>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 z-40 w-[26rem] max-w-[calc(100vw-2rem)]">
      <Card className="border-violet-500/30 shadow-2xl">
        <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 py-3">
          <CardTitle className="flex items-center gap-2 text-sm"><Bot className="h-4 w-4 text-violet-500" />{title}</CardTitle>
          <Button variant="ghost" size="icon" className="h-7 w-7" title={t("ai.close")} onClick={() => setOpen(false)}><X className="h-4 w-4" /></Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="max-h-[52vh] min-h-40 overflow-y-auto rounded-lg border bg-background/80 p-3 text-sm">
            {answer ? (
              <div className="prose prose-sm dark:prose-invert"><ReactMarkdown>{answer}</ReactMarkdown></div>
            ) : (
              <div className="flex min-h-32 flex-col items-center justify-center text-center text-muted-foreground">
                <Bot className="mb-2 h-8 w-8 text-violet-500" />
                <p className="text-xs">{hint}</p>
              </div>
            )}
          </div>
          <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={placeholder} rows={3} />
          <Button className="w-full" disabled={asking || !question.trim()} onClick={ask}>
            <MessageSquareText className="mr-2 h-4 w-4" />{asking ? t("ai.asking") : t("ai.ask")}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

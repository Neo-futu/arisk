/**
 * expert.tsx — 專家知識庫頁面
 * 通過真實 AI 對話（支持多模型）提取業務技能，索引入 3_skills 知識庫
 */
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  BookOpen, Brain, FileUp, Loader2, Plus,
  Send, Sparkles, Trash2,
} from "lucide-react"
import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { FALLBACK_MODELS, MODEL_GROUPS } from "@/components/Chat/constants"
import { fsiApi } from "@/fsiClient"
import axios from "axios"

export const Route = createFileRoute("/_layout/expert")({
  component: ExpertPage,
  head: () => ({ meta: [{ title: "Expert Knowledge Base — ARISK" }] }),
})

const BASE = (import.meta.env.VITE_API_URL as string) || ""
const authHeaders = () => {
  const t = localStorage.getItem("access_token")
  return t ? { Authorization: `Bearer ${t}` } : {}
}

const extractSkillNameFromContent = (content: string) => {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/)
  if (!match) return ""
  const nameLine = match[1].split("\n").find(line => line.startsWith("name:"))
  return nameLine ? nameLine.split(":", 2)[1].trim() : ""
}

const isPlaceholderSkillTitle = (title: string) => {
  const normalized = title.trim().toLowerCase()
  return ["new-skill", "new skill", "skill", "untitled-skill", "placeholder-skill"].includes(normalized)
}

// ── 知識文檔列表 ────────────────────────────────────────────────
function DocumentList() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: docs = [], isLoading } = useQuery({
    queryKey: ["knowledge-docs"],
    queryFn: () => axios.get(`${BASE}/api/v1/knowledge/documents?limit=50`,
      { headers: authHeaders() }).then(r => r.data),
    staleTime: 10_000,
  })
  const visibleDocs = docs.filter((d: any) => !(d.source === "skill_doc" && isPlaceholderSkillTitle(String(d.title ?? ""))))
  const sourceColor: Record<string, string> = {
    skill_doc:    "bg-blue-100 text-blue-700",
    agent_prompt: "bg-purple-100 text-purple-700",
    expert_chat:  "bg-green-100 text-green-700",
    sfc_regulation: "bg-red-100 text-red-700",
    fund_doc:     "bg-orange-100 text-orange-700",
    manual:       "bg-gray-100 text-gray-700",
  }
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <BookOpen className="h-4 w-4" />
          {t("expert.indexedDocs")}
          <Badge variant="outline" className="ml-auto">{t("expert.docCount", { count: visibleDocs.length })}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? <p className="text-xs text-muted-foreground animate-pulse">{t("expert.loading")}</p>
          : visibleDocs.length === 0 ? <p className="text-xs text-muted-foreground">{t("expert.noDocs")}</p>
          : (
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {visibleDocs.map((d: any) => (
                <div key={d.id} className="flex items-center gap-2 text-xs group">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] shrink-0 ${sourceColor[d.source] ?? "bg-gray-100 text-gray-700"}`}>
                    {d.source}
                  </span>
                  <span className="flex-1 truncate">{d.title}</span>
                  <span className="text-muted-foreground shrink-0">{t("expert.chunkCount", { count: d.chunk_count })}</span>
                  <button
                    className="invisible group-hover:visible text-muted-foreground hover:text-destructive"
                    onClick={() => axios.delete(`${BASE}/api/v1/knowledge/${d.id}`, { headers: authHeaders() })
                      .then(() => qc.invalidateQueries({ queryKey: ["knowledge-docs"] }))}
                  ><Trash2 className="h-3 w-3" /></button>
                </div>
              ))}
            </div>
          )}
      </CardContent>
    </Card>
  )
}

// ── 主頁面 ──────────────────────────────────────────────────────
function ExpertPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  // 模型選擇
  const { data: modelListRaw } = useQuery({
    queryKey: ["models-list"],
    queryFn: () => fsiApi.listModels().then(r => r.data),
    staleTime: 60_000,
  })
  const modelList = modelListRaw ?? FALLBACK_MODELS
  const [modelId, setModelId] = useState("x-ai/grok-4.20")

  // 對話狀態
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([])
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [topic, setTopic] = useState("")
  const [layer, setLayer] = useState<"chat" | "platform">("chat")
  const bottomRef = useRef<HTMLDivElement>(null)

  // 提取結果
  const [extractedSkill, setExtractedSkill] = useState("")
  const [extracting, setExtracting] = useState(false)

  // 文件上傳
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState("")

  // 保存技能
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState("")

  const addMsg = (role: string, content: string) =>
    setMessages(prev => [...prev, { role, content }])
  const updateLastAssistant = (text: string) =>
    setMessages(prev => {
      const copy = [...prev]
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role === "assistant") { copy[i] = { role: "assistant", content: text }; break }
      }
      return copy
    })

  // ── 真實 AI 流式對話 ─────────────────────────────────────────
  const sendMessage = async () => {
    const text = input.trim()
    if (!text || streaming) return
    addMsg("user", text)
    setInput("")
    setStreaming(true)

    // expert agent 的對話歷史 + 當前消息
    const history = [
      ...messages.map(m => ({ role: m.role, content: m.content })),
      { role: "user" as const, content: text },
    ]

    // 加入 assistant 佔位
    addMsg("assistant", "")

    try {
      const token = localStorage.getItem("access_token") ?? ""
      // 使用 general agent（帶知識提取上下文的系統提示）
      const resp = await fetch(`${BASE}/api/v1/fsi/agent/v2/stream`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history,
          agent: "general",
          model: modelId,
          context: {
            _expert_mode: "true",
            _instruction: "你正在幫助業務專家提取和結構化業務技能知識。請詳細詢問執行步驟、業務規則、邊界條件和輸出格式，引導專家完整描述技能。",
          },
        }),
      })

      if (!resp.ok) {
        updateLastAssistant(t("expert.requestFailed", { status: resp.status }))
        return
      }

      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buf = "", fullContent = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n"); buf = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.type === "text" && ev.content) {
              fullContent += ev.content
              updateLastAssistant(fullContent)
              bottomRef.current?.scrollIntoView({ behavior: "smooth" })
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: any) {
      updateLastAssistant(t("expert.errorPrefix", { error: err.message }))
    } finally {
      setStreaming(false)
    }
  }

  // ── AI 提取技能 ──────────────────────────────────────────────
  const extractSkill = async () => {
    if (messages.length < 2) { alert(t("expert.alertConverseFirst")); return }
    if (!topic.trim()) { alert(t("expert.alertTopicRequired")); return }
    setExtracting(true)
    try {
      const resp = await axios.post(`${BASE}/api/v1/knowledge/extract-skill`,
        { conversation: messages, topic, layer, model_id: modelId },
        { headers: authHeaders() })
      setExtractedSkill(resp.data.skill_content || "")
    } catch (err: any) {
      alert(t("expert.extractFailed", { error: err.response?.data?.detail || err.message }))
    } finally { setExtracting(false) }
  }

  // ── 保存為 3_skills 文件 ──────────────────────────────────────
  const saveSkillAsFile = async () => {
    if (!extractedSkill.trim() || !topic.trim()) return
    setSaving(true); setSaveMsg("")
    const frontmatterName = extractSkillNameFromContent(extractedSkill)
    const skillName = (frontmatterName || topic.trim().toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "").replace(/-+/g, "-")) || "skill"
    try {
      const resp = await axios.post(`${BASE}/api/v1/knowledge/save-skill`,
        { skill_name: skillName, skill_content: extractedSkill, layer: layer === "platform" ? "expert" : "chat", also_index: true },
        { headers: authHeaders() })
      setSaveMsg(`✅ ${t("expert.saved", { path: resp.data.file_path })}${resp.data.indexed ? t("expert.savedIndexed") : ""}`)
      qc.invalidateQueries({ queryKey: ["knowledge-docs"] })
    } catch (err: any) {
      setSaveMsg(`❌ ${t("expert.saveFailed", { error: err.response?.data?.detail || err.message })}`)
    } finally { setSaving(false) }
  }

  const saveToKnowledgeOnly = async () => {
    if (!extractedSkill.trim()) return
    setSaving(true); setSaveMsg("")
    try {
      const resp = await axios.post(`${BASE}/api/v1/knowledge/ingest`,
        { title: `[Expert Chat] ${topic}`, content: extractedSkill, source: "expert_chat", doc_type: "skill" },
        { headers: authHeaders() })
      setSaveMsg(`✅ ${t("expert.indexedChunks", { count: resp.data.chunk_count, mode: resp.data.search_mode })}`)
      qc.invalidateQueries({ queryKey: ["knowledge-docs"] })
    } catch (err: any) {
      setSaveMsg(`❌ ${t("expert.saveFailed", { error: err.response?.data?.detail || err.message })}`)
    } finally { setSaving(false) }
  }

  // ── 文件上傳 ─────────────────────────────────────────────────
  const uploadFile = async (file: File) => {
    setUploading(true); setUploadMsg("")
    const form = new FormData()
    form.append("file", file); form.append("source", "expert_chat"); form.append("doc_type", "experience")
    try {
      const resp = await axios.post(`${BASE}/api/v1/knowledge/ingest-file`, form,
        { headers: { ...authHeaders(), "Content-Type": "multipart/form-data" } })
      setUploadMsg(`✅ ${t("expert.uploadSuccess", { message: resp.data.message })}`)
      qc.invalidateQueries({ queryKey: ["knowledge-docs"] })
    } catch (err: any) {
      setUploadMsg(`❌ ${t("expert.saveFailed", { error: err.response?.data?.detail || err.message })}`)
    } finally { setUploading(false) }
  }

  return (
    <div className="space-y-4">
      {/* 頁面標題 */}
      <div className="flex items-center gap-3">
        <Brain className="h-6 w-6 text-primary" />
        <div className="flex-1">
          <h1 className="text-xl font-bold">{t("expert.title")}</h1>
          <p className="text-xs text-muted-foreground">{t("expert.subtitle")}</p>
        </div>
        {/* 模型選擇器 */}
        <Select value={modelId} onValueChange={setModelId}>
          <SelectTrigger className="h-8 w-52 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper" sideOffset={4} className="z-[200] max-h-80 overflow-y-auto w-64">
            {MODEL_GROUPS.map((group, gi) => {
              const items = modelList.filter(m => m.provider === group.key)
              if (!items.length) return null
              return (
                <div key={group.key}>
                  <div className={`px-2 py-1 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide ${gi > 0 ? "mt-1 border-t" : ""}`}>
                    {t(group.labelKey)}
                  </div>
                  {items.map(m => {
                    const cm = m as { id: string; label: string; baseLabel?: string; tagKey?: string | null }
                    const label = cm.baseLabel
                      ? (cm.tagKey ? `${cm.baseLabel} (${t(cm.tagKey)})` : cm.baseLabel)
                      : cm.label
                    return (
                      <SelectItem key={m.id} value={m.id} className="text-xs">
                        <span className={`${group.color} mr-1`}>{group.icon}</span>
                        {label}
                      </SelectItem>
                    )
                  })}
                </div>
              )
            })}
          </SelectContent>
        </Select>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {/* 左欄：AI 對話 + 技能提取 */}
        <div className="space-y-3">
          {/* 技能設置 */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{t("expert.topicSettings")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Input value={topic} onChange={e => setTopic(e.target.value)}
                placeholder={t("expert.topicPlaceholder")} className="text-sm" />
              <div className="flex gap-2">
                {(["chat", "platform"] as const).map(l => (
                  <button key={l}
                    className={`flex-1 rounded-md border py-1.5 text-xs transition-colors ${layer === l ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
                    onClick={() => setLayer(l)}>
                    {l === "chat" ? t("expert.layerUser") : t("expert.layerSystem")}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* AI 對話區 */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                {t("expert.chatTitle")}
                {streaming && <Badge variant="secondary" className="gap-1 text-xs ml-auto">
                  <Loader2 className="h-3 w-3 animate-spin" />{t("expert.analyzing")}
                </Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="h-56 overflow-y-auto space-y-2 border rounded-lg p-2 bg-background">
                {messages.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center py-6">
                    {t("expert.chatEmpty")}<br/>
                    <span className="text-[10px]">{t("expert.currentModel", { model: modelId })}</span>
                  </p>
                ) : messages.map((m, i) => (
                  <div key={i} className={`text-xs rounded-lg p-2 ${m.role === "user" ? "bg-primary/10 ml-6" : "bg-muted mr-6"}`}>
                    <span className="font-medium text-muted-foreground">{m.role === "user" ? t("expert.roleUser") : t("expert.roleAi")}：</span>
                    <span className="whitespace-pre-wrap">{m.content}</span>
                    {m.role === "assistant" && streaming && i === messages.length - 1 && (
                      <span className="inline-block h-3 w-0.5 bg-current animate-pulse align-middle ml-0.5" />
                    )}
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
              <div className="flex gap-2">
                <Textarea value={input} onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage() }}}
                  placeholder={t("expert.inputPlaceholder")} rows={2}
                  disabled={streaming} className="text-sm resize-none" />
                <Button size="icon" onClick={sendMessage} disabled={streaming || !input.trim()}>
                  {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* 提取技能 */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-amber-500" />{t("expert.extractTitle")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button className="w-full gap-2" variant="outline" onClick={extractSkill}
                disabled={extracting || messages.length < 2}>
                {extracting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Brain className="h-4 w-4" />}
                {extracting ? t("expert.extracting") : t("expert.extractFromChat")}
              </Button>

              {extractedSkill && (
                <div className="space-y-2">
                  <p className="text-xs text-muted-foreground">{t("expert.extractResultHint")}</p>
                  <Textarea value={extractedSkill} onChange={e => setExtractedSkill(e.target.value)}
                    rows={8} className="text-xs font-mono" />
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="default" className="gap-1.5 text-xs" onClick={saveSkillAsFile} disabled={saving}>
                      {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookOpen className="h-3.5 w-3.5" />}
                      {t("expert.saveAsSkill")}
                    </Button>
                    <Button variant="outline" className="gap-1.5 text-xs" onClick={saveToKnowledgeOnly} disabled={saving}>
                      <Plus className="h-3.5 w-3.5" />{t("expert.saveToKnowledgeOnly")}
                    </Button>
                  </div>
                  {saveMsg && <p className={`text-xs ${saveMsg.startsWith("✅") ? "text-green-600" : "text-red-500"}`}>{saveMsg}</p>}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 右欄：文件上傳 + 知識庫 */}
        <div className="space-y-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileUp className="h-4 w-4" />{t("expert.uploadTitle")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="border-2 border-dashed rounded-lg p-5 text-center cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => fileRef.current?.click()}>
                <FileUp className="h-7 w-7 mx-auto text-muted-foreground mb-1.5" />
                <p className="text-xs text-muted-foreground">{t("expert.uploadFormats")}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">{t("expert.uploadHint")}</p>
              </div>
              <input ref={fileRef} type="file" accept=".pdf,.docx,.md,.txt" className="hidden"
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => { if (e.target.files?.[0]) uploadFile(e.target.files[0]) }} />
              {uploading && <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />{t("expert.processing")}</div>}
              {uploadMsg && <p className={`text-xs ${uploadMsg.startsWith("✅") ? "text-green-600" : "text-red-500"}`}>{uploadMsg}</p>}
            </CardContent>
          </Card>

          <DocumentList />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{t("expert.knowledgeHelpTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground space-y-1.5">
              <p>📝 <strong>{t("expert.helpBackendLabel")}</strong>：{t("expert.helpBackend")}</p>
              <p>💬 <strong>{t("expert.helpExpertLabel")}</strong>：{t("expert.helpExpert")}</p>
              <p>📄 <strong>{t("expert.helpUploadLabel")}</strong>：{t("expert.helpUpload")}</p>
              <div className="border-t pt-1.5 mt-1">
                <p><code>skill_doc</code> {t("expert.helpSkillDoc")}</p>
                <p><code>agent_prompt</code> {t("expert.helpAgentPrompt")}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

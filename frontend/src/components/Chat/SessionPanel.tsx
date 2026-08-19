import { MessageSquarePlus, Search, Sparkles, Trash2, X } from "lucide-react"
import { type MouseEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import axios from "axios"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import type { ChatSessionRecord } from "@/fsiClient"
import { fsiApi } from "@/fsiClient"
import { groupSessionsByDate } from "./utils"

const BASE = (import.meta.env.VITE_API_URL as string) || ""
const authHeaders = () => {
  const t = localStorage.getItem("access_token")
  return t ? { Authorization: `Bearer ${t}` } : {}
}

interface Props {
  sessions:         ChatSessionRecord[]
  currentSessionId: string | null
  onSelect:         (id: string) => void
  onDelete:         (id: string) => void
  onNew:            () => void
}

// ── 技能提取彈窗 ──────────────────────────────────────────────────
function SkillExtractModal({
  session,
  onClose,
}: {
  session: ChatSessionRecord
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [topic,     setTopic]     = useState(session.title.slice(0, 40))
  const [layer,     setLayer]     = useState<"chat" | "expert">("chat")
  const [extracted, setExtracted] = useState("")
  const [loading,   setLoading]   = useState(false)
  const [saving,    setSaving]    = useState(false)
  const [msg,       setMsg]       = useState("")

  const extract = async () => {
    if (!topic.trim()) { alert(t("chat.alertTopicRequired")); return }
    setLoading(true); setMsg("")
    try {
      // 先拉取對話消息
      const msgsResp = await fsiApi.getChatMessages(session.id)
      const conversation = msgsResp.data.map(m => ({ role: m.role, content: m.content }))
      if (conversation.length < 2) { alert(t("chat.alertConversationTooShort")); return }

      // 從 localStorage 讀取用戶偏好模型，默認 Grok（OpenRouter，無地區限制）
      const preferredModel = localStorage.getItem("arisk_preferred_model") || "x-ai/grok-4.20"
      const resp = await axios.post(`${BASE}/api/v1/knowledge/extract-skill`,
        { conversation, topic, layer: layer === "chat" ? "chat" : "expert", model_id: preferredModel },
        { headers: authHeaders() })
      setExtracted(resp.data.skill_content || "")
    } catch (err: any) {
      setMsg(t("chat.extractFailed", { error: err.response?.data?.detail || err.message }))
    } finally { setLoading(false) }
  }

  const save = async () => {
    if (!extracted.trim()) return
    setSaving(true); setMsg("")
    const skillName = topic.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "").replace(/-+/g, "-") || "skill"
    try {
      const resp = await axios.post(`${BASE}/api/v1/knowledge/save-skill`,
        { skill_name: skillName, skill_content: extracted, layer, also_index: true },
        { headers: authHeaders() })
      setMsg(t("chat.saveSuccess", { path: resp.data.file_path, indexed: resp.data.indexed ? t("chat.savedIndexed") : "" }))
    } catch (err: any) {
      setMsg(t("chat.saveFailed", { error: err.response?.data?.detail || err.message }))
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-background border rounded-xl shadow-xl w-[500px] max-h-[80vh] flex flex-col p-4 gap-3">
        {/* 標題欄 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-500" />
            <span className="font-semibold text-sm">{t("chat.modalTitle")}</span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="text-xs text-muted-foreground">{t("chat.modalConversation", { title: session.title })}</p>

        {/* 設置 */}
        <div className="space-y-2">
          <Input value={topic} onChange={e => setTopic(e.target.value)}
            placeholder={t("chat.topicPlaceholder")} className="text-sm" />
          <div className="flex gap-2">
            {(["chat", "expert"] as const).map(l => (
              <button key={l}
                className={`flex-1 rounded border py-1 text-xs transition-colors ${layer === l ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
                onClick={() => setLayer(l)}>
                {l === "chat" ? t("chat.layerChat") : t("chat.layerExpert")}
              </button>
            ))}
          </div>
        </div>

        {/* 提取按鈕 */}
        <Button variant="outline" className="gap-2 text-xs" onClick={extract} disabled={loading}>
          {loading
            ? <><span className="h-3.5 w-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />{t("chat.extracting")}</>
            : <><Sparkles className="h-3.5 w-3.5 text-amber-500" />{t("chat.aiExtract")}</>}
        </Button>

        {/* 提取結果 */}
        {extracted && (
          <div className="flex-1 overflow-hidden flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">{t("chat.extractResultLabel")}</p>
            <Textarea value={extracted} onChange={e => setExtracted(e.target.value)}
              className="flex-1 text-xs font-mono resize-none min-h-[180px]" />
            <Button className="gap-2 text-xs" onClick={save} disabled={saving}>
              {saving ? t("chat.saving") : t("chat.saveSkill")}
            </Button>
          </div>
        )}

        {msg && <p className={`text-xs ${msg.startsWith("✅") ? "text-green-600" : "text-red-500"}`}>{msg}</p>}
      </div>
    </div>
  )
}

// ── 會話列表項 ───────────────────────────────────────────────────
function SessionItem({
  session, isActive, onSelect, onDelete, onExtractSkill,
}: {
  session:         ChatSessionRecord
  isActive:        boolean
  onSelect:        () => void
  onDelete:        () => void
  onExtractSkill:  () => void
}) {
  const { t } = useTranslation()
  const [hover, setHover] = useState(false)
  return (
    <div
      className={`group flex items-center gap-1 rounded-lg px-2 py-2 cursor-pointer text-sm transition-colors ${
        isActive ? "bg-muted font-medium" : "hover:bg-muted/50"
      }`}
      onClick={onSelect}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="flex-1 truncate text-foreground text-xs">{session.title}</span>
      {hover && (
        <div className="flex items-center gap-0.5 shrink-0">
          {/* 提取技能（醒目） */}
          <button
            className="flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium
                       bg-amber-50 text-amber-600 hover:bg-amber-100 border border-amber-200 transition-colors"
            onClick={(e: MouseEvent) => { e.stopPropagation(); onExtractSkill() }}
            title={t("chat.extractTitle")}
          >
            <Sparkles className="h-3 w-3" />{t("chat.extractButton")}
          </button>
          {/* 刪除 */}
          <button
            className="rounded p-0.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
            onClick={(e: MouseEvent) => { e.stopPropagation(); onDelete() }}
            title={t("chat.deleteTitle")}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  )
}

// ── 主面板 ───────────────────────────────────────────────────────
export function SessionPanel({ sessions, currentSessionId, onSelect, onDelete, onNew }: Props) {
  const { t } = useTranslation()
  const [query,            setQuery]           = useState("")
  const [extractingSession, setExtractingSession] = useState<ChatSessionRecord | null>(null)

  const filtered = query.trim()
    ? sessions.filter(s => s.title.toLowerCase().includes(query.toLowerCase()))
    : sessions
  const groups = groupSessionsByDate(filtered, {
    today:     t("chat.groupToday"),
    yesterday: t("chat.groupYesterday"),
    thisWeek:  t("chat.groupThisWeek"),
    older:     t("chat.groupOlder"),
  })

  return (
    <>
      <div className="flex w-60 shrink-0 flex-col border-l bg-background">
        {/* 新對話 */}
        <div className="border-b p-3">
          <Button size="sm" variant="outline" className="w-full gap-2 text-xs" onClick={onNew}>
            <MessageSquarePlus className="h-3.5 w-3.5" />{t("chat.newChat")}
          </Button>
        </div>

        {/* 搜索 */}
        <div className="px-3 py-2 border-b">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
            <Input value={query} onChange={e => setQuery(e.target.value)}
              placeholder={t("chat.searchPlaceholder")} className="h-8 pl-8 text-xs" />
          </div>
        </div>

        {/* 會話列表 */}
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-3">
          {groups.length === 0 && (
            <p className="px-3 py-4 text-center text-xs text-muted-foreground">{t("chat.noSessions")}</p>
          )}
          {groups.map(group => (
            <div key={group.label}>
              <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {group.label}
              </p>
              {group.items.map(s => (
                <SessionItem
                  key={s.id}
                  session={s}
                  isActive={s.id === currentSessionId}
                  onSelect={() => onSelect(s.id)}
                  onDelete={() => onDelete(s.id)}
                  onExtractSkill={() => setExtractingSession(s)}
                />
              ))}
            </div>
          ))}
        </div>

        {/* 底部提示 */}
        <div className="border-t px-3 py-2">
          <p className="text-[10px] text-muted-foreground flex items-center gap-1">
            <Sparkles className="h-3 w-3 text-amber-400" />
            {t("chat.hoverExtractHint")}
          </p>
        </div>
      </div>

      {/* 技能提取彈窗 */}
      {extractingSession && (
        <SkillExtractModal
          session={extractingSession}
          onClose={() => setExtractingSession(null)}
        />
      )}
    </>
  )
}

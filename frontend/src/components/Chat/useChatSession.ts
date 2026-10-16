import { useQuery } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { fsiApi } from "@/fsiClient"
import type { ChatSessionRecord } from "@/fsiClient"
import { usePageContext } from "@/platform/page-context"
import { FALLBACK_AGENTS, FALLBACK_MODELS } from "./constants"
import { parseToolCalls } from "./utils"
import type { ChatMessage, SSEEvent, ToolCallRecord } from "./types"

export function useChatSession(initialAgentId?: string) {
  const { t } = useTranslation()
  const { context: pageCtx } = usePageContext()
  const [sessions,          setSessions]          = useState<ChatSessionRecord[]>([])
  const [currentSessionId,  setCurrentSessionId]  = useState<string | null>(null)
  const [messages,          setMessages]          = useState<ChatMessage[]>([])
  const [streaming,         setStreaming]          = useState(false)
  const [input,             setInput]             = useState("")
  const [agentId,           setAgentId]           = useState(initialAgentId ?? "general")
  const [modelId,           setModelId]           = useState("auto-smart")
  const bottomRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)
  const sessionIdRef = useRef<string | null>(null)
  const skillsRefreshPromiseRef = useRef<Promise<void> | null>(null)

  useEffect(() => { sessionIdRef.current = currentSessionId }, [currentSessionId])

  useEffect(() => {
    if (initialAgentId) setAgentId(initialAgentId)
  }, [initialAgentId])

  useEffect(() => {
    skillsRefreshPromiseRef.current = fsiApi.refreshSkills()
      .then(() => {})
      .catch(() => {})
  }, [])

  // 載入用戶專屬 Agent 配置 + 會話列表
  useEffect(() => {
    // 優先加載用戶個人配置，設置默認 Agent 和模型
    fsiApi.getMyAgentConfig()
      .then(r => {
        const cfg = r.data
        if (!initialAgentId && cfg.default_agent_id) setAgentId(cfg.default_agent_id)
        if (cfg.default_model_id) setModelId(cfg.default_model_id)
      })
      .catch(() => {}) // 加載失敗時保持系統默認值

    fsiApi.listChatSessions()
      .then(r => setSessions(r.data))
      .catch(() => {})
  }, [initialAgentId])

  // 拉取 Agent / 模型列表
  const { data: agentListRaw } = useQuery({ queryKey: ["agents-list"],  queryFn: () => fsiApi.listAgents().then(r => r.data),  staleTime: 60_000 })
  const { data: modelListRaw } = useQuery({ queryKey: ["models-list"], queryFn: () => fsiApi.listModels().then(r => r.data), staleTime: 60_000 })

  // Agent 列表：API 返回 { id, name } 直接用；無數據時用 fallback 的 nameKey 翻譯
  const agentList = agentListRaw ?? FALLBACK_AGENTS.map(a => ({ id: a.id, name: t(a.nameKey) }))
  // 模型列表：API 返回 { id, label, provider, default } 直接用；無數據時用 fallback，把 tagKey 拼接到 label
  const modelList = modelListRaw ?? FALLBACK_MODELS.map(m => ({
    id: m.id,
    label: m.tagKey ? `${m.baseLabel}（${t(m.tagKey)}）` : m.baseLabel,
    provider: m.provider,
    default: m.default,
  }))

  // 只滾消息列表容器，避免 scrollIntoView 帶動整頁上移
  useEffect(() => {
    const list = listRef.current
    if (!list) return
    list.scrollTo({ top: list.scrollHeight, behavior: "smooth" })
  }, [messages])

  // ── 加載歷史會話 ─────────────────────────────────────────────────
  const loadSession = async (id: string) => {
    try {
      const res = await fsiApi.getChatMessages(id)
      const msgs: ChatMessage[] = res.data.map(m => ({
        id:          m.id,
        role:        m.role as "user" | "assistant",
        content:     m.content,
        toolCalls:   parseToolCalls(m.tool_calls) as ToolCallRecord[],
        isStreaming: false,
      }))
      setMessages(msgs)
      setCurrentSessionId(id)
      const s = sessions.find(x => x.id === id)
      if (s) { setAgentId(s.agent_id); setModelId(s.model_id) }
    } catch { /* ignore */ }
  }

  // ── 新對話 ───────────────────────────────────────────────────────
  const newChat = () => {
    setCurrentSessionId(null)
    setMessages([])
    inputRef.current?.focus()
  }

  // ── 刪除會話 ─────────────────────────────────────────────────────
  const deleteSession = async (id: string) => {
    await fsiApi.deleteChatSession(id).catch(() => {})
    setSessions(prev => prev.filter(s => s.id !== id))
    if (currentSessionId === id) newChat()
  }

  // ── 更新 messages ────────────────────────────────────────────────
  const addMessage = (msg: ChatMessage) => setMessages(prev => [...prev, msg])
  const updateLastAssistant = (fn: (m: ChatMessage) => ChatMessage) =>
    setMessages(prev => {
      const copy = [...prev]
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role === "assistant") { copy[i] = fn(copy[i]); break }
      }
      return copy
    })

  // ── SSE 流式發送 ─────────────────────────────────────────────────
  const sendMessage = async () => {
    const userText = input.trim()
    if (!userText || streaming) return
    setInput("")

    if (skillsRefreshPromiseRef.current) {
      await skillsRefreshPromiseRef.current.catch(() => {})
    }

    // 確保有會話（第一條消息時新建）
    let sid = sessionIdRef.current
    if (!sid) {
      try {
        const res = await fsiApi.createChatSession({
          title:    userText.slice(0, 30),
          agent_id: agentId,
          model_id: modelId,
        })
        sid = res.data.id
        setCurrentSessionId(sid)
        setSessions(prev => [res.data, ...prev])
      } catch { /* 無後端時不阻塞 */ }
    }

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: userText, toolCalls: [], isStreaming: false }
    addMessage(userMsg)

    const historyForApi = [
      ...messages.filter(m => !m.isStreaming).map(m => ({ role: m.role, content: m.content })),
      { role: "user" as const, content: userText },
    ]

    const assistantMsg: ChatMessage = { id: crypto.randomUUID(), role: "assistant", content: "", toolCalls: [], isStreaming: true }
    addMessage(assistantMsg)
    setStreaming(true)

    let assistantContent = ""
    const assistantToolCalls: ToolCallRecord[] = []

    try {
      // 從 JWT 中取 user_id（base64 decode payload）
      let userId: string | undefined
      try {
        const token = localStorage.getItem("access_token") ?? ""
        const payload = JSON.parse(atob(token.split(".")[1]))
        userId = payload.sub
      } catch { /* ignore */ }

      const agentContext = {
        fund_id: pageCtx.portfolio || undefined,
        as_of_date: pageCtx.date || undefined,
      }
      const response = await fsiApi.streamAgentChat(
        historyForApi, agentId, agentContext, modelId, sid ?? undefined, userId,
      )
      if (!response.ok) {
        const err = await response.text()
        updateLastAssistant(m => ({ ...m, isStreaming: false, error: t("chat.requestFailed", { status: response.status, detail: err.slice(0, 200) }) }))
        return
      }
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n"); buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          let ev: SSEEvent
          try { ev = JSON.parse(line.slice(6)) } catch { continue }
          if (ev.type === "text" && ev.content) {
            assistantContent += ev.content
            updateLastAssistant(m => ({ ...m, content: m.content + ev.content! }))
          } else if (ev.type === "tool_call" && ev.id) {
            const tc: ToolCallRecord = { id: ev.id, name: ev.name ?? "", input: (ev.input ?? {}) as Record<string, unknown>, result: null, done: false }
            assistantToolCalls.push(tc)
            updateLastAssistant(m => ({ ...m, toolCalls: [...m.toolCalls, tc] }))
          } else if (ev.type === "tool_result" && ev.id) {
            const idx = assistantToolCalls.findIndex(t => t.id === ev.id)
            if (idx >= 0) assistantToolCalls[idx] = { ...assistantToolCalls[idx], result: ev.result, done: true }
            updateLastAssistant(m => ({ ...m, toolCalls: m.toolCalls.map(t => t.id === ev.id ? { ...t, result: ev.result, done: true } : t) }))
          } else if (ev.type === "error") {
            updateLastAssistant(m => ({ ...m, isStreaming: false, error: ev.message ?? t("chat.agentError") }))
          } else if (ev.type === "done") {
            updateLastAssistant(m => ({ ...m, isStreaming: false }))
          }
        }
      }
      // 持久化本次消息對
      if (sid) {
        fsiApi.saveChatMessages(sid, [
          { role: "user",      content: userText,          tool_calls: [] },
          { role: "assistant", content: assistantContent,  tool_calls: assistantToolCalls },
        ]).then(() => {
          // 刷新 updated_at（讓會話列表排序更新）
          setSessions(prev => prev.map(s => s.id === sid ? { ...s, updated_at: new Date().toISOString() } : s)
            .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()))
        }).catch(() => {})
      }
    } catch (err) {
      updateLastAssistant(m => ({ ...m, isStreaming: false, error: err instanceof Error ? err.message : t("chat.networkError") }))
    } finally {
      setStreaming(false)
    }
  }

  return {
    sessions, currentSessionId, messages, streaming,
    input, setInput, agentId, setAgentId, modelId, setModelId,
    agentList,
    modelList,
    sendMessage, newChat, loadSession, deleteSession,
    bottomRef, listRef, inputRef,
  }
}

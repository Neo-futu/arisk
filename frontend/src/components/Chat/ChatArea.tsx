import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Bot, Loader2, Send, SquarePen } from "lucide-react"
import { useTranslation } from "react-i18next"
import { MODEL_GROUPS } from "./constants"
import { MessageBubble } from "./MessageBubble"
import type { ChatMessage } from "./types"
import type { RefObject } from "react"

type NullableRef<T> = RefObject<T | null>

interface Props {
  messages:   ChatMessage[]
  streaming:  boolean
  input:      string
  setInput:   (v: string) => void
  agentId:    string
  setAgentId: (v: string) => void
  modelId:    string
  setModelId: (v: string) => void
  agentList:  Array<{ id: string; name: string }>
  modelList:  Array<{ id: string; label: string; provider: string; default: boolean }>
  sendMessage: () => void
  newChat:     () => void
  bottomRef:   NullableRef<HTMLDivElement>
  inputRef:    NullableRef<HTMLTextAreaElement>
}

export function ChatArea({
  messages, streaming, input, setInput,
  agentId, setAgentId, modelId, setModelId,
  agentList, modelList, sendMessage, newChat,
  bottomRef, inputRef,
}: Props) {
  const { t } = useTranslation()
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  return (
    <div className="flex flex-1 flex-col min-w-0">
      {/* 頂欄 */}
      <div className="relative z-10 flex flex-wrap items-center gap-2 border-b pb-3 mb-3">
        <Bot className="h-5 w-5 text-primary shrink-0" />
        <h1 className="text-lg font-bold tracking-tight">{t("chat.title")}</h1>

        <Select value={agentId} onValueChange={setAgentId}>
          <SelectTrigger className="h-8 w-44 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {agentList.map(a => (
              <SelectItem key={a.id} value={a.id} className="text-xs">{a.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={modelId} onValueChange={setModelId}>
          <SelectTrigger className="h-8 w-56 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent position="popper" sideOffset={4} className="z-[200] max-h-80 overflow-y-auto w-64">
            {MODEL_GROUPS.map((group, gi) => {
              const items = modelList.filter(m => m.provider === group.key)
              if (!items.length) return null
              return (
                <div key={group.key}>
                  <div className={`px-2 py-1 ${gi > 0 ? "mt-1 border-t" : ""} text-[10px] font-semibold text-muted-foreground uppercase tracking-wide`}>
                    {t(group.labelKey)}
                  </div>
                  {items.map(m => (
                    <SelectItem key={m.id} value={m.id} className="text-xs">
                      <span className={`${group.color} mr-1`}>{group.icon}</span>
                      {m.label}
                      {m.default && <span className="ml-1 text-[10px] text-muted-foreground">{t("chat.defaultModelSuffix")}</span>}
                    </SelectItem>
                  ))}
                </div>
              )
            })}
          </SelectContent>
        </Select>

        <div className="ml-auto flex items-center gap-2">
          {streaming && (
            <Badge variant="secondary" className="gap-1 text-xs">
              <Loader2 className="h-3 w-3 animate-spin" />{t("chat.analyzing")}
            </Badge>
          )}
          <Button size="sm" variant="ghost" className="h-8 gap-1 text-xs text-muted-foreground" onClick={newChat} disabled={streaming} title={t("chat.newChatTitle")}>
            <SquarePen className="h-3.5 w-3.5" />{t("chat.newChat")}
          </Button>
        </div>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center text-muted-foreground">
            <Bot className="h-12 w-12 opacity-30" />
            <div>
              <p className="font-medium">{t("chat.emptyTitle")}</p>
              <p className="text-sm mt-1">{t("chat.emptySubtitle")}</p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center">
              {[t("chat.hintWamWal"), t("chat.hintVar"), t("chat.hintPositions")].map(hint => (
                <button key={hint} className="rounded-full border px-3 py-1.5 text-xs hover:bg-muted transition-colors"
                  onClick={() => { setInput(hint); inputRef.current?.focus() }}>
                  {hint}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
        <div ref={bottomRef} />
      </div>

      {/* 輸入欄 */}
      <div className="border-t pt-3 mt-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef} value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown} rows={2} disabled={streaming}
            placeholder={t("chat.inputPlaceholder", { agent: agentList.find(a => a.id === agentId)?.name ?? agentId })}
            className="flex-1 resize-none rounded-xl border border-input bg-background px-4 py-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          />
          <Button size="icon" className="h-12 w-12 rounded-xl shrink-0" onClick={sendMessage} disabled={streaming || !input.trim()}>
            {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground text-center">
          {t("chat.toolPathLabel")}<span className="font-mono">6_entry:8010 → processing:8001</span>
        </p>
      </div>
    </div>
  )
}

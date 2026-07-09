import { MessageSquarePlus, Search, Trash2 } from "lucide-react"
import { type MouseEvent, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { ChatSessionRecord } from "@/fsiClient"
import { groupSessionsByDate } from "./utils"

interface Props {
  sessions:         ChatSessionRecord[]
  currentSessionId: string | null
  onSelect:         (id: string) => void
  onDelete:         (id: string) => void
  onNew:            () => void
}

function SessionItem({
  session, isActive, onSelect, onDelete,
}: {
  session:  ChatSessionRecord
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const [hover, setHover] = useState(false)
  return (
    <div
      className={`group flex items-center gap-1 rounded-lg px-3 py-2 cursor-pointer text-sm transition-colors ${
        isActive ? "bg-muted font-medium" : "hover:bg-muted/50"
      }`}
      onClick={onSelect}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="flex-1 truncate text-foreground">{session.title}</span>
      {hover && (
        <button
          className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
          onClick={(e: MouseEvent) => { e.stopPropagation(); onDelete() }}
          title="刪除對話"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}

export function SessionPanel({ sessions, currentSessionId, onSelect, onDelete, onNew }: Props) {
  const [query, setQuery] = useState("")

  const filtered = query.trim()
    ? sessions.filter(s => s.title.toLowerCase().includes(query.toLowerCase()))
    : sessions

  const groups = groupSessionsByDate(filtered)

  return (
    <div className="flex w-60 shrink-0 flex-col border-l bg-background">
      {/* 新對話按鈕 */}
      <div className="border-b p-3">
        <Button
          size="sm"
          variant="outline"
          className="w-full gap-2 text-xs"
          onClick={onNew}
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          新對話
        </Button>
      </div>

      {/* 搜索 */}
      <div className="px-3 py-2 border-b">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <Input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索對話..."
            className="h-8 pl-8 text-xs"
          />
        </div>
      </div>

      {/* 會話列表 */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-3">
        {groups.length === 0 && (
          <p className="px-3 py-4 text-center text-xs text-muted-foreground">暫無對話記錄</p>
        )}
        {groups.map(group => (
          <div key={group.label}>
            <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {group.label}
            </p>
            {group.items.map(s => (
              <SessionItem
                key={s.id}
                session={s}
                isActive={s.id === currentSessionId}
                onSelect={() => onSelect(s.id)}
                onDelete={() => onDelete(s.id)}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

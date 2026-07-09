import { AlertTriangle } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { ToolCallCard } from "./ToolCallCard"
import type { ChatMessage } from "./types"

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user"

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
          A
        </div>
      )}
      <div className={`max-w-[80%] space-y-1 flex flex-col ${isUser ? "items-end" : "items-start"}`}>
        {msg.toolCalls.length > 0 && (
          <div className="w-full">
            {msg.toolCalls.map(tc => <ToolCallCard key={tc.id} tc={tc} />)}
          </div>
        )}

        {(msg.content || msg.isStreaming) && (
          <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
          }`}>
            {isUser ? (
              <p className="whitespace-pre-wrap">{msg.content}</p>
            ) : (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || ""}</ReactMarkdown>
                {msg.isStreaming && (
                  <span className="inline-block h-4 w-0.5 animate-pulse bg-current align-middle" />
                )}
              </div>
            )}
          </div>
        )}

        {msg.error && (
          <div className="flex items-center gap-1.5 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertTriangle className="h-3.5 w-3.5" />
            {msg.error}
          </div>
        )}
      </div>
    </div>
  )
}

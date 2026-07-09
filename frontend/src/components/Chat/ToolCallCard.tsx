import { ChevronDown, ChevronRight, Loader2, Wrench } from "lucide-react"
import { useState } from "react"
import type { ToolCallRecord } from "./types"

export function ToolCallCard({ tc }: { tc: ToolCallRecord }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="my-2 rounded-md border border-border/60 bg-muted/40 text-xs">
      <button
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        onClick={() => setOpen(o => !o)}
      >
        <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
        <span className="font-mono font-medium text-foreground">{tc.name}</span>
        <span className="text-muted-foreground truncate">
          {Object.entries(tc.input).map(([k, v]) => `${k}=${v}`).join(", ")}
        </span>
        {!tc.done && <Loader2 className="ml-auto h-3 w-3 animate-spin text-blue-500" />}
        {tc.done  && (open
          ? <ChevronDown  className="ml-auto h-3 w-3" />
          : <ChevronRight className="ml-auto h-3 w-3" />
        )}
      </button>
      {open && tc.done && tc.result !== null && (
        <div className="border-t border-border/40 px-3 py-2">
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all text-[11px] text-muted-foreground">
            {typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

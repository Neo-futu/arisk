export type SSEEventType = "start" | "text" | "tool_call" | "tool_result" | "error" | "done"

export interface SSEEvent {
  type:     SSEEventType
  content?: string
  name?:    string
  input?:   Record<string, unknown>
  result?:  unknown
  id?:      string
  message?: string
}

export interface ToolCallRecord {
  id:     string
  name:   string
  input:  Record<string, unknown>
  result: unknown | null
  done:   boolean
}

export interface ChatMessage {
  id:          string
  role:        "user" | "assistant"
  content:     string
  toolCalls:   ToolCallRecord[]
  isStreaming: boolean
  error?:      string
}

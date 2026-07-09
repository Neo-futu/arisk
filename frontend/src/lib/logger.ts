/**
 * logger.ts — 前端統一日誌模塊
 *
 * 四種日誌類型：
 *   user_action — 用戶行為（點擊按鈕、導航、表單提交）
 *   operation   — 業務操作（API 調用、數據變更）
 *   audit       — 審計（登錄/登出、敏感數據訪問）
 *   error       — 前端報錯（組件崩潰、未捕獲異常）
 *
 * 策略：
 *   - 日誌先入緩衝隊列，每 5 秒或隊列達 20 條時批量上報
 *   - error 級別立即上報，不等批次
 *   - API 不可用時降級到 console + localStorage 隊列
 */

const BASE = (import.meta.env.VITE_API_URL as string) || ""
const FLUSH_INTERVAL_MS = 5_000
const FLUSH_BATCH_SIZE  = 20
const LS_QUEUE_KEY      = "arisk_log_queue"
const LS_QUEUE_MAX      = 200

type LogType  = "user_action" | "operation" | "audit" | "error"
type LogLevel = "info" | "warn" | "error"

interface LogEntry {
  log_type: LogType
  level:    LogLevel
  module:   string
  action:   string
  detail?:  Record<string, unknown>
  url?:     string
}

// ── 隊列管理 ─────────────────────────────────────────────────────

let _queue: LogEntry[] = []
let _flushTimer: ReturnType<typeof setTimeout> | null = null

function _enqueue(entry: LogEntry): void {
  _queue.push({ ...entry, url: window.location.pathname })
  if (entry.level === "error" || _queue.length >= FLUSH_BATCH_SIZE) {
    _flush()
  } else if (!_flushTimer) {
    _flushTimer = setTimeout(_flush, FLUSH_INTERVAL_MS)
  }
}

async function _flush(): Promise<void> {
  if (_flushTimer) { clearTimeout(_flushTimer); _flushTimer = null }
  if (!_queue.length) return

  const batch = _queue.splice(0, FLUSH_BATCH_SIZE)
  const token = localStorage.getItem("access_token")
  if (!token) {
    // 未登錄時只記錄到 console，不上報
    batch.forEach(e => console.debug("[logger]", e.log_type, e.module, e.action))
    return
  }

  try {
    await fetch(`${BASE}/api/v1/logs/batch`, {
      method:  "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body:    JSON.stringify({ entries: batch }),
    })
  } catch {
    // API 失敗 → 存 localStorage 隊列
    try {
      const existing: LogEntry[] = JSON.parse(localStorage.getItem(LS_QUEUE_KEY) ?? "[]")
      const merged = [...existing, ...batch].slice(-LS_QUEUE_MAX)
      localStorage.setItem(LS_QUEUE_KEY, JSON.stringify(merged))
    } catch { /* ignore */ }
    console.warn("[logger] flush failed, queued to localStorage", batch.length, "entries")
  }
}

// 頁面卸載前強制 flush（使用 sendBeacon）
window.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && _queue.length) {
    const token = localStorage.getItem("access_token")
    if (token) {
      navigator.sendBeacon(
        `${BASE}/api/v1/logs/batch`,
        new Blob([JSON.stringify({ entries: _queue })], { type: "application/json" }),
      )
      _queue = []
    }
  }
})

// ── 公共 API ─────────────────────────────────────────────────────

export const logger = {
  /** 用戶行為：點擊、導航、表單提交等 */
  action(module: string, action: string, detail?: Record<string, unknown>) {
    _enqueue({ log_type: "user_action", level: "info", module, action, detail })
  },

  /** 業務操作：API 調用、數據讀寫 */
  operation(module: string, action: string, detail?: Record<string, unknown>) {
    _enqueue({ log_type: "operation", level: "info", module, action, detail })
  },

  /** 審計日誌：登錄/登出、敏感操作 */
  audit(module: string, action: string, detail?: Record<string, unknown>) {
    _enqueue({ log_type: "audit", level: "info", module, action, detail })
  },

  /** 一般信息 */
  info(module: string, action: string, detail?: Record<string, unknown>) {
    _enqueue({ log_type: "operation", level: "info", module, action, detail })
  },

  /** 警告 */
  warn(module: string, action: string, detail?: Record<string, unknown>) {
    _enqueue({ log_type: "operation", level: "warn", module, action, detail })
    console.warn(`[${module}] ${action}`, detail)
  },

  /** 錯誤：立即上報 */
  error(module: string, action: string, detail?: Record<string, unknown>) {
    _enqueue({ log_type: "error", level: "error", module, action, detail })
    console.error(`[${module}] ${action}`, detail)
  },

  /** 手動觸發 flush（登出前調用） */
  flush: _flush,
}

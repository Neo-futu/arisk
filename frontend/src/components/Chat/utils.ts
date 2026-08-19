import type { ChatSessionRecord } from "@/fsiClient"

export interface SessionGroup {
  label: string
  items: ChatSessionRecord[]
}

export interface SessionGroupLabels {
  today:     string
  yesterday: string
  thisWeek:  string
  older:     string
}

export function groupSessionsByDate(
  sessions: ChatSessionRecord[],
  labels: SessionGroupLabels,
): SessionGroup[] {
  const now        = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yestStart  = new Date(todayStart); yestStart.setDate(yestStart.getDate() - 1)
  const weekStart  = new Date(todayStart); weekStart.setDate(weekStart.getDate() - 7)

  const bucket = (s: ChatSessionRecord) => new Date(s.updated_at)
  const today     = sessions.filter(s => bucket(s) >= todayStart)
  const yesterday = sessions.filter(s => bucket(s) >= yestStart  && bucket(s) < todayStart)
  const thisWeek  = sessions.filter(s => bucket(s) >= weekStart  && bucket(s) < yestStart)
  const older     = sessions.filter(s => bucket(s) < weekStart)

  return [
    ...(today.length     ? [{ label: labels.today,     items: today }]     : []),
    ...(yesterday.length ? [{ label: labels.yesterday, items: yesterday }] : []),
    ...(thisWeek.length  ? [{ label: labels.thisWeek,  items: thisWeek }]  : []),
    ...(older.length     ? [{ label: labels.older,     items: older }]     : []),
  ]
}

export function parseToolCalls(raw: string): unknown[] {
  try { return JSON.parse(raw) } catch { return [] }
}

import { createFileRoute } from "@tanstack/react-router"
import { ChatArea } from "@/components/Chat/ChatArea"
import { SessionPanel } from "@/components/Chat/SessionPanel"
import { useChatSession } from "@/components/Chat/useChatSession"

export const Route = createFileRoute("/_layout/chat")({
  validateSearch: (search: Record<string, unknown>) => ({
    agent: typeof search.agent === "string" ? search.agent : undefined,
  }),
  component: ChatPage,
  head: () => ({ meta: [{ title: "Agent Chat — ARISK" }] }),
})

function ChatPage() {
  const { agent } = Route.useSearch()
  const chat = useChatSession(agent)

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-0">
      {/* 左側：對話區 */}
      <ChatArea
        messages={chat.messages}
        streaming={chat.streaming}
        input={chat.input}
        setInput={chat.setInput}
        agentId={chat.agentId}
        setAgentId={chat.setAgentId}
        modelId={chat.modelId}
        setModelId={chat.setModelId}
        agentList={chat.agentList}
        modelList={chat.modelList}
        sendMessage={chat.sendMessage}
        newChat={chat.newChat}
        bottomRef={chat.bottomRef}
        inputRef={chat.inputRef}
      />

      {/* 右側：會話歷史面板 */}
      <SessionPanel
        sessions={chat.sessions}
        currentSessionId={chat.currentSessionId}
        onSelect={chat.loadSession}
        onDelete={chat.deleteSession}
        onNew={chat.newChat}
      />
    </div>
  )
}

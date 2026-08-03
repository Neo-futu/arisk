import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  type InvestmentRiskTopic,
  getInvestmentRiskTopic,
} from "@/modules/investment-risk/content"

function TopicList({ title, items }: { title: string; items: string[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

export function InvestmentRiskTopicPage({
  topicId,
}: {
  topicId: InvestmentRiskTopic["id"]
}) {
  const topic = getInvestmentRiskTopic(topicId)

  if (!topic) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-4 text-sm text-destructive">
          無法找到對應的投資風險功能頁。
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline">投資風險模塊</Badge>
          <Badge variant="secondary">{topic.subtitle}</Badge>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{topic.title}</h1>
        <p className="max-w-4xl text-sm text-muted-foreground">{topic.summary}</p>
      </div>

      <TopicList title="核心能力" items={topic.capabilities} />

      <div className="grid gap-4 xl:grid-cols-2">
        <TopicList title="2_processing 建議路由" items={topic.processingRoutes} />
        <TopicList title="1_datastorage 建議表" items={topic.storageTables} />
      </div>

      <TopicList title="Agent / MCP 集成" items={topic.agentIntegration} />
    </div>
  )
}

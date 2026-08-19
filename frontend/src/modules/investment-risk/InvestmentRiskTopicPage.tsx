import { useTranslation } from "react-i18next"

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
  const { t } = useTranslation()
  const topic = getInvestmentRiskTopic(topicId)

  if (!topic) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-4 text-sm text-destructive">
          {t("investmentRisk.module.topicPageNotFound")}
        </CardContent>
      </Card>
    )
  }

  const capabilities = t(topic.capabilitiesKey, { returnObjects: true }) as string[]
  const agentIntegration = t(topic.agentIntegrationKey, { returnObjects: true }) as string[]

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline">{t("investmentRisk.module.tag")}</Badge>
          <Badge variant="secondary">{topic.subtitle}</Badge>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{t(topic.titleKey)}</h1>
        <p className="max-w-4xl text-sm text-muted-foreground">{t(topic.summaryKey)}</p>
      </div>

      <TopicList title={t("investmentRisk.module.coreCapabilities")} items={capabilities} />

      <div className="grid gap-4 xl:grid-cols-2">
        <TopicList title={t("investmentRisk.module.processingRoutes")} items={topic.processingRoutes} />
        <TopicList title={t("investmentRisk.module.storageTables")} items={topic.storageTables} />
      </div>

      <TopicList title={t("investmentRisk.module.agentIntegration")} items={agentIntegration} />
    </div>
  )
}

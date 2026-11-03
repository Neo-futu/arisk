import { useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { DataManagementPage } from "@/modules/data-management/DataManagementPage"
import { IndicatorExplorerPage } from "@/modules/indicator-explorer/IndicatorExplorerPage"

export type MarketDataTab = "market" | "indicators"

export function MarketDataIndicatorsPage({ tab = "market" }: { tab?: MarketDataTab }) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  function setTab(next: MarketDataTab) {
    void navigate({
      to: "/indicator-explorer",
      search: { tab: next },
      replace: true,
    })
  }

  return (
    <div className="space-y-5" data-testid="market-data-indicators">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("nav.marketDataIndicators")}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("marketDataIndicators.subtitle")}</p>
      </div>

      <Tabs value={tab} onValueChange={(value) => setTab(value as MarketDataTab)}>
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="market" data-testid="mdi-tab-market">{t("marketDataIndicators.marketTab")}</TabsTrigger>
          <TabsTrigger value="indicators" data-testid="mdi-tab-indicators">{t("marketDataIndicators.indicatorsTab")}</TabsTrigger>
        </TabsList>

        <TabsContent value="market" className="mt-4">
          <DataManagementPage lockedSection="market" hideHeader />
        </TabsContent>

        <TabsContent value="indicators" className="mt-4">
          <IndicatorExplorerPage embed />
        </TabsContent>
      </Tabs>
    </div>
  )
}

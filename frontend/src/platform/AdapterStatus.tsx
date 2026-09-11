import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import type { AdapterBundle } from "@/fsiClient"

export function AdapterStatusBar({
  adapters,
  engine,
  engineVersion,
}: {
  adapters?: AdapterBundle | null
  engine?: string
  engineVersion?: string
}) {
  const { t } = useTranslation()
  const items = [
    { key: "financepy", label: "FinancePy" },
    { key: "riskfolio", label: "Riskfolio-Lib" },
    { key: "ore", label: "ORE / QuantLib" },
  ] as const

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="platform-adapters">
      <Badge variant="outline">{engine || "ARISK RiskEngine"}{engineVersion ? ` ${engineVersion}` : ""}</Badge>
      {items.map((item) => {
        const probe = adapters?.[item.key]
        const available = Boolean(probe?.available)
        return (
          <Badge key={item.key} variant={available ? "default" : "secondary"}>
            {item.label}
            {" · "}
            {available ? t("engine.adapterReady") : t("engine.adapterFallback")}
            {probe?.version ? ` ${probe.version}` : ""}
          </Badge>
        )
      })}
    </div>
  )
}

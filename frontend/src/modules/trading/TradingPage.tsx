import { DataManagementPage } from "@/modules/data-management/DataManagementPage"

export function TradingPage() {
  return (
    <DataManagementPage
      initialSection="trades"
      lockedSection="trades"
      titleKey="trading.title"
      subtitleKey="trading.subtitle"
    />
  )
}

/** Platform menu groups aligned with AppSidebar — used by system admin UIs. */

export type PlatformMenuGroupId =
  | "core"
  | "invest"
  | "data"
  | "governance"
  | "ops"
  | "ai"
  | "system"
  | "legacy"

export const PLATFORM_MENU_GROUPS: Array<{
  id: PlatformMenuGroupId
  titleKey: string
  codes: string[]
}> = [
  {
    id: "core",
    titleKey: "systemConfig.groupCore",
    codes: ["dashboard", "portfolio-cockpit"],
  },
  {
    id: "invest",
    titleKey: "systemConfig.groupInvest",
    codes: ["investment-risk", "portfolio-opt", "risk-testing"],
  },
  {
    id: "data",
    titleKey: "systemConfig.groupData",
    codes: ["data-management", "indicator-explorer", "sql-library", "valuation", "trading"],
  },
  {
    id: "governance",
    titleKey: "systemConfig.groupGovernance",
    codes: ["risk-governance", "risk-rules", "compliance"],
  },
  {
    id: "ops",
    titleKey: "systemConfig.groupOps",
    codes: ["reports", "schedules", "autorisk"],
  },
  {
    id: "ai",
    titleKey: "systemConfig.groupAi",
    codes: ["chat", "expert"],
  },
  {
    id: "system",
    titleKey: "systemConfig.groupSystem",
    codes: ["admin", "system-config", "api-keys", "notifications", "settings"],
  },
  {
    id: "legacy",
    titleKey: "systemConfig.groupLegacy",
    codes: ["positions"],
  },
]

export function groupMenusByPlatform<T extends { code: string }>(
  menus: T[],
): Array<{ id: PlatformMenuGroupId; titleKey: string; menus: T[] }> {
  const byCode = new Map(menus.map((menu) => [menu.code, menu]))
  const used = new Set<string>()
  const groups = PLATFORM_MENU_GROUPS.map((group) => {
    const rows = group.codes
      .map((code) => byCode.get(code))
      .filter((menu): menu is T => Boolean(menu))
    for (const row of rows) used.add(row.code)
    return { id: group.id, titleKey: group.titleKey, menus: rows }
  }).filter((group) => group.menus.length > 0)

  const extras = menus.filter((menu) => !used.has(menu.code))
  if (extras.length) {
    groups.push({
      id: "legacy",
      titleKey: "systemConfig.groupOther",
      menus: extras,
    })
  }
  return groups
}

import { expect, test, type Page } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const user = (isSuperuser: boolean) => ({
  id: isSuperuser ? "00000000-0000-4000-8000-000000000001" : "00000000-0000-4000-8000-000000000002",
  email: isSuperuser ? "admin@example.com" : "viewer@example.com",
  full_name: isSuperuser ? "Admin" : "Viewer",
  is_active: true,
  is_superuser: isSuperuser,
  created_at: "2026-09-09T00:00:00Z",
})

async function mockSession(
  page: Page,
  options: {
    isSuperuser: boolean
    menuPaths?: string[]
    menuStages?: Record<string, "GA" | "BETA" | "HIDDEN">
  },
) {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "menu-test-token")
    localStorage.setItem("arisk_lang", "zh-CN")
  })

  await page.route("**/api/v1/users/me", (route) => route.fulfill({ json: user(options.isSuperuser) }))
  await page.route("**/api/v1/access-control/me", (route) => route.fulfill({
    json: {
      user_id: user(options.isSuperuser).id,
      is_superuser: options.isSuperuser,
      roles: [],
      permission_codes: [],
      menu_codes: [],
      menu_paths: options.menuPaths ?? [],
      menu_stages: options.menuStages ?? {},
      portfolios: [],
      can_manage_access: options.isSuperuser,
      can_manage_system: options.isSuperuser,
    },
  }))

  await page.route("**/api/v1/fsi/**", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Mocked dependency unavailable" }),
  }))
  await page.route("**/api/v1/fsi/agent/v2/agents", (route) => route.fulfill({
    json: [
      { id: "general", name: "通用助理" },
      { id: "market-researcher", name: "市场研究员" },
      { id: "fund-reporter", name: "基金报表助理" },
      { id: "risk-analyst", name: "ARISK 风控分析师" },
      { id: "valuation-reviewer", name: "估值复核员" },
      { id: "month-end-closer", name: "月结工作流助理" },
    ],
  }))
  await page.route("**/api/v1/fsi/agent/v2/models", (route) => route.fulfill({
    json: [{ id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", provider: "anthropic", default: true }],
  }))
  await page.route("**/api/v1/agent-config/me", (route) => route.fulfill({ json: {} }))
  await page.route("**/api/v1/chat/sessions", (route) => route.fulfill({ json: [] }))
  await page.route("**/api/v1/knowledge/refresh-skills", (route) => route.fulfill({
    json: { ok: true, scanned: 0, indexed: 0, message: "ok" },
  }))
}

const CORE_NAV_IDS = [
  "dashboard",
  "portfolio-cockpit",
  "investment-risk",
  "portfolio-optimization",
  "risk-testing",
  "data-management",
  "market-data-indicators",
  "valuation",
  "trading",
  "risk-governance",
  "reports",
  "schedules",
  "autorisk",
  "agent-ai",
  "system-management",
]

test("superuser sees the new first-level architecture and Beta state", async ({ page }) => {
  await mockSession(page, {
    isSuperuser: true,
    menuStages: {
      "/risk-testing": "BETA",
      "/portfolio-opt": "GA",
      "/reports": "GA",
      "/schedules": "GA",
      "/autorisk": "GA",
    },
  })
  await page.goto("/settings")

  for (const id of CORE_NAV_IDS) {
    await expect(page.getByTestId(`nav-${id}`)).toBeVisible()
  }
  await expect(page.getByTestId("nav-risk-testing").getByText("Beta")).toBeVisible()

  await page.getByTestId("nav-investment-risk").getByRole("button").click()
  await expect(page.getByTestId("nav-risk-exposure")).toBeVisible()
  await expect(page.getByTestId("nav-counterparty-risk")).toBeVisible()
  await expect(page.getByTestId("nav-factor-behavior")).toBeVisible()

  await page.getByTestId("nav-portfolio-optimization").getByRole("button").click()
  await expect(page.getByTestId("nav-portfolio-construction")).toBeVisible()
  await expect(page.getByTestId("nav-po-optimization")).toBeVisible()
  await expect(page.getByTestId("nav-po-constraints")).toBeVisible()
  await expect(page.getByTestId("nav-simulated-portfolio")).toBeVisible()
  await expect(page.getByTestId("nav-po-comparison")).toBeVisible()
  await expect(page.getByTestId("nav-portfolio-validation")).toBeVisible()

  await page.getByTestId("nav-risk-testing").getByRole("button").click()
  await expect(page.getByTestId("nav-historical-backtest")).toBeVisible()
  await expect(page.getByTestId("nav-xva")).toBeVisible()
  await expect(page.getByTestId("nav-liquidity-stress-reserved")).toHaveCount(0)
})

test("normal user only sees groups backed by granted menu_paths", async ({ page }) => {
  await mockSession(page, {
    isSuperuser: false,
    menuPaths: ["/", "/reports", "/schedules", "/autorisk", "/chat", "/settings"],
    menuStages: {
      "/": "GA",
      "/reports": "GA",
      "/schedules": "GA",
      "/autorisk": "GA",
      "/chat": "GA",
      "/settings": "GA",
      "/portfolio-opt": "BETA",
      "/risk-testing": "HIDDEN",
    },
  })
  await page.goto("/settings")

  await expect(page.getByTestId("nav-dashboard")).toBeVisible()
  await expect(page.getByTestId("nav-reports")).toBeVisible()
  await expect(page.getByTestId("nav-schedules")).toBeVisible()
  await expect(page.getByTestId("nav-autorisk")).toBeVisible()
  await expect(page.getByTestId("nav-agent-ai")).toBeVisible()
  await expect(page.getByTestId("nav-system-management")).toBeVisible()
  await expect(page.getByTestId("nav-investment-risk")).toHaveCount(0)
  await expect(page.getByTestId("nav-portfolio-optimization")).toHaveCount(0)
  await expect(page.getByTestId("nav-risk-testing")).toHaveCount(0)
  await expect(page.getByTestId("nav-data-management")).toHaveCount(0)
})

test("platform capability links support navigation, deep links, and refresh", async ({ page }) => {
  await mockSession(page, { isSuperuser: true })
  await page.goto("/settings")

  await page.getByTestId("nav-trading").getByRole("button").click()
  await expect(page).toHaveURL(/\/trading\/?$/)
  await expect(page.getByTestId("data-section-trades")).toHaveAttribute("data-state", "active")
  await page.reload()
  await expect(page.getByTestId("data-section-trades")).toHaveAttribute("data-state", "active")

  await page.getByTestId("nav-agent-ai").getByRole("button").click()
  await page.getByTestId("nav-risk-agent").click()
  await expect(page).toHaveURL(/\/chat\?agent=risk-analyst$/)
  await expect(page.getByTestId("agent-selector")).toHaveAttribute("data-agent-id", "risk-analyst")
  await page.reload()
  await expect(page.getByTestId("agent-selector")).toHaveAttribute("data-agent-id", "risk-analyst")
})

test("core workbench, copilot context, chart, table, export, loading and empty", async ({ page }) => {
  await mockSession(page, { isSuperuser: true })
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto("/risk-testing/sensitivity")
  await expect(page.getByTestId("platform-workbench")).toBeVisible()
  await expect(page.getByTestId("platform-parameter")).toBeVisible()
  await expect(page.getByTestId("platform-copilot")).toBeVisible()
  await page.getByTestId("platform-copilot").click()
  await expect(page.getByTestId("platform-ai-context")).toContainText("Module: risk-testing")
  await expect(page.getByTestId("platform-ai-context")).toContainText("Portfolio:")
  await expect(page.getByTestId("platform-ai-context")).toContainText("Date:")
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByTestId("platform-workbench")).toBeVisible()
})

test("preserved routes remain directly accessible", async ({ page }) => {
  await mockSession(page, { isSuperuser: true })
  const routes = [
    "/investment-risk/overview",
    "/risk-testing/sensitivity",
    "/portfolio-opt",
    "/reports",
    "/schedules",
    "/autorisk",
    "/valuation",
    "/compliance",
    "/risk-rules",
    "/trading",
    "/risk-governance",
  ]

  for (const path of routes) {
    await page.goto(path)
    await expect(page).toHaveURL(new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/?$`))
    await expect(page.getByRole("main").last()).toBeVisible()
  }

  await page.goto("/portfolio-opt#parameters")
  await expect(page).toHaveURL(/\/portfolio-opt#parameters$/)
  await expect(page.locator("#parameters")).toBeVisible()
  await page.reload()
  await expect(page.locator("#parameters")).toBeVisible()

  await page.goto("/portfolio-opt#construction")
  await expect(page.locator("#construction")).toBeVisible()
  await page.goto("/investment-risk/overview#asset-risk")
  await expect(page.locator("#asset-risk")).toBeVisible()
})

test("first-level menus own their routes and do not open sibling groups", async ({ page }) => {
  await mockSession(page, { isSuperuser: true })
  await page.goto("/settings")

  await page.getByTestId("nav-autorisk").getByRole("button").click()
  await expect(page).toHaveURL(/\/autorisk\/?$/)
  await expect(page.getByTestId("nav-model-validation")).toHaveCount(0)

  await page.getByTestId("nav-reports").getByRole("button").click()
  await expect(page).toHaveURL(/\/reports\/?$/)
  await expect(page.getByTestId("nav-model-validation")).toHaveCount(0)

  await page.getByTestId("nav-risk-governance").getByRole("button").click()
  await expect(page.getByTestId("nav-model-validation")).toBeVisible()
  await page.getByTestId("nav-model-validation").click()
  await expect(page).toHaveURL(/\/risk-governance#model-validation$/)
  await expect(page.locator("#model-validation")).toBeVisible()

  await page.getByTestId("nav-liquidity-governance").click()
  await expect(page).toHaveURL(/\/risk-governance#liquidity$/)
  await expect(page.locator("#liquidity")).toBeVisible()

  await page.getByTestId("nav-trading").getByRole("button").click()
  await expect(page).toHaveURL(/\/trading\/?$/)
  await expect(page.getByTestId("data-section-trades")).toHaveAttribute("data-state", "active")

  await page.getByTestId("nav-valuation").getByRole("button").click()
  await expect(page).toHaveURL(/\/valuation\/?$/)

  await page.getByTestId("nav-market-data-indicators").getByRole("button").click()
  await page.getByTestId("nav-market-data").click()
  await expect(page).toHaveURL(/\/indicator-explorer#quotes$/)
  await expect(page.getByTestId("nav-data-workbench")).toHaveCount(0)

  await page.goto("/data-management")
  await expect(page).toHaveURL(/\/data-management\/?$/)
  await expect(page.getByTestId("nav-market-data")).toHaveCount(0)
  await expect(page.getByTestId("nav-indicator-explorer")).toHaveCount(0)

  await page.goto("/autorisk")
  await expect(page.getByTestId("nav-model-validation")).toHaveCount(0)
  await page.goto("/reports")
  await expect(page.getByTestId("nav-model-validation")).toHaveCount(0)
  await page.goto("/valuation")
  await expect(page.getByTestId("nav-model-validation")).toHaveCount(0)
})

test("workbench homepage shows greeting, todos and feature entries", async ({ page }) => {
  await mockSession(page, {
    isSuperuser: true,
    menuStages: {
      "/portfolio-cockpit": "GA",
      "/investment-risk": "GA",
      "/portfolio-opt": "GA",
      "/risk-testing": "BETA",
      "/reports": "GA",
      "/autorisk": "GA",
      "/chat": "GA",
    },
  })
  await page.goto("/")

  await expect(page.getByTestId("home-workbench")).toBeVisible()
  await expect(page.getByRole("heading", { name: /你好，Admin/ })).toBeVisible()
  await expect(page.getByTestId("home-shortcut-portfolio-cockpit")).toBeVisible()
  await expect(page.getByTestId("home-shortcut-investment-risk")).toBeVisible()
  await expect(page.getByText("平台状态总览")).toBeVisible()
  await expect(page.getByTestId("nav-dashboard")).toContainText("工作台")
})

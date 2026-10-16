import { useQuery } from "@tanstack/react-query"
import { useMemo, useState } from "react"

import { fsiApi, type LqaPortfolioAnalytics } from "@/fsiClient"

const LEFT_SCENARIOS = [
  "CUSTOM",
  "RUSSIA98",
  "OIL08",
  "BEARSTEARNS08",
  "LEHMAN08",
  "GREECE10",
  "DEBTCEILING11",
  "EURODEBT11",
  "BREXIT16",
  "DECEMBER18",
]
const RIGHT_SCENARIOS = [
  "MILD",
  "MODERATE",
  "SEVERE",
  "EXTREME",
  "THIRDAVENUE15",
  "COVID20",
  "UKRAINE22",
  "BANKRUN23",
  "TARIFF25",
]

type Params = {
  scenario: string
  redemptionPct: number
  costMultiple: number
  includeCurrentDay: boolean
}

function money(value: number | null | undefined) {
  if (value == null) return "—"
  return Math.round(value).toLocaleString("en-US")
}

function num(value: number | null | undefined, digits = 1) {
  if (value == null) return "—"
  return Number(value).toFixed(digits)
}

function exportSecuritiesCsv(
  fundId: string,
  asOfDate: string,
  scenario: string,
  rows: NonNullable<LqaPortfolioAnalytics["securities"]>,
) {
  const headers = [
    "security_code",
    "security_name",
    "market_value",
    "mv_weight_pct",
    "liq_horizon_days",
    "scenario_lqdty_class",
    "hk_sfc_port_lqdty_class",
    "unif_mkt_imp_cost",
    "bid_ask_bps",
    "expected_daily_volume",
    "cost",
    "sector_score",
    "liquidity_sector",
  ]
  const lines = [
    headers.join(","),
    ...rows.map((row) =>
      [
        row.security_code,
        JSON.stringify(row.security_name ?? ""),
        row.market_value ?? "",
        row.mv_weight_pct ?? "",
        row.liq_horizon_days ?? "",
        JSON.stringify(row.scenario_lqdty_class ?? ""),
        JSON.stringify(row.hk_sfc_port_lqdty_class ?? ""),
        row.unif_mkt_imp_cost ?? "",
        row.bid_ask_bps ?? "",
        row.expected_daily_volume ?? "",
        row.cost ?? "",
        row.sector_score ?? "",
        JSON.stringify(row.liquidity_sector ?? ""),
      ].join(","),
    ),
  ]
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = `security-stress-${fundId}-${asOfDate}-${scenario}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

export function LqapPortfolioLiquidity({ fundId, asOfDate }: { fundId: string; asOfDate: string }) {
  const [draft, setDraft] = useState<Params>({
    scenario: "SEVERE",
    redemptionPct: 100,
    costMultiple: 0.5,
    includeCurrentDay: true,
  })
  const [applied, setApplied] = useState<Params>(draft)
  const [view, setView] = useState<"mv" | "positions">("mv")
  const [panel, setPanel] = useState<"horizon" | "securities">("horizon")
  const [menuOpen, setMenuOpen] = useState(false)

  const query = useQuery({
    queryKey: ["lqa-portfolio", fundId, asOfDate, applied],
    queryFn: () =>
      fsiApi
        .getLqaPortfolio(fundId, asOfDate, {
          scenario: applied.scenario,
          redemptionPct: applied.redemptionPct,
          costMultiple: applied.costMultiple,
          includeCurrentDay: applied.includeCurrentDay,
        })
        .then((r) => r.data),
    retry: 1,
  })
  const data = query.data
  const securities = data?.securities ?? []
  const maxBar = useMemo(() => {
    const rows = data?.horizons ?? []
    const values = rows.map((row) => (view === "mv" ? Number(row.mv_weight_pct ?? 0) : row.positions))
    return Math.max(1, ...values)
  }, [data, view])

  const dirty =
    draft.scenario !== applied.scenario ||
    draft.redemptionPct !== applied.redemptionPct ||
    draft.costMultiple !== applied.costMultiple ||
    draft.includeCurrentDay !== applied.includeCurrentDay

  const runStress = () => {
    const next = {
      ...draft,
      redemptionPct: Math.min(100, Math.max(0.01, Number(draft.redemptionPct) || 100)),
      costMultiple: Math.min(10, Math.max(0.01, Number(draft.costMultiple) || 0.5)),
    }
    setDraft(next)
    setApplied(next)
    void query.refetch()
  }

  return (
    <div className="overflow-hidden rounded-md border border-zinc-700 bg-[#141414] text-[12px] text-orange-400 shadow-inner">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-700 bg-[#1c1c1c] px-3 py-2">
        <div>
          <p className="text-[11px] tracking-wide text-orange-300">Portfolio Liquidity Analytics</p>
          <p className="text-sm font-semibold text-orange-200">LQAP · {fundId}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-orange-200">
          <span>Currency {data?.currency ?? "USD"}</span>
          <span className="rounded bg-orange-500/20 px-2 py-0.5 font-mono text-orange-100">
            {data?.data_as_of ?? asOfDate}
          </span>
          <button
            type="button"
            onClick={runStress}
            disabled={query.isFetching}
            className="rounded border border-orange-500 bg-orange-500/25 px-3 py-1 font-semibold text-orange-50 hover:bg-orange-500/40 disabled:opacity-50"
          >
            {query.isFetching ? "计算中…" : dirty ? "按参数重新计算" : "重新压力测试"}
          </button>
        </div>
      </header>

      <div className="grid lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-3 border-b border-zinc-700 p-3 lg:border-b-0 lg:border-r">
          <p className="font-semibold text-orange-200">Portfolio Liquidation Assumptions</p>
          <label className="block space-y-1">
            <span>Redemption Size</span>
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={0.01}
                max={100}
                step={0.1}
                value={draft.redemptionPct}
                onChange={(event) =>
                  setDraft((prev) => ({ ...prev, redemptionPct: Number(event.target.value) }))
                }
                className="w-full rounded border border-orange-700/60 bg-orange-500/15 px-2 py-1 font-mono text-orange-100"
              />
              <span className="shrink-0 text-orange-200">%</span>
            </div>
          </label>
          <div className="grid grid-cols-[1fr_88px] gap-2">
            <label className="space-y-1">
              <span>Target Cost</span>
              <div className="rounded border border-orange-700/60 bg-orange-500/15 px-2 py-1">Bid-Ask</div>
            </label>
            <label className="space-y-1">
              <span>倍数</span>
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  min={0.01}
                  max={10}
                  step={0.1}
                  value={draft.costMultiple}
                  onChange={(event) =>
                    setDraft((prev) => ({ ...prev, costMultiple: Number(event.target.value) }))
                  }
                  className="w-full rounded border border-orange-700/60 bg-orange-500/15 px-1 py-1 font-mono text-orange-100"
                />
                <span className="shrink-0 text-orange-200">x</span>
              </div>
            </label>
          </div>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.includeCurrentDay}
              onChange={(event) =>
                setDraft((prev) => ({ ...prev, includeCurrentDay: event.target.checked }))
              }
            />
            Incl Curr Day in Settlement
          </label>

          <div className="relative">
            <p className="mb-1 font-semibold text-orange-200">Scenario Definition</p>
            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              className="flex w-full items-center justify-between rounded border border-orange-500 bg-orange-500/20 px-2 py-1.5 font-semibold text-orange-100"
            >
              {draft.scenario === "CUSTOM" ? "Custom" : draft.scenario}
              <span>▾</span>
            </button>
            {menuOpen ? (
              <div className="absolute z-20 mt-1 grid w-full grid-cols-2 gap-x-2 rounded border border-zinc-600 bg-[#0e0e0e] p-2 shadow-xl">
                {[LEFT_SCENARIOS, RIGHT_SCENARIOS].map((column) => (
                  <div key={column[0]} className="space-y-0.5">
                    {column.map((code) => (
                      <button
                        key={code}
                        type="button"
                        className={`block w-full rounded px-1 py-0.5 text-left hover:bg-orange-500/20 ${
                          code === draft.scenario ? "bg-sky-700 text-white" : ""
                        }`}
                        onClick={() => {
                          setDraft((prev) => ({ ...prev, scenario: code }))
                          setMenuOpen(false)
                        }}
                      >
                        {code === "CUSTOM" ? "Custom" : code}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <button
            type="button"
            onClick={runStress}
            disabled={query.isFetching}
            className="w-full rounded border border-sky-600 bg-sky-700/80 px-3 py-2 font-semibold text-white hover:bg-sky-600 disabled:opacity-50"
          >
            {query.isFetching ? "压力测试计算中…" : "重新压力测试计算"}
          </button>
          {dirty ? <p className="text-[11px] text-amber-300">参数已改，点击按钮后按新参数更新结果。</p> : null}

          <Overview data={data} />
          <div>
            <p className="font-semibold text-orange-200">Redemption Scenario</p>
            <Kv k="Nominal" v={money(data?.redemption.nominal)} />
            <Kv k="Cost" v={money(data?.redemption.cost)} />
            <Kv k="Value" v={money(data?.redemption.value)} />
            <Kv k="Residual Mkt Val" v={money(data?.redemption.residual_market_value)} />
          </div>
        </aside>

        <section className="min-w-0 p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex gap-3">
              <button
                type="button"
                className={panel === "horizon" ? "border-b border-orange-300 text-orange-100" : "text-zinc-400"}
                onClick={() => setPanel("horizon")}
              >
                Horizon Analysis
              </button>
              <button
                type="button"
                className={panel === "securities" ? "border-b border-orange-300 text-orange-100" : "text-zinc-400"}
                onClick={() => setPanel("securities")}
              >
                Stress Details
              </button>
            </div>
            {panel === "horizon" ? (
              <div className="flex items-center gap-2 text-orange-200">
                <span>View</span>
                <button type="button" className={view === "mv" ? "text-sky-300" : "text-zinc-500"} onClick={() => setView("mv")}>
                  % MV
                </button>
                <button
                  type="button"
                  className={view === "positions" ? "text-sky-300" : "text-zinc-500"}
                  onClick={() => setView("positions")}
                >
                  # Positions
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-3 text-zinc-400">
                <span>
                  情景 {applied.scenario} · {securities.length} 只
                </span>
                <button
                  type="button"
                  onClick={() => exportSecuritiesCsv(fundId, asOfDate, applied.scenario, securities)}
                  className="rounded border border-orange-700/60 px-2 py-0.5 text-orange-200 hover:bg-orange-500/20"
                >
                  导出 CSV
                </button>
              </div>
            )}
          </div>

          {query.isFetching && !data ? <p className="text-zinc-400">Loading…</p> : null}
          {query.isError ? <p className="text-red-400">无法载入产品压力测试。</p> : null}
          {data?.message ? <p className="mb-2 text-amber-300">{data.message}</p> : null}

          {panel === "horizon" ? (
            <>
              <div className="mb-1 flex items-end justify-between">
                <p className="font-semibold text-orange-200">Group · Liquidity Horizon</p>
                <p className="text-zinc-400">Not Covered ({data?.not_covered_positions ?? 0})</p>
              </div>
              <div className="flex h-44 items-end gap-2 border-b border-zinc-700 px-1">
                {(data?.horizons ?? []).map((row) => {
                  const value = view === "mv" ? Number(row.mv_weight_pct ?? 0) : row.positions
                  const height = `${Math.max(2, (value / maxBar) * 100)}%`
                  return (
                    <div key={row.id} className="flex h-full min-w-0 flex-1 flex-col justify-end">
                      <div className="mx-auto w-full max-w-[42px] bg-sky-500" style={{ height }} title={`${row.label} ${value}`} />
                    </div>
                  )
                })}
              </div>
              <div className="mt-1 flex gap-2 text-center text-[10px] leading-tight text-zinc-300">
                {(data?.horizons ?? []).map((row) => (
                  <div key={row.id} className="min-w-0 flex-1">
                    {row.id === "not_covered" ? "Not Covered" : row.label.replace(" days", "").replace(" day", "")}
                  </div>
                ))}
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-zinc-200">
                  <thead className="text-orange-300">
                    <tr>
                      <th className="py-1 pr-2 font-medium">Liquidity Horizon</th>
                      <th className="py-1 pr-2 text-right font-medium">MV Wgt</th>
                      <th className="py-1 pr-2 text-right font-medium">Trade Size</th>
                      <th className="py-1 pr-2 text-right font-medium">Liq. Horizon</th>
                      <th className="py-1 pr-2 text-right font-medium">Sector Score</th>
                      <th className="py-1 font-medium">Sector</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.horizons ?? []).map((row) => (
                      <tr key={row.id} className="border-t border-zinc-800">
                        <td className="py-1 pr-2">{row.label}</td>
                        <td className="py-1 pr-2 text-right font-mono">{num(row.mv_weight_pct, 1)}%</td>
                        <td className="py-1 pr-2 text-right font-mono">{money(row.trade_size)}</td>
                        <td className="py-1 pr-2 text-right font-mono">{num(row.liq_horizon_days, 1)}</td>
                        <td className="py-1 pr-2 text-right font-mono">{row.sector_score ?? "—"}</td>
                        <td className="py-1">{row.sector ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <>
              <div className="mb-1 flex items-end justify-between">
                <p className="font-semibold text-orange-200">Stress Details · {applied.scenario}</p>
                <p className="text-zinc-400">Cost ×{applied.costMultiple} · 赎回 {applied.redemptionPct}%</p>
              </div>
              <div className="max-h-[520px] overflow-auto">
                <table className="w-full min-w-[960px] text-left text-zinc-200">
                  <thead className="sticky top-0 bg-[#141414] text-orange-300">
                    <tr>
                      <th className="py-1 pr-2 font-medium">Security</th>
                      <th className="py-1 pr-2 text-right font-medium">MV (CCY)</th>
                      <th className="py-1 pr-2 text-right font-medium">MV Wgt (%)</th>
                      <th className="py-1 pr-2 text-right font-medium">Liq. Horizon (Days)</th>
                      <th className="py-1 pr-2 font-medium">Scenario Class</th>
                      <th className="py-1 pr-2 font-medium">Base Class</th>
                      <th className="py-1 pr-2 text-right font-medium">Mkt Imp Cost (frac)</th>
                      <th className="py-1 pr-2 text-right font-medium">Bid-Ask (bps)</th>
                      <th className="py-1 pr-2 text-right font-medium">EDV (CCY)</th>
                      <th className="py-1 pr-2 text-right font-medium">Cost (CCY)</th>
                      <th className="py-1 pr-2 text-right font-medium">Sector Score (1–100)</th>
                      <th className="py-1 font-medium">Sector</th>
                    </tr>
                  </thead>
                  <tbody>
                    {securities.map((row) => (
                      <tr key={row.security_code} className="border-t border-zinc-800">
                        <td className="py-1 pr-2">
                          <span className="font-medium text-zinc-100">{row.security_name}</span>
                          <span className="ml-1 font-mono text-[10px] text-zinc-400">{row.security_code}</span>
                        </td>
                        <td className="py-1 pr-2 text-right font-mono">{money(row.market_value)}</td>
                        <td className="py-1 pr-2 text-right font-mono">{num(row.mv_weight_pct, 2)}%</td>
                        <td className="py-1 pr-2 text-right font-mono text-orange-100">{num(row.liq_horizon_days, 1)}</td>
                        <td className="py-1 pr-2 text-sky-200">{row.scenario_lqdty_class}</td>
                        <td className="py-1 pr-2">{row.hk_sfc_port_lqdty_class ?? "—"}</td>
                        <td className="py-1 pr-2 text-right font-mono">{num(row.unif_mkt_imp_cost, 4)}</td>
                        <td className="py-1 pr-2 text-right font-mono">{num(row.bid_ask_bps, 1)}</td>
                        <td className="py-1 pr-2 text-right font-mono">{money(row.expected_daily_volume)}</td>
                        <td className="py-1 pr-2 text-right font-mono">{money(row.cost)}</td>
                        <td className="py-1 pr-2 text-right font-mono">{row.sector_score ?? "—"}</td>
                        <td className="py-1">{row.liquidity_sector ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </div>

      <details className="border-t border-zinc-700 px-3 py-2 text-zinc-300">
        <summary className="cursor-pointer text-orange-200">
          流动性口径：股票类=参与率×ADTV；债券/CD=bid-ask（非参与率拆天）；现金/存款/回购=合约期限。
          有值 {data?.lqa_populated_fields ?? 0}/{data?.lqa_fields.length ?? 0} 类
          {data?.lqa_proxy_positions ? ` · ${data.lqa_proxy_positions} 只已计算` : ""}
        </summary>
        <ul className="mt-2 space-y-1 font-mono text-[11px]">
          {(data?.lqa_fields ?? []).map((field) => (
            <li key={field.field}>
              {field.field} · 有值 {field.populated ?? 0} 只 · {field.proxy ?? "计算"}
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}

function Overview({ data }: { data: LqaPortfolioAnalytics | undefined }) {
  const o = data?.overview
  return (
    <div>
      <p className="font-semibold text-orange-200">Portfolio Overview</p>
      <Kv k="Mkt Val" v={money(o?.market_value)} />
      <Kv k="Positions" v={o ? String(o.positions) : "—"} />
      <Kv k="Bid-Ask (bps)" v={num(o?.bid_ask_bps, 2)} />
      <Kv k="Annual Volatility" v={o?.annual_volatility == null ? "—" : num(o.annual_volatility, 2)} />
      <Kv k="Daily Volatility" v={o?.daily_volatility == null ? "—" : num(o.daily_volatility, 2)} />
      <Kv k="Pct of EDV" v={o?.pct_of_edv == null ? "—" : `${num(o.pct_of_edv, 1)}%`} />
      <Kv k="Liq. Horizon (Days)" v={o?.liq_horizon_days == null ? "—" : num(o.liq_horizon_days, 1)} />
      <Kv k="Global Score" v={o?.global_score == null ? "—" : String(o.global_score)} />
    </div>
  )
}

function Kv({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="text-orange-400/90">{k}</span>
      <span className="font-mono text-orange-100">{v}</span>
    </div>
  )
}

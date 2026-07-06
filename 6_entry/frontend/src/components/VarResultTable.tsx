import type { VarMethodResult } from '../types/var'

type Props = {
  rows: VarMethodResult[]
}

function formatMoney(v: number): string {
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export default function VarResultTable({ rows }: Props) {
  if (!rows.length) {
    return <div className="hint">尚無結果</div>
  }

  return (
    <table className="result-table">
      <thead>
        <tr>
          <th>方法</th>
          <th>VaR(HKD)</th>
          <th>VaR(%NAV)</th>
          <th>CVaR(HKD)</th>
          <th>樣本數</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.method_requested || r.method}-${r.sample_size}`}>
            <td>{r.method || r.method_requested || 'UNKNOWN'}</td>
            <td>{formatMoney(r.var_hkd || 0)}</td>
            <td>{(r.var_pct_nav || 0).toFixed(6)}%</td>
            <td>{formatMoney(r.cvar_hkd || 0)}</td>
            <td>{r.sample_size || 0}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

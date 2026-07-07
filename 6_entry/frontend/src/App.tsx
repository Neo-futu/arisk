import { useMemo, useState } from 'react'
import './App.css'
import { fetchAgentVarSkill, fetchDirectVarCompare } from './api/varApi'
import VarResultTable from './components/VarResultTable'
import type { VarMethodResult, VarRequest } from './types/var'

function App() {
  const [mode, setMode] = useState<'direct' | 'agent'>('direct')
  const [fundId, setFundId] = useState('BHMMF001')
  const [asOfDate, setAsOfDate] = useState('2026-06-25')
  const [confidence, setConfidence] = useState('0.99')
  const [horizonDays, setHorizonDays] = useState('1')
  const [simulations, setSimulations] = useState('10000')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [rows, setRows] = useState<VarMethodResult[]>([])
  const [maxVarPctNav, setMaxVarPctNav] = useState(0)
  const [summary, setSummary] = useState('')

  const request: VarRequest = useMemo(
    () => ({
      fund_id: fundId.trim(),
      as_of_date: asOfDate.trim(),
      confidence: Number(confidence),
      horizon_days: Number(horizonDays),
      simulations: Number(simulations),
    }),
    [fundId, asOfDate, confidence, horizonDays, simulations]
  )

  async function onRun(): Promise<void> {
    setLoading(true)
    setError('')
    setSummary('')
    try {
      if (mode === 'direct') {
        const out = await fetchDirectVarCompare(request)
        setRows(out.results || [])
        setMaxVarPctNav(out.max_var_pct_nav || 0)
      } else {
        const out = await fetchAgentVarSkill(request)
        setRows(out.results || [])
        setMaxVarPctNav(out.max_var_pct_nav || 0)
        setSummary(out.summary || '')
      }
    } catch (e) {
      setRows([])
      setMaxVarPctNav(0)
      setSummary('')
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <h1>ARISK Frontend</h1>
          <p className="subtitle">React 前端（獨立目錄）- Agent / Direct 雙模式 VaR 測試台</p>
        </div>
        <div className="mode-tabs">
          <button className={mode === 'direct' ? 'tab active' : 'tab'} onClick={() => setMode('direct')}>
            Direct Query
          </button>
          <button className={mode === 'agent' ? 'tab active' : 'tab'} onClick={() => setMode('agent')}>
            Agent Skill
          </button>
        </div>
      </header>

      <section className="card">
        <h2>查詢參數</h2>
        <div className="grid">
          <label>
            Fund ID
            <input value={fundId} onChange={(e) => setFundId(e.target.value)} />
          </label>
          <label>
            As Of Date
            <input value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />
          </label>
          <label>
            Confidence
            <input value={confidence} onChange={(e) => setConfidence(e.target.value)} />
          </label>
          <label>
            Horizon Days
            <input value={horizonDays} onChange={(e) => setHorizonDays(e.target.value)} />
          </label>
          <label>
            Simulations
            <input value={simulations} onChange={(e) => setSimulations(e.target.value)} />
          </label>
        </div>
        <div className="actions">
          <button className="run" onClick={onRun} disabled={loading}>
            {loading ? '執行中...' : mode === 'direct' ? '執行 Direct Query' : '執行 Agent Skill'}
          </button>
        </div>
        {error ? <div className="error">{error}</div> : null}
      </section>

      <section className="card">
        <h2>三方法結果</h2>
        <VarResultTable rows={rows} />
        <p className="hint">max_var_pct_nav: {maxVarPctNav.toFixed(6)}%</p>
      </section>

      {mode === 'agent' ? (
        <section className="card">
          <h2>Agent Summary</h2>
          <pre className="summary">{summary || '尚無 summary'}</pre>
        </section>
      ) : null}
    </main>
  )
}

export default App

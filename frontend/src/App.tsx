import { useEffect, useState } from 'react'
import { api } from './api'
import { CompareTable } from './components/CompareTable'
import { DefinitionPanel } from './components/DefinitionPanel'
import { DefinitionsPage } from './components/DefinitionsPage'
import type { CompareResult, Store, Version } from './types'

type Tab = 'compare' | 'definitions'

export function App() {
  const [tab, setTab] = useState<Tab>('compare')
  const [stores, setStores] = useState<Store[]>([])
  const [versions, setVersions] = useState<Version[]>([])

  const [leftVersion, setLeftVersion] = useState('v1')
  const [rightVersion, setRightVersion] = useState('v2')
  const [startDate, setStartDate] = useState('2026-10-28')
  const [endDate, setEndDate] = useState('2026-11-05')
  const [storeId, setStoreId] = useState<string>('')

  const [result, setResult] = useState<CompareResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.stores().then(setStores)
    api.versions().then((vs) => {
      setVersions(vs)
      const ids = vs.map((v) => v.version_id)
      if (ids.includes('v1')) setLeftVersion('v1')
      if (ids.includes('v2')) setRightVersion('v2')
    })
  }, [])

  const runCompare = () => {
    setLoading(true)
    setError(null)
    api
      .compare({
        left_version_id: leftVersion,
        right_version_id: rightVersion,
        start_date: startDate,
        end_date: endDate,
        store_id: storeId || null,
      })
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (tab === 'compare') runCompare()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  const storeName = (id: string) =>
    stores.find((s) => s.store_id === id)?.store_name ?? id
  const metrics = result?.left.metric_order ?? []

  return (
    <div className="app">
      <header>
        <h1>净销售额指标工作台</h1>
        <nav>
          <button className={tab === 'compare' ? 'active' : ''} onClick={() => setTab('compare')}>
            版本对比查询
          </button>
          <button className={tab === 'definitions' ? 'active' : ''} onClick={() => setTab('definitions')}>
            口径版本管理
          </button>
        </nav>
      </header>

      {tab === 'compare' && (
        <main>
          <section className="query-bar">
            <label>
              左版本
              <select value={leftVersion} onChange={(e) => setLeftVersion(e.target.value)}>
                {versions.map((v) => (
                  <option key={v.version_id} value={v.version_id}>{v.version_id} · {v.label}</option>
                ))}
              </select>
            </label>
            <label>
              右版本
              <select value={rightVersion} onChange={(e) => setRightVersion(e.target.value)}>
                {versions.map((v) => (
                  <option key={v.version_id} value={v.version_id}>{v.version_id} · {v.label}</option>
                ))}
              </select>
            </label>
            <label>开始日期<input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label>
            <label>结束日期<input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></label>
            <label>
              门店
              <select value={storeId} onChange={(e) => setStoreId(e.target.value)}>
                <option value="">全部门店</option>
                {stores.map((s) => (
                  <option key={s.store_id} value={s.store_id}>{s.store_name}</option>
                ))}
              </select>
            </label>
            <button className="primary" onClick={runCompare} disabled={loading}>
              {loading ? '查询中…' : '查询'}
            </button>
          </section>

          {error && <p className="error">{error}</p>}

          {result && (
            <>
              <DefinitionPanel title={`左：${result.left.version.label}`} definitions={result.left.definitions} />
              <DefinitionPanel title={`右：${result.right.version.label}`} definitions={result.right.definitions} />

              <section>
                <h2>并排对比（点击 V1/V2 单元格可下钻订单与退款明细）</h2>
                <CompareTable
                  left={result.left}
                  right={result.right}
                  metrics={metrics}
                  storeName={storeName}
                />
              </section>
            </>
          )}
        </main>
      )}

      {tab === 'definitions' && (
        <main>
          <DefinitionsPage />
        </main>
      )}
    </div>
  )
}

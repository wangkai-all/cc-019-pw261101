import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Definition, Version } from '../types'

/**
 * Definition governance page.
 * Published versions are frozen (read-only); rule changes happen by cloning
 * a published version into a draft, editing it, validating and publishing.
 */
export function DefinitionsPage() {
  const [versions, setVersions] = useState<Version[]>([])
  const [selected, setSelected] = useState<string>('')
  const [defs, setDefs] = useState<Definition[]>([])
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [newId, setNewId] = useState('')
  const [newLabel, setNewLabel] = useState('')

  const refreshVersions = () =>
    api.versions().then((vs) => {
      setVersions(vs)
      if (!selected && vs.length) setSelected(vs[0].version_id)
    })

  useEffect(() => {
    refreshVersions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selected) return
    api.definitions(selected).then(setDefs).catch(() => setDefs([]))
    setMessage(null)
  }, [selected])

  const current = versions.find((v) => v.version_id === selected)
  const isDraft = current?.status === 'draft'
  const base = defs.filter((d) => d.kind === 'base')
  const derived = defs.filter((d) => d.kind === 'derived')

  const updateDef = (key: string, patch: Partial<Definition>) =>
    setDefs((ds) => ds.map((d) => (d.metric_key === key ? { ...d, ...patch } : d)))

  const validate = async () =>
    api.validate({ base, derived }).then((r) =>
      setMessage(r.valid ? { ok: true, text: '校验通过：依赖、循环与表达式均合法' } : { ok: false, text: r.errors.join('；') }),
    )

  const save = async () => {
    try {
      await api.saveDraft(selected, { base, derived })
      setMessage({ ok: true, text: '草稿已保存（发布前仍会强制校验）' })
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message })
    }
  }

  const publish = async () => {
    try {
      const v = await api.publish(selected)
      setMessage({ ok: true, text: `版本 ${v.version_id} 已发布并冻结` })
      await refreshVersions()
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message })
    }
  }

  const createDraft = async () => {
    if (!newId.trim() || !newLabel.trim()) {
      setMessage({ ok: false, text: '新版本 id 和名称都必填' })
      return
    }
    try {
      const v = await api.createDraft(selected, newId.trim(), newLabel.trim())
      setNewId('')
      setNewLabel('')
      await refreshVersions()
      setSelected(v.version_id)
      setMessage({ ok: true, text: `已基于 ${selected} 创建草稿 ${v.version_id}` })
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message })
    }
  }

  return (
    <div className="def-page">
      <div className="version-bar">
        <label>
          口径版本：
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {versions.map((v) => (
              <option key={v.version_id} value={v.version_id}>
                {v.version_id} · {v.label}（{v.status === 'published' ? '已发布/冻结' : '草稿'}）
              </option>
            ))}
          </select>
        </label>
        <span className={`badge ${isDraft ? 'badge-draft' : 'badge-published'}`}>
          {isDraft ? '草稿，可编辑' : '已发布，冻结只读'}
        </span>
      </div>

      <section className="editor">
        <h3>基础指标（数据粒度 / 时间字段 / 聚合方式）</h3>
        <table className="edit-table">
          <thead>
            <tr>
              <th>指标</th>
              <th>数据粒度</th>
              <th>时间字段</th>
              <th>聚合</th>
              <th>来源表</th>
              <th>金额字段</th>
            </tr>
          </thead>
          <tbody>
            {base.map((d) => (
              <tr key={d.metric_key}>
                <td>{d.metric_name} <code>{d.metric_key}</code></td>
                <td><input value={d.grain ?? ''} disabled={!isDraft} onChange={(e) => updateDef(d.metric_key, { grain: e.target.value })} /></td>
                <td>
                  <select value={d.time_field ?? ''} disabled={!isDraft} onChange={(e) => updateDef(d.metric_key, { time_field: e.target.value })}>
                    <option value="orders.order_date">orders.order_date（订单支付日）</option>
                    <option value="refunds.refund_date">refunds.refund_date（实际退款日）</option>
                  </select>
                </td>
                <td>
                  <select value={d.aggregation ?? ''} disabled={!isDraft} onChange={(e) => updateDef(d.metric_key, { aggregation: e.target.value })}>
                    <option value="sum">sum</option>
                    <option value="count">count</option>
                  </select>
                </td>
                <td><input value={d.source_table ?? ''} disabled={!isDraft} onChange={(e) => updateDef(d.metric_key, { source_table: e.target.value })} /></td>
                <td><input value={d.amount_field ?? ''} disabled={!isDraft} onChange={(e) => updateDef(d.metric_key, { amount_field: e.target.value })} /></td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3>派生指标（公式仅允许指标引用与四则运算）</h3>
        <table className="edit-table">
          <thead>
            <tr><th>指标</th><th>公式</th></tr>
          </thead>
          <tbody>
            {derived.map((d) => (
              <tr key={d.metric_key}>
                <td>{d.metric_name} <code>{d.metric_key}</code></td>
                <td>
                  <input
                    className="formula-input"
                    value={d.formula ?? ''}
                    disabled={!isDraft}
                    onChange={(e) => updateDef(d.metric_key, { formula: e.target.value })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {isDraft && (
          <div className="actions">
            <button onClick={validate}>校验</button>
            <button onClick={save}>保存草稿</button>
            <button className="primary" onClick={publish}>发布并冻结</button>
          </div>
        )}
        {message && <p className={message.ok ? 'ok' : 'error'}>{message.text}</p>}
      </section>

      <section className="clone">
        <h3>改规则另开新版本</h3>
        <p className="muted">
          基于当前版本（{selected}）复制出草稿，已发布版本的历史查询不会随之改变。
        </p>
        <input placeholder="新版本 id，如 v3" value={newId} onChange={(e) => setNewId(e.target.value)} />
        <input placeholder="版本名称" value={newLabel} onChange={(e) => setNewLabel(e.target.value)} />
        <button onClick={createDraft}>创建草稿</button>
      </section>
    </div>
  )
}

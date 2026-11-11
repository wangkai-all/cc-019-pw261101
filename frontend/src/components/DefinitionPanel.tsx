import type { Definition } from '../types'

/**
 * Shows the definitions actually used by a query result. The backend echoes
 * the frozen snapshot of the selected version, so what is displayed here
 * always matches the numbers next to it — never the current editor state.
 */
export function DefinitionPanel({
  title,
  definitions,
}: {
  title: string
  definitions: Definition[]
}) {
  const base = definitions.filter((d) => d.kind === 'base')
  const derived = definitions.filter((d) => d.kind === 'derived')
  return (
    <section className="def-panel">
      <h3>{title} 实际使用的定义</h3>
      <div className="def-grid">
        {base.map((d) => (
          <div className="def-card" key={d.metric_key}>
            <div className="def-card-head">
              <span className="def-name">{d.metric_name}</span>
              <code>{d.metric_key}</code>
            </div>
            <dl>
              <div><dt>数据粒度</dt><dd>{d.grain}</dd></div>
              <div><dt>时间字段</dt><dd><code>{d.time_field}</code></dd></div>
              <div><dt>聚合方式</dt><dd>{d.aggregation}</dd></div>
              <div><dt>来源表</dt><dd><code>{d.source_table}</code></dd></div>
              <div><dt>金额字段</dt><dd><code>{d.amount_field}</code></dd></div>
            </dl>
          </div>
        ))}
        {derived.map((d) => (
          <div className="def-card derived" key={d.metric_key}>
            <div className="def-card-head">
              <span className="def-name">{d.metric_name}</span>
              <code>{d.metric_key}</code>
            </div>
            <dl>
              <div>
                <dt>派生公式</dt>
                <dd><code className="formula">{d.formula}</code></dd>
              </div>
            </dl>
          </div>
        ))}
      </div>
    </section>
  )
}

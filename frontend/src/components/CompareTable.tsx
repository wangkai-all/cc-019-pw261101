import { useMemo, useState } from 'react'
import { DrillModal } from './DrillModal'
import { formatMetric, subtractMoney } from '../format'
import type { MetricRow, QueryResult } from '../types'

type CellKey = { date: string; store_id: string }

/** Full outer join of two versions' rows on (date, store). */
function mergeRows(left: QueryResult, right: QueryResult): CellKey[] {
  const map = new Map<string, CellKey>()
  for (const r of [...left.rows, ...right.rows]) {
    map.set(`${r.date}|${r.store_id}`, { date: r.date, store_id: r.store_id })
  }
  return [...map.values()].sort((a, b) =>
    a.date === b.date
      ? a.store_id.localeCompare(b.store_id)
      : a.date.localeCompare(b.date),
  )
}

export function CompareTable({
  left,
  right,
  metrics,
  storeName,
}: {
  left: QueryResult
  right: QueryResult
  metrics: string[]
  storeName: (id: string) => string
}) {
  const [drill, setDrill] = useState<({ versionId: string } & CellKey) | null>(null)

  const leftMap = useMemo(
    () => new Map(left.rows.map((r) => [`${r.date}|${r.store_id}`, r])),
    [left],
  )
  const rightMap = useMemo(
    () => new Map(right.rows.map((r) => [`${r.date}|${r.store_id}`, r])),
    [right],
  )
  const keys = useMemo(() => mergeRows(left, right), [left, right])

  const diff = (l: MetricRow | undefined, r: MetricRow | undefined, key: string) => {
    const lv = l?.metrics[key] ?? null
    const rv = r?.metrics[key] ?? null
    if (key === 'refund_rate') {
      // rates are null when denominator is zero; show blank if either side is null
      if (lv === null || rv === null) return null
      return (parseFloat(rv) - parseFloat(lv)).toFixed(4)
    }
    return subtractMoney(rv, lv)
  }

  return (
    <>
      <div className="table-wrap">
        <table className="compare-table">
          <thead>
            <tr>
              <th rowSpan={2}>日期</th>
              <th rowSpan={2}>门店</th>
              {metrics.map((m) => (
                <th colSpan={3} key={m}>
                  {left.definitions.find((d) => d.metric_key === m)?.metric_name ?? m}
                </th>
              ))}
            </tr>
            <tr>
              {metrics.map((m) => (
                <FragmentHeader
                  key={m}
                  leftLabel={left.version.version_id}
                  rightLabel={right.version.version_id}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const id = `${k.date}|${k.store_id}`
              const l = leftMap.get(id)
              const r = rightMap.get(id)
              return (
                <tr key={id}>
                  <td>{k.date}</td>
                  <td>{storeName(k.store_id)}</td>
                  {metrics.map((m) => (
                    <FragmentCells
                      key={m}
                      metricKey={m}
                      lv={l?.metrics[m] ?? null}
                      rv={r?.metrics[m] ?? null}
                      diff={diff(l, r, m)}
                      leftVersionId={left.version.version_id}
                      rightVersionId={right.version.version_id}
                      onDrill={(versionId) =>
                        setDrill({ versionId, date: k.date, store_id: k.store_id })
                      }
                    />
                  ))}
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="totals">
              <td colSpan={2}>合计</td>
              {metrics.map((m) => (
                <FragmentCells
                  key={m}
                  metricKey={m}
                  lv={left.totals[m] ?? null}
                  rv={right.totals[m] ?? null}
                  diff={
                    m === 'refund_rate'
                      ? left.totals[m] === null || right.totals[m] === null
                        ? null
                        : (parseFloat(right.totals[m]!) - parseFloat(left.totals[m]!)).toFixed(4)
                      : subtractMoney(right.totals[m], left.totals[m])
                  }
                  leftVersionId={left.version.version_id}
                  rightVersionId={right.version.version_id}
                />
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      {drill && (
        <DrillModal
          versionId={drill.versionId}
          date={drill.date}
          storeId={drill.store_id}
          onClose={() => setDrill(null)}
        />
      )}
    </>
  )
}

function FragmentHeader({ leftLabel, rightLabel }: { leftLabel: string; rightLabel: string }) {
  return (
    <>
      <th className="num col-v1">{leftLabel}</th>
      <th className="num col-v2">{rightLabel}</th>
      <th className="num col-diff">差额(右−左)</th>
    </>
  )
}

function FragmentCells({
  metricKey,
  lv,
  rv,
  diff,
  leftVersionId,
  rightVersionId,
  onDrill,
}: {
  metricKey: string
  lv: string | null
  rv: string | null
  diff: string | null
  leftVersionId: string
  rightVersionId: string
  onDrill?: (versionId: string) => void
}) {
  const diffClass =
    diff === null || parseFloat(diff) === 0
      ? 'num col-diff muted'
      : parseFloat(diff) < 0
        ? 'num col-diff neg'
        : 'num col-diff pos'
  return (
    <>
      <td
        className={`num col-v1${onDrill ? ' drillable' : ''}`}
        onClick={onDrill ? () => onDrill(leftVersionId) : undefined}
        title={onDrill ? '点击下钻到订单与退款明细' : undefined}
      >
        {formatMetric(metricKey, lv)}
      </td>
      <td
        className={`num col-v2${onDrill ? ' drillable' : ''}`}
        onClick={onDrill ? () => onDrill(rightVersionId) : undefined}
        title={onDrill ? '点击下钻到订单与退款明细' : undefined}
      >
        {formatMetric(metricKey, rv)}
      </td>
      <td className={diffClass}>{diff === null ? '' : formatMetric(metricKey, diff)}</td>
    </>
  )
}

import { useEffect, useState } from 'react'
import { api } from '../api'
import { formatMoney } from '../format'
import type { DrillResult } from '../types'

export function DrillModal({
  versionId,
  date,
  storeId,
  onClose,
}: {
  versionId: string
  date: string
  storeId: string
  onClose: () => void
}) {
  const [data, setData] = useState<DrillResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .drill({ version_id: versionId, date, store_id: storeId })
      .then((r) => !cancelled && setData(r))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [versionId, date, storeId])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>
            明细下钻 · {storeId} · {date}
          </h3>
          <button className="btn-ghost" onClick={onClose}>
            关闭
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        {!data && !error && <p className="muted">加载中…</p>}
        {data && (
          <>
            <p className="muted">
              退款归属时间字段：<code>{data.refund_time_field}</code>
            </p>
            <h4>订单（支付）</h4>
            <table className="drill-table">
              <thead>
                <tr>
                  <th>订单号</th>
                  <th>下单日期</th>
                  <th className="num">支付金额</th>
                </tr>
              </thead>
              <tbody>
                {data.orders.length === 0 && (
                  <tr>
                    <td colSpan={3} className="muted center">
                      当日无支付订单
                    </td>
                  </tr>
                )}
                {data.orders.map((o) => (
                  <tr key={o.order_id}>
                    <td>{o.order_id}</td>
                    <td>{o.order_date}</td>
                    <td className="num">{formatMoney(o.paid_amount ?? null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h4>退款明细</h4>
            <table className="drill-table">
              <thead>
                <tr>
                  <th>退款单号</th>
                  <th>关联订单</th>
                  <th>实际退款日期</th>
                  <th className="num">退款金额</th>
                </tr>
              </thead>
              <tbody>
                {data.refunds.length === 0 && (
                  <tr>
                    <td colSpan={4} className="muted center">
                      当日无退款
                    </td>
                  </tr>
                )}
                {data.refunds.map((r) => (
                  <tr key={r.refund_id}>
                    <td>{r.refund_id}</td>
                    <td>{r.order_id}</td>
                    <td>{r.refund_date}</td>
                    <td className="num">{formatMoney(r.refund_amount ?? null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  )
}

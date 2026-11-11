export type VersionStatus = 'draft' | 'published'

export interface Version {
  version_id: string
  label: string
  status: VersionStatus
  created_at: string
  published_at: string | null
}

export interface Definition {
  metric_key: string
  metric_name: string
  kind: 'base' | 'derived'
  grain: string | null
  time_field: string | null
  aggregation: string | null
  source_table: string | null
  amount_field: string | null
  formula: string | null
}

export interface Store {
  store_id: string
  store_name: string
}

export interface MetricRow {
  date: string
  store_id: string
  metrics: Record<string, string | null>
}

export interface QueryResult {
  version: Version
  definitions: Definition[]
  stores: Store[]
  rows: MetricRow[]
  totals: Record<string, string | null>
  metric_order: string[]
}

export interface CompareResult {
  left: QueryResult
  right: QueryResult
}

export interface DrillRow {
  order_id?: string
  store_id?: string
  order_date?: string
  paid_amount?: string
  refund_id?: string
  refund_date?: string
  refund_amount?: string
}

export interface DrillResult {
  version: Version
  date: string
  store_id: string
  refund_time_field: string
  orders: DrillRow[]
  refunds: DrillRow[]
}

import type {
  CompareResult,
  Definition,
  DrillResult,
  Store,
  Version,
} from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(body.detail ?? '请求失败')
  }
  return resp.json() as Promise<T>
}

export const api = {
  stores: () => request<Store[]>('/api/stores'),
  versions: () => request<Version[]>('/api/versions'),
  definitions: (versionId: string) =>
    request<Definition[]>(`/api/versions/${versionId}/definitions`),
  compare: (payload: {
    left_version_id: string
    right_version_id: string
    start_date: string
    end_date: string
    store_id: string | null
  }) => request<CompareResult>('/api/compare', { method: 'POST', body: JSON.stringify(payload) }),
  drill: (payload: { version_id: string; date: string; store_id: string }) =>
    request<DrillResult>('/api/drill', { method: 'POST', body: JSON.stringify(payload) }),
  createDraft: (sourceId: string, versionId: string, label: string) =>
    request<Version>(`/api/versions/${sourceId}/draft`, {
      method: 'POST',
      body: JSON.stringify({ version_id: versionId, label }),
    }),
  saveDraft: (
    versionId: string,
    payload: { base: Definition[]; derived: Definition[] },
  ) =>
    request<{ status: string }>(`/api/versions/${versionId}/definitions`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  publish: (versionId: string) =>
    request<Version>(`/api/versions/${versionId}/publish`, { method: 'POST' }),
  validate: (payload: { base: Definition[]; derived: Definition[] }) =>
    request<{ valid: boolean; errors: string[] }>('/api/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

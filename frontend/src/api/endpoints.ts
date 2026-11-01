import { api } from './client'

export type ColumnMeta = {
  name: string
  type: string
  n_missing: number
  missing_pct: number
  nunique: number
  uniqueness: number
  sample: string[]
  stats: Record<string, unknown>
  pii: string | null
  excluded: boolean
  exclude_reason: string | null
}

export type DatasetOut = {
  id: string
  name: string
  source_type: string
  nrows: number
  ncols: number
  columns: ColumnMeta[]
  health: Record<string, unknown>
  event_time_col: string | null
  entity_col: string | null
  data_hash: string
  preview?: Record<string, unknown>[]
}

export type GuardCheck = { id: string; verdict: string; detail: string; column?: string }
export type GuardReport = { verdict: string; checks: GuardCheck[]; exclude_auto: Record<string, string>; split_kind?: string }

export type ModelOut = {
  id: number
  name: string
  status: string
  task_type: string
  target_col: string
  dataset: { id: string; name: string; nrows: number; ncols: number }
  excluded_cols: string[]
  guard_verdict: string
  guard_report?: GuardReport
  threshold: number | null
  active_version: number | null
  hero_metric?: number | null
  profit_scaled?: number | null
  metrics?: Record<string, unknown> | null
  cost_matrix?: Record<string, unknown> | null
  threshold_info?: Record<string, unknown> | null
  actionable?: Record<string, unknown> | null
  schedule?: Record<string, unknown> | null
  versions?: { id: number; version: number; status: string; created_at: string; guard_verdict: string | null }[]
}

export type Driver = { feature: string; impact: number; direction: string }
export type Reason = { feature: string; value: unknown; impact: number; direction: string; text?: string }

export type Prediction = {
  prediction_id: string
  label?: string
  probability?: number
  prediction?: number
  decision?: boolean
  threshold?: number
  interval_low?: number
  interval_high?: number
  conformal?: { coverage: number; prediction_set: string[] }
  out_of_distribution: boolean
  ood_note?: string
  confidence_note?: string
  top_reasons?: Reason[]
}

export const loginApi = (email: string, password: string) =>
  api<{ user: { id: number; email: string; role: string; must_change_password: boolean } }>('/api/auth/login', { json: { email, password } })
export const changePasswordApi = (old_password: string, new_password: string) =>
  api('/api/auth/change-password', { json: { old_password, new_password } })
export const logoutApi = () => api('/api/auth/logout', { method: 'POST' })

export const listDatasets = () => api<{ id: string; name: string; source_type: string; nrows: number; ncols: number; created_at: string }[]>('/api/datasets')
export const uploadDataset = (form: FormData) => api<DatasetOut>('/api/datasets/upload', { form })
export const getDataset = (id: string, rows = 20) => api<DatasetOut>(`/api/datasets/${id}?rows=${rows}`)
export const patchDataset = (id: string, body: Record<string, unknown>) => api<DatasetOut>(`/api/datasets/${id}`, { method: 'PATCH', json: body })

export const listConnections = () => api<{ id: number; name: string; db_type: string }[]>('/api/connections')
export const createConnection = (body: Record<string, unknown>) => api('/api/connections', { json: body })
export const testConnection = (id: number) => api<{ ok: boolean; tables: string[]; error?: string }>(`/api/connections/${id}/test`, { method: 'POST' })
export const buildFeatures = (body: Record<string, unknown>) => api<{ job_id: string }>('/api/features/build', { json: body })

export const listModels = () => api<ModelOut[]>('/api/models')
export const createModel = (body: Record<string, unknown>) => api<ModelOut>('/api/models', { json: body })
export const getModel = (id: number) => api<ModelOut>(`/api/models/${id}`)
export const patchModel = (id: number, body: Record<string, unknown>) => api<ModelOut>(`/api/models/${id}`, { method: 'PATCH', json: body })
export const recheckModel = (id: number) => api<GuardReport>(`/api/models/${id}/recheck`, { method: 'POST' })
export const trainModel = (id: number, body: Record<string, unknown>) => api<{ job_id: string }>(`/api/models/${id}/train`, { json: body })
export const getJob = (id: string) => api<{ id: string; status: string; progress: Record<string, unknown>; error: string | null }>(`/api/jobs/${id}`)
export const cancelJob = (id: string) => api(`/api/jobs/${id}/cancel`, { method: 'POST' })
export const setProfit = (id: number, body: Record<string, unknown>) => api<Record<string, unknown>>(`/api/models/${id}/profit`, { json: body })
export const getModelCard = (id: number) => api<{ card_md: string; version: number; llm_narrative?: string }>(`/api/models/${id}/card`)
export const regenerateCard = (id: number) => api(`/api/models/${id}/card/regenerate`, { method: 'POST' })
export const getSnippets = (id: number) => api<{ curl: string; python: string; javascript: string; one_c: string; url: string; example: Record<string, unknown> }>(`/api/models/${id}/snippets`)
export const rollbackModel = (id: number, version: number) => api(`/api/models/${id}/rollback`, { json: { version } })
export const runMonitor = (id: number) => api<{ job_id: string }>(`/api/models/${id}/monitor/run`, { method: 'POST' })
export const getMonitor = (id: number) => api<any[]>(`/api/models/${id}/monitor`)
export const runPlaybook = (id: number, form: FormData) => api<{ job_id: string }>(`/api/models/${id}/playbook`, { form })

export const predictApi = (id: number, data: Record<string, unknown>[], include: string[] = []) =>
  api<{ predictions: Prediction[]; latency_ms: number; warnings?: string[] }>(`/api/v1/models/${id}/predict`, { json: { data, include } })
export const whatifApi = (id: number, data: Record<string, unknown>, changes: Record<string, unknown>) =>
  api<{ before: Prediction; after: Prediction; caution: string }>(`/api/v1/models/${id}/whatif`, { json: { data, changes } })
export const counterfactualApi = (id: number, data: Record<string, unknown>) =>
  api<Record<string, unknown>>(`/api/v1/models/${id}/counterfactual`, { json: { data } })
export const getSchema = (id: number) => api<{ input_schema: { properties: Record<string, Record<string, unknown>> }; example: Record<string, unknown>; threshold: number | null }>(`/api/v1/models/${id}/schema`)

export const listKeys = () => api<{ id: number; name: string; prefix: string; model_ids: number[]; rate_limit_rpm: number; created_at: string; last_used_at: string | null; revoked_at: string | null }[]>('/api/keys')
export const createKey = (body: Record<string, unknown>) => api<{ key: string; prefix: string; id: number }>('/api/keys', { json: body })
export const revokeKey = (id: number) => api(`/api/keys/${id}/revoke`, { method: 'POST' })

export const adminStats = () => api<Record<string, number>>('/api/admin/stats')
export const adminLlm = () => api<{ enabled: boolean; base_url: string; model: string; api_key_masked: string }>('/api/admin/llm')
export const adminPutLlm = (body: Record<string, unknown>) => api('/api/admin/llm', { method: 'PUT', json: body })
export const adminUsers = () => api<{ id: number; email: string; display_name: string; role: string; must_change_password: boolean; is_active?: boolean }[]>('/api/auth/users')
export const adminCreateUser = (body: Record<string, unknown>) => api('/api/auth/users', { json: body })
export const adminPatchUser = (id: number, body: Record<string, unknown>) => api(`/api/auth/users/${id}`, { method: 'PATCH', json: body })
export const adminWebhooks = () => api<{ id: number; url: string; model_id: number | null; events: string[]; active: boolean }[]>('/api/admin/webhooks')
export const adminCreateWebhook = (body: Record<string, unknown>) => api('/api/admin/webhooks', { json: body })

export const publicInfo = (slug: string) => api<{ name: string; task_type: string; has_password: boolean; input_schema: { properties: Record<string, Record<string, unknown>> }; example: Record<string, unknown> }>(`/api/public/p/${slug}`)
export const publicPredict = (slug: string, data: Record<string, unknown>, password?: string) =>
  api<{ prediction: Prediction; warnings?: string[] }>(`/api/public/p/${slug}/predict`, { json: { data, password } })
export const managePublic = (modelId: number, body: Record<string, unknown>) => api<{ enabled: boolean; url?: string }>(`/api/public/manage/${modelId}`, { json: body })
export const llmStatus = () => api<{ enabled: boolean; model: string | null }>('/api/llm/status')
export const mcpConfig = () => api<{ enabled: boolean; claude_desktop?: string; cursor?: string; http_command?: string }>(`/api/setup/mcp-config?t=${Date.now()}`)

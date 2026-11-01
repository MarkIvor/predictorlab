export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    const d = body.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      return d
        .map((e: { loc?: (string | number)[]; msg?: string }) => {
          const field = e.loc?.filter((p) => typeof p === 'string').join('.')
          return field ? `${field}: ${e.msg ?? 'неверное значение'}` : (e.msg ?? 'неверное значение')
        })
        .join('; ')
    }
    return `Ошибка ${res.status}`
  } catch {
    return `Ошибка ${res.status}`
  }
}

export async function api<T>(path: string, options: { method?: string; json?: unknown; form?: FormData } = {}): Promise<T> {
  const init: RequestInit = { credentials: 'include', method: options.method ?? (options.json !== undefined ? 'POST' : 'GET') }
  if (options.json !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(options.json)
  } else if (options.form !== undefined) {
    init.body = options.form
  }
  const res = await fetch(path, init)
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  if (res.status === 204) return undefined as T
  return res.json()
}

export type SseEvent = { event: string; data: unknown; id?: number }

export async function* sse(path: string, signal?: AbortSignal): AsyncGenerator<SseEvent> {
  const res = await fetch(path, { credentials: 'include', signal })
  if (!res.body) throw new Error('Поток недоступен')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'message'
      let data = ''
      let id: number | undefined
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
        else if (line.startsWith('id:')) id = Number(line.slice(3).trim())
      }
      if (data) {
        try {
          yield { event, data: JSON.parse(data), id }
        } catch {
          yield { event, data, id }
        }
      }
    }
  }
}

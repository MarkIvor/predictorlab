import { useSyncExternalStore } from 'react'
import { dict, type Lang } from './dict'

const listeners = new Set<() => void>()
let current: Lang = 'ru'
try {
  const saved = localStorage.getItem('pl-lang')
  if (saved === 'ru' || saved === 'en') current = saved
} catch { /* noop */ }

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

export function setLang(lang: Lang) {
  current = lang
  try { localStorage.setItem('pl-lang', lang) } catch { /* noop */ }
  listeners.forEach((fn) => fn())
}

export function useLang(): Lang {
  return useSyncExternalStore(subscribe, () => current)
}

export function t(key: string, params?: Record<string, string | number>): string {
  const table = dict[current] ?? dict.ru
  let s = table[key] ?? dict.ru[key] ?? key
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v))
  return s
}

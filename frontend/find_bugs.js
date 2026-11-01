import fs from 'fs'
import path from 'path'

function walk(d) {
  for (const f of fs.readdirSync(d)) {
    const p = path.join(d, f)
    if (fs.statSync(p).isDirectory()) { walk(p); continue }
    if (!f.endsWith('.tsx')) continue
    const s = fs.readFileSync(p, 'utf8')
    const lines = s.split('\n')
    lines.forEach((l, i) => {
      if (/gridColumn:\s*'span\s+\d+\s+}}/.test(l)) {
        console.log(`${p}:${i + 1}: ${l.trim()}`)
      }
    })
  }
}
walk('src')

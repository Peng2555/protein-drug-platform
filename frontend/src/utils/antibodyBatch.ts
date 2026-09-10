import { apiJson } from '@/api/client'
import { decodeBytesAuto, stripBom } from './fileEncoding'

export interface AntibodyRow {
  id: string
  heavy: string
  light?: string | null
}

const AA = /^[ACDEFGHIKLMNPQRSTVWY]+$/
const ROLE_SUFFIX = /^(.+?)(?:[_/\-|.]|chain)(heavy|light|h|l)$/i

function looksLikeSequence(raw: string) {
  const seq = raw.replace(/[\s\d]/g, '').toUpperCase()
  return seq.length >= 5 && AA.test(seq)
}

function normSeq(raw: string) {
  return raw.replace(/\s/g, '').toUpperCase()
}

function headerKey(raw: string) {
  return raw.trim().toLowerCase().replace(/\s+/g, '_')
}

function splitCsvLine(line: string) {
  if (line.includes('\t')) return line.split('\t').map((p) => p.trim())
  if (line.includes('|') && line.split('|').length >= line.split(',').length) {
    return line.split('|').map((p) => p.trim())
  }
  const semi = line.split(';')
  const comma = line.split(',')
  return semi.length > comma.length ? semi.map((p) => p.trim()) : comma.map((p) => p.trim())
}

function classifyFastaHeader(hid: string): { base: string; role: 'H' | 'L' | null } {
  const u = hid.trim()
  const ul = u.toUpperCase()
  if (ul === 'H' || ul === 'HEAVY') return { base: '', role: 'H' }
  if (ul === 'L' || ul === 'LIGHT') return { base: '', role: 'L' }
  const m = u.match(ROLE_SUFFIX)
  if (m) {
    const role = m[2].toUpperCase()
    const base = m[1].replace(/[_./|-]+$/, '')
    if (role === 'HEAVY' || role === 'H') return { base, role: 'H' }
    if (role === 'LIGHT' || role === 'L') return { base, role: 'L' }
  }
  return { base: u, role: null }
}

function parseFastaRecords(text: string): Array<{ id: string; seq: string }> {
  const rows: Array<{ id: string; seq: string }> = []
  let id: string | null = null
  const parts: string[] = []
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('>')) {
      if (id) {
        const seq = parts.join('').toUpperCase()
        if (seq.length >= 5) rows.push({ id, seq })
      }
      id = line.slice(1).split(/\s/)[0]
      parts.length = 0
    } else {
      parts.push(line.replace(/\s/g, ''))
    }
  }
  if (id) {
    const seq = parts.join('').toUpperCase()
    if (seq.length >= 5) rows.push({ id, seq })
  }
  return rows
}

export function parseAntibodyFasta(text: string): AntibodyRow[] {
  const records = parseFastaRecords(text)
  const grouped = new Map<string, { H?: string; L?: string }>()
  const unlabeled: AntibodyRow[] = []
  const genericH: string[] = []
  const genericL: string[] = []

  for (const rec of records) {
    const { base, role } = classifyFastaHeader(rec.id)
    if (base === '' && role === 'H') {
      genericH.push(rec.seq)
      continue
    }
    if (base === '' && role === 'L') {
      genericL.push(rec.seq)
      continue
    }
    if (role == null) {
      unlabeled.push({ id: rec.id, heavy: rec.seq })
      continue
    }
    const slot = grouped.get(base) || {}
    slot[role] = rec.seq
    grouped.set(base, slot)
  }

  const antibodies: AntibodyRow[] = []
  if (genericH.length || genericL.length) {
    if (genericH.length === 1 && genericL.length === 1) {
      antibodies.push({ id: 'Ab', heavy: genericH[0], light: genericL[0] })
    } else if (genericL.length && !genericH.length) {
      return []
    } else if (genericL.length && genericH.length === genericL.length) {
      genericH.forEach((h, i) => {
        antibodies.push({ id: `Ab${i + 1}`, heavy: h, light: genericL[i] })
      })
    } else if (!genericL.length) {
      genericH.forEach((seq, i) => {
        antibodies.push({ id: genericH.length === 1 ? 'H' : `H${i + 1}`, heavy: seq })
      })
    }
  }
  antibodies.push(...unlabeled)
  for (const [base, slot] of grouped) {
    if (slot.H) antibodies.push({ id: base, heavy: slot.H, light: slot.L })
  }
  return antibodies
}

const ID_HEADERS = new Set(['id', 'vhh_id', 'name', 'antibody_id', 'ab_id', '抗体id'])
const HEAVY_HEADERS = new Set([
  'heavy',
  'heavy_sequence',
  'heavy_seq',
  'h',
  'sequence',
  'seq',
  '序列',
  '重链',
  '重链序列',
])
const LIGHT_HEADERS = new Set(['light', 'light_sequence', 'light_seq', 'l', '轻链', '轻链序列'])

function looksLikeHeader(parts: string[]) {
  return parts.some((p) => {
    const k = headerKey(p)
    return ID_HEADERS.has(k) || HEAVY_HEADERS.has(k) || LIGHT_HEADERS.has(k)
  })
}

export function parseAntibodyCsv(text: string): AntibodyRow[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  if (!lines.length) return []
  const first = splitCsvLine(lines[0])
  let start = 0
  let idI = 0
  let heavyI = 1
  let lightI: number | null = null
  if (looksLikeHeader(first)) {
    start = 1
    const keys = first.map(headerKey)
    idI = keys.findIndex((k) => ID_HEADERS.has(k))
    if (idI < 0) idI = 0
    heavyI = keys.findIndex((k) => HEAVY_HEADERS.has(k))
    if (heavyI < 0) heavyI = 1
    const li = keys.findIndex((k) => LIGHT_HEADERS.has(k))
    lightI = li >= 0 ? li : null
  } else if (first.length >= 3) {
    lightI = 2
  }

  const rows: AntibodyRow[] = []
  let autoIdx = 1
  for (const line of lines.slice(start)) {
    const parts = splitCsvLine(line)
    if (parts.length === 1 && looksLikeSequence(parts[0])) {
      rows.push({ id: `Ab_${String(autoIdx).padStart(3, '0')}`, heavy: normSeq(parts[0]) })
      autoIdx += 1
      continue
    }
    let id = (parts[idI] || '').trim().replace(/^"|"$/g, '')
    if (!id) {
      id = `Ab_${String(autoIdx).padStart(3, '0')}`
      autoIdx += 1
    }
    const heavyRaw = parts[heavyI] || ''
    let lightRaw = lightI != null ? parts[lightI] || '' : ''
    if (lightI == null && parts.length >= 3 && looksLikeSequence(parts[2])) lightRaw = parts[2]
    const heavy = normSeq(heavyRaw.replace(/^"|"$/g, ''))
    const light = lightRaw.trim() ? normSeq(lightRaw.replace(/^"|"$/g, '')) : ''
    if (!looksLikeSequence(heavy)) continue
    rows.push({ id, heavy, light: light && looksLikeSequence(light) ? light : undefined })
  }
  return rows
}

export function parseAntibodyText(text: string): { rows: AntibodyRow[]; format: 'csv' | 'fasta' } {
  text = stripBom(text.trim())
  if (!text) return { rows: [], format: 'csv' }
  if (text.trimStart().startsWith('>')) {
    return { rows: parseAntibodyFasta(text), format: 'fasta' }
  }
  return { rows: parseAntibodyCsv(text), format: 'csv' }
}

export function formatAntibodyDisplay(rows: AntibodyRow[], fmt: 'csv' | 'fasta') {
  if (!rows.length) return ''
  if (fmt === 'fasta') {
    return (
      rows
        .map((r) =>
          r.light
            ? `>${r.id}_H\n${r.heavy}\n>${r.id}_L\n${r.light}`
            : `>${r.id}\n${r.heavy}`,
        )
        .join('\n') + '\n'
    )
  }
  return [
    'id,heavy,light',
    ...rows.map((r) => `${r.id},${r.heavy},${r.light || ''}`),
  ].join('\n')
}

function bytesToBase64(bytes: Uint8Array) {
  const chunk = 0x8000
  let binary = ''
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunk)))
  }
  return btoa(binary)
}

function isLikelyXlsx(bytes: Uint8Array) {
  return bytes.length >= 2 && bytes[0] === 0x50 && bytes[1] === 0x4b
}

export interface AntibodyImportResult {
  text: string
  encoding: string
  format: 'csv' | 'fasta'
  rows: AntibodyRow[]
  row_count: number
}

export async function importAntibodyFile(file: File): Promise<AntibodyImportResult> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  const isExcel = ext === 'xlsx' || ext === 'xlsm' || isLikelyXlsx(bytes)

  try {
    const data = await apiJson<AntibodyImportResult>('/api/batches/parse-antibody-csv-b64', {
      method: 'POST',
      data: { filename: file.name, content_b64: bytesToBase64(bytes) },
    })
    return data
  } catch (err) {
    if (isExcel) {
      throw new Error(
        err instanceof Error
          ? err.message
          : '无法解析 Excel 文件。请另存为 CSV UTF-8 或 FASTA 后重试。',
      )
    }
    const { text, encoding } = decodeBytesAuto(bytes)
    const parsed = parseAntibodyText(text)
    if (!parsed.rows.length) {
      throw new Error(err instanceof Error ? err.message : '文件解析失败。请确认格式。')
    }
    return {
      text: formatAntibodyDisplay(parsed.rows, parsed.format),
      encoding: `${encoding}（本地解析）`,
      format: parsed.format,
      rows: parsed.rows,
      row_count: parsed.rows.length,
    }
  }
}

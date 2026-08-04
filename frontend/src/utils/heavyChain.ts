import { apiJson } from '@/api/client'
import { decodeBytesAuto, stripBom } from './fileEncoding'

export interface HeavyChainRow {
  id: string
  sequence: string
}

function looksLikeSequence(raw: string) {
  const seq = raw.replace(/[\s\d]/g, '').toUpperCase()
  return seq.length >= 5 && /^[ACDEFGHIKLMNPQRSTVWY]+$/.test(seq)
}

function splitCsvLine(line: string) {
  if (line.includes('\t')) return line.split('\t')
  if (line.includes('|')) return line.split('|').map((p) => p.trim())
  const semi = line.split(';')
  const comma = line.split(',')
  return semi.length > comma.length ? semi : comma
}

export function parseHeavyFasta(text: string): HeavyChainRow[] {
  const rows: HeavyChainRow[] = []
  let id: string | null = null
  let parts: string[] = []
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('>')) {
      if (id) rows.push({ id, sequence: parts.join('').toUpperCase() })
      id = line.slice(1).split(/\s/)[0]
      parts = []
    } else {
      parts.push(line.replace(/\s/g, ''))
    }
  }
  if (id) rows.push({ id, sequence: parts.join('').toUpperCase() })
  return rows.filter((r) => r.sequence.length >= 5)
}

export function parseHeavyChainText(text: string): { rows: HeavyChainRow[]; format: 'csv' | 'fasta' } {
  text = stripBom(text.trim())
  if (!text) return { rows: [], format: 'csv' }
  if (text.trimStart().startsWith('>')) {
    return { rows: parseHeavyFasta(text), format: 'fasta' }
  }

  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  let start = 0
  const h = lines[0]?.toLowerCase() || ''
  if (
    h.includes('vhh_id') ||
    h.includes('sequence') ||
    h.includes('重链') ||
    h.includes('序列') ||
    h.startsWith('id,') ||
    h.startsWith('id;') ||
    h.startsWith('id\t')
  ) {
    start = 1
  }

  const rows: HeavyChainRow[] = []
  let autoIdx = 1
  for (const line of lines.slice(start)) {
    const parts = splitCsvLine(line)
    if (parts.length >= 2) {
      const id = parts[0].trim().replace(/^"|"$/g, '')
      const seqRaw = (parts.length > 2 ? parts.slice(1).join(',') : parts[1]).trim().replace(/^"|"$/g, '')
      const sequence = seqRaw.replace(/\s/g, '').toUpperCase()
      if (id && looksLikeSequence(sequence)) rows.push({ id, sequence })
      continue
    }
    const ws = line.match(/^(\S+)\s+([ACDEFGHIKLMNPQRSTVWY\s]+)$/i)
    if (ws) {
      const id = ws[1].trim()
      const sequence = ws[2].replace(/\s/g, '').toUpperCase()
      if (looksLikeSequence(sequence)) rows.push({ id, sequence })
      continue
    }
    if (looksLikeSequence(line)) {
      rows.push({
        id: `VHH_${String(autoIdx).padStart(3, '0')}`,
        sequence: line.replace(/\s/g, '').toUpperCase(),
      })
      autoIdx += 1
    }
  }
  return { rows, format: 'csv' }
}

export function formatHeavyChainDisplay(rows: HeavyChainRow[], fmt: 'csv' | 'fasta') {
  if (!rows.length) return ''
  if (fmt === 'fasta') {
    return rows.map((r) => `>${r.id}\n${r.sequence}`).join('\n') + '\n'
  }
  return ['vhh_id,sequence', ...rows.map((r) => `${r.id},${r.sequence}`)].join('\n')
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

export interface HeavyImportResult {
  text: string
  encoding: string
  format: 'csv' | 'fasta'
  rows: HeavyChainRow[]
  row_count: number
}

export async function importHeavyChainFile(file: File): Promise<HeavyImportResult> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  const isExcel = ext === 'xlsx' || ext === 'xlsm' || isLikelyXlsx(bytes)

  try {
    const data = await apiJson<HeavyImportResult>('/api/batches/parse-heavy-csv-b64', {
      method: 'POST',
      data: { filename: file.name, content_b64: bytesToBase64(bytes) },
    })
    return data
  } catch (err) {
    if (isExcel) {
      throw new Error(
        err instanceof Error
          ? err.message
          : '无法解析 Excel 文件。请在 Excel 中「另存为 → CSV UTF-8」或 .txt 后重试。',
      )
    }
    const { text, encoding } = decodeBytesAuto(bytes)
    const parsed = parseHeavyChainText(text)
    if (!parsed.rows.length) {
      throw new Error(err instanceof Error ? err.message : '文件解析失败。请确认格式。')
    }
    return {
      text: formatHeavyChainDisplay(parsed.rows, parsed.format),
      encoding: `${encoding}（本地解析）`,
      format: parsed.format,
      rows: parsed.rows,
      row_count: parsed.rows.length,
    }
  }
}

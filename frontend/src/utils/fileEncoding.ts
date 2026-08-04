export function stripBom(text: string) {
  return text.replace(/^\uFEFF/, '')
}

function textQualityScore(text: string) {
  if (!text || !text.trim()) return 0
  const len = Math.max(text.length, 1)
  const bad = (text.match(/\uFFFD/g) || []).length
  const printable = (text.match(/[\t\n\r\x20-\x7E\u4e00-\u9fff]/g) || []).length
  let score = printable / len - bad * 0.1
  if (text.includes(',') || text.includes('\t') || text.includes(';')) score += 0.08
  if (/^>/m.test(text)) score += 0.12
  const firstLine = text.split(/\r?\n/)[0] || ''
  if (/vhh|sequence|^id[,;\t]/i.test(firstLine)) score += 0.12
  const mojibake = (text.match(/[\u00C0-\u024F]{3,}/g) || []).length
  score -= mojibake * 0.03
  return score
}

export function decodeBytesAuto(bytes: Uint8Array) {
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return { text: stripBom(new TextDecoder('utf-8').decode(bytes.slice(3))), encoding: 'UTF-8' }
  }
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) {
    return { text: stripBom(new TextDecoder('utf-16le').decode(bytes.slice(2))), encoding: 'UTF-16 LE' }
  }
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) {
    return { text: stripBom(new TextDecoder('utf-16be').decode(bytes.slice(2))), encoding: 'UTF-16 BE' }
  }

  const candidates = [
    { encoding: 'UTF-8', text: stripBom(new TextDecoder('utf-8', { fatal: false }).decode(bytes)) },
  ]
  try {
    candidates.push({
      encoding: 'GB18030',
      text: stripBom(new TextDecoder('gb18030').decode(bytes)),
    })
  } catch {
    /* ignore */
  }

  return candidates.reduce((a, b) => (textQualityScore(b.text) > textQualityScore(a.text) ? b : a))
}

export async function readTextFileAutoEncoding(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer())
  return decodeBytesAuto(bytes)
}

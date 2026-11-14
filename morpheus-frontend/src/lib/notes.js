// Note-app integration that works in any browser on any device — no per-app APIs needed.
//  • Share sheet (navigator.share): Samsung Notes, Google Keep, Apple Notes, OneNote, Obsidian mobile…
//  • Obsidian URI (obsidian://new): Obsidian desktop + mobile
//  • Markdown / text download: Notepad, TextEdit, any editor, or drop into an Obsidian vault
//  • Clipboard: paste anywhere

const OBSIDIAN_KEY = 'morpheus-obsidian'

function list(value) {
  return Array.isArray(value) ? value.filter(Boolean) : []
}

function isoDate(value) {
  const date = value ? new Date(value) : new Date()
  return Number.isNaN(date.getTime()) ? new Date().toISOString().slice(0, 10) : date.toISOString().slice(0, 10)
}

function tag(value) {
  return String(value).trim().toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '')
}

export function dreamTitle(dream) {
  return (dream.title || 'Untitled Dream').trim()
}

export function noteFileName(dream, ext) {
  const safe = dreamTitle(dream).replace(/[\\/:*?"<>|#^[\]]+/g, '').trim() || 'Dream'
  return `${isoDate(dream.created_at)} ${safe}.${ext}`
}

/** Plain text — best for share sheets, Notepad and phone note apps. */
export function dreamToText(dream) {
  const parts = [dreamTitle(dream), isoDate(dream.created_at)]
  const text = dream.raw_text || dream.transcription
  if (text) parts.push('', 'Dream', text)
  if (dream.analysis) parts.push('', 'Interpretation', dream.analysis)
  const symbols = list(dream.symbols)
  const emotions = list(dream.emotions)
  if (symbols.length) parts.push('', `Symbols: ${symbols.join(', ')}`)
  if (emotions.length) parts.push(`Emotions: ${emotions.join(', ')}`)
  if (list(dream.sources).length) parts.push(`Sources: ${dream.sources.join('; ')}`)
  parts.push('', '— Morpheus')
  return parts.join('\n')
}

/** Markdown with YAML front matter — tags and dates become searchable in Obsidian. */
export function dreamToMarkdown(dream) {
  const symbols = list(dream.symbols)
  const emotions = list(dream.emotions)
  const tags = ['dream', ...symbols.map(tag), ...emotions.map((e) => `emotion/${tag(e)}`)].filter(Boolean)
  const front = [
    '---',
    `title: "${dreamTitle(dream).replace(/"/g, '\\"')}"`,
    `date: ${isoDate(dream.created_at)}`,
    `tags: [${[...new Set(tags)].join(', ')}]`,
    'source: Morpheus',
    '---',
  ]
  const body = [`# ${dreamTitle(dream)}`]
  const text = dream.raw_text || dream.transcription
  if (text) body.push('', '## Dream', '', text)
  if (dream.analysis) body.push('', '## Interpretation', '', dream.analysis)
  if (symbols.length) body.push('', `**Symbols:** ${symbols.join(', ')}`)
  if (emotions.length) body.push('', `**Emotions:** ${emotions.join(', ')}`)
  if (list(dream.sources).length) body.push('', `**Sources:** ${dream.sources.join('; ')}`)
  return `${front.join('\n')}\n\n${body.join('\n')}\n`
}

export function canShare() {
  return typeof navigator !== 'undefined' && typeof navigator.share === 'function'
}

export async function shareDream(dream) {
  await navigator.share({ title: dreamTitle(dream), text: dreamToText(dream) })
}

export function downloadDream(dream, format) {
  const isMd = format === 'md'
  const blob = new Blob([isMd ? dreamToMarkdown(dream) : dreamToText(dream)], {
    type: isMd ? 'text/markdown;charset=utf-8' : 'text/plain;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = noteFileName(dream, isMd ? 'md' : 'txt')
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function copyDream(dream) {
  await navigator.clipboard.writeText(dreamToText(dream))
}

export function loadObsidianSettings() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(OBSIDIAN_KEY) || '{}')
    return { vault: saved.vault || '', folder: saved.folder ?? 'Dreams' }
  } catch {
    return { vault: '', folder: 'Dreams' }
  }
}

export function saveObsidianSettings(settings) {
  try {
    window.localStorage.setItem(OBSIDIAN_KEY, JSON.stringify(settings))
  } catch {
    // storage unavailable — settings apply for this session only
  }
}

/** Opens Obsidian (desktop or mobile) and creates the note. Empty vault → last opened vault. */
export function openInObsidian(dream, { vault, folder }) {
  const name = noteFileName(dream, 'md').replace(/\.md$/, '')
  const path = folder ? `${folder.replace(/^\/+|\/+$/g, '')}/${name}` : name
  const params = new URLSearchParams({ file: path, content: dreamToMarkdown(dream) })
  if (vault) params.set('vault', vault)
  // URLSearchParams encodes spaces as "+", which Obsidian keeps literally.
  window.location.href = `obsidian://new?${params.toString().replace(/\+/g, '%20')}`
}

/** Reads a dream out of an exported note file (.txt / .md), dropping front matter and headings. */
export async function readNoteFile(file) {
  const raw = await file.text()
  return raw
    .replace(/^---[\s\S]*?\n---\s*/, '')
    .replace(/^#{1,6}\s+/gm, '')
    .trim()
}

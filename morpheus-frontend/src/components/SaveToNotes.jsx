import { useEffect, useRef, useState } from 'react'

import {
  canShare,
  copyDream,
  downloadDream,
  loadObsidianSettings,
  openInObsidian,
  saveObsidianSettings,
  shareDream,
} from '../lib/notes.js'

// "Save to notes" menu: share sheet, Obsidian, .md / .txt download, clipboard.
export default function SaveToNotes({ dream, align = 'left', tone = 'gold' }) {
  const [open, setOpen] = useState(false)
  const [obsidian, setObsidian] = useState(loadObsidianSettings)
  const [showObsidian, setShowObsidian] = useState(false)
  const [feedback, setFeedback] = useState('')
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    function onPointer(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    function onKey(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function flash(message) {
    setFeedback(message)
    window.setTimeout(() => setFeedback(''), 2200)
  }

  async function run(action) {
    try {
      await action()
      setOpen(false)
    } catch (error) {
      if (error?.name !== 'AbortError') flash('That did not work on this device.')
    }
  }

  const palette =
    tone === 'paper'
      ? { text: '#BDB9AE', accent: '#F2EDE1', border: '#352F28', bg: '#1F1E1A', hover: '#2C2A24' }
      : { text: '#E6DFA9', accent: '#FFDE6E', border: '#1f1f1f', bg: '#101010', hover: '#181818' }

  const item = {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: '2px',
    padding: '9px 12px',
    border: 'none',
    borderRadius: '8px',
    background: 'transparent',
    color: palette.accent,
    fontSize: '13px',
    textAlign: 'left',
    cursor: 'pointer',
  }
  const hint = { color: palette.text, opacity: 0.7, fontSize: '11px' }
  const field = {
    width: '100%',
    border: `1px solid ${palette.border}`,
    borderRadius: '6px',
    background: 'transparent',
    color: palette.accent,
    padding: '6px 8px',
    fontSize: '12px',
    outline: 'none',
  }

  return (
    <div ref={rootRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          border: `1px solid ${palette.border}`,
          borderRadius: '999px',
          background: palette.bg,
          color: palette.accent,
          padding: '7px 14px',
          fontSize: '13px',
          cursor: 'pointer',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
          <path d="M14 3v6h6M9 14h6M9 18h4" />
        </svg>
        Save to notes
      </button>

      {feedback ? (
        <span role="status" style={{ marginLeft: '10px', color: palette.text, fontSize: '12px' }}>
          {feedback}
        </span>
      ) : null}

      {open ? (
        <div
          role="menu"
          style={{
            position: 'absolute',
            zIndex: 20,
            bottom: 'calc(100% + 8px)',
            [align === 'right' ? 'right' : 'left']: 0,
            width: '264px',
            padding: '6px',
            border: `1px solid ${palette.border}`,
            borderRadius: '12px',
            background: palette.bg,
            boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
          }}
        >
          {canShare() ? (
            <button type="button" role="menuitem" style={item} onClick={() => run(() => shareDream(dream))}>
              Share to a notes app
              <span style={hint}>Samsung Notes, Keep, Apple Notes, OneNote…</span>
            </button>
          ) : null}

          <button
            type="button"
            role="menuitem"
            style={item}
            onClick={() => run(() => openInObsidian(dream, obsidian))}
          >
            Open in Obsidian
            <span style={hint}>
              {obsidian.vault ? `Vault “${obsidian.vault}”` : 'Last opened vault'}
              {obsidian.folder ? ` · ${obsidian.folder}/` : ''}
            </span>
          </button>
          <button
            type="button"
            style={{ ...item, padding: '2px 12px 8px', fontSize: '11px', color: palette.text }}
            onClick={() => setShowObsidian((s) => !s)}
          >
            {showObsidian ? 'Done' : 'Obsidian settings'}
          </button>
          {showObsidian ? (
            <div style={{ display: 'grid', gap: '6px', padding: '0 12px 10px' }}>
              <input
                style={field}
                placeholder="Vault name (optional)"
                value={obsidian.vault}
                onChange={(e) => {
                  const next = { ...obsidian, vault: e.target.value }
                  setObsidian(next)
                  saveObsidianSettings(next)
                }}
              />
              <input
                style={field}
                placeholder="Folder (e.g. Dreams)"
                value={obsidian.folder}
                onChange={(e) => {
                  const next = { ...obsidian, folder: e.target.value }
                  setObsidian(next)
                  saveObsidianSettings(next)
                }}
              />
            </div>
          ) : null}

          <div style={{ height: '1px', margin: '4px 8px', background: palette.border }} />

          <button type="button" role="menuitem" style={item} onClick={() => run(() => downloadDream(dream, 'md'))}>
            Download Markdown (.md)
            <span style={hint}>Obsidian, Notion, Bear, any vault</span>
          </button>
          <button type="button" role="menuitem" style={item} onClick={() => run(() => downloadDream(dream, 'txt'))}>
            Download text (.txt)
            <span style={hint}>Notepad, TextEdit, any editor</span>
          </button>
          <button
            type="button"
            role="menuitem"
            style={item}
            onClick={() =>
              run(async () => {
                await copyDream(dream)
                flash('Copied')
              })
            }
          >
            Copy to clipboard
            <span style={hint}>Paste into any app</span>
          </button>
        </div>
      ) : null}
    </div>
  )
}

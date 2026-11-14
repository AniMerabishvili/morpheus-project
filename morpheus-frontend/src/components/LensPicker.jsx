import { useEffect, useState } from 'react'

import { fetchLibrary, saveBooks } from '../lib/lenses.js'

const GOLD = '#FFDE6E'
const GOLD_PALE = '#E6DFA9'
const MUTED = '#9b9164'
const BORDER = '#1f1f1f'

// Choose any number of books from Morpheus's library to read the dream through.
// None selected → the whole library is used.
export default function LensPicker({ value, onChange, disabled }) {
  const [open, setOpen] = useState(false)
  const [books, setBooks] = useState([])
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let alive = true
    fetchLibrary()
      .then((library) => {
        if (!alive) return
        setBooks(library)
        // Drop saved ids for books no longer in the library.
        const valid = value.filter((id) => library.some((b) => b.id === id))
        if (valid.length !== value.length) {
          onChange(valid)
          saveBooks(valid)
        }
      })
      .catch(() => alive && setLoadError('Could not load the library.'))
    return () => {
      alive = false
    }
    // Only on mount: value/onChange are read once to prune stale ids.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function update(next) {
    onChange(next)
    saveBooks(next)
  }

  function toggle(id) {
    update(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])
  }

  const selected = books.filter((b) => value.includes(b.id))
  const allSelected = books.length > 0 && selected.length === books.length
  const summary =
    selected.length === 0 || allSelected
      ? `All ${books.length || ''} books`.replace('  ', ' ')
      : selected.length === 1
        ? selected[0].title
        : `${selected.length} books`

  return (
    <div style={{ width: '100%' }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        aria-expanded={open}
        style={styles.toggle}
      >
        <span style={{ color: MUTED }}>Read through</span>
        <span style={styles.summary}>{summary}</span>
        <span aria-hidden="true" style={{ ...styles.chevron, transform: open ? 'rotate(180deg)' : 'none' }}>
          ⌄
        </span>
      </button>

      {open ? (
        <div style={styles.panel}>
          <div style={styles.panelHead}>
            <span>Morpheus library</span>
            <span style={{ display: 'flex', gap: '12px' }}>
              <button type="button" style={styles.link} disabled={disabled || allSelected} onClick={() => update(books.map((b) => b.id))}>
                Select all
              </button>
              <button type="button" style={styles.link} disabled={disabled || !value.length} onClick={() => update([])}>
                Clear
              </button>
            </span>
          </div>

          {loadError ? <p style={styles.note}>{loadError}</p> : null}
          {!books.length && !loadError ? <p style={styles.note}>Loading books…</p> : null}

          <ul className="no-scrollbar" style={styles.list}>
            {books.map((book) => {
              const active = value.includes(book.id)
              return (
                <li key={book.id}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={active}
                    onClick={() => toggle(book.id)}
                    disabled={disabled}
                    style={{ ...styles.book, ...(active ? styles.bookActive : {}) }}
                  >
                    <span style={{ ...styles.check, ...(active ? styles.checkActive : {}) }} aria-hidden="true">
                      {active ? '✓' : ''}
                    </span>
                    <span style={{ minWidth: 0 }}>
                      <span style={styles.title}>{book.title}</span>
                      {book.author ? <span style={styles.author}>{book.author}</span> : null}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>

          <p style={styles.note}>
            Choose as many as you like. Passages are retrieved only from the books you pick; with none picked, the whole
            library is used.
          </p>
        </div>
      ) : null}
    </div>
  )
}

const styles = {
  toggle: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '9px 12px',
    border: `1px solid ${BORDER}`,
    borderRadius: '10px',
    background: '#101010',
    color: GOLD_PALE,
    fontSize: '13px',
    cursor: 'pointer',
    textAlign: 'left',
  },
  summary: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: GOLD },
  chevron: { color: MUTED, transition: 'transform 160ms ease', lineHeight: 1 },
  panel: {
    marginTop: '8px',
    padding: '10px',
    border: `1px solid ${BORDER}`,
    borderRadius: '10px',
    background: '#101010',
  },
  panelHead: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '2px 4px 8px',
    color: MUTED,
    fontSize: '11px',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  link: {
    border: 'none',
    background: 'none',
    padding: 0,
    color: GOLD,
    fontSize: '11px',
    letterSpacing: 'normal',
    textTransform: 'none',
    cursor: 'pointer',
  },
  list: {
    listStyle: 'none',
    margin: 0,
    padding: 0,
    display: 'grid',
    gap: '2px',
    maxHeight: '260px',
    overflowY: 'auto',
  },
  book: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px',
    border: '1px solid transparent',
    borderRadius: '8px',
    background: 'transparent',
    textAlign: 'left',
    cursor: 'pointer',
    transition: 'background 140ms ease, border-color 140ms ease',
  },
  bookActive: { background: 'rgba(255, 222, 110, 0.08)', borderColor: 'rgba(255, 222, 110, 0.22)' },
  check: {
    flexShrink: 0,
    width: '16px',
    height: '16px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: `1px solid #3a3626`,
    borderRadius: '4px',
    color: '#0f0f0f',
    fontSize: '11px',
    fontWeight: 700,
  },
  checkActive: { background: GOLD, borderColor: GOLD },
  title: { display: 'block', color: GOLD_PALE, fontSize: '13px', lineHeight: 1.3 },
  author: { display: 'block', color: MUTED, fontSize: '11px', marginTop: '2px' },
  note: { margin: '8px 4px 2px', color: MUTED, fontSize: '11px', lineHeight: 1.5 },
}

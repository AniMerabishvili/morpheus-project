import { useState } from 'react'

import { DreamCardPreview, DreamModalPreview } from '../components/Dashboard.jsx'

const analysis =
  'სიზმარი მიუთითებს, რომ სიბნელის პერიოდი შენთვის აუცილებელი ეტაპია. ვარსკვლავები შენი შინაგანი რესურსია, რომელიც მხოლოდ მაშინ ჩანს, როცა გარემო ჩუმდება. '.repeat(
    6,
  )

const dreams = Array.from({ length: 6 }).map((_, index) => ({
  id: String(index),
  title: 'ისარი გულში და უკანასკნელი დამშვიდობება',
  raw_text: 'ღამით ვიდექი მინდორში და ვარსკვლავებს ვუყურებდი.',
  analysis,
  created_at: '2026-10-05T03:00:00Z',
}))

export default function CardPreview() {
  const [selected, setSelected] = useState(null)

  return (
    <main className="min-h-screen bg-[#0f0f0f] p-4">
      <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {dreams.map((dream) => (
          <DreamCardPreview
            key={dream.id}
            dream={dream}
            onOpen={(letterRect) => setSelected({ dream, letterRect })}
            onDelete={async () => {}}
          />
        ))}
      </div>
      {selected ? (
        <DreamModalPreview
          dream={selected.dream}
          letterRect={selected.letterRect}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </main>
  )
}

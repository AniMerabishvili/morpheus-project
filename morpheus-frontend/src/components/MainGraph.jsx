import { useState } from 'react'

import DreamGraph from './DreamGraph.jsx'

function MainGraph({ onStatsChange, stats }) {
  const [isDreamPanelOpen, setIsDreamPanelOpen] = useState(false)
  const graphStats = stats || { nodes: 0, dreams: 0, symbols: 0, links: 0 }

  return (
    <main className="relative h-[100dvh] w-full overflow-hidden bg-[#0f0f0f] text-[#E6DFA9]">
      <div className="absolute inset-0">
        <DreamGraph
          onPanelOpenChange={setIsDreamPanelOpen}
          onStatsChange={onStatsChange}
        />
      </div>

      <div
        className={`absolute bottom-24 left-5 z-30 rounded-xl border border-[#1f1f1f] bg-[#0f0f0f]/85 p-4 backdrop-blur-md transition-opacity duration-200 md:bottom-5 ${
          isDreamPanelOpen ? 'opacity-0 md:opacity-100' : 'opacity-100'
        }`}
      >
        <p className="mb-4 text-xs font-bold text-[#8A7129]">
          {graphStats.nodes} nodes · {graphStats.dreams} dreams · {graphStats.symbols} symbols ·{' '}
          {graphStats.links} links
        </p>
        <p className="mb-3 text-sm font-black uppercase tracking-[0.18em] text-[#8A7129]">
          Legend
        </p>
        <div className="space-y-2 text-sm font-bold text-[#E6DFA9]">
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 rounded-full bg-[#FFDE6E]" />
            <span>Dream</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 rounded-full bg-[#8A7129]" />
            <span>Symbol</span>
          </div>
        </div>
      </div>
    </main>
  )
}

export default MainGraph

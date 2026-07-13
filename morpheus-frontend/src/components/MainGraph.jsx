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

      {/* Stats + legend panel */}
      <div
        className={`absolute bottom-20 left-3 right-24 z-30 rounded-lg border border-[#1f1f1f] bg-[#0f0f0f]/80 p-2 backdrop-blur-md transition-opacity duration-200 md:bottom-5 md:left-5 md:right-auto md:rounded-xl md:p-4 ${
          isDreamPanelOpen ? 'opacity-0 md:opacity-100' : 'opacity-100'
        }`}
      >
        <p className="mb-2 truncate text-[10px] font-bold leading-4 text-[#8A7129] md:mb-4 md:text-xs md:leading-5">
          {graphStats.nodes} nodes · {graphStats.dreams} dreams · {graphStats.symbols} symbols ·{' '}
          {graphStats.links} links
        </p>
        <p className="mb-2 hidden text-[10px] font-black uppercase tracking-[0.18em] text-[#8A7129] md:mb-3 md:block md:text-sm">
          Legend
        </p>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs font-bold text-[#E6DFA9] md:block md:space-y-2 md:text-sm">
          <div className="flex items-center gap-1.5 md:gap-3">
            <span className="h-2.5 w-2.5 rounded-full bg-[#FFDE6E] md:h-3 md:w-3" />
            <span>Dream</span>
          </div>
          <div className="flex items-center gap-1.5 md:gap-3">
            <span className="h-2.5 w-2.5 rounded-full bg-[#8A7129] md:h-3 md:w-3" />
            <span>Symbol</span>
          </div>
        </div>
      </div>
    </main>
  )
}

export default MainGraph

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

      {/* Stats + legend */}
      <div
        className={`absolute bottom-20 left-3 right-24 z-30 rounded-xl border border-[#1f1f1f] bg-[#121212]/85 px-3 py-2.5 backdrop-blur-md transition-opacity duration-200 md:bottom-5 md:left-5 md:right-auto md:px-4 md:py-3 ${
          isDreamPanelOpen ? 'opacity-0 md:opacity-100' : 'opacity-100'
        }`}
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-[#E6DFA9]/80 md:text-xs">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[#FFDE6E]" />
            Dreams <span className="tabular-nums text-[#8A7129]">{graphStats.dreams}</span>
          </span>
          {graphStats.view !== 'emotions' ? (
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[#8A7129]" />
              Symbols <span className="tabular-nums text-[#8A7129]">{graphStats.symbols}</span>
            </span>
          ) : null}
          {graphStats.view !== 'keywords' ? (
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[#95A5A6]" />
              Emotions <span className="tabular-nums text-[#8A7129]">{graphStats.emotions || 0}</span>
            </span>
          ) : null}
          <span className="hidden text-[#5f5a44] sm:inline">
            {graphStats.nodes} nodes · {graphStats.links} links
          </span>
        </div>
      </div>
    </main>
  )
}

export default MainGraph

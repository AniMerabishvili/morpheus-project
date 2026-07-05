import { useEffect, useMemo, useRef, useState } from 'react'

function getNodeId(value) {
  if (!value) {
    return ''
  }
  if (typeof value === 'string') {
    return value
  }
  return value.id || ''
}

function formatDate(value) {
  if (!value) {
    return 'Unknown date'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown date'
  }

  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date)
}

function DreamGraph({ onPanelOpenChange, onStatsChange }) {
  const containerRef = useRef(null)
  const [ForceGraph2D, setForceGraph2D] = useState(null)
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 })
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [dreamDetails, setDreamDetails] = useState({})
  const [selectedNode, setSelectedNode] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    let isMounted = true

    import('react-force-graph-2d').then((module) => {
      if (isMounted) {
        setForceGraph2D(() => module.default)
      }
    })

    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    const element = containerRef.current
    if (!element) {
      return undefined
    }

    function updateDimensions() {
      const rect = element.getBoundingClientRect()
      setDimensions({
        width: Math.max(320, Math.floor(rect.width)),
        height: Math.max(360, Math.floor(rect.height)),
      })
    }

    updateDimensions()
    const observer = new ResizeObserver(updateDimensions)
    observer.observe(element)

    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    async function fetchGraphData() {
      setIsLoading(true)
      setErrorMessage('')

      try {
        const [graphResponse, dreamsResponse] = await Promise.all([
          fetch('/v1/graph/data', { signal: controller.signal }),
          fetch('/v1/dreams', { signal: controller.signal }),
        ])

        const graphPayload = await graphResponse.json()
        const dreamsPayload = await dreamsResponse.json()

        if (!graphResponse.ok) {
          throw new Error(
            graphPayload?.detail || `Graph request failed with status ${graphResponse.status}`,
          )
        }
        if (!dreamsResponse.ok) {
          throw new Error(
            dreamsPayload?.detail || `Dream request failed with status ${dreamsResponse.status}`,
          )
        }

        const nodes = Array.isArray(graphPayload.nodes) ? graphPayload.nodes : []
        const links = Array.isArray(graphPayload.links) ? graphPayload.links : []
        const dreams = Array.isArray(dreamsPayload) ? dreamsPayload : []

        setGraphData({ nodes, links })
        setDreamDetails(
          dreams.reduce((details, dream) => {
            details[`dream-${dream.id}`] = dream
            return details
          }, {}),
        )
        onStatsChange?.({
          nodes: nodes.length,
          dreams: nodes.filter((node) => node.type === 'dream').length,
          symbols: nodes.filter((node) => node.type === 'keyword').length,
          links: links.length,
        })
      } catch (error) {
        if (error.name !== 'AbortError') {
          setErrorMessage(error.message || 'Could not load graph data.')
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    fetchGraphData()
    return () => controller.abort()
  }, [onStatsChange])

  const selectedDream = selectedNode ? dreamDetails[selectedNode.id] || selectedNode : null

  useEffect(() => {
    onPanelOpenChange?.(Boolean(selectedDream))
  }, [onPanelOpenChange, selectedDream])

  const selectedSymbols = useMemo(() => {
    if (!selectedNode) {
      return []
    }

    const keywordById = new Map(
      graphData.nodes
        .filter((node) => node.type === 'keyword')
        .map((node) => [node.id, node.label]),
    )

    return graphData.links
      .filter((link) => getNodeId(link.source) === selectedNode.id)
      .map((link) => keywordById.get(getNodeId(link.target)))
      .filter(Boolean)
  }, [graphData.links, graphData.nodes, selectedNode])

  return (
    <div ref={containerRef} className="relative h-full w-full bg-[#0f0f0f]">
      {isLoading ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0f0f0f]">
          <div
            className="h-12 w-12 animate-spin rounded-full border-2 border-[#1f1f1f] border-t-[#FFDE6E]"
            aria-label="Loading dream graph"
            role="status"
          />
        </div>
      ) : null}

      {errorMessage ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0f0f0f] px-6 text-center text-[#E6DFA9]">
          {errorMessage}
        </div>
      ) : null}

      {ForceGraph2D && dimensions.width > 0 && dimensions.height > 0 ? (
        <ForceGraph2D
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="#0f0f0f"
          nodeColor={(node) => node.color}
          nodeLabel={(node) => node.label}
          nodeVal={(node) => (node.type === 'dream' ? 9 : 5)}
          nodeRelSize={1}
          linkColor={() => '#1f1f1f'}
          linkWidth={1.4}
          cooldownTicks={90}
          onNodeClick={(node) => {
            if (node.type !== 'dream') {
              return
            }
            if (selectedNode && selectedNode.id === node.id) {
              setSelectedNode(null)
            } else {
              setSelectedNode(node)
            }
          }}
          onBackgroundClick={() => setSelectedNode(null)}
        />
      ) : null}

      <aside
        className={`absolute bottom-16 right-0 top-20 z-40 w-full max-w-md transform border-l border-[#1f1f1f] bg-[#141414] p-4 shadow-2xl transition-transform duration-300 sm:w-[420px] sm:p-6 md:bottom-0 ${
          selectedDream ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {selectedDream ? (
          <div className="flex h-full flex-col gap-5 overflow-y-auto">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-semibold leading-tight text-[#FFDE6E] sm:text-3xl">
                  {selectedDream.title || selectedNode.label || 'Untitled Dream'}
                </h2>
                <p className="mt-2 text-sm font-bold text-[#8A7129]">
                  {formatDate(selectedDream.created_at || selectedNode.created_at)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedNode(null)}
                className="rounded-lg px-3 py-1 text-3xl leading-none text-[#E6DFA9] transition hover:text-[#FFDE6E] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
                aria-label="Close dream panel"
              >
                ×
              </button>
            </div>

            <p className="whitespace-pre-wrap text-base leading-8 text-[#E6DFA9]">
              {selectedDream.analysis || 'No analysis available yet.'}
            </p>

            {selectedSymbols.length ? (
              <div>
                <p className="mb-3 font-bold text-[#FFDE6E]">Symbols</p>
                <div className="flex flex-wrap gap-2">
                  {selectedSymbols.map((symbol) => (
                    <span
                      key={symbol}
                      className="rounded-full bg-[#8A7129] px-3 py-1 text-sm font-bold text-[#E6DFA9]"
                    >
                      {symbol}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </aside>
    </div>
  )
}

export default DreamGraph

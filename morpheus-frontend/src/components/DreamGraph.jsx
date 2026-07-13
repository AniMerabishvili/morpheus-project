import { useEffect, useMemo, useRef, useState } from 'react'

import { apiFetch } from '../lib/api.js'

const DEFAULT_DREAM_COLOR = '#FFDE6E'
const DEFAULT_EMOTION_COLOR = '#95A5A6'

const VIEW_MODES = [
  { id: 'keywords', label: 'Keywords' },
  { id: 'emotions', label: 'Emotions' },
  { id: 'combined', label: 'Combined' },
]

function getNodeId(value) {
  if (!value) return ''
  if (typeof value === 'string') return value
  return value.id || ''
}

function formatDate(value) {
  if (!value) return 'Unknown date'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

function DreamGraph({ onPanelOpenChange, onStatsChange }) {
  const graphRef = useRef(null)
  const containerRef = useRef(null)
  const [ForceGraph2D, setForceGraph2D] = useState(null)
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 })
  const [viewMode, setViewMode] = useState('keywords')
  const [rawData, setRawData] = useState({
    nodes: [],
    keyword_links: [],
    emotion_links: [],
    emotion_colors: {},
  })
  const [dreamDetails, setDreamDetails] = useState({})
  const [selectedNode, setSelectedNode] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    let isMounted = true
    import('react-force-graph-2d').then((m) => {
      if (isMounted) setForceGraph2D(() => m.default)
    })
    return () => { isMounted = false }
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return undefined
    function update() {
      const r = el.getBoundingClientRect()
      setDimensions({
        width: Math.max(320, Math.floor(r.width)),
        height: Math.max(360, Math.floor(r.height)),
      })
    }
    update()
    const obs = new ResizeObserver(update)
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    async function fetchData() {
      setIsLoading(true)
      setErrorMessage('')
      try {
        const [graphRes, dreamsRes] = await Promise.all([
          apiFetch('/v1/graph/data', { signal: controller.signal }),
          apiFetch('/v1/dreams', { signal: controller.signal }),
        ])
        const graphPayload = await graphRes.json()
        const dreamsPayload = await dreamsRes.json()

        const nodes = Array.isArray(graphPayload.nodes) ? graphPayload.nodes : []
        setRawData({
          nodes,
          keyword_links: graphPayload.keyword_links || [],
          emotion_links: graphPayload.emotion_links || [],
          emotion_colors: graphPayload.emotion_colors || {},
        })

        const dreams = Array.isArray(dreamsPayload) ? dreamsPayload : []
        setDreamDetails(
          dreams.reduce((acc, d) => {
            acc[`dream-${d.id}`] = d
            return acc
          }, {}),
        )

        onStatsChange?.({
          nodes: nodes.length,
          dreams: nodes.filter((n) => n.type === 'dream').length,
          symbols: nodes.filter((n) => n.type === 'keyword').length,
          links: (graphPayload.keyword_links || []).length,
        })
      } catch (error) {
        if (error.name !== 'AbortError') {
          setErrorMessage(error.message || 'Could not load graph data.')
        }
      } finally {
        if (!controller.signal.aborted) setIsLoading(false)
      }
    }

    fetchData()
    return () => controller.abort()
  }, [onStatsChange])

  // Active graph switches nodes + links based on view mode.
  const graphData = useMemo(() => {
    const emotionCounts = new Map()
    const dreamDates = []
    ;(rawData.emotion_links || []).forEach((link) => {
      const targetId = getNodeId(link?.target)
      if (!targetId) return
      emotionCounts.set(targetId, (emotionCounts.get(targetId) || 0) + 1)
    })
    ;(rawData.nodes || []).forEach((node) => {
      if (node?.type !== 'dream' || !node.created_at) return
      const date = new Date(node.created_at)
      if (!Number.isNaN(date.getTime())) dreamDates.push(date)
    })

    const earliestDreamDate = dreamDates.length
      ? new Date(Math.min(...dreamDates.map((date) => date.getTime())))
      : null
    const accountAgeDays = earliestDreamDate
      ? Math.floor((Date.now() - earliestDreamDate.getTime()) / 86400000)
      : 0
    const maxEmotionCount = Math.max(...emotionCounts.values(), 0)

    const nodes = rawData.nodes.filter((n) => {
      if (!n?.id) return false
      if (n.type === 'dream') return true
      if (viewMode === 'keywords') return n.type === 'keyword'
      if (viewMode === 'emotions') return n.type === 'emotion'
      return n.type === 'keyword' || n.type === 'emotion'
    }).map((node) => {
      if (node.type === 'dream') {
        return {
          ...node,
          color: DEFAULT_DREAM_COLOR,
        }
      }

      if (node.type === 'emotion') {
        const emotionKey = String(node.label || node.id.replace(/^emotion-/, '')).trim().toLowerCase()
        const emotionColor = rawData.emotion_colors[emotionKey] || node.color || DEFAULT_EMOTION_COLOR
        const emotionDreamCount = emotionCounts.get(node.id) || 0
        return {
          ...node,
          color: emotionColor,
          dream_count: emotionDreamCount,
          cluster_dream_count: emotionDreamCount,
          is_dominant: Boolean(
            accountAgeDays >= 90
            && maxEmotionCount > 0
            && emotionDreamCount === maxEmotionCount
          ),
        }
      }

      return {
        ...node,
        color: node.color || '#8A7129',
      }
    })

    const nodeIds = new Set(nodes.map((node) => node.id))
    const sourceLinks = viewMode === 'keywords'
      ? rawData.keyword_links
      : viewMode === 'emotions'
        ? rawData.emotion_links
        : [...(rawData.keyword_links || []), ...(rawData.emotion_links || [])]
    const links = (sourceLinks || [])
      .map((link) => {
        const source = getNodeId(link?.source)
        const target = getNodeId(link?.target)
        if (!source || !target || !nodeIds.has(source) || !nodeIds.has(target)) {
          return null
        }
        return { ...link, source, target }
      })
      .filter(Boolean)

    return { nodes, links }
  }, [rawData, viewMode])

  useEffect(() => {
    if (!graphRef.current) return undefined
    const frame = window.requestAnimationFrame(() => {
      graphRef.current?.d3ReheatSimulation?.()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [graphData])

  const visibleNodeCount = graphData.nodes.length
  const visibleDreamCount = graphData.nodes.filter((n) => n.type === 'dream').length
  const visibleSymbolCount = graphData.nodes.filter((n) => n.type === 'keyword').length

  useEffect(() => {
    onStatsChange?.({
      nodes: visibleNodeCount,
      dreams: visibleDreamCount,
      symbols: visibleSymbolCount,
      links: graphData.links.length,
    })
  }, [graphData.links.length, onStatsChange, visibleDreamCount, visibleNodeCount, visibleSymbolCount])

  const activeSelectedNode = selectedNode
    ? graphData.nodes.find((node) => node.id === selectedNode.id) || selectedNode
    : null
  const selectedDream = activeSelectedNode
    ? dreamDetails[activeSelectedNode.id] || activeSelectedNode
    : null

  useEffect(() => {
    onPanelOpenChange?.(Boolean(selectedDream))
  }, [onPanelOpenChange, selectedDream])

  // Symbols connected to selected dream node (keyword mode)
  const selectedSymbols = useMemo(() => {
    if (!selectedNode) return []
    const kwMap = new Map(
      graphData.nodes
        .filter((n) => n?.type === 'keyword')
        .map((n) => [n.id, n.label]),
    )
    return graphData.links
      .filter((l) => l?.type === 'dream_keyword' && getNodeId(l.source) === selectedNode.id)
      .map((l) => kwMap.get(getNodeId(l.target)))
      .filter(Boolean)
  }, [graphData.links, graphData.nodes, selectedNode])

  // Legend: unique (emotion, color) pairs present in the current graph.
  const emotionLegend = useMemo(() => {
    const seen = new Map()
    if (viewMode === 'keywords') return []

    graphData.nodes.forEach((n) => {
      if (n?.type === 'emotion' && n.label) {
        seen.set(n.label, n.color || DEFAULT_EMOTION_COLOR)
      } else if (n?.type === 'dream' && n.dominant_emotion && n.color !== DEFAULT_DREAM_COLOR) {
        if (!seen.has(n.dominant_emotion)) seen.set(n.dominant_emotion, n.color)
      }
    })
    return [...seen.entries()]
  }, [graphData.nodes, viewMode])

  return (
    <div className="flex h-full w-full flex-col bg-[#0f0f0f]">
      <div className="shrink-0 px-5 pb-3 pt-20">
        <div className="flex items-center gap-5">
          {VIEW_MODES.map((mode) => (
            <button
              key={mode.id}
              type="button"
              onClick={() => setViewMode(mode.id)}
              className={`text-xs font-bold text-white transition-opacity ${
                viewMode === mode.id
                  ? 'opacity-100'
                  : 'opacity-40 hover:opacity-60'
              }`}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>

      <div ref={containerRef} className="relative min-h-0 flex-1 bg-[#0f0f0f]">
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

      {/* Emotion color legend */}
      {!isLoading && !errorMessage && emotionLegend.length > 0 ? (
        <div className="absolute left-4 right-4 top-2 z-20 flex gap-1.5 overflow-x-auto py-1 md:top-4 md:right-auto md:max-h-[min(42vh,22rem)] md:min-w-52 md:flex-col md:gap-1.5 md:overflow-x-hidden md:overflow-y-auto md:rounded-lg md:border md:border-[#1f1f1f] md:bg-[#141414]/90 md:p-3 md:backdrop-blur-md">
          <p className="hidden flex-shrink-0 px-1 text-[10px] font-black uppercase tracking-widest text-[#8A7129] md:mb-1 md:block md:px-0">
            Emotions
          </p>
          {emotionLegend.map(([label, color]) => (
            <div key={label} className="flex flex-shrink-0 items-center gap-1.5 rounded-full border border-[#1f1f1f] bg-[#141414]/80 px-2 py-1 backdrop-blur-md md:gap-2 md:rounded-none md:border-0 md:bg-transparent md:px-0 md:py-0 md:backdrop-blur-0">
              <span
                className="h-2 w-2 flex-shrink-0 rounded-full md:h-2.5 md:w-2.5"
                style={{ background: color }}
              />
              <span className="text-[10px] font-bold capitalize text-[#E6DFA9] md:text-xs">{label}</span>
            </div>
          ))}
        </div>
      ) : null}

      {ForceGraph2D && dimensions.width > 0 && dimensions.height > 0 ? (
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="#0f0f0f"
          nodeColor={(node) => node?.color || DEFAULT_DREAM_COLOR}
          nodeLabel={(node) => node?.label || ''}
          nodeVal={(node) => {
            if (node?.type === 'dream') return 9
            return 5 + Math.min(node?.cluster_dream_count || 0, 12) * 1.2
          }}
          nodeRelSize={1}
          nodeCanvasObject={(node, ctx, globalScale) => {
            if (typeof node?.x !== 'number' || typeof node?.y !== 'number') return
            const val =
              node.type === 'dream'
                ? 9
                : 5 + Math.min(node.cluster_dream_count || 0, 12) * 1.2
            const radius = Math.sqrt(val)
            ctx.save()
            ctx.beginPath()
            ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
            ctx.fillStyle = node.color || DEFAULT_DREAM_COLOR
            ctx.fill()
            const showLabel =
              (node.type === 'keyword' && node.is_dominant) ||
              (node.type === 'emotion' && node.is_dominant)
            if (showLabel) {
              const fontSize = Math.max(10, 13 / globalScale)
              ctx.font = `700 ${fontSize}px sans-serif`
              ctx.textAlign = 'center'
              ctx.textBaseline = 'top'
              ctx.fillStyle = '#FFDE6E'
              ctx.fillText(node.label || '', node.x, node.y + radius + 2)
            }
            ctx.restore()
          }}
          nodeCanvasObjectMode={(node) =>
            (
              (node?.type === 'keyword' && node.is_dominant)
              || (node?.type === 'emotion' && node.is_dominant)
            )
              ? 'replace'
              : 'before'
          }
          linkColor={() => '#1f1f1f'}
          linkWidth={1.4}
          cooldownTicks={90}
          onNodeClick={(node) => {
            if (node?.type !== 'dream') return
            setSelectedNode((prev) => (prev?.id === node.id ? null : node))
          }}
          onBackgroundClick={() => setSelectedNode(null)}
        />
      ) : null}

      {/* Side panel */}
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
                  {selectedDream.title || activeSelectedNode?.label || 'Untitled Dream'}
                </h2>
                <p className="mt-2 text-sm font-bold text-[#8A7129]">
                  {formatDate(selectedDream.created_at || activeSelectedNode?.created_at)}
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

            {/* Dominant emotion badge */}
            {activeSelectedNode?.dominant_emotion ? (
              <div className="flex items-center gap-2">
                <span
                  className="h-3 w-3 flex-shrink-0 rounded-full"
                  style={{ background: activeSelectedNode?.color || DEFAULT_DREAM_COLOR }}
                />
                <span className="text-sm font-bold capitalize text-[#E6DFA9]">
                  {activeSelectedNode?.dominant_emotion}
                </span>
              </div>
            ) : null}

            {selectedDream.raw_text ? (
              <div>
                <p className="mb-2 text-sm font-bold text-[#8A7129]">Your dream</p>
                <p className="whitespace-pre-wrap text-base leading-7 text-[#E6DFA9]">
                  {selectedDream.raw_text}
                </p>
              </div>
            ) : null}

            <div>
              <p className="mb-2 text-sm font-bold text-[#8A7129]">Analysis</p>
              <p className="whitespace-pre-wrap text-base leading-8 text-[#E6DFA9]">
                {selectedDream.analysis || 'No analysis available yet.'}
              </p>
            </div>

            {selectedSymbols.length ? (
              <div>
                <p className="mb-3 font-bold text-[#FFDE6E]">Symbols</p>
                <div className="flex flex-wrap gap-2">
                  {selectedSymbols.map((s) => (
                    <span
                      key={s}
                      className="rounded-full bg-[#8A7129] px-3 py-1 text-sm font-bold text-[#E6DFA9]"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {Array.isArray(selectedDream.emotions) && selectedDream.emotions.length > 0 ? (
              <div>
                <p className="mb-3 font-bold text-[#FFDE6E]">Emotions</p>
                <div className="flex flex-wrap gap-2">
                  {selectedDream.emotions.map((em) => {
                    const key = em.trim().toLowerCase()
                    const color = rawData.emotion_colors[key] || DEFAULT_EMOTION_COLOR
                    return (
                      <span
                        key={em}
                        className="rounded-full px-3 py-1 text-sm font-bold text-[#0f0f0f]"
                        style={{ background: color }}
                      >
                        {em}
                      </span>
                    )
                  })}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </aside>
      </div>
    </div>
  )
}

export default DreamGraph

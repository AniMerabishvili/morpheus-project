import { useEffect, useRef } from 'react'

// Fibrous "agentic" sphere: glowing hubs on an uneven shell, joined by bundles of
// faint silky strands. Idle → slow drift. Active → it writhes and reacts to mic level.
const HUB_COUNT = 46
const LINKS_PER_HUB = 3
const STRANDS_PER_LINK = 9
const INNER_FIBERS = 90
const STRAYS = 10

const rand = (min, max) => min + Math.random() * (max - min)

function buildShape() {
  const hubs = []
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < HUB_COUNT; i += 1) {
    const y = 1 - ((i + 0.5) / HUB_COUNT) * 2
    const ring = Math.sqrt(1 - y * y)
    const theta = golden * i + rand(-0.3, 0.3)
    hubs.push({
      x: Math.cos(theta) * ring,
      y: y + rand(-0.06, 0.06),
      z: Math.sin(theta) * ring,
      r: rand(0.88, 1.08), // uneven silhouette
      phase: rand(0, Math.PI * 2),
      size: Math.random() < 0.3 ? rand(1.4, 2.2) : rand(0.7, 1.3),
    })
  }

  const links = []
  const seen = new Set()
  hubs.forEach((hub, i) => {
    hubs
      .map((other, j) => ({ j, d: (hub.x - other.x) ** 2 + (hub.y - other.y) ** 2 + (hub.z - other.z) ** 2 }))
      .filter(({ j }) => j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, LINKS_PER_HUB)
      .forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`
        if (seen.has(key)) return
        seen.add(key)
        links.push({
          a: i,
          b: j,
          strands: Array.from({ length: STRANDS_PER_LINK }, () => ({
            o1: [rand(-1, 1), rand(-1, 1), rand(-1, 1)],
            o2: [rand(-1, 1), rand(-1, 1), rand(-1, 1)],
            phase: rand(0, Math.PI * 2),
            alpha: rand(0.25, 1),
          })),
        })
      })
  })

  // Faint fibers that sag through the interior, giving depth to the core.
  const inner = Array.from({ length: INNER_FIBERS }, () => ({
    a: Math.floor(Math.random() * HUB_COUNT),
    b: Math.floor(Math.random() * HUB_COUNT),
    sag: rand(0.25, 0.7),
    o: [rand(-1, 1), rand(-1, 1), rand(-1, 1)],
    phase: rand(0, Math.PI * 2),
  })).filter((f) => f.a !== f.b)

  const strays = Array.from({ length: STRAYS }, () => ({
    hub: Math.floor(Math.random() * HUB_COUNT),
    reach: rand(0.25, 0.6),
    curl: rand(-1, 1),
    phase: rand(0, Math.PI * 2),
  }))

  return { hubs, links, inner, strays }
}

export default function AgenticOrb({ analyserRef, active = false, size = 220 }) {
  const canvasRef = useRef(null)
  const activeRef = useRef(active)

  useEffect(() => {
    activeRef.current = active
  }, [active])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined
    const ctx = canvas.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = size * dpr
    canvas.height = size * dpr
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

    const { hubs, links, inner, strays } = buildShape()
    const world = hubs.map(() => [0, 0, 0])
    let data = null
    let level = 0
    let energy = 0
    let rotY = rand(0, Math.PI * 2)
    let t = 0
    let last = performance.now()
    let frameId = 0

    function readLevel() {
      const analyser = analyserRef?.current
      if (!analyser) return 0
      if (!data || data.length !== analyser.frequencyBinCount) data = new Uint8Array(analyser.frequencyBinCount)
      analyser.getByteFrequencyData(data)
      let sum = 0
      for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i]
      return Math.min(1, Math.sqrt(sum / data.length) / 100)
    }

    function frame(now) {
      const dt = Math.min(0.05, (now - last) / 1000) * (reduceMotion ? 0.3 : 1)
      last = now
      t += dt

      const isActive = activeRef.current
      level += ((isActive ? readLevel() : 0) - level) * 0.2
      energy += ((isActive ? 0.45 + level * 1.3 : 0.08) - energy) * 0.05
      rotY += dt * (0.1 + energy * 0.55)
      const tiltX = 0.3 + Math.sin(t * 0.3) * 0.12
      const cY = Math.cos(rotY)
      const sY = Math.sin(rotY)
      const cX = Math.cos(tiltX)
      const sX = Math.sin(tiltX)
      const half = size / 2
      const R = size * 0.34 * (1 + level * 0.1)
      const focal = 3

      // 3D point (unit space) → screen [x, y, depth 0..1]
      function project(x, y, z) {
        const x1 = x * cY - z * sY
        const z1 = x * sY + z * cY
        const y1 = y * cX - z1 * sX
        const z2 = y * sX + z1 * cX
        const s = focal / (focal + z2)
        return [half + x1 * R * s, half + y1 * R * s, (1.3 - z2) / 2.6]
      }

      hubs.forEach((h, i) => {
        const breathe = h.r * (1 + Math.sin(t * (0.8 + energy * 2.4) + h.phase) * (0.03 + energy * 0.09))
        world[i][0] = h.x * breathe
        world[i][1] = h.y * breathe
        world[i][2] = h.z * breathe
      })

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, size, size)
      ctx.globalCompositeOperation = 'lighter'
      ctx.lineCap = 'round'

      const faint = new Path2D()
      const mid = new Path2D()
      const bright = new Path2D()
      const sway = 0.08 + energy * 0.22

      function curve(path, A, B, o1, o2, spread, phase) {
        const dx = B[0] - A[0]
        const dy = B[1] - A[1]
        const dz = B[2] - A[2]
        const len = Math.hypot(dx, dy, dz)
        const k = spread * len
        const w = Math.sin(t * (0.9 + energy * 2) + phase)
        // Control points bulge slightly outward so bundles hug the shell.
        const c1 = [A[0] + dx / 3 + o1[0] * k * w, A[1] + dy / 3 + o1[1] * k * w, A[2] + dz / 3 + o1[2] * k * w]
        const c2 = [A[0] + (dx * 2) / 3 + o2[0] * k, A[1] + (dy * 2) / 3 + o2[1] * k, A[2] + (dz * 2) / 3 + o2[2] * k]
        const pa = project(...A)
        const p1 = project(...c1.map((v) => v * 1.06))
        const p2 = project(...c2.map((v) => v * 1.06))
        const pb = project(...B)
        path.moveTo(pa[0], pa[1])
        path.bezierCurveTo(p1[0], p1[1], p2[0], p2[1], pb[0], pb[1])
        return (pa[2] + pb[2]) / 2
      }

      for (const link of links) {
        const A = world[link.a]
        const B = world[link.b]
        for (const s of link.strands) {
          const target = s.alpha > 0.8 ? bright : s.alpha > 0.5 ? mid : faint
          curve(target, A, B, s.o1, s.o2, 0.18 + sway, s.phase)
        }
      }

      for (const f of inner) {
        const A = world[f.a]
        const B = world[f.b]
        const sagged = A.map((v, i) => ((v + B[i]) / 2) * (1 - f.sag))
        curve(faint, A, sagged, f.o, f.o, 0.3 + sway, f.phase)
        curve(faint, sagged, B, f.o, f.o, 0.3 + sway, f.phase + 1)
      }

      for (const s of strays) {
        const A = world[s.hub]
        const reach = 1 + s.reach * (0.6 + energy * 1.2)
        const B = [A[0] * reach + s.curl * 0.15 * Math.sin(t + s.phase), A[1] * reach, A[2] * reach]
        curve(mid, A, B, [s.curl, -s.curl, s.curl], [-s.curl, s.curl, 0], 0.5, s.phase)
      }

      ctx.lineWidth = 0.45
      ctx.strokeStyle = 'rgba(242, 238, 224, 0.07)'
      ctx.stroke(faint)
      ctx.lineWidth = 0.55
      ctx.strokeStyle = 'rgba(242, 238, 224, 0.16)'
      ctx.stroke(mid)
      ctx.lineWidth = 0.7
      ctx.strokeStyle = 'rgba(250, 247, 236, 0.3)'
      ctx.stroke(bright)

      // Glowing hubs.
      ctx.shadowColor = 'rgba(255, 252, 240, 0.9)'
      hubs.forEach((h, i) => {
        const [x, y, depth] = project(...world[i])
        const radius = h.size * (0.55 + depth * 0.6) * (1 + level * 0.5)
        ctx.shadowBlur = 6 * depth
        ctx.fillStyle = `rgba(255, 252, 240, ${0.35 + depth * 0.6})`
        ctx.beginPath()
        ctx.arc(x, y, radius, 0, Math.PI * 2)
        ctx.fill()
      })
      ctx.shadowBlur = 0
      ctx.globalCompositeOperation = 'source-over'

      frameId = requestAnimationFrame(frame)
    }

    frameId = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(frameId)
  }, [analyserRef, size])

  return <canvas ref={canvasRef} aria-hidden="true" style={{ width: size, height: size, display: 'block' }} />
}

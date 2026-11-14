import { useId } from 'react'

// Morpheus mark: a square that is crisp above a diagonal cut and dissolves into
// blur below it, like waking thought sliding into a dream.
const CUT_LEFT = 14.6 // y where the cut meets the left side (24-unit box)
const CUT_RIGHT = 9.4 // y where the cut meets the right side

export function LogoMark({ size = 22, color = '#FFDE6E' }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ overflow: 'visible' }}>
      <defs>
        <clipPath id={`${id}-top`}>
          <polygon points={`-4,-4 28,-4 28,${CUT_RIGHT} -4,${CUT_LEFT}`} />
        </clipPath>
        <clipPath id={`${id}-bottom`}>
          <polygon points={`-4,${CUT_LEFT} 28,${CUT_RIGHT} 28,30 -4,30`} />
        </clipPath>
        <filter id={`${id}-blur`} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="1.15" />
        </filter>
      </defs>
      <g clipPath={`url(#${id}-bottom)`}>
        <rect x="5.4" y="5.6" width="13.2" height="13.6" rx="0.6" fill={color} opacity="0.92" filter={`url(#${id}-blur)`} />
      </g>
      <g clipPath={`url(#${id}-top)`}>
        <rect x="5" y="5" width="14" height="14" fill={color} />
      </g>
      <line x1="2.2" y1={CUT_LEFT + 0.5} x2="21.8" y2={CUT_RIGHT - 0.5} stroke={color} strokeWidth="0.35" opacity="0.35" />
    </svg>
  )
}

export default function Logo({ size = 22, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark size={size} />
      <span className="text-[15px] font-semibold tracking-[-0.01em] text-[#FFDE6E]">Morpheus</span>
    </span>
  )
}

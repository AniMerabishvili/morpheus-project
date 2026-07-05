import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const GOLD = '#FFDE6E'
const GOLD_PALE = '#E6DFA9'
const GOLD_SHADOW = '#8A7129'
const BG = '#0f0f0f'
const SURFACE = '#141414'
const BORDER = '#1f1f1f'
const MUTED = '#9b9164'
const BAR_COUNT = 28

const initialBars = Array.from({ length: BAR_COUNT }, () => 8)

function formatTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function getRecorderOptions() {
  if (!window.MediaRecorder) {
    return { options: undefined, extension: 'webm' }
  }

  if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
    return {
      options: { mimeType: 'audio/webm;codecs=opus' },
      extension: 'webm',
    }
  }

  if (MediaRecorder.isTypeSupported('audio/webm')) {
    return {
      options: { mimeType: 'audio/webm' },
      extension: 'webm',
    }
  }

  if (MediaRecorder.isTypeSupported('audio/mp4')) {
    return {
      options: { mimeType: 'audio/mp4' },
      extension: 'mp4',
    }
  }

  return { options: undefined, extension: 'webm' }
}

function VoiceRecorder({ onDreamRecorded, onClose }) {
  const navigate = useNavigate()
  const [mode, setMode] = useState('voice')
  const [status, setStatus] = useState('idle')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [audioBlob, setAudioBlob] = useState(null)
  const [audioUrl, setAudioUrl] = useState('')
  const [dreamText, setDreamText] = useState('')
  const [result, setResult] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [bars, setBars] = useState(initialBars)

  const mediaRecorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const animationRef = useRef(null)
  const extensionRef = useRef('webm')
  const discardRecordingRef = useRef(false)

  const isRecording = status === 'recording'
  const isUploading = status === 'uploading'
  const canSubmitText = dreamText.trim().length >= 20 && !isUploading

  useEffect(() => {
    if (!isRecording) {
      return undefined
    }

    const intervalId = window.setInterval(() => {
      setElapsedSeconds((seconds) => seconds + 1)
    }, 1000)

    return () => window.clearInterval(intervalId)
  }, [isRecording])

  useEffect(() => {
    return () => {
      stopMediaTracks()
      stopWaveform()
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl)
      }
    }
  }, [audioUrl])

  function resetComponent(nextMode = mode) {
    discardRecordingRef.current = true
    stopRecordingIfActive()
    stopMediaTracks()
    stopWaveform()
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl)
    }
    chunksRef.current = []
    mediaRecorderRef.current = null
    setMode(nextMode)
    setStatus('idle')
    setElapsedSeconds(0)
    setAudioBlob(null)
    setAudioUrl('')
    setDreamText('')
    setResult(null)
    setErrorMessage('')
    setBars(initialBars)
  }

  function switchMode(nextMode) {
    if (nextMode === mode) {
      return
    }
    resetComponent(nextMode)
  }

  function stopRecordingIfActive() {
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state === 'recording') {
      recorder.stop()
    }
  }

  function stopMediaTracks() {
    if (!streamRef.current) {
      return
    }
    streamRef.current.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  function stopWaveform() {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current)
      animationRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
    }
    analyserRef.current = null
  }

  function startWaveform(stream) {
    const AudioContext = window.AudioContext || window.webkitAudioContext
    if (!AudioContext) {
      return
    }

    const audioContext = new AudioContext()
    const analyser = audioContext.createAnalyser()
    analyser.fftSize = 256
    const source = audioContext.createMediaStreamSource(stream)
    source.connect(analyser)

    audioContextRef.current = audioContext
    analyserRef.current = analyser

    const data = new Uint8Array(analyser.frequencyBinCount)

    function draw() {
      analyser.getByteFrequencyData(data)
      const step = Math.max(1, Math.floor(data.length / BAR_COUNT))
      const nextBars = Array.from({ length: BAR_COUNT }, (_, index) => {
        const value = data[index * step] || 0
        return Math.max(8, Math.round((value / 255) * 72))
      })
      setBars(nextBars)
      animationRef.current = requestAnimationFrame(draw)
    }

    draw()
  }

  async function startRecording() {
    setErrorMessage('')
    setResult(null)

    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus('error')
      setErrorMessage('Microphone recording is not supported in this browser.')
      return
    }

    if (!window.MediaRecorder) {
      setStatus('error')
      setErrorMessage('MediaRecorder is not supported in this browser.')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const { options, extension } = getRecorderOptions()
      const recorder = new MediaRecorder(stream, options)

      streamRef.current = stream
      mediaRecorderRef.current = recorder
      chunksRef.current = []
      extensionRef.current = extension

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }

      recorder.onstop = () => {
        if (discardRecordingRef.current) {
          discardRecordingRef.current = false
          chunksRef.current = []
          return
        }

        const type = options?.mimeType || 'audio/webm'
        const blob = new Blob(chunksRef.current, { type })
        if (!blob.size) {
          setStatus('error')
          setErrorMessage('No audio was captured. Please try recording again.')
          return
        }

        const previewUrl = URL.createObjectURL(blob)
        setAudioBlob(blob)
        setAudioUrl((previousUrl) => {
          if (previousUrl) {
            URL.revokeObjectURL(previousUrl)
          }
          return previewUrl
        })
        setStatus('recorded')
      }

      recorder.start()
      discardRecordingRef.current = false
      setElapsedSeconds(0)
      setBars(initialBars)
      setStatus('recording')
      startWaveform(stream)
    } catch (error) {
      setStatus('error')
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        setErrorMessage('Microphone permission was denied. You can switch to Text mode instead.')
      } else {
        setErrorMessage('Could not access the microphone. Please check your browser settings.')
      }
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state === 'recording') {
      recorder.stop()
    }
    stopMediaTracks()
    stopWaveform()
  }

  async function submitVoice() {
    if (!audioBlob) {
      return
    }

    setStatus('uploading')
    setErrorMessage('')

    const formData = new FormData()
    formData.append('audio', audioBlob, `dream.${extensionRef.current}`)

    try {
      const response = await fetch('/v1/dreams/process', {
        method: 'POST',
        body: formData,
      })
      const data = await parseResponse(response)
      setResult(data)
      setStatus('done')
      onDreamRecorded?.(data)
    } catch (error) {
      setStatus('error')
      setErrorMessage(error.message || 'Could not analyse the recording.')
    }
  }

  async function submitText() {
    if (!canSubmitText) {
      return
    }

    setStatus('uploading')
    setErrorMessage('')

    try {
      const response = await fetch('/v1/dreams/process-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dream_text: dreamText.trim() }),
      })
      const data = await parseResponse(response)
      setResult(data)
      setStatus('done')
      onDreamRecorded?.(data)
    } catch (error) {
      setStatus('error')
      setErrorMessage(error.message || 'Could not analyse the dream text.')
    }
  }

  async function parseResponse(response) {
    let payload = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }

    if (!response.ok) {
      const detail = payload?.detail || `Request failed with status ${response.status}`
      throw new Error(detail)
    }

    return payload
  }

  return (
    <section style={styles.card}>
      <div style={styles.header}>
        <p style={styles.eyebrow}>Morpheus</p>
        <h1 style={styles.title}>Share your dream</h1>
      </div>

      <div style={styles.modeToggle} aria-label="Dream input mode">
        <button
          type="button"
          onClick={() => switchMode('voice')}
          style={{
            ...styles.modeButton,
            ...(mode === 'voice' ? styles.modeButtonActive : {}),
          }}
        >
          Voice
        </button>
        <button
          type="button"
          onClick={() => switchMode('text')}
          style={{
            ...styles.modeButton,
            ...(mode === 'text' ? styles.modeButtonActive : {}),
          }}
        >
          Text
        </button>
      </div>
      {mode === 'voice' ? (
        <VoiceMode
          status={status}
          elapsedSeconds={elapsedSeconds}
          bars={bars}
          audioUrl={audioUrl}
          onStart={startRecording}
          onStop={stopRecording}
          onSubmit={submitVoice}
          onReset={() => resetComponent('voice')}
        />
      ) : (
        <TextMode
          value={dreamText}
          status={status}
          canSubmit={canSubmitText}
          onChange={setDreamText}
          onSubmit={submitText}
        />
      )}

      {isUploading ? <p style={styles.loading}>Analysing your dream...</p> : null}

      {errorMessage ? <p style={styles.error}>{errorMessage}</p> : null}

      {result ? (
        <ResultsCard
          result={result}
          onViewGraph={() => {
            onClose?.()
            navigate('/graph')
          }}
        />
      ) : null}
    </section>
  )
}

function VoiceMode({
  status,
  elapsedSeconds,
  bars,
  audioUrl,
  onStart,
  onStop,
  onSubmit,
  onReset,
}) {
  const isRecording = status === 'recording'
  const isRecorded = status === 'recorded' || status === 'done'
  const isUploading = status === 'uploading'

  return (
    <div style={styles.modePanel}>
      <button
        type="button"
        onClick={isRecording ? onStop : onStart}
        disabled={isUploading}
        aria-label={isRecording ? 'Stop recording' : 'Start recording'}
        style={{
          ...styles.recordButton,
          ...(isRecording ? styles.recordButtonActive : {}),
        }}
      >
        {isRecording ? 'Stop' : 'Record'}
      </button>

      <p style={styles.timer}>{formatTime(elapsedSeconds)}</p>

      <div style={styles.waveform} aria-hidden="true">
        {bars.map((height, index) => (
          <span
            key={index}
            style={{
              ...styles.waveBar,
              height: `${height}px`,
              opacity: isRecording ? 1 : 0.45,
            }}
          />
        ))}
      </div>

      {audioUrl ? (
        <audio controls src={audioUrl} style={styles.audioPreview}>
          <track kind="captions" />
        </audio>
      ) : null}

      {isRecorded ? (
        <div style={styles.actionRow}>
          <button
            type="button"
            onClick={onSubmit}
            disabled={isUploading}
            style={styles.primaryButton}
          >
            Analyse Dream
          </button>
          <button type="button" onClick={onReset} style={styles.secondaryButton}>
            Re-record
          </button>
        </div>
      ) : null}
    </div>
  )
}

function TextMode({ value, status, canSubmit, onChange, onSubmit }) {
  const isUploading = status === 'uploading'

  return (
    <div style={styles.modePanel}>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Describe your dream... / აღწერეთ თქვენი სიზმარი..."
        disabled={isUploading}
        rows={8}
        style={styles.textarea}
      />
      <div style={styles.textMeta}>
        <span>{value.trim().length} characters</span>
        <span>Minimum 20 characters</span>
      </div>
      <button
        type="button"
        onClick={onSubmit}
        disabled={!canSubmit}
        style={{
          ...styles.primaryButton,
          ...(!canSubmit ? styles.buttonDisabled : {}),
        }}
      >
        Analyse Dream
      </button>
    </div>
  )
}

function ResultsCard({ result, onViewGraph }) {
  const symbols = Array.isArray(result.symbols) ? result.symbols : []
  const emotions = Array.isArray(result.emotions) ? result.emotions : []

  return (
    <section style={styles.resultCard}>
      <h2 style={styles.resultTitle}>{result.title || 'Untitled Dream'}</h2>
      <p style={styles.analysis}>{result.analysis}</p>

      <PillGroup label="Symbols" items={symbols} />
      <PillGroup label="Emotions" items={emotions} />

      <button
        type="button"
        onClick={onViewGraph}
        style={styles.graphButton}
      >
        View in Graph
      </button>
    </section>
  )
}

function PillGroup({ label, items }) {
  if (!items.length) {
    return null
  }

  return (
    <div style={styles.pillSection}>
      <p style={styles.pillLabel}>{label}</p>
      <div style={styles.pillWrap}>
        {items.map((item) => (
          <span key={`${label}-${item}`} style={styles.pill}>
            {item}
          </span>
        ))}
      </div>
    </div>
  )
}

const styles = {
  card: {
    width: 'min(760px, 100%)',
    border: `1px solid ${BORDER}`,
    borderRadius: '8px',
    background: SURFACE,
    padding: '24px',
    boxSizing: 'border-box',
  },
  header: {
    marginBottom: '24px',
    paddingRight: '56px',
  },
  eyebrow: {
    margin: '0 0 8px',
    color: GOLD_SHADOW,
    letterSpacing: '0.22em',
    textTransform: 'uppercase',
    fontSize: '12px',
    fontWeight: 900,
  },
  title: {
    margin: 0,
    color: GOLD_PALE,
    fontSize: 'clamp(32px, 7vw, 48px)',
    fontWeight: 600,
    lineHeight: 1,
  },
  modeToggle: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '8px',
    marginBottom: '24px',
  },
  modeButton: {
    border: `1px solid ${BORDER}`,
    borderRadius: '6px',
    background: '#101010',
    color: GOLD_PALE,
    padding: '12px 16px',
    cursor: 'pointer',
    fontWeight: 700,
  },
  modeButtonActive: {
    background: 'rgba(255, 222, 110, 0.16)',
    borderColor: GOLD,
    color: GOLD,
    boxShadow: `inset 0 -3px 0 ${GOLD}`,
  },
  modePanel: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '18px',
  },
  recordButton: {
    width: '168px',
    height: '168px',
    borderRadius: '999px',
    border: `1px solid ${BORDER}`,
    background: '#101010',
    color: GOLD_PALE,
    cursor: 'pointer',
    fontSize: '20px',
    fontWeight: 800,
    transition: 'box-shadow 180ms ease, transform 180ms ease, background 180ms ease',
  },
  recordButtonActive: {
    background: 'rgba(255, 222, 110, 0.18)',
    color: GOLD,
    boxShadow: `0 0 0 10px rgba(255, 222, 110, 0.08), 0 0 44px rgba(255, 222, 110, 0.34)`,
    transform: 'scale(1.02)',
  },
  timer: {
    margin: 0,
    color: GOLD,
    fontSize: '28px',
    fontVariantNumeric: 'tabular-nums',
  },
  waveform: {
    width: '100%',
    minHeight: '96px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '5px',
    padding: '16px',
    boxSizing: 'border-box',
    border: `1px solid ${BORDER}`,
    borderRadius: '8px',
    background: '#101010',
  },
  waveBar: {
    width: '7px',
    borderRadius: '999px',
    background: GOLD,
    transition: 'height 80ms linear',
  },
  audioPreview: {
    width: '100%',
  },
  actionRow: {
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  primaryButton: {
    border: `1px solid ${GOLD}`,
    borderRadius: '6px',
    background: GOLD,
    color: BG,
    padding: '12px 18px',
    cursor: 'pointer',
    fontWeight: 900,
  },
  secondaryButton: {
    border: `1px solid ${BORDER}`,
    borderRadius: '6px',
    background: '#101010',
    color: GOLD_PALE,
    padding: '12px 18px',
    cursor: 'pointer',
    fontWeight: 800,
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: 'not-allowed',
  },
  textarea: {
    width: '100%',
    boxSizing: 'border-box',
    resize: 'vertical',
    minHeight: '190px',
    border: `1px solid ${BORDER}`,
    borderRadius: '8px',
    background: '#101010',
    color: GOLD_PALE,
    padding: '16px',
    font: 'inherit',
    outlineColor: GOLD,
  },
  textMeta: {
    width: '100%',
    display: 'flex',
    justifyContent: 'space-between',
    gap: '12px',
    color: MUTED,
    fontSize: '14px',
  },
  loading: {
    margin: '22px 0 0',
    color: GOLD_PALE,
    textAlign: 'center',
    fontWeight: 700,
  },
  error: {
    margin: '22px 0 0',
    color: '#ffcf8a',
    textAlign: 'center',
  },
  resultCard: {
    marginTop: '24px',
    border: `1px solid ${BORDER}`,
    borderRadius: '8px',
    background: '#101010',
    padding: '20px',
    textAlign: 'left',
  },
  resultTitle: {
    margin: '0 0 12px',
    color: GOLD,
    fontSize: '28px',
  },
  analysis: {
    margin: 0,
    color: GOLD_PALE,
    lineHeight: 1.65,
    whiteSpace: 'pre-wrap',
  },
  pillSection: {
    marginTop: '18px',
  },
  pillLabel: {
    margin: '0 0 8px',
    color: GOLD,
    fontWeight: 800,
  },
  pillWrap: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
  },
  pill: {
    borderRadius: '999px',
    background: GOLD_SHADOW,
    color: GOLD_PALE,
    padding: '6px 10px',
    fontSize: '14px',
    fontWeight: 700,
  },
  graphButton: {
    marginTop: '20px',
    border: `1px solid ${GOLD}`,
    borderRadius: '6px',
    background: 'transparent',
    color: GOLD,
    padding: '10px 14px',
    cursor: 'pointer',
    fontWeight: 900,
  },
}

export default VoiceRecorder

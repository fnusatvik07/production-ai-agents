import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronLeft, ChevronRight, Play } from 'lucide-react'
import { projects } from '../data/projects'

const INTERVAL = 5000

const BG = {
  '#3b82f6': ['#0a1628', '#0f2444'],
  '#f97316': ['#1a0800', '#3d1200'],
  '#ef4444': ['#1a0000', '#3d0000'],
  '#a855f7': ['#0f0520', '#1e0a3f'],
  '#22c55e': ['#020e06', '#051a0c'],
  '#06b6d4': ['#001018', '#001d2a'],
  '#0ea5e9': ['#000d18', '#001628'],
  '#8b5cf6': ['#090320', '#160838'],
  '#f59e0b': ['#120800', '#281000'],
  '#ec4899': ['#140010', '#280020'],
}

export default function Hero() {
  const [idx, setIdx] = useState(0)
  const [progress, setProgress] = useState(0)
  const project = projects[idx]
  const [c1, c2] = BG[project.accent] || ['#0a0a1a', '#111111']

  const next = useCallback(() => {
    setIdx(i => (i + 1) % projects.length)
    setProgress(0)
  }, [])

  const prev = useCallback(() => {
    setIdx(i => (i - 1 + projects.length) % projects.length)
    setProgress(0)
  }, [])

  // Auto advance + progress bar
  useEffect(() => {
    setProgress(0)
    const start = Date.now()
    const tick = setInterval(() => {
      const elapsed = Date.now() - start
      setProgress(Math.min(100, (elapsed / INTERVAL) * 100))
    }, 50)
    const advance = setTimeout(next, INTERVAL)
    return () => { clearInterval(tick); clearTimeout(advance) }
  }, [idx, next])

  // Keyboard
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [next, prev])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100vh', minHeight: 600, overflow: 'hidden' }}>
      {/* Background */}
      <AnimatePresence mode="wait">
        <motion.div
          key={`bg-${idx}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.7 }}
          style={{
            position: 'absolute', inset: 0,
            background: `linear-gradient(145deg, ${c1} 0%, ${c2} 40%, #111111 100%)`,
          }}
        />
      </AnimatePresence>

      {/* Dot grid overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.12) 1px, transparent 1px)',
        backgroundSize: '36px 36px',
        opacity: 0.25,
      }} />

      {/* Accent radial glow */}
      <AnimatePresence mode="wait">
        <motion.div
          key={`glow-${idx}`}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.8 }}
          style={{
            position: 'absolute', top: '5%', right: '-5%',
            width: '50%', height: '90%',
            background: `radial-gradient(ellipse, ${project.accent}28 0%, transparent 65%)`,
            pointerEvents: 'none',
          }}
        />
      </AnimatePresence>

      {/* Large project number bg watermark */}
      <AnimatePresence mode="wait">
        <motion.div
          key={`num-${idx}`}
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -40 }}
          transition={{ duration: 0.6 }}
          style={{
            position: 'absolute', right: 60, bottom: 80,
            fontSize: 'clamp(160px, 22vw, 280px)',
            fontWeight: 900, color: 'rgba(255,255,255,0.03)',
            lineHeight: 1, userSelect: 'none', pointerEvents: 'none',
            letterSpacing: '-0.05em',
          }}
        >
          {project.id}
        </motion.div>
      </AnimatePresence>

      {/* Bottom fade */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0, height: 200,
        background: 'linear-gradient(to top, #111111 0%, transparent 100%)',
        pointerEvents: 'none',
      }} />

      {/* Left arrow */}
      <button
        onClick={prev}
        style={{
          position: 'absolute', left: 20, top: '50%', transform: 'translateY(-50%)',
          zIndex: 20, width: 44, height: 44, borderRadius: 12,
          border: '1px solid rgba(255,255,255,0.15)',
          background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(8px)',
          color: 'rgba(255,255,255,0.8)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'background 0.15s',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,0,0,0.75)'}
        onMouseLeave={e => e.currentTarget.style.background = 'rgba(0,0,0,0.5)'}
      >
        <ChevronLeft size={20} />
      </button>

      {/* Right arrow */}
      <button
        onClick={next}
        style={{
          position: 'absolute', right: 20, top: '50%', transform: 'translateY(-50%)',
          zIndex: 20, width: 44, height: 44, borderRadius: 12,
          border: '1px solid rgba(255,255,255,0.15)',
          background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(8px)',
          color: 'rgba(255,255,255,0.8)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'background 0.15s',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,0,0,0.75)'}
        onMouseLeave={e => e.currentTarget.style.background = 'rgba(0,0,0,0.5)'}
      >
        <ChevronRight size={20} />
      </button>

      {/* Main content */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 10,
        display: 'flex', alignItems: 'center',
        maxWidth: 1440, margin: '0 auto', padding: '80px 80px 120px',
        left: '50%', transform: 'translateX(-50%)', width: '100%',
      }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={`content-${idx}`}
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            style={{ maxWidth: 680 }}
          >
            {/* Category + number */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18 }}>
              <span style={{
                padding: '4px 12px', borderRadius: 6,
                background: `${project.accent}30`, border: `1px solid ${project.accent}55`,
                color: project.accent, fontSize: 11, fontWeight: 700,
                letterSpacing: '0.08em', textTransform: 'uppercase',
              }}>
                {project.category}
              </span>
              <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.35)', fontWeight: 600 }}>
                Project {idx + 1} of {projects.length}
              </span>
            </div>

            {/* Title */}
            <h1 style={{
              fontSize: 'clamp(36px, 5.5vw, 72px)', fontWeight: 900,
              color: '#ffffff', lineHeight: 1.04, letterSpacing: '-0.035em',
              margin: '0 0 14px',
            }}>
              {project.title}
            </h1>

            {/* Tagline */}
            <p style={{
              fontSize: 19, color: 'rgba(255,255,255,0.8)', fontWeight: 500,
              lineHeight: 1.5, margin: '0 0 10px', maxWidth: 560,
            }}>
              {project.tagline}
            </p>

            {/* Description */}
            <p style={{
              fontSize: 14, color: 'rgba(255,255,255,0.5)',
              lineHeight: 1.75, margin: '0 0 22px', maxWidth: 520,
            }}>
              {project.description}
            </p>

            {/* Tech pills */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 28 }}>
              {project.tech.slice(0, 5).map(t => (
                <span key={t} style={{
                  padding: '4px 13px', borderRadius: 20,
                  border: `1px solid ${project.accent}40`,
                  background: `${project.accent}16`,
                  color: 'rgba(255,255,255,0.7)', fontSize: 12, fontWeight: 600,
                }}>
                  {t}
                </span>
              ))}
            </div>

            {/* Buttons */}
            <div style={{ display: 'flex', gap: 12 }}>
              <Link to={`/project/${project.id}`} style={{ textDecoration: 'none' }}>
                <motion.button
                  whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '13px 26px', borderRadius: 10, border: 'none',
                    background: project.accent, color: '#fff',
                    fontSize: 15, fontWeight: 700, cursor: 'pointer',
                    boxShadow: `0 4px 20px ${project.accent}55`,
                  }}
                >
                  <Play size={15} fill="#fff" strokeWidth={0} />
                  Open Project
                </motion.button>
              </Link>
              <motion.button
                whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
                onClick={next}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '13px 22px', borderRadius: 10,
                  border: '1px solid rgba(255,255,255,0.2)',
                  background: 'rgba(255,255,255,0.08)', backdropFilter: 'blur(6px)',
                  color: '#fff', fontSize: 15, fontWeight: 600, cursor: 'pointer',
                }}
              >
                Next Project
                <ChevronRight size={15} />
              </motion.button>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Bottom controls: dots + progress */}
      <div style={{
        position: 'absolute', bottom: 28, left: 0, right: 0, zIndex: 20,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
      }}>
        {/* Dots */}
        <div style={{ display: 'flex', gap: 8 }}>
          {projects.map((p, i) => (
            <button
              key={p.id}
              onClick={() => { setIdx(i); setProgress(0) }}
              style={{
                width: i === idx ? 24 : 8, height: 8,
                borderRadius: 4, border: 'none', cursor: 'pointer',
                background: i === idx ? p.accent : 'rgba(255,255,255,0.25)',
                transition: 'all 0.3s ease',
                padding: 0,
              }}
            />
          ))}
        </div>

        {/* Progress bar */}
        <div style={{
          width: 200, height: 2, borderRadius: 1,
          background: 'rgba(255,255,255,0.12)', overflow: 'hidden',
        }}>
          <motion.div
            style={{
              height: '100%', borderRadius: 1,
              background: project.accent,
              width: `${progress}%`,
            }}
            transition={{ duration: 0.05 }}
          />
        </div>
      </div>
    </div>
  )
}

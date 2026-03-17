import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useState } from 'react'
import { ArrowRight, Network, GitPullRequest, AlertTriangle, Layers, TrendingUp, Database, Globe, GitBranch, GraduationCap, Target } from 'lucide-react'

const ICONS = {
  '01': Network, '02': GitPullRequest, '03': AlertTriangle, '04': Layers,
  '05': TrendingUp, '06': Database, '07': Globe, '08': GitBranch,
  '09': GraduationCap, '10': Target,
}

const CARD_BG = {
  '#3b82f6': 'linear-gradient(155deg, #0b1e3d 0%, #14306a 100%)',
  '#f97316': 'linear-gradient(155deg, #2a0e00 0%, #5c2000 100%)',
  '#ef4444': 'linear-gradient(155deg, #2a0000 0%, #5c0000 100%)',
  '#a855f7': 'linear-gradient(155deg, #170840 0%, #2e1270 100%)',
  '#22c55e': 'linear-gradient(155deg, #031209 0%, #0a2e14 100%)',
  '#06b6d4': 'linear-gradient(155deg, #001520 0%, #00293a 100%)',
  '#0ea5e9': 'linear-gradient(155deg, #001020 0%, #002040 100%)',
  '#8b5cf6': 'linear-gradient(155deg, #100630 0%, #220d60 100%)',
  '#f59e0b': 'linear-gradient(155deg, #1e0e00 0%, #3d1e00 100%)',
  '#ec4899': 'linear-gradient(155deg, #1e0018 0%, #3d0035 100%)',
}

export default function ProjectCard({ project }) {
  const [hovered, setHovered] = useState(false)
  const bg = CARD_BG[project.accent] || 'linear-gradient(155deg, #111 0%, #1a1a2e 100%)'
  const Icon = ICONS[project.id] || Layers

  return (
    <Link to={`/project/${project.id}`} style={{ textDecoration: 'none', flexShrink: 0 }}>
      <motion.div
        style={{
          position: 'relative', width: 300, height: 210,
          borderRadius: 14, overflow: 'hidden', cursor: 'pointer',
          background: bg,
          border: '1px solid rgba(255,255,255,0.07)',
        }}
        onHoverStart={() => setHovered(true)}
        onHoverEnd={() => setHovered(false)}
        whileHover={{ scale: 1.04, zIndex: 20 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        {/* Dot grid */}
        <div style={{
          position: 'absolute', inset: 0, opacity: 0.1,
          backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.6) 1px, transparent 1px)',
          backgroundSize: '22px 22px',
        }} />

        {/* Top-right accent glow */}
        <div style={{
          position: 'absolute', top: -30, right: -30,
          width: 120, height: 120,
          background: `radial-gradient(circle, ${project.accent}45 0%, transparent 70%)`,
          pointerEvents: 'none',
        }} />

        {/* Bottom gradient */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 90,
          background: 'linear-gradient(to top, rgba(0,0,0,0.9) 0%, transparent 100%)',
        }} />

        {/* Project number badge */}
        <div style={{
          position: 'absolute', top: 12, left: 12,
          padding: '3px 8px', borderRadius: 6,
          background: project.accent, color: '#fff',
          fontSize: 11, fontWeight: 800,
          boxShadow: `0 2px 8px ${project.accent}66`,
        }}>
          #{project.id}
        </div>

        {/* Center icon */}
        <div style={{
          position: 'absolute', top: '30%', left: '50%',
          transform: 'translate(-50%, -50%)',
        }}>
          <div style={{
            width: 64, height: 64, borderRadius: 18,
            background: `${project.accent}20`,
            border: `1.5px solid ${project.accent}40`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon size={28} color={project.accent} strokeWidth={1.5} />
          </div>
        </div>

        {/* Bottom: title + tech tags */}
        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '0 14px 14px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', lineHeight: 1.3, marginBottom: 7 }}>
            {project.title}
          </div>
          <div style={{ display: 'flex', gap: 5 }}>
            {project.tech.slice(0, 2).map(t => (
              <span key={t} style={{
                padding: '2px 8px', borderRadius: 10,
                background: 'rgba(255,255,255,0.1)',
                color: 'rgba(255,255,255,0.65)', fontSize: 10, fontWeight: 600,
              }}>{t}</span>
            ))}
          </div>
        </div>

        {/* Hover overlay */}
        <AnimatePresence>
          {hovered && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              style={{
                position: 'absolute', inset: 0,
                background: 'rgba(0,0,0,0.88)',
                backdropFilter: 'blur(4px)',
                display: 'flex', flexDirection: 'column',
                justifyContent: 'space-between', padding: 16,
              }}
            >
              {/* Icon + title */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <Icon size={18} color={project.accent} strokeWidth={2} />
                  <span style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>
                    {project.title}
                  </span>
                </div>
                <p style={{
                  fontSize: 12, color: 'rgba(255,255,255,0.65)',
                  lineHeight: 1.6, margin: 0,
                }}>
                  {project.tagline}
                </p>
              </div>
              {/* Bottom */}
              <div>
                <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 10 }}>
                  {project.tech.slice(0, 3).map(t => (
                    <span key={t} style={{
                      padding: '3px 8px', borderRadius: 10,
                      background: `${project.accent}22`,
                      border: `1px solid ${project.accent}44`,
                      color: project.accent, fontSize: 10, fontWeight: 600,
                    }}>{t}</span>
                  ))}
                </div>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  color: project.accent, fontSize: 13, fontWeight: 700,
                }}>
                  Explore <ArrowRight size={13} />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </Link>
  )
}

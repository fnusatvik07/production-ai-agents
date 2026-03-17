import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft, BookOpen, GitBranch, Code2, GraduationCap,
  Network, GitPullRequest, AlertTriangle, Layers, TrendingUp,
  Database, Globe, Target, CheckCircle2, Terminal, Lightbulb, Users, Zap,
} from 'lucide-react'
import { getProjectById, projects } from '../data/projects'
import MermaidDiagram from '../components/MermaidDiagram'
import CodeBlock from '../components/CodeBlock'
import ProjectCard from '../components/ProjectCard'

const ICONS = {
  '01': Network, '02': GitPullRequest, '03': AlertTriangle, '04': Layers,
  '05': TrendingUp, '06': Database, '07': Globe, '08': GitBranch,
  '09': GraduationCap, '10': Target,
}

const TABS = [
  { value: 'overview',      label: 'Overview',      Icon: BookOpen },
  { value: 'architecture',  label: 'Architecture',  Icon: GitBranch },
  { value: 'code',          label: 'Key Code',      Icon: Code2 },
  { value: 'tutorial',      label: 'Tutorial',      Icon: GraduationCap },
]

/* ── Shared style tokens ───────────────────────────────────────── */
const S = {
  card: {
    background: '#181818',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 16,
    padding: '32px 36px',
  },
  eyebrow: {
    display: 'block', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em',
    textTransform: 'uppercase', color: 'rgba(255,255,255,0.35)', marginBottom: 14,
  },
  h2: {
    fontSize: 26, fontWeight: 800, color: '#fff',
    letterSpacing: '-0.02em', margin: '0 0 14px', lineHeight: 1.2,
  },
  h3: {
    fontSize: 20, fontWeight: 700, color: '#fff',
    letterSpacing: '-0.01em', margin: '0 0 10px', lineHeight: 1.3,
  },
  body: {
    fontSize: 17, color: 'rgba(255,255,255,0.72)',
    lineHeight: 1.8, margin: 0,
  },
  small: {
    fontSize: 14, color: 'rgba(255,255,255,0.42)',
    lineHeight: 1.7, margin: 0,
  },
}

export default function ProjectDetail() {
  const { id } = useParams()
  const project = getProjectById(id)
  const [activeTab, setActiveTab] = useState('overview')

  useEffect(() => {
    setActiveTab('overview')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [id])

  if (!project) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#111111' }}>
        <div style={{ textAlign: 'center' }}>
          <p style={{ color: 'rgba(255,255,255,0.4)', marginBottom: 16 }}>Project not found</p>
          <Link to="/" style={{ textDecoration: 'none', color: '#3b82f6', fontSize: 14 }}>← Back to all projects</Link>
        </div>
      </div>
    )
  }

  const ProjectIcon = ICONS[project.id] || Layers
  const related = projects.filter(p => p.id !== project.id && p.category === project.category).slice(0, 3)
  const moreProjects = related.length < 3 ? [
    ...related,
    ...projects.filter(p => p.id !== project.id && p.category !== project.category).slice(0, 3 - related.length)
  ] : related

  return (
    <div style={{ minHeight: '100vh', background: '#111111' }}>

      {/* ── Hero ─────────────────────────────────────────────────── */}
      <div style={{
        position: 'relative', overflow: 'hidden',
        background: `linear-gradient(160deg, ${project.accent}20 0%, #111111 55%)`,
        paddingTop: 64,
      }}>
        <div style={{
          position: 'absolute', inset: 0, opacity: 0.06, pointerEvents: 'none',
          backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.7) 1px, transparent 1px)',
          backgroundSize: '32px 32px',
        }} />
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 100,
          background: 'linear-gradient(to top, #111111, transparent)', pointerEvents: 'none',
        }} />

        <div style={{ position: 'relative', zIndex: 10, maxWidth: 1100, margin: '0 auto', padding: '52px 32px 64px' }}>
          <motion.div initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.3 }} style={{ marginBottom: 32 }}>
            <Link to="/" style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 7 }}>
              <ArrowLeft size={15} color="rgba(255,255,255,0.4)" />
              <span style={{ fontSize: 14, color: 'rgba(255,255,255,0.4)', fontWeight: 500 }}>All Projects</span>
            </Link>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
            style={{ display: 'flex', gap: 56, alignItems: 'flex-start', flexWrap: 'wrap' }}
          >
            {/* Left */}
            <div style={{ flex: '1 1 480px', minWidth: 0 }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18 }}>
                <span style={{
                  padding: '5px 14px', borderRadius: 7,
                  background: `${project.accent}28`, border: `1px solid ${project.accent}50`,
                  color: project.accent, fontSize: 11, fontWeight: 700,
                  letterSpacing: '0.08em', textTransform: 'uppercase',
                }}>{project.category}</span>
                <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.3)', fontWeight: 500 }}>Project #{project.id}</span>
              </div>

              <h1 style={{
                fontSize: 'clamp(32px, 4.5vw, 56px)', fontWeight: 900, color: '#fff',
                lineHeight: 1.05, letterSpacing: '-0.035em', margin: '0 0 16px',
              }}>
                {project.title}
              </h1>

              <p style={{ fontSize: 20, color: 'rgba(255,255,255,0.8)', fontWeight: 500, lineHeight: 1.55, margin: '0 0 12px' }}>
                {project.tagline}
              </p>
              <p style={{ fontSize: 16, color: 'rgba(255,255,255,0.5)', lineHeight: 1.8, margin: '0 0 28px', maxWidth: 560 }}>
                {project.description}
              </p>

              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {project.tech.map(t => (
                  <span key={t} style={{
                    padding: '6px 14px', borderRadius: 20,
                    border: `1px solid ${project.accent}45`,
                    background: `${project.accent}18`,
                    color: 'rgba(255,255,255,0.8)', fontSize: 13, fontWeight: 600,
                  }}>{t}</span>
                ))}
              </div>
            </div>

            {/* Right: icon */}
            <div style={{ flex: '0 0 auto', paddingTop: 8 }}>
              <div style={{
                width: 160, height: 160, borderRadius: 32,
                background: `${project.accent}15`,
                border: `2px solid ${project.accent}30`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: `0 0 80px ${project.accent}25, inset 0 0 40px ${project.accent}10`,
              }}>
                <ProjectIcon size={72} color={project.accent} strokeWidth={1.1} />
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* ── Tab Bar ──────────────────────────────────────────────── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 50,
        background: 'rgba(17,17,17,0.97)', backdropFilter: 'blur(16px)',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
      }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', padding: '0 32px', display: 'flex' }}>
          {TABS.map(({ value, label, Icon }) => {
            const active = activeTab === value
            return (
              <button key={value} onClick={() => setActiveTab(value)} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '16px 20px',
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 14, fontWeight: active ? 700 : 500,
                color: active ? '#fff' : 'rgba(255,255,255,0.4)',
                borderBottom: active ? `2px solid ${project.accent}` : '2px solid transparent',
                transition: 'all 0.15s', whiteSpace: 'nowrap',
              }}
                onMouseEnter={e => { if (!active) e.currentTarget.style.color = 'rgba(255,255,255,0.7)' }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.color = 'rgba(255,255,255,0.4)' }}
              >
                <Icon size={15} />
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────── */}
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '48px 32px 100px' }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}
          >

            {/* ══ OVERVIEW ══════════════════════════════════════════ */}
            {activeTab === 'overview' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

                {/* Problem — full width callout */}
                <div style={{
                  ...S.card,
                  borderLeft: `4px solid ${project.accent}`,
                  background: `linear-gradient(135deg, ${project.accent}10 0%, #181818 100%)`,
                }}>
                  <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                    <div style={{
                      width: 44, height: 44, borderRadius: 12, flexShrink: 0, marginTop: 2,
                      background: `${project.accent}20`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Zap size={22} color={project.accent} strokeWidth={1.8} />
                    </div>
                    <div>
                      <span style={{ ...S.eyebrow, color: project.accent }}>The Problem</span>
                      <p style={{ ...S.body, fontSize: 18 }}>{project.overview?.problem}</p>
                    </div>
                  </div>
                </div>

                {/* Who + Why — two columns */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 20 }}>
                  <div style={S.card}>
                    <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                      <div style={{
                        width: 40, height: 40, borderRadius: 10, flexShrink: 0,
                        background: 'rgba(255,255,255,0.06)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <Users size={20} color="rgba(255,255,255,0.6)" strokeWidth={1.8} />
                      </div>
                      <div>
                        <span style={S.eyebrow}>Who Uses It</span>
                        <p style={S.body}>{project.overview?.whoUsesIt}</p>
                      </div>
                    </div>
                  </div>

                  <div style={S.card}>
                    <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                      <div style={{
                        width: 40, height: 40, borderRadius: 10, flexShrink: 0,
                        background: 'rgba(255,255,255,0.06)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <Lightbulb size={20} color="rgba(255,255,255,0.6)" strokeWidth={1.8} />
                      </div>
                      <div>
                        <span style={S.eyebrow}>Why It Matters</span>
                        <p style={S.body}>{project.overview?.whyItMatters}</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Tech stack — full width */}
                <div style={S.card}>
                  <span style={S.eyebrow}>Tech Stack</span>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    {project.tech.map((t, i) => (
                      <div key={t} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '10px 18px', borderRadius: 12,
                        border: `1px solid ${project.accent}30`,
                        background: `${project.accent}0e`,
                      }}>
                        <span style={{
                          width: 22, height: 22, borderRadius: 6,
                          background: project.accent,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 10, fontWeight: 800, color: '#fff', flexShrink: 0,
                        }}>{i + 1}</span>
                        <span style={{ fontSize: 15, fontWeight: 600, color: 'rgba(255,255,255,0.85)' }}>{t}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ══ ARCHITECTURE ══════════════════════════════════════ */}
            {activeTab === 'architecture' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

                <div style={S.card}>
                  <span style={S.eyebrow}>System Architecture</span>
                  <h2 style={{ ...S.h2, marginBottom: 6 }}>How {project.title} Works</h2>
                  <p style={{ ...S.body, marginBottom: 28 }}>{project.description}</p>
                  <MermaidDiagram code={project.mermaid} />
                </div>

                {/* Component breakdown */}
                <div style={S.card}>
                  <span style={S.eyebrow}>Core Components</span>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
                    {project.tech.map((t, i) => (
                      <div key={t} style={{
                        padding: '16px 18px', borderRadius: 12,
                        border: `1px solid rgba(255,255,255,0.07)`,
                        background: 'rgba(255,255,255,0.03)',
                        display: 'flex', flexDirection: 'column', gap: 8,
                      }}>
                        <div style={{
                          width: 8, height: 8, borderRadius: '50%', background: project.accent,
                        }} />
                        <span style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>{t}</span>
                        <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)' }}>Component {i + 1}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ══ CODE ══════════════════════════════════════════════ */}
            {activeTab === 'code' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

                {/* Explanation above code */}
                <div style={S.card}>
                  <span style={S.eyebrow}>Core Pattern</span>
                  <h2 style={S.h2}>The Heart of {project.title}</h2>
                  <p style={S.body}>
                    This is the central implementation pattern — the specific piece of code that makes this agent work.
                    {' '}Understand this, and you understand the whole system.
                  </p>
                </div>

                {/* Code block — no extra wrapper, let it breathe */}
                <div style={{ borderRadius: 16, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }}>
                  {/* File header */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '12px 20px',
                    background: '#1e1e1e',
                    borderBottom: '1px solid rgba(255,255,255,0.07)',
                  }}>
                    <Terminal size={14} color="rgba(255,255,255,0.4)" />
                    <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', fontFamily: 'monospace' }}>
                      project-{project.id}/src/agent.py
                    </span>
                  </div>
                  <CodeBlock code={project.keyCode} language="python" />
                </div>

                {/* Explanation below */}
                <div style={S.card}>
                  <span style={S.eyebrow}>What This Does</span>
                  <p style={S.body}>
                    This snippet shows the central pattern for{' '}
                    <strong style={{ color: '#fff' }}>{project.title}</strong>.{' '}
                    {project.description}
                  </p>
                  <div style={{
                    marginTop: 24, padding: '16px 20px', borderRadius: 10,
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.06)',
                  }}>
                    <p style={{ ...S.small, display: 'flex', alignItems: 'center', gap: 8 }}>
                      <CheckCircle2 size={14} color="rgba(255,255,255,0.3)" />
                      See the full implementation with tests in the GitHub repository.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* ══ TUTORIAL ══════════════════════════════════════════ */}
            {activeTab === 'tutorial' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

                {/* Prerequisites */}
                <div style={{
                  ...S.card, padding: '24px 32px',
                  background: `${project.accent}0c`,
                  border: `1px solid ${project.accent}25`,
                }}>
                  <span style={{ ...S.eyebrow, color: project.accent }}>Before You Start</span>
                  <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                    {[
                      'Python 3.11+',
                      'Docker + Docker Compose',
                      'Anthropic API key',
                      ...(project.tech.includes('Neo4j') ? ['Neo4j credentials'] : []),
                      ...(project.tech.includes('GitHub API') ? ['GitHub personal access token'] : []),
                    ].map(item => (
                      <div key={item} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <CheckCircle2 size={15} color={project.accent} />
                        <span style={{ fontSize: 15, color: 'rgba(255,255,255,0.7)', fontWeight: 500 }}>{item}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Steps */}
                <div style={S.card}>
                  <span style={S.eyebrow}>Step-by-Step Guide</span>
                  <h2 style={{ ...S.h2, marginBottom: 32 }}>Getting Started with {project.title}</h2>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                    {project.tutorial.map((step, i) => {
                      const isLast = i === project.tutorial.length - 1
                      const parts = step.split(/(`[^`]+`)/)
                      return (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, x: -16 }}
                          whileInView={{ opacity: 1, x: 0 }}
                          viewport={{ once: true }}
                          transition={{ delay: i * 0.06, duration: 0.35 }}
                          style={{ display: 'flex', gap: 20, position: 'relative' }}
                        >
                          {/* Step number + line */}
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0, width: 40 }}>
                            <div style={{
                              width: 40, height: 40, borderRadius: 12, flexShrink: 0,
                              background: project.accent,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              fontSize: 16, fontWeight: 800, color: '#fff',
                              boxShadow: `0 4px 16px ${project.accent}55`,
                              zIndex: 1,
                            }}>
                              {i + 1}
                            </div>
                            {!isLast && (
                              <div style={{
                                width: 2, flex: 1, minHeight: 32,
                                background: `linear-gradient(to bottom, ${project.accent}60, ${project.accent}15)`,
                                margin: '4px 0',
                              }} />
                            )}
                          </div>

                          {/* Step content */}
                          <div style={{ flex: 1, paddingTop: 8, paddingBottom: isLast ? 0 : 28 }}>
                            <p style={{ ...S.body, fontSize: 16, margin: 0 }}>
                              {parts.map((part, pi) =>
                                part.startsWith('`') && part.endsWith('`')
                                  ? <code key={pi} style={{
                                      padding: '2px 8px', borderRadius: 5,
                                      background: `${project.accent}20`,
                                      border: `1px solid ${project.accent}35`,
                                      color: project.accent,
                                      fontSize: 14, fontFamily: 'monospace', fontWeight: 600,
                                    }}>{part.slice(1, -1)}</code>
                                  : <span key={pi}>{part}</span>
                              )}
                            </p>
                          </div>
                        </motion.div>
                      )
                    })}
                  </div>
                </div>

              </div>
            )}

          </motion.div>
        </AnimatePresence>

        {/* ── More Projects ─────────────────────────────────────── */}
        {moreProjects.length > 0 && (
          <div style={{ marginTop: 80, paddingTop: 48, borderTop: '1px solid rgba(255,255,255,0.07)' }}>
            <p style={{ ...S.eyebrow, marginBottom: 6 }}>Continue Learning</p>
            <h3 style={{ ...S.h3, fontSize: 22, marginBottom: 28 }}>More Projects</h3>
            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
              {moreProjects.map(p => <ProjectCard key={p.id} project={p} />)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

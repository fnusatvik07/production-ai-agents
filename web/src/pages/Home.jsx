import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import Hero from '../components/Hero'
import ProjectCard from '../components/ProjectCard'
import { projects, categories, getProjectsByIds } from '../data/projects'

export default function Home() {
  return (
    <div style={{ minHeight: '100vh', background: '#111111' }}>
      <Hero />

      {/* All Projects Grid */}
      <div style={{ maxWidth: 1320, margin: '0 auto', padding: '64px 32px 96px' }}>

        {/* Section heading */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          style={{ textAlign: 'center', marginBottom: 56 }}
        >
          <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.35)', marginBottom: 12 }}>
            COLLECTION
          </p>
          <h2 style={{ fontSize: 'clamp(28px, 4vw, 42px)', fontWeight: 800, color: '#fff', letterSpacing: '-0.03em', margin: '0 0 14px' }}>
            10 Production-Ready AI Agent Blueprints
          </h2>
          <p style={{ fontSize: 17, color: 'rgba(255,255,255,0.45)', maxWidth: 560, margin: '0 auto', lineHeight: 1.65 }}>
            Each project ships with architecture diagrams, annotated code, and a step-by-step tutorial.
          </p>
        </motion.div>

        {/* Category sections */}
        {categories.map((cat, ci) => {
          const catProjects = getProjectsByIds(cat.projectIds)
          const accent = catProjects[0]?.accent || '#6366f1'
          return (
            <motion.div
              key={cat.name}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ delay: ci * 0.05, duration: 0.4 }}
              style={{ marginBottom: 56 }}
            >
              {/* Category label */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
                <div style={{ width: 3, height: 20, borderRadius: 2, background: accent, flexShrink: 0 }} />
                <span style={{ fontSize: 16, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>{cat.name}</span>
                <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }} />
                <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>
                  {catProjects.length} {catProjects.length === 1 ? 'project' : 'projects'}
                </span>
              </div>

              {/* Centered card grid */}
              <div style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 20,
                justifyContent: catProjects.length < 3 ? 'center' : 'flex-start',
              }}>
                {catProjects.map((project, i) => (
                  <motion.div
                    key={project.id}
                    initial={{ opacity: 0, scale: 0.96 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.06, duration: 0.3 }}
                  >
                    <ProjectCard project={project} />
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )
        })}
      </div>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid rgba(255,255,255,0.07)', padding: '28px 32px', textAlign: 'center' }}>
        <p style={{ color: 'rgba(255,255,255,0.25)', fontSize: 13 }}>
          10 production-ready AI agent blueprints · LangGraph · A2A Protocol · FastMCP · AutoGen
        </p>
      </footer>
    </div>
  )
}

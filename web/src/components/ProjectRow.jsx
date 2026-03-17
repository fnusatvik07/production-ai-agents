import { useRef } from 'react'
import { motion } from 'framer-motion'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import ProjectCard from './ProjectCard'

export default function ProjectRow({ category, projects }) {
  const scrollRef = useRef(null)

  function scroll(dir) {
    if (!scrollRef.current) return
    scrollRef.current.scrollBy({ left: dir * 330, behavior: 'smooth' })
  }

  const accent = projects[0]?.accent || '#6366f1'

  return (
    <motion.section
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.45 }}
      style={{ marginBottom: 48 }}
    >
      {/* Row header */}
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '0 32px', marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {/* Accent bar */}
            <div style={{ width: 3, height: 22, borderRadius: 2, background: accent }} />
            <span style={{ fontSize: 17, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>
              {category}
            </span>
            <span style={{
              padding: '2px 8px', borderRadius: 6,
              background: 'rgba(255,255,255,0.07)',
              color: 'rgba(255,255,255,0.4)',
              fontSize: 11, fontWeight: 600,
            }}>
              {projects.length}
            </span>
          </div>

          {/* Scroll buttons */}
          <div style={{ display: 'flex', gap: 6 }}>
            {[[-1, ChevronLeft], [1, ChevronRight]].map(([dir, Icon]) => (
              <button
                key={dir}
                onClick={() => scroll(dir)}
                style={{
                  width: 30, height: 30, borderRadius: 8, border: 'none',
                  background: 'rgba(255,255,255,0.08)',
                  color: 'rgba(255,255,255,0.6)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', transition: 'background 0.15s, color 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.14)'; e.currentTarget.style.color = '#fff' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.08)'; e.currentTarget.style.color = 'rgba(255,255,255,0.6)' }}
              >
                <Icon size={15} />
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Card row */}
      <div style={{ padding: '0 32px' }}>
        <div ref={scrollRef} className="row-scroll">
          {projects.map((project, i) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07, duration: 0.35 }}
            >
              <ProjectCard project={project} />
            </motion.div>
          ))}
        </div>
      </div>
    </motion.section>
  )
}

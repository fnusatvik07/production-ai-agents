import { Link, useLocation } from 'react-router-dom'
import { motion, useScroll, useTransform } from 'framer-motion'
import { Cpu, Github } from 'lucide-react'
import { Group, Text, Badge } from '@mantine/core'

export default function Navbar() {
  const location = useLocation()
  const { scrollY } = useScroll()
  const bg = useTransform(scrollY, [0, 80], ['rgba(17,17,17,0)', 'rgba(17,17,17,0.97)'])
  const border = useTransform(scrollY, [0, 80], ['rgba(255,255,255,0)', 'rgba(255,255,255,0.08)'])

  return (
    <motion.nav
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
        background: bg,
        borderBottom: '1px solid',
        borderColor: border,
        backdropFilter: 'blur(12px)',
      }}
    >
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '0 32px', height: 60 }}>
        <Group justify="space-between" h="100%">

          {/* Logo */}
          <Link to="/" style={{ textDecoration: 'none' }}>
            <Group gap={10} align="center">
              <div style={{
                width: 30, height: 30, borderRadius: 8,
                background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Cpu size={15} color="#fff" strokeWidth={2.5} />
              </div>
              <Text fw={800} size="md" style={{ color: '#fff', letterSpacing: '-0.02em' }}>
                Agent<Text component="span" fw={800} style={{ color: '#6366f1' }}>Blueprints</Text>
              </Text>
              <Badge
                size="xs" radius="sm" variant="light" color="indigo"
                style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.05em' }}
              >
                10 PROJECTS
              </Badge>
            </Group>
          </Link>

          {/* Right side */}
          <Group gap={24} align="center">
            {[['/', 'Projects']].map(([path, label]) => (
              <Link key={path} to={path} style={{ textDecoration: 'none' }}>
                <Text
                  size="sm" fw={500}
                  style={{
                    color: location.pathname === path ? '#fff' : 'rgba(255,255,255,0.5)',
                    transition: 'color 0.15s',
                  }}
                >
                  {label}
                </Text>
              </Link>
            ))}
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 32, height: 32, borderRadius: 8,
                background: 'rgba(255,255,255,0.07)',
                color: 'rgba(255,255,255,0.7)',
                transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)'; e.currentTarget.style.color = '#fff' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.07)'; e.currentTarget.style.color = 'rgba(255,255,255,0.7)' }}
            >
              <Github size={16} />
            </a>
          </Group>

        </Group>
      </div>
    </motion.nav>
  )
}

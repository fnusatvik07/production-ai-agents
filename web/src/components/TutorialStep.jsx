import { motion } from 'framer-motion'
import { Code, Text } from '@mantine/core'

export default function TutorialStep({ step, index, accent }) {
  // Parse inline code backticks
  const parts = step.split(/(`[^`]+`)/)

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.07, duration: 0.4 }}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 16,
        paddingBottom: 24,
        position: 'relative',
      }}
    >
      {/* Step number badge */}
      <div
        style={{
          position: 'relative',
          zIndex: 10,
          width: 32,
          height: 32,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 14,
          fontWeight: 700,
          flexShrink: 0,
          color: '#fff',
          background: accent,
          boxShadow: `0 0 12px ${accent}66`,
        }}
      >
        {index + 1}
      </div>

      {/* Step content */}
      <div style={{ flex: 1, paddingTop: 4 }}>
        <Text c="rgba(255,255,255,0.8)" size="sm" lh={1.7}>
          {parts.map((part, i) => {
            if (part.startsWith('`') && part.endsWith('`')) {
              return (
                <Code
                  key={i}
                  style={{
                    background: `${accent}22`,
                    color: accent,
                    border: `1px solid ${accent}33`,
                    fontSize: 12,
                    padding: '1px 6px',
                    borderRadius: 4,
                  }}
                >
                  {part.slice(1, -1)}
                </Code>
              )
            }
            return <span key={i}>{part}</span>
          })}
        </Text>
      </div>
    </motion.div>
  )
}

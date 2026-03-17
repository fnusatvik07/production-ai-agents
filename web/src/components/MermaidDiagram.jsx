import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import { Paper, Center, Loader, Alert, Text, Code } from '@mantine/core'

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#1e3a5f',
    primaryTextColor: '#fff',
    primaryBorderColor: '#3b82f6',
    lineColor: '#6b7280',
    secondaryColor: '#1a1a2e',
    tertiaryColor: '#0d1117',
    background: '#141414',
    mainBkg: '#1e293b',
    nodeBorder: '#334155',
    clusterBkg: '#0f172a',
    titleColor: '#f1f5f9',
    edgeLabelBackground: '#1e293b',
    fontSize: '14px',
  },
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    padding: 20,
  },
  securityLevel: 'loose',
})

let diagramCounter = 0

export default function MermaidDiagram({ code }) {
  const ref = useRef(null)
  const [error, setError] = useState(null)
  const [rendered, setRendered] = useState(false)

  useEffect(() => {
    if (!ref.current || !code) return
    setError(null)
    setRendered(false)

    const id = `mermaid-diagram-${++diagramCounter}-${Date.now()}`

    mermaid
      .render(id, code)
      .then(({ svg }) => {
        if (ref.current) {
          ref.current.innerHTML = svg
          const svgEl = ref.current.querySelector('svg')
          if (svgEl) {
            svgEl.style.maxWidth = '100%'
            svgEl.style.height = 'auto'
            svgEl.removeAttribute('height')
          }
          setRendered(true)
        }
      })
      .catch((err) => {
        console.error('Mermaid render error:', err)
        setError(err.message || 'Failed to render diagram')
      })
  }, [code])

  if (error) {
    return (
      <Paper p="xl" bg="dark.8" radius="md">
        <Alert
          color="red"
          title="Diagram render error"
          variant="light"
          mb="md"
        >
          <Text size="sm">{error}</Text>
        </Alert>
        <details>
          <summary style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12, cursor: 'pointer' }}>
            Raw diagram source
          </summary>
          <Code block mt="xs" style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>
            {code}
          </Code>
        </details>
      </Paper>
    )
  }

  return (
    <Paper p="xl" bg="dark.8" radius="md">
      {!rendered && (
        <Center py={64}>
          <Loader color="blue" size="sm" mr="sm" />
          <Text c="dimmed" size="sm">Rendering diagram…</Text>
        </Center>
      )}
      <div
        ref={ref}
        className="mermaid-wrap"
        style={{
          display: rendered ? 'flex' : 'none',
          justifyContent: 'center',
          padding: '24px 0',
          overflowX: 'auto',
        }}
      />
    </Paper>
  )
}

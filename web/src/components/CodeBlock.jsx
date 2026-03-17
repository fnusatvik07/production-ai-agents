import { CodeHighlight } from '@mantine/code-highlight'
import { Paper } from '@mantine/core'

export default function CodeBlock({ code, language = 'python', title }) {
  return (
    <Paper radius="md" style={{ overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }}>
      <CodeHighlight
        code={code}
        language={language}
        withCopyButton
        copyLabel="Copy code"
        copiedLabel="Copied!"
        style={{ fontSize: 13, lineHeight: 1.6 }}
      />
    </Paper>
  )
}

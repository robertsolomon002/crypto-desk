import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { safeHttpUrl } from '@/lib/format'

// Model output is untrusted (Section 3.6). react-markdown builds React elements from the Markdown
// syntax tree and never renders raw HTML (no rehype-raw; `skipHtml` drops it entirely). Links
// must be http(s) and open in a new tab without a referrer; images are never loaded (they could
// track the reader or break the CSP), only their alt text is shown.

const components: Components = {
  a({ href, children }) {
    const url = href ? safeHttpUrl(href) : null
    if (!url) return <span>{children}</span>
    return (
      <a href={url} target="_blank" rel="noopener noreferrer nofollow" className="underline">
        {children}
      </a>
    )
  },
  img({ alt }) {
    return alt ? <span className="text-muted-foreground">[{alt}]</span> : null
  },
  table({ children }) {
    return (
      <div className="my-2 overflow-x-auto">
        <table className="w-full border-collapse font-mono text-xs tabular-nums">{children}</table>
      </div>
    )
  },
  th({ children }) {
    return <th className="border-b px-2 py-1 text-left font-medium">{children}</th>
  },
  td({ children }) {
    return <td className="border-b border-border/50 px-2 py-1">{children}</td>
  },
  code({ children }) {
    return <code className="rounded bg-muted px-1 font-mono text-[0.85em]">{children}</code>
  },
  pre({ children }) {
    return <pre className="my-2 overflow-x-auto rounded-md bg-muted p-2 text-xs">{children}</pre>
  },
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5 [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-medium">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {text}
      </ReactMarkdown>
    </div>
  )
}

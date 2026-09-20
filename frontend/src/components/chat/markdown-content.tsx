import { useMemo, type AnchorHTMLAttributes, type ComponentProps } from "react"
import rehypeMathjax from "rehype-mathjax/chtml"
import remarkMath from "remark-math"
import {
  defaultRehypePlugins,
  defaultRemarkPlugins,
  Streamdown,
  type Components,
} from "streamdown"

import { cn } from "cn"

const remarkPlugins: NonNullable<ComponentProps<typeof Streamdown>["remarkPlugins"]> = [
  ...Object.values(defaultRemarkPlugins),
  [remarkMath, { singleDollarTextMath: true }],
]
const rehypePlugins: NonNullable<ComponentProps<typeof Streamdown>["rehypePlugins"]> = [
  ...Object.values(defaultRehypePlugins),
  [rehypeMathjax, { chtml: { fontURL: "/fonts/mathjax" } }],
]
const CITATION_PREFIX = "#paper-citation-"

export function MarkdownContent({
  children,
  streaming = false,
  citations = [],
  onCitationClick,
  className,
}: {
  children: string
  streaming?: boolean
  citations?: string[]
  onCitationClick?: (citationId: string) => void
  className?: string
}) {
  const markdown = useMemo(
    () => normalizeAgentMarkdown(children, citations),
    [children, citations],
  )
  const components = useMemo<Components>(
    () => ({
      a: ({ href, children: label, className, node: _node, ...props }) => {
        if (href?.startsWith(CITATION_PREFIX)) {
          const citationId = decodeURIComponent(href.slice(CITATION_PREFIX.length))
          return (
            <a
              {...(props as AnchorHTMLAttributes<HTMLAnchorElement>)}
              href={href}
              className={cn(
                className,
                "relative -top-0.5 mx-0.5 inline-flex items-center rounded-sm bg-primary/10 px-1 py-0.5 text-[0.75em] font-semibold leading-none text-primary no-underline ring-1 ring-primary/20 transition-colors hover:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
              data-paper-citation=""
              aria-label={`打开引用 ${label}`}
              onClick={(event) => {
                event.preventDefault()
                onCitationClick?.(citationId)
              }}
            >
              {label}
            </a>
          )
        }
        return (
          <a
            {...(props as AnchorHTMLAttributes<HTMLAnchorElement>)}
            href={href}
            className={className}
            target="_blank"
            rel="noreferrer"
          >
            {label}
          </a>
        )
      },
    }),
    [onCitationClick],
  )

  return (
    <Streamdown
      className={cn("agent-markdown min-w-0 text-[15px] leading-7", className)}
      mode={streaming ? "streaming" : "static"}
      parseIncompleteMarkdown={streaming}
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={components}
      controls={{ code: true, table: true }}
      lineNumbers={false}
      linkSafety={{ enabled: true }}
    >
      {markdown}
    </Streamdown>
  )
}

export function inlineCitationIds(content: string, citations: string[]): Set<string> {
  const allowed = new Set(citations)
  const found = new Set<string>()
  let fenced = false
  for (const line of content.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) {
      fenced = !fenced
      continue
    }
    if (fenced) continue
    let codeTicks = 0
    for (let index = 0; index < line.length; index += 1) {
      if (line[index] === "`") {
        const run = line.slice(index).match(/^`+/)?.[0] ?? "`"
        codeTicks = codeTicks === 0 ? run.length : codeTicks === run.length ? 0 : codeTicks
        index += run.length - 1
        continue
      }
      if (codeTicks === 0) {
        const citation = line.slice(index).match(/^\[(cit_[A-Za-z0-9_-]+)]/)
        if (citation && allowed.has(citation[1])) {
          found.add(citation[1])
          index += citation[0].length - 1
        }
      }
    }
  }
  return found
}

function normalizeAgentMarkdown(content: string, citations: string[]): string {
  const citationNumbers = new Map(citations.map((id, index) => [id, index + 1]))
  let fenced = false

  return content
    .split("\n")
    .map((line) => {
      if (/^\s*(```|~~~)/.test(line)) {
        fenced = !fenced
        return line
      }
      if (fenced) return line
      const displayMath = line.match(/^\s*\$\$(.+)\$\$\s*$/)
      if (displayMath) return `$$\n${displayMath[1]}\n$$`
      return normalizeInline(line, citationNumbers)
    })
    .join("\n")
}

function normalizeInline(line: string, citations: Map<string, number>): string {
  let result = ""
  let index = 0
  let codeTicks = 0

  while (index < line.length) {
    if (line[index] === "`") {
      const run = line.slice(index).match(/^`+/)?.[0] ?? "`"
      codeTicks = codeTicks === 0 ? run.length : codeTicks === run.length ? 0 : codeTicks
      result += run
      index += run.length
      continue
    }
    if (codeTicks === 0) {
      const citation = line.slice(index).match(/^\[(cit_[A-Za-z0-9_-]+)]/)
      const number = citation ? citations.get(citation[1]) : undefined
      if (citation && number !== undefined) {
        result += `[${number}](${CITATION_PREFIX}${encodeURIComponent(citation[1])})`
        index += citation[0].length
        continue
      }
      const delimiter = line.slice(index, index + 2)
      if (delimiter === "\\(" || delimiter === "\\)") {
        result += "$"
        index += 2
        continue
      }
      if (delimiter === "\\[" || delimiter === "\\]") {
        result += "$$"
        index += 2
        continue
      }
    }
    result += line[index]
    index += 1
  }
  return result
}

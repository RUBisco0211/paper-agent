import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { createMathPlugin } from "@streamdown/math";
import { mermaid } from "@streamdown/mermaid";
import * as React from "react";
import { Streamdown } from "streamdown";
import "katex/dist/katex.min.css";

import { cn } from "@/lib/utils";

const math = createMathPlugin({ singleDollarTextMath: true });
const DEFAULT_PLUGINS = { code, math, cjk, mermaid };

// Mermaid embeds its own stylesheet in each SVG; token references keep existing
// diagrams in sync with system theme changes without remounting the message.
const DIAGRAM_THEME: React.ComponentProps<typeof Streamdown>["mermaid"] = {
  config: {
    theme: "base",
    themeVariables: { fontFamily: "var(--font-mono)" },
    themeCSS: `
			.node rect, .node circle, .node ellipse, .node polygon, .actor {
				fill: var(--card); stroke: var(--primary);
			}
			text, .nodeLabel, .edgeLabel, .edgeLabel p, .actor text {
				fill: var(--foreground); color: var(--foreground);
			}
			.edgeLabel, .edgeLabel rect, .labelBkg {
				background-color: var(--background); fill: var(--background);
			}
			.flowchart-link, .edgePath .path, .actor-line, .messageLine0, .messageLine1 {
				stroke: var(--muted-foreground);
			}
			marker path { fill: var(--muted-foreground); stroke: var(--muted-foreground); }
		`,
  },
};

function Markdown({
  className,
  plugins = DEFAULT_PLUGINS,
  controls = false,
  mermaid: diagramTheme = DIAGRAM_THEME,
  ...props
}: React.ComponentProps<typeof Streamdown>) {
  return (
    <Streamdown
      data-slot="markdown"
      plugins={plugins}
      controls={controls}
      mermaid={diagramTheme}
      className={cn("cn-markdown w-full min-w-0 overflow-hidden", className)}
      {...props}
    />
  );
}

export { Markdown };

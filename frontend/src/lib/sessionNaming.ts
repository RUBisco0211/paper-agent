import type { Msg } from "@agentscope-ai/agentscope/message";
import type { QueryClient } from "@tanstack/react-query";

import { readQuoteReferences } from "@/components/chat/quoteReferences";
import { sameSessionId } from "@/lib/agentSessions";
import { sessionApi } from "@/lib/api/agentscope/session";
import type { SessionListResponse } from "@/types/agent";
import type { BoundSession } from "@/types/session";

export interface SessionNameInput {
  text: string;
  excerpts: string[];
}

/** Collect the text and quoted excerpts that the naming model may use. */
export function sessionNameInput(message: Msg): SessionNameInput {
  const text = message.content
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("\n\n")
    .trim();
  const excerpts = readQuoteReferences(message.metadata).flatMap(
    (reference) => {
      const selected = reference.selected_text.trim();
      const comment = reference.comment.trim();
      const source =
        "source_title" in reference
          ? (reference.source_title?.trim() ?? "")
          : "";
      const imageFallback =
        reference.kind === "parsed_block" && reference.include_image
          ? "图片或图表"
          : "";
      const value = [
        selected || source || imageFallback,
        comment ? `评论：${comment}` : "",
      ]
        .filter(Boolean)
        .join("\n");
      return value ? [value] : [];
    },
  );
  return { text, excerpts };
}

/** Request a name for a new session from its first prompt. */
export async function generateSessionName(
  agentId: string,
  sessionId: string,
  input: SessionNameInput & {
    projectName?: string;
    projectDescription?: string;
  },
): Promise<string> {
  const result = await sessionApi.generateName(sessionId, {
    agent_id: agentId,
    text: input.text,
    excerpts: input.excerpts,
    ...(input.projectName ? { project_name: input.projectName } : {}),
    ...(input.projectDescription
      ? { project_description: input.projectDescription }
      : {}),
  });
  return result.name;
}

/** Replace the generated name in every cache that renders the session. */
export function applySessionName(
  queryClient: QueryClient,
  agentId: string,
  sessionId: string,
  name: string,
): void {
  queryClient.setQueryData<BoundSession[]>(["bound-sessions"], (current) =>
    current?.map((item) =>
      sameSessionId(item.session.session.id, sessionId)
        ? {
            ...item,
            session: {
              ...item.session,
              session: {
                ...item.session.session,
                config: { ...item.session.session.config, name },
              },
            },
          }
        : item,
    ),
  );
  queryClient.setQueryData<SessionListResponse>(
    ["agent-sessions", agentId],
    (current) =>
      current
        ? {
            ...current,
            sessions: current.sessions.map((view) =>
              sameSessionId(view.session.id, sessionId)
                ? {
                    ...view,
                    session: {
                      ...view.session,
                      config: { ...view.session.config, name },
                    },
                  }
                : view,
            ),
          }
        : current,
  );
  void queryClient.invalidateQueries({ queryKey: ["bound-sessions"] });
  void queryClient.invalidateQueries({ queryKey: ["agent-sessions", agentId] });
}

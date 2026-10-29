import type { ContentBlock, Msg } from "@agentscope-ai/agentscope/message";
import { UserMsg } from "@agentscope-ai/agentscope/message";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Link, useNavigate, useOutletContext } from "react-router-dom";

import { useApi } from "@/components/providers/ApiProvider";
import { availableChatModels, createBoundSession } from "@/lib/agentSessions";
import {
  applySessionName,
  generateSessionName,
  sessionNameInput,
} from "@/lib/sessionNaming";
import { describeError } from "@/lib/errors";
import { chatApi } from "@/lib/api/agentscope/chat";
import { TextInput } from "@/components/chat/TextInput";
import { mentionMetadata, mentionPlaceholders, mentionRequest, type MentionCandidate } from "@/lib/mentions";
import { Button } from "@/components/ui/Button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { reasoningEffortsForModel } from "@/components/chat/chatView";
import type { ChatWorkspaceContext } from "./ChatPage";
import { ChatQuoteContext } from "@/components/chat/chatQuoteContext";
import { QuoteBadge } from "@/components/chat/QuoteBadge";
import {
  normalizePdfQuoteRects,
  readQuoteReferences,
} from "@/components/chat/quoteReferences";
import type { QuoteReference } from "@/types/chat";

export function NewChatPage() {
  const { api } = useApi();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const {
    draftQuoteKey,
    draftProjectId: projectId,
    setDraftProjectId: setProjectId,
  } = useOutletContext<ChatWorkspaceContext>();
  const projects = useQuery({
    queryKey: ["sidebar-projects"],
    queryFn: () => api.projects.list({ limit: 100 }),
  });
  const [modelKey, setModelKey] = useState("");
  const [effort, setEffort] = useState("default");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retryText, setRetryText] = useState("");
  const pendingSession = useRef<{ agentId: string; sessionId: string } | null>(
    null,
  );
  const pendingMessage = useRef<Msg | null>(null);
  const namingStarted = useRef(false);
  const [pendingQuotes, setPendingQuotes] = useState<QuoteReference[]>([]);
  const pendingQuotesRef = useRef(pendingQuotes);
  pendingQuotesRef.current = pendingQuotes;
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const quoteBridge = useContext(ChatQuoteContext);
  const addPendingQuote = useCallback((reference: QuoteReference) => {
    if (busyRef.current) return false;
    if (pendingQuotesRef.current.length >= 8) {
      toast.error("每次提问最多引用 8 处内容");
      return false;
    }
    pendingQuotesRef.current = [...pendingQuotesRef.current, reference];
    setPendingQuotes(pendingQuotesRef.current);
    return true;
  }, []);
  useEffect(
    () => quoteBridge?.register(draftQuoteKey, addPendingQuote),
    [quoteBridge, draftQuoteKey, addPendingQuote],
  );
  useEffect(() => {
    pendingQuotesRef.current = [];
    setPendingQuotes([]);
    if (!pendingSession.current) {
      pendingMessage.current = null;
      setRetryText("");
      setError("");
    }
  }, [draftQuoteKey]);
  const models = useQuery({
    queryKey: ["available-chat-models"],
    queryFn: () => availableChatModels(api),
  });
  const catalog = useQuery({
    queryKey: ["llm-catalog"],
    queryFn: api.sessions.llmCatalog,
  });
  const selected =
    models.data?.find(
      (item) => `${item.credential_id}:${item.model}` === modelKey,
    ) ?? models.data?.[0];
  const selectedKey = selected
    ? `${selected.credential_id}:${selected.model}`
    : "";
  const efforts = selected
    ? reasoningEffortsForModel(
        catalog.data?.providers ?? [],
        selected.type,
        selected.model,
      )
    : [];
  const namingProject = projectId
    ? projects.data?.items.find((project) => project.id === projectId)
    : undefined;

  const [mentions, setMentions] = useState<MentionCandidate[]>([]);
  /** Mentions of the message being retried; the input has already been cleared. */
  const sentMentions = useRef<MentionCandidate[]>([]);
  const mentionCandidatesQuery = useQuery({
    queryKey: ["mention-candidates", projectId || "library"],
    queryFn: async () => {
      const page = projectId
        ? await api.projects.papers(projectId, { limit: 200 })
        : await api.library.list({ limit: 200 });
      return page.items.map((item) => ({
        user_paper_id: item.id,
        title: item.title || "未命名文献",
      }));
    },
  });
  const mentionCandidates = mentionCandidatesQuery.data ?? [];

  async function sendFirst(blocks: ContentBlock[], retry = false) {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      const message =
        retry && pendingMessage.current
          ? pendingMessage.current
          : UserMsg({ name: "user", content: blocks });
      const body = blocks
        .filter((block) => block.type === "text")
        .map((block) => block.text)
        .join("\n\n");
      const rendered = mentionPlaceholders(
        body,
        retry ? sentMentions.current : mentions,
      );
      const mentionPayload = mentionRequest(rendered.mentions);
      if (!retry && (pendingQuotes.length || mentionPayload.length)) {
        message.metadata = {
          paper_agent: {
            body,
            mentions: mentionMetadata(rendered.mentions),
            references: pendingQuotes.map((reference) =>
              reference.kind === "pdf_selection"
                ? {
                    ...reference,
                    rects: normalizePdfQuoteRects(reference.rects ?? []),
                  }
                : reference,
            ),
          },
        };
      }
      if (!retry) sentMentions.current = rendered.mentions;
      pendingMessage.current = message;
      const parameters = { ...selected.parameters };
      if (effort !== "default") parameters.reasoning_effort = effort;
      const session =
        pendingSession.current ??
        (await createBoundSession(api, {
          projectId: projectId || undefined,
          modelConfig: { ...selected, parameters },
        }));
      pendingSession.current = session;
      if (!namingStarted.current) {
        namingStarted.current = true;
        try {
          const namingInput = sessionNameInput(message);
          if (namingInput.text || namingInput.excerpts.length) {
            void generateSessionName(session.agentId, session.sessionId, {
              ...namingInput,
              projectName: namingProject?.name,
              projectDescription: namingProject?.description ?? undefined,
            })
              .then((name) =>
                applySessionName(
                  queryClient,
                  session.agentId,
                  session.sessionId,
                  name,
                ),
              )
              .catch((cause) => {
                console.warn("会话命名失败", cause);
              });
          }
        } catch (cause) {
          console.warn("会话命名失败", cause);
        }
      }
      const references = readQuoteReferences(message.metadata);
      if (references.length || mentionPayload.length) {
        await chatApi.triggerQuoted({
          agent_id: session.agentId,
          session_id: session.sessionId,
          text: rendered.text,
          references,
          mentions: mentionPayload,
        });
      } else {
        await chatApi.trigger({
          agent_id: session.agentId,
          session_id: session.sessionId,
          input: message,
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["bound-sessions"] });
      navigate(`/chat/${session.agentId}/${session.sessionId}`, {
        replace: true,
      });
    } catch (cause) {
      setError(describeError(cause));
      setRetryText(
        blocks
          .filter((block) => block.type === "text")
          .map((block) => block.text)
          .join("\n"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex min-h-0 flex-1 items-center justify-center px-5 pb-20">
        <div className="w-full max-w-(--chat-content-max-width) space-y-7">
          <div className="text-center">
            <h2 className="text-2xl font-medium tracking-tight">
              想了解哪篇文献？
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              从一个问题开始，也可以请我比较或总结文献。
            </p>
          </div>
          {models.isSuccess && models.data.length === 0 && (
            <p className="text-center text-sm text-muted-foreground">
              请先
              <Link className="ml-1 underline" to="/settings">
                配置模型
              </Link>
            </p>
          )}
          {models.isError && (
            <p role="alert" className="text-center text-sm text-destructive">
              模型列表加载失败，请刷新重试
            </p>
          )}
          <TextInput
            className="w-full"
            mentionCandidates={mentionCandidates}
            onMentions={setMentions}
            quoteSlot={
              pendingQuotes.length ? (
                <>
                  {pendingQuotes.map((reference, index) => (
                    <QuoteBadge
                      key={index}
                      reference={reference}
                      onEdit={(comment) => {
                        if (!busy)
                          setPendingQuotes((current) =>
                            current.map((item, itemIndex) =>
                              itemIndex === index ? { ...item, comment } : item,
                            ),
                          );
                      }}
                      onRemove={() => {
                        if (!busy)
                          setPendingQuotes((current) =>
                            current.filter(
                              (_, itemIndex) => itemIndex !== index,
                            ),
                          );
                      }}
                    />
                  ))}
                </>
              ) : undefined
            }
            allowEmptyText={pendingQuotes.length > 0}
            headerSlot={
              <div className="flex items-center gap-2 px-2 py-1">
                <Select
                  value={projectId || "global"}
                  onValueChange={(value) =>
                    setProjectId(value === "global" ? "" : value)
                  }
                  disabled={busy || Boolean(pendingSession.current)}
                >
                  <SelectTrigger className="max-w-40" aria-label="所属项目">
                    <SelectValue placeholder="选择项目" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="global">全局</SelectItem>
                    {projects.data?.items.map((project) => (
                      <SelectItem key={project.id} value={project.id}>
                        {project.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={selectedKey}
                  onValueChange={(value) => {
                    setModelKey(value);
                    setEffort("default");
                  }}
                  disabled={busy || !models.data?.length}
                >
                  <SelectTrigger className="max-w-56">
                    <SelectValue placeholder="选择模型" />
                  </SelectTrigger>
                  <SelectContent>
                    {models.data?.map((item) => (
                      <SelectItem
                        key={`${item.credential_id}:${item.model}`}
                        value={`${item.credential_id}:${item.model}`}
                      >
                        {item.type.replace(/_credential$/, "")} · {item.model}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {efforts.length > 0 && (
                  <Select
                    value={effort}
                    onValueChange={setEffort}
                    disabled={busy}
                  >
                    <SelectTrigger
                      className="h-8 w-32 border-0 bg-transparent text-xs"
                      aria-label="思考强度"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">默认思考</SelectItem>
                      {efforts.map((item) => (
                        <SelectItem key={item} value={item}>
                          {item}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            }
            onSend={(blocks) => void sendFirst(blocks)}
            disabled={busy}
            sendDisabled={!selected}
            allowedInputTypes={[]}
            fileProcessor={async () => null}
          />
          {error && (
            <div role="alert" className="space-y-2 text-sm text-destructive">
              <p>发送失败：{error}</p>
              {pendingMessage.current && (
                <div className="rounded-lg border p-3 text-foreground">
                  <p className="line-clamp-3 whitespace-pre-wrap">
                    {retryText}
                  </p>
                  <Button
                    className="mt-2"
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      void sendFirst(pendingMessage.current!.content, true)
                    }
                  >
                    重试发送
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

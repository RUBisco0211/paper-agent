import { useInfiniteQuery } from "@tanstack/react-query";
import { FileText, Search } from "lucide-react";
import { useContext, useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

import { useApi } from "@/components/providers/ApiProvider";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { PaperReadingPage } from "@/pages/PaperReadingPage";
import type { PaperQuote, QuoteReference } from "@/types/chat";
import { ChatQuoteContext } from "./chatQuoteContext";

export function ConversationPapersPanel({
  projectId,
  sessionId,
  onReadingChange,
}: {
  projectId: string | null;
  sessionId: string | null;
  onReadingChange?: (reading: boolean) => void;
}) {
  const { api } = useApi();
  const [query, setQuery] = useState("");
  const searchQuery = useDebouncedValue(query.trim());
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [searchQuery]);
  const [readingId, setReadingId] = useState<string | null>(null);
  const [locatedQuote, setLocatedQuote] = useState<PaperQuote | null>(null);
  useEffect(
    () => onReadingChange?.(Boolean(readingId)),
    [readingId, onReadingChange],
  );
  const quoteBridge = useContext(ChatQuoteContext);
  useEffect(() => {
    if (!sessionId) return;
    return quoteBridge?.registerPaperOpener(sessionId, (reference) => {
      setReadingId(reference.user_paper_id);
      setLocatedQuote(reference);
      return true;
    });
  }, [quoteBridge, sessionId]);
  const papers = useInfiniteQuery({
    queryKey: projectId
      ? ["project-papers", projectId, "sidebar", searchQuery]
      : ["papers", "sidebar", searchQuery],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      projectId
        ? api.projects.papers(projectId, {
            q: searchQuery || undefined,
            limit: 200,
            offset: pageParam,
          })
        : api.library.list({
            q: searchQuery || undefined,
            limit: 200,
            offset: pageParam,
          }),
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.items.length;
      return lastPage.items.length > 0 && nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
  });
  const items = papers.data?.pages.flatMap((page) => page.items) ?? [];

  function addQuote(reference: QuoteReference) {
    return Boolean(sessionId && quoteBridge?.add(sessionId, reference));
  }

  if (readingId)
    return (
      <PaperReadingPage
        paperId={readingId}
        embedded
        locatedQuote={locatedQuote}
        onBack={() => {
          setReadingId(null);
          setLocatedQuote(null);
        }}
        onQuote={sessionId ? addQuote : undefined}
      />
    );

  return (
    <aside
      aria-label={projectId ? "项目文献" : "全局文献"}
      className="flex h-full min-h-0 flex-col overflow-hidden bg-background"
    >
      {
        <div className="shrink-0 border-b p-2">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label={projectId ? "搜索项目文献" : "搜索个人文献库"}
              placeholder={projectId ? "搜索项目文献" : "搜索个人文献库"}
              className="pl-9"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                if (listRef.current) listRef.current.scrollTop = 0;
              }}
            />
          </div>
        </div>
      }
      <div
        ref={listRef}
        className="min-h-0 flex-1 overflow-y-auto p-2"
        onScroll={(event) => {
          const list = event.currentTarget;
          if (
            list.scrollHeight - list.scrollTop - list.clientHeight <= 64 &&
            query.trim() === searchQuery &&
            papers.hasNextPage &&
            !papers.isFetching &&
            !papers.isFetchNextPageError
          ) {
            void papers.fetchNextPage();
          }
        }}
      >
        {papers.isPending && (
          <p className="p-2 text-sm text-muted-foreground">加载中…</p>
        )}
        {papers.isError && !papers.isFetchNextPageError && (
          <p role="alert" className="p-2 text-sm text-destructive">
            无法读取文献，请稍后重试
          </p>
        )}
        {papers.isSuccess && items.length === 0 && (
          <p className="p-2 text-sm text-muted-foreground">
            {query ? "没有匹配的文献" : "暂无文献"}
          </p>
        )}
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => {
              setReadingId(item.id);
              setLocatedQuote(null);
            }}
            className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-muted"
          >
            <FileText className="mt-0.5 size-4 shrink-0" />
            <span className="flex min-w-0 flex-1 flex-col gap-1">
              <span
                className="line-clamp-2"
                title={item.title || item.original_filename || "未命名文献"}
              >
                {item.title || item.original_filename || "未命名文献"}
              </span>
              {item.authors.length > 0 && (
                <span
                  className="line-clamp-1 text-xs text-muted-foreground"
                  title={item.authors.join("、")}
                >
                  {item.authors.join("、")}
                </span>
              )}
              {(item.venue || item.year) && (
                <span
                  className="line-clamp-1 text-xs text-muted-foreground"
                  title={[item.venue, item.year].filter(Boolean).join(" · ")}
                >
                  {[item.venue, item.year].filter(Boolean).join(" · ")}
                </span>
              )}
            </span>
          </button>
        ))}
        {papers.isFetchingNextPage && (
          <p className="p-2 text-sm text-muted-foreground">加载中…</p>
        )}
        {papers.isFetchNextPageError && (
          <div className="p-2">
            <p role="alert" className="text-sm text-destructive">
              无法加载更多文献，请重试
            </p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void papers.fetchNextPage()}
              disabled={
                papers.isFetchingNextPage || query.trim() !== searchQuery
              }
            >
              重试
            </Button>
          </div>
        )}
      </div>
    </aside>
  );
}

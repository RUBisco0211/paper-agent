// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { createQueryClient } from "@/app/query";
import { ChatQuoteContext } from "./chatQuoteContext";
import type { PaperQuote } from "@/types/chat";
import { ConversationPapersPanel } from "./ConversationPapersPanel";

vi.mock("@/components/providers/ApiProvider", () => ({
  useApi: () => ({
    api: {
      library: {
        list: async () => ({
          items: [{ id: "global-paper", title: "全局测试文献" }],
          total: 1,
        }),
      },
      projects: {
        papers: async () => ({ items: [{ id: "paper-1", title: "测试文献" }] }),
      },
    },
  }),
}));
vi.mock("@/pages/PaperReadingPage", () => ({
  PaperReadingPage: ({
    onBack,
    onQuote,
    locatedQuote,
  }: {
    onBack: () => void;
    onQuote?: (reference: unknown) => boolean;
    locatedQuote?: PaperQuote | null;
  }) => (
    <section
      aria-label="侧栏阅读器"
      data-located-block={locatedQuote?.block_id}
    >
      <button onClick={onBack}>返回文献列表</button>
      <button
        onClick={() =>
          onQuote?.({ kind: "pdf_selection", selected_text: "引文" })
        }
      >
        添加到对话
      </button>
    </section>
  ),
}));

it("shows library papers when the conversation scope is global", async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ConversationPapersPanel projectId={null} sessionId="session-1" />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("button", { name: "全局测试文献" }),
  ).toBeTruthy();
  expect(screen.getByRole("complementary", { name: "全局文献" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "测试文献" })).toBeNull();
});

it("opens a paper inside the conversation sidebar and returns to its list", async () => {
  const add = vi.fn(() => true);
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ChatQuoteContext.Provider
        value={{
          register: () => () => {},
          add,
          registerPaperOpener: () => () => {},
          openPaper: () => true,
        }}
      >
        <ConversationPapersPanel projectId="project-1" sessionId="session-1" />
      </ChatQuoteContext.Provider>
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "测试文献" }));
  expect(screen.getByRole("region", { name: "侧栏阅读器" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "添加到对话" }));
  expect(add).toHaveBeenCalledWith(
    "session-1",
    expect.objectContaining({ kind: "pdf_selection", selected_text: "引文" }),
  );
  await user.click(screen.getByRole("button", { name: "返回文献列表" }));
  expect(screen.getByRole("button", { name: "测试文献" })).toBeTruthy();
});

it("opens a quoted paper in the sidebar with its saved block locator", async () => {
  let openPaper: ((reference: PaperQuote) => boolean) | undefined;
  const quote = {
    kind: "parsed_block" as const,
    user_paper_id: "paper-1",
    version: "v1",
    page: 2,
    block_id: 4,
    start: 0,
    end: 4,
    selected_text: "引文",
    comment: "",
  };
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ChatQuoteContext.Provider
        value={{
          register: () => () => {},
          add: () => true,
          registerPaperOpener: (_sessionId, opener) => {
            openPaper = opener;
            return () => {
              openPaper = undefined;
            };
          },
          openPaper: () => true,
        }}
      >
        <ConversationPapersPanel projectId="project-1" sessionId="session-1" />
      </ChatQuoteContext.Provider>
    </QueryClientProvider>,
  );
  act(() => {
    expect(openPaper?.(quote)).toBe(true);
  });
  expect(
    screen
      .getByRole("region", { name: "侧栏阅读器" })
      .getAttribute("data-located-block"),
  ).toBe("4");
});

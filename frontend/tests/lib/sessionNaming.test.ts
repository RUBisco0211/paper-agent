import { UserMsg } from "@agentscope-ai/agentscope/message";
import { expect, it } from "vitest";

import { createQueryClient } from "@/app/query";
import { applySessionName, sessionNameInput } from "@/lib/sessionNaming";

it("builds naming input from the first prompt and its quote references", () => {
  const message = UserMsg({ name: "user", content: "比较这两篇文献" });
  message.metadata = {
    paper_agent: {
      body: "比较这两篇文献",
      references: [
        {
          kind: "parsed_block",
          user_paper_id: "paper-1",
          version: "v1",
          page: 2,
          selected_text: "检索增强生成的局限",
          comment: "关注召回率",
        },
        {
          kind: "pdf_selection",
          user_paper_id: "paper-2",
          version: "v1",
          page: 3,
          selected_text: "方法对比",
          comment: "",
        },
      ],
    },
  };

  expect(sessionNameInput(message)).toEqual({
    text: "比较这两篇文献",
    excerpts: ["检索增强生成的局限\n评论：关注召回率", "方法对比"],
  });
});

it("keeps a reference-only first prompt as naming input", () => {
  const message = UserMsg({ name: "user", content: "" });
  message.metadata = {
    paper_agent: {
      body: "",
      references: [
        {
          kind: "message",
          source_message_id: "message-1",
          block_index: 0,
          start: 0,
          end: 2,
          selected_text: "关键结论",
          comment: "",
        },
      ],
    },
  };

  expect(sessionNameInput(message)).toEqual({
    text: "",
    excerpts: ["关键结论"],
  });
});

it("uses an image quote source when a reference has no selected text", () => {
  const message = UserMsg({ name: "user", content: "" });
  message.metadata = {
    paper_agent: {
      body: "",
      references: [
        {
          kind: "parsed_block",
          user_paper_id: "paper-1",
          version: "v1",
          page: 4,
          selected_text: "",
          comment: "",
          include_image: true,
          source_title: "检索增强生成综述",
        },
      ],
    },
  };

  expect(sessionNameInput(message)).toEqual({
    text: "",
    excerpts: ["检索增强生成综述"],
  });
});

it("updates the cached session name in the sidebar and chat lists", () => {
  const queryClient = createQueryClient();
  queryClient.setQueryData(["bound-sessions"], [
    {
      agentId: "agent-1",
      session: {
        session: { id: "session-1", config: { name: "2026-10-19 10:00:00" } },
      },
      binding: { session_id: "session-1", project_id: null, scope: "library" },
    },
  ] as never);
  queryClient.setQueryData(["agent-sessions", "agent-1"], {
    sessions: [
      { session: { id: "session-1", config: { name: "2026-10-19 10:00:00" } } },
    ],
    total: 1,
  } as never);

  applySessionName(queryClient, "agent-1", "session-1", "RAG 方法比较");

  const bound = queryClient.getQueryData(["bound-sessions"]) as Array<{
    session: { session: { config: { name: string } } };
  }>;
  expect(bound[0].session.session.config.name).toBe("RAG 方法比较");
  const chats = queryClient.getQueryData(["agent-sessions", "agent-1"]) as {
    sessions: Array<{ session: { config: { name: string } } }>;
  };
  expect(chats.sessions[0].session.config.name).toBe("RAG 方法比较");
});

// @vitest-environment jsdom
import type { Msg, ToolCallBlock } from "@agentscope-ai/agentscope/message";
import { ReplyFinishedReason } from "@agentscope-ai/agentscope/event";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import "@upstream/i18n";
import { StatusBadge } from "@upstream/components/badge/StatusBadge";
import { TooltipProvider } from "@upstream/components/ui/tooltip";
import { ASMessageBubble } from "./ASMessageBubble";
import { ConfirmCard } from "./ConfirmCard";
import { TextInput } from "./TextInput";
import { ToolStateIcon } from "./tool-renderers/_shared";

it("Chat input uses the theme radius when the composer is rendered", () => {
  const { container } = render(
    <TooltipProvider>
      <TextInput
        onSend={vi.fn()}
        fileProcessor={async () => null}
        allowedInputTypes={[]}
      />
    </TooltipProvider>,
  );
  expect(
    container
      .querySelector('[data-tour="chat-input"]')
      ?.classList.contains("rounded-lg"),
  ).toBe(true);
  for (const button of screen.getAllByRole("button")) {
    expect(button.classList.contains("rounded-md")).toBe(true);
    expect(button.classList.contains("rounded-full")).toBe(false);
  }
});

it("Confirmation preview uses the theme surface when tool approval is pending", () => {
  const call = {
    id: "approval",
    type: "tool_call",
    name: "import_papers",
    input: '{"count":2}',
  } as ToolCallBlock;
  const { container } = render(
    <ConfirmCard
      toolCall={call}
      onUserConfirm={vi.fn().mockResolvedValue(undefined)}
    />,
  );
  const preview = screen.getByText(/"count"/).closest(".overflow-y-auto")!;
  expect(preview.classList.contains("bg-background")).toBe(true);
  expect(preview.classList.contains("bg-white")).toBe(false);
  expect(container.firstElementChild?.classList.contains("rounded-lg")).toBe(
    true,
  );
});

it.each([
  {
    status: "completed" as const,
    foreground: "text-success",
    background: "bg-success/10",
  },
  {
    status: "failed" as const,
    foreground: "text-destructive",
    background: "bg-destructive/10",
  },
])(
  "Status badge uses semantic colors when execution is $status",
  ({ status, foreground, background }) => {
    const { container } = render(<StatusBadge status={status} />);
    expect(container.firstElementChild?.classList.contains(foreground)).toBe(
      true,
    );
    expect(container.firstElementChild?.classList.contains(background)).toBe(
      true,
    );
  },
);

it.each([
  { state: "success" as const, foreground: "text-success" },
  { state: "error" as const, foreground: "text-destructive" },
])(
  "Tool result uses the semantic status color when its state is $state",
  ({ state, foreground }) => {
    const { container } = render(<ToolStateIcon state={state} />);
    expect(container.querySelector("svg")?.classList.contains(foreground)).toBe(
      true,
    );
  },
);

it("Message error uses the theme surface when the assistant reply fails", () => {
  const message = {
    id: "failed-reply",
    role: "assistant",
    content: [],
    created_at: "2026-10-06T00:00:00Z",
    finished_at: "2026-10-06T00:00:04Z",
    finished_reason: ReplyFinishedReason.ERROR,
  } as unknown as Msg;
  render(<ASMessageBubble message={message} onUserConfirm={() => {}} />);
  const alert = screen.getByRole("alert");
  expect(alert.classList.contains("bg-destructive/10")).toBe(true);
  expect(alert.classList.contains("border-destructive/30")).toBe(true);
  expect(alert.className).not.toMatch(/(?:dark:)?(?:bg|border|text)-red-/);
});

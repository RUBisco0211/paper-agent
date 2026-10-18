// @vitest-environment jsdom
import type { Msg } from "@agentscope-ai/agentscope/message";
import { ReplyFinishedReason } from "@agentscope-ai/agentscope/event";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import "@/i18n";
import { TooltipProvider } from "@/components/ui/Tooltip";
import { MessageBubble } from "./MessageBubble";
import { TextInput } from "./TextInput";
import { ToolStateIcon } from "@/components/chat/toolRenderers/shared";

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
  render(<MessageBubble message={message} onUserConfirm={() => {}} />);
  const alert = screen.getByRole("alert");
  expect(alert.classList.contains("bg-(--destructive-subtle)")).toBe(true);
  expect(alert.classList.contains("border-(--destructive-border)")).toBe(true);
  expect(alert.className).not.toMatch(/(?:dark:)?(?:bg|border|text)-red-/);
});

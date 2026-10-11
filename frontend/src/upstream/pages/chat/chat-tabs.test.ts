import { expect, it } from "vitest"

import { closeChatTab, readChatTabs, replaceDraftTab } from "./chat-tabs"

it("restores only unique chat routes from saved tabs", () => {
  expect(readChatTabs(JSON.stringify({ paths: ["/chat/a/1", "/chat/a/1", "/library", "/chat/new"], activePath: "/chat/a/1" }))).toEqual({ paths: ["/chat/a/1", "/chat/new"], activePath: "/chat/a/1" })
})

it("shows no tabs when the last tab closes", () => {
  expect(closeChatTab(["/chat/a/1"], "/chat/a/1", "/chat/a/1")).toEqual({ paths: [], activePath: "/chat" })
})

it("replaces the draft tab with the new session after its first message", () => {
  expect(replaceDraftTab(["/chat/a/1", "/chat/new"], "/chat/new", "/chat/a/2")).toEqual(["/chat/a/1", "/chat/a/2"])
})

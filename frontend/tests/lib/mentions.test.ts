import { describe, expect, it } from "vitest"

import {
  mentionLabel,
  mentionPlaceholders,
  mentionRequest,
  mentionTag,
  readMessageMentions,
  renderMessageMentions,
} from "@/lib/mentions"

const scalable = { user_paper_id: "p-1", title: "Safe and Scalable Payload Transport" }
const filtering = { user_paper_id: "p-2", title: "Beyond Safety Filtering" }

describe("mention placeholders", () => {
  it("numbers the tokens in the order they appear in the message", () => {
    expect(
      mentionPlaceholders(`先看 @${scalable.title}，再看 @${filtering.title}`, [scalable, filtering]),
    ).toEqual({
      text: "先看 @{{1}}，再看 @{{2}}",
      mentions: [scalable, filtering],
    })
  })

  it("leaves no gap in the numbering when a token is already gone", () => {
    expect(mentionPlaceholders(`只看 @${filtering.title}`, [scalable, filtering])).toEqual({
      text: "只看 @{{1}}",
      mentions: [filtering],
    })
  })

  it("returns the text untouched when the message names no paper", () => {
    expect(mentionPlaceholders("讲讲这两篇", [])).toEqual({
      text: "讲讲这两篇",
      mentions: [],
    })
  })
})

describe("mention request payload", () => {
  it("indexes the mentions from one so they line up with the placeholders", () => {
    expect(mentionRequest([scalable, filtering])).toEqual([
      { index: 1, user_paper_id: "p-1" },
      { index: 2, user_paper_id: "p-2" },
    ])
  })
})

const recorded = {
  index: 1,
  user_paper_id: "p-1",
  title: "Safe and Scalable Payload Transport",
  has_fulltext: true,
}

describe("mentions recorded on a sent message", () => {
  it("reads them from the message metadata", () => {
    expect(
      readMessageMentions({ paper_agent: { mentions: [recorded, { index: "x" }] } }),
    ).toEqual([recorded])
  })

  it("reads nothing when the message recorded none", () => {
    expect(readMessageMentions({ paper_agent: { body: "正文" } })).toEqual([])
    expect(readMessageMentions(null)).toEqual([])
  })

  it("shortens a long title for a chip", () => {
    expect(mentionLabel("Safe and Scalable Payload Transport")).toBe("Safe and Scalable Payloa…")
    expect(mentionLabel("短标题")).toBe("短标题")
  })

  it("replaces the marker the service wrote with the chip markup", () => {
    expect(
      renderMessageMentions(
        "对比 @《Safe and Scalable Payload Transport》(paper:p-1)（待补全文）和正文",
        [recorded],
        mentionTag,
      ),
    ).toBe(
      '对比 <paper-mention title="Safe and Scalable Payload Transport">@Safe and Scalable Payloa…</paper-mention>和正文',
    )
  })

  it("leaves text that only looks like a marker untouched", () => {
    expect(
      renderMessageMentions("@《另一篇文献》(paper:p-9) 讲了什么", [recorded], mentionTag),
    ).toBe("@《另一篇文献》(paper:p-9) 讲了什么")
  })

  it("chips the readable token of a message this tab just sent", () => {
    expect(
      renderMessageMentions(
        "对比 @Safe and Scalable Payload Transport 和正文",
        [recorded],
        mentionTag,
      ),
    ).toBe(
      '对比 <paper-mention title="Safe and Scalable Payload Transport">@Safe and Scalable Payloa…</paper-mention> 和正文',
    )
  })
})

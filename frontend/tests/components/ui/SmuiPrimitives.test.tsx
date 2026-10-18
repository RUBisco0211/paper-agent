// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { FieldLegend, FieldTitle } from "@/components/ui/Field";
import { Label } from "@/components/ui/Label";

import { Card, CardTitle } from "@/components/ui/Card";
import { ScrollBar } from "@/components/ui/ScrollArea";

const labelClasses = [
  "text-label",
  "text-muted-foreground",
  "uppercase",
  "tracking-label",
  "font-normal",
];

afterEach(cleanup);

describe("SMUI business primitives", () => {
  it("Button uses the UI text token when rendered without styling overrides", () => {
    render(<Button>Continue</Button>);
    expect(screen.getByRole("button").classList.contains("text-ui")).toBe(true);
  });

  it.each([
    ["Label", <Label key="label">Name</Label>],
    ["FieldTitle", <FieldTitle key="title">Name</FieldTitle>],
    [
      "FieldLegend",
      <fieldset key="legend">
        <FieldLegend variant="label">Name</FieldLegend>
      </fieldset>,
    ],
  ])(
    "%s supplies the label typography when rendered without call-site styles",
    (_, element) => {
      render(element);
      expect([...screen.getByText("Name").classList]).toEqual(
        expect.arrayContaining(labelClasses),
      );
    },
  );

  it("CardTitle supplies muted uppercase typography when rendered without call-site styles", () => {
    render(<CardTitle>Account</CardTitle>);
    expect([...screen.getByText("Account").classList]).toEqual(
      expect.arrayContaining([
        "text-xs",
        "text-muted-foreground",
        "uppercase",
        "tracking-label",
        "font-normal",
      ]),
    );
  });

  it("Card uses a glowing border instead of elevation when rendered", () => {
    const { container } = render(<Card>Account</Card>);
    const card = container.querySelector('[data-slot="card"]')!;
    expect([...card.classList]).toEqual(
      expect.arrayContaining([
        "card-glow",
        "border",
        "border-border",
        "flex",
        "flex-col",
        "gap-6",
        "py-6",
      ]),
    );
    expect(card.className).not.toMatch(/\b(?:shadow|ring)-/);
  });

  it("Badge uses label typography and theme radius when rendered", () => {
    render(<Badge>Ready</Badge>);
    const badge = screen.getByText("Ready");
    expect([...badge.classList]).toEqual(
      expect.arrayContaining([
        "text-label",
        "uppercase",
        "tracking-label",
        "rounded-md",
      ]),
    );
    expect(badge.classList.contains("rounded-full")).toBe(false);
  });

  it("ScrollBar uses theme radius when composing its thumb", () => {
    const scrollbar = ScrollBar({});
    const thumb = scrollbar.props.children;
    expect(thumb.props.className.split(" ")).toContain("rounded-sm");
    expect(thumb.props.className.split(" ")).not.toContain("rounded-full");
  });

  it("Checkbox uses theme radius when rendered", () => {
    render(<Checkbox aria-label="Select" />);
    expect(
      screen.getByRole("checkbox").classList.contains("rounded-[4px]"),
    ).toBe(true);
    expect(screen.getByRole("checkbox").className).not.toContain(
      "rounded-full",
    );
  });
});

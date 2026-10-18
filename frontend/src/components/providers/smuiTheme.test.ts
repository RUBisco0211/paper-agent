import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { cn } from "@/lib/utils";

const css = readFileSync(
  new URL("../../index.css", import.meta.url),
  "utf8",
);

function palette(selector: string) {
  const start = css.indexOf("{", css.indexOf(`${selector} {`));
  let depth = 1;
  let end = start + 1;
  while (depth && end < css.length) {
    if (css[end] === "{") depth++;
    if (css[end] === "}") depth--;
    end++;
  }
  const block = css.slice(start + 1, end - 1).replace(/\/\*[\s\S]*?\*\//g, "");
  return Object.fromEntries(
    [...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(([, key, value]) => [
      key,
      value.trim(),
    ]),
  );
}

const light = palette(":root");
const dark = { ...light, ...palette(".dark") };

function resolve(tokens: Record<string, string>, name: string): string {
  const value = tokens[name];
  if (!value) throw new Error(`Missing theme token: ${name}`);
  return value.replace(/var\((--[\w-]+)\)/g, (_, key: string) =>
    resolve(tokens, key),
  );
}

function rgb(color: string) {
  const match = color.match(/^hsl\(([\d.]+) ([\d.]+)% ([\d.]+)%\)$/);
  if (!match)
    throw new Error(`Expected an opaque HSL color, received ${color}`);
  const [, hue, saturation, lightness] = match.map(Number);
  const s = saturation / 100;
  const l = lightness / 100;
  const a = s * Math.min(l, 1 - l);
  return [0, 8, 4].map((offset) => {
    const k = (offset + hue / 30) % 12;
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  });
}

function luminance(color: string | number[]) {
  const linear = (typeof color === "string" ? rgb(color) : color).map(
    (value) =>
      value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(
  tokens: Record<string, string>,
  foreground: string,
  background: string,
) {
  const values = [
    luminance(resolve(tokens, foreground)),
    luminance(resolve(tokens, background)),
  ].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

describe("SMUI theme", () => {
  it("uses Snow Storm surfaces when the system is light", () => {
    expect(resolve(light, "--background")).toBe("hsl(218 27% 94%)");
    expect(resolve(light, "--primary")).toBe("hsl(213 32% 40%)");
  });

  it("uses Polar Night surfaces when the system is dark", () => {
    expect(resolve(dark, "--background")).toBe("hsl(213 16% 12%)");
    expect(resolve(dark, "--primary")).toBe("hsl(193 44% 67%)");
  });

  it("keeps control corners sharp when the radius scale is inherited", () => {
    expect(light["--radius"]).toBe("0rem");
    expect(css).toContain("--radius-xs: var(--radius)");
    expect(css).toContain("--radius-2xl: calc(var(--radius) * 1.8)");
  });

  it.each(["light", "dark"])(
    "keeps body and action text readable when the mode is %s",
    (mode) => {
      const tokens = mode === "light" ? light : dark;
      for (const [foreground, background] of [
        ["--foreground", "--background"],
        ["--muted-foreground", "--card"],
        ["--primary-foreground", "--primary"],
        ["--accent-foreground", "--accent"],
      ]) {
        expect(
          contrast(tokens, foreground, background),
          `${foreground} on ${background}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    },
  );

  it.each(["light", "dark"])(
    "keeps status text readable when the mode is %s",
    (mode) => {
      const tokens = mode === "light" ? light : dark;
      for (const foreground of [
        "--success",
        "--warning",
        "--info",
        "--destructive",
      ]) {
        expect(
          contrast(tokens, foreground, "--background"),
          foreground,
        ).toBeGreaterThanOrEqual(4.5);
      }
    },
  );

  it.each(["light", "dark"])(
    "keeps status text readable on tinted surfaces when the mode is %s",
    (mode) => {
      const tokens = mode === "light" ? light : dark;
      for (const foreground of [
        "--success",
        "--warning",
        "--info",
        "--destructive",
      ]) {
        const ink = rgb(resolve(tokens, foreground));
        for (const surface of ["--background", "--card"]) {
          const base = rgb(resolve(tokens, surface));
          for (const opacity of [0.1, 0.15, 0.2]) {
            const fill = base.map(
              (channel, index) =>
                channel * (1 - opacity) + ink[index] * opacity,
            );
            const values = [luminance(ink), luminance(fill)].sort(
              (a, b) => b - a,
            );
            expect(
              (values[0] + 0.05) / (values[1] + 0.05),
              `${foreground}/${opacity} on ${surface}`,
            ).toBeGreaterThanOrEqual(4.5);
          }
        }
      }
    },
  );

  it("uses a locally loaded monospace face when typography is inherited", () => {
    expect(css).toMatch(
      /@import\s+["']@fontsource-variable\/jetbrains-mono["']/,
    );
    expect(css).toMatch(/--font-sans:\s*["']JetBrains Mono Variable["']/);
    expect(css).not.toContain("fonts.googleapis.com");
  });

  it("retains the custom font size and semantic color when classes are merged", () => {
    expect(cn("text-sm text-muted-foreground", "text-ui")).toBe(
      "text-muted-foreground text-ui",
    );
    expect(cn("text-label text-primary", "text-destructive")).toBe(
      "text-label text-destructive",
    );
  });
});

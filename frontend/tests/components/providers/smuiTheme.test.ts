import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { cn } from "@/lib/utils";

const css = readFileSync(
  new URL("../../../src/index.css", import.meta.url),
  "utf8",
);

/** 配色已拆到主题文件，:root 里的颜色 token 从这里取。 */
const themeCss = readFileSync(
  new URL("../../../src/styles/themes/vintage-paper.css", import.meta.url),
  "utf8",
);

function palette(selector: string, source: string = themeCss) {
  const start = source.indexOf("{", source.indexOf(`${selector} {`));
  let depth = 1;
  let end = start + 1;
  while (depth && end < source.length) {
    if (source[end] === "{") depth++;
    if (source[end] === "}") depth--;
    end++;
  }
  const block = source.slice(start + 1, end - 1).replace(/\/\*[\s\S]*?\*\//g, "");
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

/** oklch 的色相/彩度/明度换算成 sRGB，用于对比度判断。 */
function oklchToRgb(lightness: number, chroma: number, hue: number) {
  const radians = (hue * Math.PI) / 180;
  const a = chroma * Math.cos(radians);
  const b = chroma * Math.sin(radians);
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const linear = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  return linear.map((value) => Math.min(1, Math.max(0, value)));
}

function rgb(color: string) {
  const oklch = color.match(
    /^oklch\(([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+))?\)$/,
  );
  if (oklch) {
    const [, l, c, h, alpha] = oklch;
    if (alpha !== undefined && Number(alpha) !== 1)
      throw new Error(`Expected an opaque color, received ${color}`);
    return oklchToRgb(Number(l), Number(c), Number(h));
  }
  const match = color.match(/^hsl\(([\d.]+) ([\d.]+)% ([\d.]+)%\)$/);
  if (!match)
    throw new Error(`Expected an opaque HSL or OKLCH color, received ${color}`);
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
  it("uses paper surfaces when the system is light", () => {
    expect(resolve(light, "--background")).toBe("oklch(0.9518 0.0054 95.1011)");
    expect(resolve(light, "--primary")).toBe("oklch(0.5943 0.0251 67.3138)");
  });

  it("uses dark paper surfaces when the system is dark", () => {
    expect(resolve(dark, "--background")).toBe("oklch(0.2741 0.0047 67.6302)");
    // 暗色主按钮提亮，使可见文字与底色对比达到 4.5:1。
    expect(resolve(dark, "--primary")).toBe("oklch(0.8000 0.0185 67.5245)");
  });

  it("keeps control corners when the radius scale is inherited", () => {
    // 配色主题覆盖圆角时也会显式给出；这里只确认它是个确定值。
    const radius = light["--radius"] ?? palette(":root", css)["--radius"];
    expect(radius).toBeTruthy();
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

  it("uses a locally loaded face for latin text and code", () => {
    expect(css).toMatch(/@import\s+["']@fontsource\/maple-mono\/400\.css["']/);
    expect(css).toMatch(/--font-sans:\s*"Maple Mono", "PingFang SC"/);
    expect(css).toMatch(/--font-mono:\s*"Maple Mono", "PingFang SC"/);
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

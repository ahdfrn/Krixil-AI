/**
 * Real Ink-render tests for the components ui/*.tsx can't otherwise be checked by — a pure
 * render.ts test proves the data-shaping logic is right, but not that Yoga's flexbox actually
 * lays it out sanely. Caught live: StatusBar's two sides ran together with zero gap between them
 * because a Box with no explicit width has nothing for justifyContent: "space-between" to
 * distribute — this file exists so that class of bug doesn't come back silently.
 */
import React from "react";
import { render } from "ink-testing-library";
import { describe, expect, it } from "vitest";
import { StatusBar } from "../ui/StatusBar.js";

describe("StatusBar", () => {
  it("keeps a real gap between the summary and the keyboard hints", () => {
    const { lastFrame, unmount } = render(<StatusBar toolCalls={3} testAttempts={1} />);
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("3 tool calls");
    expect(frame).toContain("1 test attempt");
    expect(frame).toContain("/help /model /cwd /undo /exit");
    // The regression this guards: summary and hints must not be directly adjacent with no
    // whitespace between them (e.g. "...attempt/help..." instead of "...attempt   /help...").
    expect(frame).not.toMatch(/attempts?\/help/);
  });

  it("omits the test-attempt segment when there are none", () => {
    const { lastFrame, unmount } = render(<StatusBar toolCalls={0} testAttempts={0} />);
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("0 tool calls");
    expect(frame).not.toContain("test attempt");
  });
});

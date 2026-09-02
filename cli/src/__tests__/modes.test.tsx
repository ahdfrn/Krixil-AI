import React from "react";
import { render } from "ink-testing-library";
import { describe, expect, it, vi } from "vitest";
import { App } from "../ui/App.js";
import type { KrixilApi } from "../api.js";

// UI tests must never checkpoint or execute verification commands against the user's repo.
vi.mock("../checkpoint.js", () => ({
  autoCheckpoint: vi.fn(async () => null),
  workingTreeChangeSummary: vi.fn(async () => null),
  findLastCheckpoint: vi.fn(async () => null),
  diffStatSinceCheckpoint: vi.fn(async () => ""),
  resetToBeforeCheckpoint: vi.fn(),
}));
vi.mock("../projectConfig.js", () => ({ loadProjectConfig: () => null }));

const tick = () => new Promise((resolve) => setTimeout(resolve, 20));
const ENTER = "\r", TAB = "\t", DOWN = "\u001b[B", ESC = "\u001b";

function setup() {
  const run = { id: "run-1", status: "completed", steps: [], final_response: "Done" };
  const api = {
    listModels: vi.fn(async () => []),
    chat: vi.fn(async () => ({ conversation_id: "private-session", message: { content: "Hello" }, model: "mock" })),
    publicChat: vi.fn(async () => ({ content: "Public answer", model: "nemotron", provider: "openrouter" })),
    runAgent: vi.fn(async () => run),
    getStatus: vi.fn(async () => run),
  };
  const screen = render(<App api={api as unknown as KrixilApi} hostRoot="D:\\" initialDir="Krixil" />);
  const write = async (value: string) => { screen.stdin.write(value); await tick(); };
  return { api, screen, write };
}

describe("Chat / Code modes and two-choice model menu", () => {
  it("starts in Chat and Tab preserves the draft without submitting", async () => {
    const { api, screen, write } = setup();
    try {
      await tick();
      expect(screen.lastFrame()).toContain("[CHAT]");
      await write("my draft");
      await write(TAB);
      expect(screen.lastFrame()).toContain("[CODE]");
      expect(screen.lastFrame()).toContain("> my draft");
      await write(TAB);
      expect(screen.lastFrame()).toContain("[CHAT]");
      expect(api.chat).not.toHaveBeenCalled();
      expect(api.runAgent).not.toHaveBeenCalled();
    } finally { screen.unmount(); }
  });

  it("routes plain input in Code to the agent, then Chat to conversation", async () => {
    const { api, screen, write } = setup();
    try {
      await tick(); await write(TAB); await write("fix the bug"); await write(ENTER);
      expect(api.runAgent).toHaveBeenCalledOnce();
      expect(api.runAgent.mock.calls[0]).toEqual([expect.stringContaining("fix the bug"), "auto", undefined, "native"]);
      expect(api.chat).not.toHaveBeenCalled();
      await write(TAB); await write("hello"); await write(ENTER);
      expect(api.chat).toHaveBeenCalledOnce();
    } finally { screen.unmount(); }
  });

  it("slash opens choices without sending; Escape returns to an empty prompt", async () => {
    const { api, screen, write } = setup();
    try {
      await tick(); await write("/");
      expect(screen.lastFrame()).toContain("SELECT MODEL");
      expect(screen.lastFrame()).toContain("Auto");
      expect(screen.lastFrame()).toContain("NVIDIA");
      await write(ESC);
      expect(screen.lastFrame()).not.toContain("SELECT MODEL");
      expect(screen.lastFrame()).toContain("Type a message…");
      expect(api.chat).not.toHaveBeenCalled();
      expect(api.publicChat).not.toHaveBeenCalled();
    } finally { screen.unmount(); }
  });

  it("NVIDIA requires consent; Tab to Code resets to Auto without sharing draft/history", async () => {
    const { api, screen, write } = setup();
    try {
      await tick(); await write("hello"); await write(ENTER);
      await write("/"); await write(DOWN); await write(ENTER);
      expect(screen.lastFrame()).toContain("NVIDIA · public only");
      await write("explain recursion"); await write(ENTER);
      expect(api.publicChat).not.toHaveBeenCalled();
      await write(TAB);
      expect(screen.lastFrame()).toContain("[CHAT]");
      await write("y");
      expect(api.publicChat).toHaveBeenCalledWith("explain recursion", expect.any(AbortSignal));
      await write(TAB);
      expect(screen.lastFrame()).toContain("[CODE]");
      expect(screen.lastFrame()).not.toContain("NVIDIA · public only");
      await write("fix another bug"); await write(ENTER);
      expect(api.runAgent.mock.calls[0]).toEqual([expect.any(String), "auto", undefined, "native"]);
      expect(api.publicChat).toHaveBeenCalledOnce();
    } finally { screen.unmount(); }
  });

  it("selecting NVIDIA from Code returns to Chat; Auto is selectable again", async () => {
    const { screen, write } = setup();
    try {
      await tick(); await write(TAB); await write("/"); await write(DOWN); await write(ENTER);
      expect(screen.lastFrame()).toContain("[CHAT]");
      expect(screen.lastFrame()).toContain("NVIDIA · public only");
      await write("/"); await write(DOWN); await write(ENTER);
      expect(screen.lastFrame()).not.toContain("NVIDIA · public only");
    } finally { screen.unmount(); }
  });

  it("a slash inside a draft is ordinary text, not a model switch", async () => {
    const { screen, write } = setup();
    try {
      await tick(); await write("explain src"); await write("/"); await write("app");
      expect(screen.lastFrame()).toContain("explain src/app");
      expect(screen.lastFrame()).not.toContain("SELECT MODEL");
    } finally { screen.unmount(); }
  });

  it("does not change mode or model while a response is pending", async () => {
    const { api, screen, write } = setup();
    let complete!: (value: { conversation_id: string; message: { content: string }; model: string }) => void;
    api.chat.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    try {
      await tick(); await write("hello"); await write(ENTER);
      await write(TAB);
      expect(screen.lastFrame()).toContain("[CHAT]");
      await write("/");
      expect(screen.lastFrame()).not.toContain("SELECT MODEL");
      expect(api.runAgent).not.toHaveBeenCalled();
      complete({ conversation_id: "private-session", message: { content: "Hello" }, model: "mock" });
      await tick();
      await write(TAB);
      expect(screen.lastFrame()).toContain("[CODE]");
    } finally { screen.unmount(); }
  });
});

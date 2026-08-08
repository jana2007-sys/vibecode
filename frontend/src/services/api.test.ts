import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CandidateProfile } from "../types/candidate";
import { api, parseInterviewResponse } from "./api";

const candidate: CandidateProfile = {
  id: "custom-abc",
  name: "Riley Doe",
  role: "Backend Developer",
  experience_level: "mid",
  years_of_experience: 3,
  skills: [{ name: "Python", level: "intermediate" }],
  learning_journey: [],
  preferred_languages: ["Python"],
  focus_areas: ["Backend API design"],
  notes: "",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function postedBody(callIndex = 0): unknown {
  const init = vi.mocked(globalThis.fetch).mock.calls[callIndex][1] as RequestInit;
  return JSON.parse(String(init.body));
}

describe("api.startInterview", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs { sessionId, candidate } to /api/interview", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse({ reply: "Welcome!", done: false })
    );

    const response = await api.startInterview("sess-1", candidate);

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/interview",
      expect.objectContaining({ method: "POST" })
    );
    expect(postedBody()).toEqual({ sessionId: "sess-1", candidate });
    expect(response).toEqual({ reply: "Welcome!", done: false });
  });

  it("POSTs { sessionId, message } when continuing the interview", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse({ reply: "Next question", done: false })
    );

    await api.continueInterview("sess-1", "I can explain this.");

    expect(postedBody()).toEqual({ sessionId: "sess-1", message: "I can explain this." });
  });
});

describe("parseInterviewResponse", () => {
  it("parses a minimal in-progress response", () => {
    expect(parseInterviewResponse({ reply: "Hi", done: false })).toEqual({
      reply: "Hi",
      done: false,
      feedback: null,
    });
  });

  it("parses a completed response with feedback", () => {
    const raw = {
      reply: "Done",
      done: true,
      feedback: { summary: "Nice", strengths: ["Python"], gaps: [], next: ["SQL"] },
    };
    expect(parseInterviewResponse(raw)).toEqual(raw);
  });

  it("rejects malformed payloads", () => {
    expect(() => parseInterviewResponse(null)).toThrow();
    expect(() => parseInterviewResponse({ reply: "" })).toThrow();
    expect(() => parseInterviewResponse({ reply: "x", done: "yes" })).toThrow();
  });
});

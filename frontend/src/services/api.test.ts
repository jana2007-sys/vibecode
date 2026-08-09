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

describe("candidate endpoints", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists candidates from GET /api/candidates", async () => {
    const items = [
      { id: "candidate-001", name: "Alex Rivera", email: "alex@example.com", skills: [], learning_journey: [] },
    ];
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse({ items, total: 1 })
    );

    const result = await api.listCandidates();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/candidates",
      expect.anything()
    );
    expect(result).toEqual({ items, total: 1 });
  });

  it("creates a candidate with POST /api/candidates", async () => {
    const created = { id: "candidate-999", name: "Riley Doe", skills: [], learning_journey: [] };
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(created));

    const result = await api.createCandidate({
      name: "Riley Doe",
      email: "riley@example.com",
      role: "Backend Developer",
      skills: [],
      learning_journey: [],
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/candidates",
      expect.objectContaining({ method: "POST" })
    );
    expect(postedBody()).toMatchObject({ name: "Riley Doe", email: "riley@example.com" });
    expect(result).toEqual(created);
  });

  it("fetches a candidate's interview history", async () => {
    const history = { candidate_id: "candidate-001", items: [], total: 0 };
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(history));

    const result = await api.getCandidateHistory("candidate-001");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/candidates/candidate-001/interviews",
      expect.anything()
    );
    expect(result).toEqual(history);
  });

  it("fetches a report for a session", async () => {
    const report = {
      session_id: "sess-1",
      candidate: { id: "candidate-001", name: "Alex Rivera", role: "Backend Engineer" },
      feedback: { summary: "Nice", strengths: [], improvements: [], topics: [] },
    };
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(report));

    const result = await api.getReport("candidate-001", "sess-1");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/candidates/candidate-001/interviews/sess-1/report",
      expect.anything()
    );
    expect(result).toEqual(report);
  });

  it("builds the PDF download URL", () => {
    expect(api.reportPdfUrl("candidate-001", "sess-1")).toBe(
      "/api/candidates/candidate-001/interviews/sess-1/report/pdf"
    );
  });
});

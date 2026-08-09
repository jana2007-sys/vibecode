import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InterviewProvider } from "../context/InterviewContext";
import type { Candidate, CandidateCreate, CandidateProfile } from "../types/candidate";
import type { InterviewResponse } from "../types/interview";
import { CandidateSelection } from "./CandidateSelection";

const seeded: Candidate[] = [
  {
    id: "candidate-001",
    name: "Alex Rivera",
    email: "alex@example.com",
    role: "Backend Engineer",
    years_of_experience: 2,
    experience_level: "mid",
    skills: [
      { name: "Python", level: "intermediate" },
      { name: "SQL", level: "beginner" },
    ],
    learning_journey: [
      { type: "project", title: "RESTful Blog API", description: "" },
    ],
    preferred_languages: ["Python"],
    focus_areas: ["Backend API design"],
    strengths: ["Debugging"],
    notes: "",
  },
];

const apiMock = vi.hoisted(() => ({
  listCandidates: vi.fn<() => Promise<{ items: Candidate[]; total: number }>>(),
  createCandidate: vi.fn<(body: CandidateCreate) => Promise<Candidate>>(),
  startInterview: vi.fn<(sessionId: string, candidate: CandidateProfile) => Promise<unknown>>(),
  continueInterview: vi.fn<(sessionId: string, message: string) => Promise<unknown>>(),
  health: vi.fn<() => Promise<unknown>>(),
  getCandidateHistory: vi.fn(),
  getReport: vi.fn(),
  reportPdfUrl: vi.fn<(candidateId: string, sessionId: string) => string>(),
}));

vi.mock("../services/api", () => ({
  api: apiMock,
  parseInterviewResponse: (value: unknown) => value as InterviewResponse,
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/candidates"]}>
      <InterviewProvider>
        <Routes>
          <Route path="/candidates" element={<CandidateSelection />} />
          <Route path="/interview" element={<div>Interview page</div>} />
        </Routes>
      </InterviewProvider>
    </MemoryRouter>
  );
}

describe("CandidateSelection", () => {
  beforeEach(() => {
    apiMock.startInterview.mockClear();
    apiMock.createCandidate.mockClear();
    apiMock.listCandidates.mockResolvedValue({ items: seeded, total: seeded.length });
  });

  it("loads candidates from the backend and shows the selected profile", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/Who's taking the interview\?/i)).toBeInTheDocument()
    );
    expect(screen.getAllByText("Alex Rivera").length).toBeGreaterThan(0);
    expect(screen.getByText("alex@example.com")).toBeInTheDocument();
  });

  it("shows an empty state when the backend has no candidates", async () => {
    apiMock.listCandidates.mockResolvedValue({ items: [], total: 0 });
    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create Your Profile" })).toBeInTheDocument()
    );
  });

  it("opens the profile form when the card is clicked", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create Your Profile" })).toBeInTheDocument()
    );
    await user.click(screen.getByRole("button", { name: "Create Your Profile" }));

    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Target Role")).toBeInTheDocument();
    expect(screen.getByLabelText("Experience Level")).toBeInTheDocument();
    expect(screen.getByLabelText("Programming Languages")).toBeInTheDocument();
    expect(screen.getByLabelText("Technical Skills")).toBeInTheDocument();
    expect(screen.getByLabelText("Technologies")).toBeInTheDocument();
    expect(screen.getByLabelText("Focus Areas")).toBeInTheDocument();
    expect(screen.getByLabelText("Known Strengths")).toBeInTheDocument();
    expect(screen.getByLabelText("Projects")).toBeInTheDocument();
    expect(screen.getByLabelText("Notes")).toBeInTheDocument();
  });

  it("shows a validation error when submitting without a name", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create Your Profile" })).toBeInTheDocument()
    );
    await user.click(screen.getByRole("button", { name: "Create Your Profile" }));

    await user.click(screen.getByRole("button", { name: /Save Profile/ }));

    expect(screen.getByRole("alert")).toHaveTextContent("Please enter the candidate's name.");
    expect(apiMock.createCandidate).not.toHaveBeenCalled();
    expect(apiMock.startInterview).not.toHaveBeenCalled();
  });

  it("POSTs the profile to the backend and refreshes the list, but does not auto-start", async () => {
    const created: Candidate = {
      id: "candidate-999",
      name: "Riley Doe",
      email: "riley@example.com",
      role: "Backend Developer",
      years_of_experience: 6,
      experience_level: "senior",
      skills: [
        { name: "FastAPI", level: "advanced" },
        { name: "Docker", level: "advanced" },
        { name: "PostgreSQL", level: "advanced" },
      ],
      learning_journey: [{ type: "project", title: "RESTful Blog API", description: "" }],
      preferred_languages: ["Python", "SQL"],
      focus_areas: ["Backend API design", "Databases"],
      strengths: ["Debugging", "Collaboration"],
      notes: "",
    };
    apiMock.createCandidate.mockResolvedValue(created);
    apiMock.listCandidates.mockResolvedValue({ items: [...seeded, created], total: 2 });

    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create Your Profile" })).toBeInTheDocument()
    );
    await user.click(screen.getByRole("button", { name: "Create Your Profile" }));

    await user.type(screen.getByLabelText("Name"), "Riley Doe");
    await user.type(screen.getByLabelText("Email"), "riley@example.com");
    await user.type(screen.getByLabelText("Target Role"), "Backend Developer");
    await user.type(screen.getByLabelText("Programming Languages"), "Python, SQL");
    await user.type(screen.getByLabelText("Technical Skills"), "FastAPI, Docker");
    await user.type(screen.getByLabelText("Focus Areas"), "Backend API design, Databases");
    await user.type(screen.getByLabelText("Projects"), "RESTful Blog API");
    await user.type(screen.getByLabelText("Technologies"), "PostgreSQL");
    await user.type(screen.getByLabelText("Known Strengths"), "Debugging, Collaboration");
    await user.selectOptions(screen.getByLabelText("Experience Level"), "senior");

    await user.click(screen.getByRole("button", { name: /Save Profile/ }));

    await waitFor(() => expect(apiMock.createCandidate).toHaveBeenCalledTimes(1));
    const body = apiMock.createCandidate.mock.calls[0][0];
    expect(body.name).toBe("Riley Doe");
    expect(body.email).toBe("riley@example.com");
    expect(body.experience_level).toBe("senior");
    expect(body.skills.map((skill) => skill.name)).toEqual(
      expect.arrayContaining(["FastAPI", "Docker", "PostgreSQL"])
    );
    expect(body.skills.every((skill) => skill.level === "advanced")).toBe(true);
    expect(body.strengths).toEqual(["Debugging", "Collaboration"]);

    // The newly created candidate is fetched from the backend and shown.
    await waitFor(() =>
      expect(screen.getAllByText("Riley Doe").length).toBeGreaterThan(0)
    );

    // Saving a profile must NOT start an interview.
    expect(apiMock.startInterview).not.toHaveBeenCalled();
    expect(screen.queryByText("Interview page")).not.toBeInTheDocument();
  });

  it("starts the interview from a selected persisted candidate", async () => {
    apiMock.startInterview.mockResolvedValue({ reply: "Welcome!", done: false, feedback: null });

    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByText("Alex Rivera").length).toBeGreaterThan(0)
    );

    await user.click(screen.getByRole("button", { name: /Begin Interview/ }));

    await waitFor(() => expect(apiMock.startInterview).toHaveBeenCalledTimes(1));
    const [sessionId, candidate] = apiMock.startInterview.mock.calls[0];
    expect(sessionId).toEqual(expect.any(String));
    expect(candidate.id).toBe("candidate-001");
    expect(candidate.name).toBe("Alex Rivera");
    // Persisted-only fields are stripped from the wire payload.
    expect(candidate).not.toHaveProperty("email");
    expect(candidate).not.toHaveProperty("strengths");

    await waitFor(() => expect(screen.getByText("Interview page")).toBeInTheDocument());
  });

  it("closing the form does not create a candidate or start an interview", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create Your Profile" })).toBeInTheDocument()
    );
    await user.click(screen.getByRole("button", { name: "Create Your Profile" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(apiMock.createCandidate).not.toHaveBeenCalled();
    expect(apiMock.startInterview).not.toHaveBeenCalled();
  });
});

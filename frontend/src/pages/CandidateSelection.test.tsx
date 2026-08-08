import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InterviewProvider } from "../context/InterviewContext";
import type { CandidateProfile } from "../types/candidate";
import type { InterviewResponse } from "../types/interview";
import { CandidateSelection } from "./CandidateSelection";

const apiMock = vi.hoisted(() => ({
  startInterview: vi.fn<(sessionId: string, candidate: CandidateProfile) => Promise<unknown>>(),
  continueInterview: vi.fn<(sessionId: string, message: string) => Promise<unknown>>(),
  health: vi.fn<() => Promise<unknown>>(),
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

describe("CandidateSelection — Create Your Profile", () => {
  beforeEach(() => {
    apiMock.startInterview.mockClear();
  });

  it("renders the Create Your Profile card alongside the predefined candidates", () => {
    renderPage();
    expect(screen.getByRole("button", { name: "Create Your Profile" })).toBeInTheDocument();
    expect(screen.getAllByText("Create Your Profile").length).toBeGreaterThan(0);
    // Predefined candidates are still shown.
    expect(screen.getByText(/Who's taking the interview\?/i)).toBeInTheDocument();
  });

  it("opens the profile form when the card is clicked", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Create Your Profile" }));

    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Target Role")).toBeInTheDocument();
    expect(screen.getByLabelText("Experience Level")).toBeInTheDocument();
    expect(screen.getByLabelText("Programming Languages")).toBeInTheDocument();
    expect(screen.getByLabelText("Technical Skills")).toBeInTheDocument();
    expect(screen.getByLabelText("Technologies")).toBeInTheDocument();
    expect(screen.getByLabelText("Focus Areas")).toBeInTheDocument();
    expect(screen.getByLabelText("Projects")).toBeInTheDocument();
  });

  it("shows a validation error when submitting without a name", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: "Create Your Profile" }));

    await user.click(screen.getByRole("button", { name: /Start Interview/ }));

    expect(screen.getByRole("alert")).toHaveTextContent("Please enter the candidate's name.");
    expect(apiMock.startInterview).not.toHaveBeenCalled();
  });

  it("builds a custom profile and starts the interview on submit", async () => {
    apiMock.startInterview.mockResolvedValue({ reply: "Welcome!", done: false, feedback: null });

    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: "Create Your Profile" }));

    await user.type(screen.getByLabelText("Name"), "Riley Doe");
    await user.type(screen.getByLabelText("Target Role"), "Backend Developer");
    await user.type(screen.getByLabelText("Programming Languages"), "Python, SQL");
    await user.type(screen.getByLabelText("Technical Skills"), "FastAPI, Docker");
    await user.type(screen.getByLabelText("Focus Areas"), "Backend API design, Databases");
    await user.type(screen.getByLabelText("Projects"), "RESTful Blog API");
    await user.type(screen.getByLabelText("Technologies"), "PostgreSQL");
    await user.selectOptions(screen.getByLabelText("Experience Level"), "senior");

    await user.click(screen.getByRole("button", { name: /Start Interview/ }));

    await waitFor(() => expect(apiMock.startInterview).toHaveBeenCalledTimes(1));

    const [sessionId, candidate] = apiMock.startInterview.mock.calls[0];
    expect(sessionId).toEqual(expect.any(String));
    expect(candidate.id.startsWith("custom-")).toBe(true);
    expect(candidate.name).toBe("Riley Doe");
    expect(candidate.role).toBe("Backend Developer");
    expect(candidate.experience_level).toBe("senior");
    expect(candidate.years_of_experience).toBe(6);
    expect(candidate.skills.map((skill) => skill.name)).toEqual(
      expect.arrayContaining(["FastAPI", "Docker", "PostgreSQL"])
    );
    expect(candidate.skills.every((skill) => skill.level === "advanced")).toBe(true);
    expect(candidate.preferred_languages).toEqual(["Python", "SQL"]);
    expect(candidate.focus_areas).toEqual(["Backend API design", "Databases"]);

    await waitFor(() => expect(screen.getByText("Interview page")).toBeInTheDocument());
  });

  it("closing the form does not start an interview", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: "Create Your Profile" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(apiMock.startInterview).not.toHaveBeenCalled();
  });
});

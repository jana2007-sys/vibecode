import { describe, expect, it } from "vitest";
import {
  buildCustomProfile,
  EXPERIENCE_LEVELS,
  splitList,
  validateCustomProfile,
  type CustomProfileFormData,
} from "./customProfile";

function form(overrides: Partial<CustomProfileFormData> = {}): CustomProfileFormData {
  return {
    name: "Riley Doe",
    email: "riley@example.com",
    role: "Backend Developer",
    experienceLevel: "mid",
    programmingLanguages: "Python, SQL",
    technicalSkills: "FastAPI, Docker",
    focusAreas: "Backend API design, Databases",
    projects: "RESTful Blog API\nELT Pipeline",
    technologies: "PostgreSQL, Docker",
    strengths: "Debugging, Collaboration",
    notes: "Loves systems design.",
    ...overrides,
  };
}

describe("splitList", () => {
  it("splits comma and newline separated values and trims whitespace", () => {
    expect(splitList("  Python ,SQL\nJavaScript ")).toEqual(["Python", "SQL", "JavaScript"]);
  });

  it("deduplicates and drops empty entries", () => {
    expect(splitList("Python, python, , SQL, SQL")).toEqual(["Python", "python", "SQL"]);
  });

  it("returns an empty list for blank input", () => {
    expect(splitList("  \n ")).toEqual([]);
    expect(splitList("")).toEqual([]);
  });
});

describe("validateCustomProfile", () => {
  it("requires a name", () => {
    expect(validateCustomProfile(form({ name: "  " }))).toBe("Please enter the candidate's name.");
  });

  it("requires an email", () => {
    expect(validateCustomProfile(form({ email: "" }))).toBe("Please enter the candidate's email.");
  });

  it("requires a well-formed email", () => {
    expect(validateCustomProfile(form({ email: "not-an-email" }))).toBe(
      "Please enter a valid email address."
    );
  });

  it("requires a role", () => {
    expect(validateCustomProfile(form({ role: "" }))).toBe("Please enter the target role.");
  });

  it("accepts a complete profile", () => {
    expect(validateCustomProfile(form())).toBeNull();
  });
});

describe("buildCustomProfile", () => {
  it("builds a CandidateCreate payload with a name, email, and role", () => {
    const profile = buildCustomProfile(form());
    expect(profile.name).toBe("Riley Doe");
    expect(profile.email).toBe("riley@example.com");
    expect(profile.role).toBe("Backend Developer");
  });

  it("maps experience level to skill levels and years", () => {
    const mid = buildCustomProfile(form());
    expect(mid.experience_level).toBe("mid");
    expect(mid.years_of_experience).toBe(3);

    const junior = buildCustomProfile(form({ experienceLevel: "junior" }));
    expect(junior.experience_level).toBe("junior");
    expect(junior.years_of_experience).toBe(1);
    expect(junior.skills.every((skill) => skill.level === "beginner")).toBe(true);

    const senior = buildCustomProfile(form({ experienceLevel: "senior" }));
    expect(senior.experience_level).toBe("senior");
    expect(senior.years_of_experience).toBe(6);
    expect(senior.skills.every((skill) => skill.level === "advanced")).toBe(true);
  });

  it("merges technologies into the skill list without duplicates", () => {
    const profile = buildCustomProfile(form());
    const names = profile.skills.map((skill) => skill.name);
    expect(names).toContain("FastAPI");
    expect(names).toContain("PostgreSQL");
    // Docker appears in both skills and technologies but is reported once.
    expect(names.filter((name) => name === "Docker")).toHaveLength(1);
    expect(profile.skills.every((skill) => skill.level === "intermediate")).toBe(true);
  });

  it("splits languages, focus areas, projects, and strengths", () => {
    const profile = buildCustomProfile(form());
    expect(profile.preferred_languages).toEqual(["Python", "SQL"]);
    expect(profile.focus_areas).toEqual(["Backend API design", "Databases"]);
    expect(profile.strengths).toEqual(["Debugging", "Collaboration"]);
    expect(profile.learning_journey).toEqual([
      { type: "project", title: "RESTful Blog API", description: "" },
      { type: "project", title: "ELT Pipeline", description: "" },
    ]);
  });

  it("trims the name, email, role, and notes", () => {
    const profile = buildCustomProfile(
      form({
        name: "  Riley Doe  ",
        email: "  riley@example.com  ",
        role: "  Backend Developer ",
        notes: "  Some notes.  ",
      })
    );
    expect(profile.name).toBe("Riley Doe");
    expect(profile.email).toBe("riley@example.com");
    expect(profile.role).toBe("Backend Developer");
    expect(profile.notes).toBe("Some notes.");
  });

  it("exposes the supported experience levels", () => {
    expect(EXPERIENCE_LEVELS).toEqual(["junior", "mid", "senior"]);
  });
});

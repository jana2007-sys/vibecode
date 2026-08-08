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
    role: "Backend Developer",
    experienceLevel: "mid",
    programmingLanguages: "Python, SQL",
    technicalSkills: "FastAPI, Docker",
    focusAreas: "Backend API design, Databases",
    projects: "RESTful Blog API\nELT Pipeline",
    technologies: "PostgreSQL, Docker",
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

  it("requires a role", () => {
    expect(validateCustomProfile(form({ role: "" }))).toBe("Please enter the target role.");
  });

  it("accepts a complete profile", () => {
    expect(validateCustomProfile(form())).toBeNull();
  });
});

describe("buildCustomProfile", () => {
  it("uses the custom- id prefix for difficulty personalization", () => {
    const profile = buildCustomProfile(form());
    expect(profile.id.startsWith("custom-")).toBe(true);
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

  it("splits languages, focus areas, and projects", () => {
    const profile = buildCustomProfile(form());
    expect(profile.preferred_languages).toEqual(["Python", "SQL"]);
    expect(profile.focus_areas).toEqual(["Backend API design", "Databases"]);
    expect(profile.learning_journey).toEqual([
      { type: "project", title: "RESTful Blog API", description: "" },
      { type: "project", title: "ELT Pipeline", description: "" },
    ]);
  });

  it("trims the name and role", () => {
    const profile = buildCustomProfile(form({ name: "  Riley Doe  ", role: "  Backend Developer " }));
    expect(profile.name).toBe("Riley Doe");
    expect(profile.role).toBe("Backend Developer");
  });

  it("exposes the supported experience levels", () => {
    expect(EXPERIENCE_LEVELS).toEqual(["junior", "mid", "senior"]);
  });
});

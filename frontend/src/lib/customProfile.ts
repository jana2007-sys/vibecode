/** Build a backend-ready ``CandidateProfile`` from the "Create Your Profile" form.

The wire shape matches the backend ``CandidateProfile`` model exactly (field
names are snake_case, no extra fields allowed). Custom profiles use the
``custom-`` id prefix so the backend personalizes the plan the same way it does
for predefined candidates — through CandidateAnalyzer -> QuestionPlanner ->
InterviewEngine -> EvaluationEngine -> FollowUpAdvisor -> FeedbackGenerator.

Level mapping: the form's experience level drives each skill's self-reported
level so the planner's keyword weights reflect the candidate (junior -> beginner
gaps, mid -> intermediate, senior -> advanced) and the difficulty mix stays
appropriate (junior leans easy, senior leans hard).
*/

import type { CandidateProfile, SkillLevel } from "../types/candidate";

export type ExperienceLevel = "junior" | "mid" | "senior";

export interface CustomProfileFormData {
  name: string;
  role: string;
  experienceLevel: ExperienceLevel;
  programmingLanguages: string;
  technicalSkills: string;
  focusAreas: string;
  projects: string;
  technologies: string;
}

/** Skill level each technical skill/technology is reported at, per experience level. */
export const SKILL_LEVEL_BY_EXPERIENCE: Record<ExperienceLevel, string> = {
  junior: "beginner",
  mid: "intermediate",
  senior: "advanced",
};

/** Display-only years of experience derived from the experience level. */
export const YEARS_BY_EXPERIENCE: Record<ExperienceLevel, number> = {
  junior: 1,
  mid: 3,
  senior: 6,
};

export const EXPERIENCE_LEVELS: ExperienceLevel[] = ["junior", "mid", "senior"];

/** Split a comma/line separated list into trimmed, de-duplicated entries. */
export function splitList(value: string): string[] {
  const seen = new Set<string>();
  const items: string[] = [];
  for (const raw of value.split(/[,\n]/)) {
    const item = raw.trim();
    if (!item || seen.has(item)) continue;
    seen.add(item);
    items.push(item);
  }
  return items;
}

function makeId(): string {
  try {
    return `custom-${crypto.randomUUID()}`;
  } catch {
    return `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

/** Merge technical skills and technologies into a deduplicated skill list. */
function collectSkills(data: CustomProfileFormData): SkillLevel[] {
  const level = SKILL_LEVEL_BY_EXPERIENCE[data.experienceLevel];
  const names = splitList(data.technicalSkills);
  for (const technology of splitList(data.technologies)) {
    if (!names.includes(technology)) names.push(technology);
  }
  return names.map((name) => ({ name, level }));
}

/** Convert the "Create Your Profile" form into the backend ``CandidateProfile`` contract. */
export function buildCustomProfile(data: CustomProfileFormData): CandidateProfile {
  return {
    id: makeId(),
    name: data.name.trim(),
    role: data.role.trim(),
    experience_level: data.experienceLevel,
    years_of_experience: YEARS_BY_EXPERIENCE[data.experienceLevel],
    skills: collectSkills(data),
    learning_journey: splitList(data.projects).map((title) => ({
      type: "project",
      title,
      description: "",
    })),
    preferred_languages: splitList(data.programmingLanguages),
    focus_areas: splitList(data.focusAreas),
    notes: "",
  };
}

/** Minimal client-side validation: a custom profile needs a name and a role. */
export function validateCustomProfile(data: CustomProfileFormData): string | null {
  if (!data.name.trim()) return "Please enter the candidate's name.";
  if (!data.role.trim()) return "Please enter the target role.";
  return null;
}

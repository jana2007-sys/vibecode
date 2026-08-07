/** Mirrors backend `SkillLevel`. */
export interface SkillLevel {
  name: string;
  level: "beginner" | "intermediate" | "advanced" | "unknown";
}

/** Mirrors backend `LearningJourneyEntry`. */
export interface LearningJourneyEntry {
  type: "course" | "project" | "book" | "practice";
  title: string;
  description?: string;
}

/** Mirrors backend `CandidateProfile`. */
export interface CandidateProfile {
  id: string;
  name: string;
  role?: string;
  years_of_experience?: number;
  skills: SkillLevel[];
  learning_journey: LearningJourneyEntry[];
  preferred_languages?: string[];
  focus_areas?: string[];
  notes?: string;
}

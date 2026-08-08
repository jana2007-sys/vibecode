/** Candidate profile types.

The wire shape matches the backend `CandidateProfile` model exactly (field
names are snake_case) because the candidate object is passed through verbatim to
`POST /api/interview` and the backend forbids extra fields. Nothing sensitive is
ever stored or sent beyond what ships in `src/data/candidates.ts`.
*/

export interface SkillLevel {
  name: string;
  level: string;
}

export interface LearningJourneyEntry {
  type: string;
  title: string;
  description?: string;
}

export interface CandidateProfile {
  id: string;
  name: string;
  role?: string;
  years_of_experience?: number;
  experience_level?: string;
  skills: SkillLevel[];
  learning_journey: LearningJourneyEntry[];
  preferred_languages?: string[];
  focus_areas?: string[];
  notes?: string;
}

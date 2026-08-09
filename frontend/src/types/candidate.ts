/** Candidate profile types.

The wire shape matches the backend `CandidateProfile` model exactly (field
names are snake_case) because the candidate object is passed through verbatim to
`POST /api/interview` and the backend forbids extra fields.

A persisted candidate (`Candidate`) extends the wire shape with `email` and
`strengths`, which live only on the backend `candidates` resource. Before the
candidate is sent to the interactive interview endpoint it must be reduced back
to the wire shape via `toWireProfile` — the interview contract never sees
`email`/`strengths`.
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

/** A persisted candidate row from `GET/POST /api/candidates`. */
export interface Candidate extends CandidateProfile {
  email?: string;
  strengths?: string[];
  /** True for profiles added via the API; false for the predefined seeded ones. */
  is_custom?: boolean;
}

/** Payload to create (or upsert-by-email) a candidate. */
export interface CandidateCreate {
  name: string;
  email: string;
  role: string;
  years_of_experience?: number;
  experience_level?: string;
  skills: SkillLevel[];
  learning_journey: LearningJourneyEntry[];
  preferred_languages?: string[];
  focus_areas?: string[];
  strengths?: string[];
  notes?: string;
}

/** Reduce a candidate to the exact `POST /interview` wire shape. */
export function toWireProfile(candidate: CandidateProfile): CandidateProfile {
  return {
    id: candidate.id,
    name: candidate.name,
    role: candidate.role,
    years_of_experience: candidate.years_of_experience,
    experience_level: candidate.experience_level,
    skills: candidate.skills,
    learning_journey: candidate.learning_journey,
    preferred_languages: candidate.preferred_languages,
    focus_areas: candidate.focus_areas,
    notes: candidate.notes,
  };
}

/** Convert a `CandidateCreate` form payload into a candidate ready to POST. */
export function toCandidateCreate(candidate: Candidate): CandidateCreate {
  return {
    name: candidate.name,
    email: candidate.email ?? "",
    role: candidate.role ?? "",
    years_of_experience: candidate.years_of_experience,
    experience_level: candidate.experience_level,
    skills: candidate.skills,
    learning_journey: candidate.learning_journey,
    preferred_languages: candidate.preferred_languages,
    focus_areas: candidate.focus_areas,
    strengths: candidate.strengths,
    notes: candidate.notes,
  };
}

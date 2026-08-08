/** Candidate selection page. */

import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import {
  AlertCircleIcon,
  ArrowRightIcon,
  BookIcon,
  CheckIcon,
  CloseIcon,
  LayersIcon,
  PlusIcon,
  SparklesIcon,
  UserIcon,
} from "../components/ui/Icons";
import { SectionHeading } from "../components/ui/SectionHeading";
import { useInterviewContext } from "../context/InterviewContext";
import { CANDIDATES } from "../data/candidates";
import {
  buildCustomProfile,
  EXPERIENCE_LEVELS,
  type CustomProfileFormData,
  validateCustomProfile,
} from "../lib/customProfile";
import type { CandidateProfile } from "../types/candidate";

const levelTone: Record<string, "emerald" | "amber" | "slate"> = {
  advanced: "emerald",
  intermediate: "emerald",
  beginner: "amber",
};

function Initials({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold text-white shadow-lg shadow-indigo-500/25">
      {initials}
    </div>
  );
}

interface CandidateCardProps {
  candidate: CandidateProfile;
  selected: boolean;
  onSelect: () => void;
}

function CandidateCard({ candidate, selected, onSelect }: CandidateCardProps) {
  return (
    <Card
      role="radio"
      aria-checked={selected}
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      className={`cursor-pointer p-6 transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 ${
        selected
          ? "border-indigo-400/50 bg-indigo-500/[0.07] shadow-glow"
          : "hover:-translate-y-0.5 hover:border-white/20 hover:bg-white/[0.06]"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Initials name={candidate.name} />
          <div>
            <h3 className="text-lg font-semibold text-white">
              {candidate.name}
            </h3>
            <p className="text-sm text-slate-400">{candidate.role}</p>
          </div>
        </div>
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border transition-colors ${
            selected
              ? "border-indigo-400 bg-indigo-500 text-white"
              : "border-white/20 bg-white/5 text-transparent"
          }`}
          aria-hidden="true"
        >
          <CheckIcon className="h-3.5 w-3.5" />
        </span>
      </div>

      {typeof candidate.years_of_experience === "number" ? (
        <p className="mt-3 text-xs text-slate-500">
          {candidate.years_of_experience} yr(s) experience
        </p>
      ) : null}

      <div className="mt-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Skills
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {candidate.skills.map((skill) => (
            <Badge key={skill.name} tone={levelTone[skill.level] ?? "slate"}>
              {skill.name}
              {skill.level && skill.level !== "unknown" ? (
                <span className="opacity-70">· {skill.level}</span>
              ) : null}
            </Badge>
          ))}
        </div>
      </div>

      {candidate.focus_areas && candidate.focus_areas.length > 0 ? (
        <div className="mt-4">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <LayersIcon className="h-3.5 w-3.5" />
            Focus areas
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {candidate.focus_areas.map((area) => (
              <span
                key={area}
                className="inline-flex items-center rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300"
              >
                {area}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {candidate.learning_journey.length > 0 ? (
        <div className="mt-4">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <BookIcon className="h-3.5 w-3.5" />
            Learning journey
          </p>
          <ul className="mt-2 space-y-2">
            {candidate.learning_journey.map((entry, index) => (
              <li key={`${entry.title}-${index}`} className="flex gap-2.5 text-sm">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400/70" />
                <span className="text-slate-300">
                  <span className="font-medium text-slate-200">
                    {entry.title}
                  </span>
                  {entry.description ? (
                    <span className="text-slate-500">
                      {" "}
                      — {entry.description}
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}

// --- Create Your Profile -----------------------------------------------------

const EMPTY_FORM: CustomProfileFormData = {
  name: "",
  role: "",
  experienceLevel: "mid",
  programmingLanguages: "",
  technicalSkills: "",
  focusAreas: "",
  projects: "",
  technologies: "",
};

const inputClasses =
  "w-full rounded-xl border border-white/10 bg-ink-900/60 px-4 py-3 text-[15px] leading-relaxed text-slate-100 " +
  "placeholder:text-slate-500 transition-colors focus:border-indigo-400/50 focus:outline-none focus:ring-2 focus:ring-indigo-500/30";

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
}

function Field({ id, label, hint, children }: FieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </label>
      {children}
      {hint ? <p className="mt-1.5 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

interface CreateProfileFormProps {
  loading: boolean;
  onCancel: () => void;
  onSubmit: (data: CustomProfileFormData) => void;
}

function CreateProfileForm({ loading, onCancel, onSubmit }: CreateProfileFormProps) {
  const [data, setData] = useState<CustomProfileFormData>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof CustomProfileFormData>(
    key: K,
    value: CustomProfileFormData[K]
  ) {
    setData((prev) => ({ ...prev, [key]: value }));
    setError(null);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const validationError = validateCustomProfile(data);
    if (validationError) {
      setError(validationError);
      return;
    }
    onSubmit(data);
  }

  return (
    <Card className="border-indigo-400/40 bg-indigo-500/[0.05] p-6 sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/25">
            <UserIcon className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">Create Your Profile</h3>
            <p className="text-sm text-slate-400">
              We'll personalize a technical interview around this profile.
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={loading}
          aria-label="Close custom profile form"
        >
          <CloseIcon className="h-4 w-4" />
        </Button>
      </div>

      <form onSubmit={handleSubmit} className="mt-6 grid gap-5 sm:grid-cols-2" noValidate>
        <Field id="cp-name" label="Name">
          <input
            id="cp-name"
            value={data.name}
            onChange={(event) => update("name", event.target.value)}
            placeholder="e.g. Alex Rivera"
            className={inputClasses}
          />
        </Field>

        <Field id="cp-role" label="Target Role">
          <input
            id="cp-role"
            value={data.role}
            onChange={(event) => update("role", event.target.value)}
            placeholder="e.g. Backend Developer"
            className={inputClasses}
          />
        </Field>

        <Field id="cp-level" label="Experience Level">
          <select
            id="cp-level"
            value={data.experienceLevel}
            onChange={(event) =>
              update("experienceLevel", event.target.value as CustomProfileFormData["experienceLevel"])
            }
            className={`${inputClasses} appearance-none`}
          >
            {EXPERIENCE_LEVELS.map((level) => (
              <option key={level} value={level} className="bg-ink-900 text-slate-100">
                {level.charAt(0).toUpperCase() + level.slice(1)}
              </option>
            ))}
          </select>
        </Field>

        <Field
          id="cp-languages"
          label="Programming Languages"
          hint="Comma-separated, e.g. Python, SQL, JavaScript"
        >
          <input
            id="cp-languages"
            value={data.programmingLanguages}
            onChange={(event) => update("programmingLanguages", event.target.value)}
            placeholder="Python, SQL"
            className={inputClasses}
          />
        </Field>

        <Field
          id="cp-skills"
          label="Technical Skills"
          hint="Comma-separated, e.g. FastAPI, Docker, Pandas"
        >
          <input
            id="cp-skills"
            value={data.technicalSkills}
            onChange={(event) => update("technicalSkills", event.target.value)}
            placeholder="FastAPI, SQL, Docker"
            className={inputClasses}
          />
        </Field>

        <Field
          id="cp-technologies"
          label="Technologies"
          hint="Comma-separated, e.g. PostgreSQL, Redis, Kafka"
        >
          <input
            id="cp-technologies"
            value={data.technologies}
            onChange={(event) => update("technologies", event.target.value)}
            placeholder="PostgreSQL, Redis"
            className={inputClasses}
          />
        </Field>

        <Field
          id="cp-focus"
          label="Focus Areas"
          hint="Comma-separated, e.g. Backend APIs, Databases, Testing"
        >
          <input
            id="cp-focus"
            value={data.focusAreas}
            onChange={(event) => update("focusAreas", event.target.value)}
            placeholder="Backend APIs, Databases"
            className={inputClasses}
          />
        </Field>

        <Field
          id="cp-projects"
          label="Projects"
          hint="Comma-separated, e.g. RESTful Blog API, ELT Pipeline"
        >
          <textarea
            id="cp-projects"
            value={data.projects}
            onChange={(event) => update("projects", event.target.value)}
            placeholder="RESTful Blog API, ELT Pipeline"
            rows={2}
            className={`${inputClasses} resize-none`}
          />
        </Field>

        {error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-200 sm:col-span-2"
          >
            <AlertCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="flex flex-col-reverse items-stretch gap-3 sm:col-span-2 sm:flex-row sm:items-center sm:justify-end">
          <Button
            type="button"
            variant="secondary"
            onClick={onCancel}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button type="submit" size="lg" loading={loading} disabled={loading}>
            Start Interview
            <ArrowRightIcon className="h-4 w-4" />
          </Button>
        </div>
      </form>
    </Card>
  );
}

function CreateProfileCard({ onClick }: { onClick: () => void }) {
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
      aria-label="Create Your Profile"
      className="group cursor-pointer border-dashed border-indigo-400/40 bg-indigo-500/[0.04] p-6 transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 hover:-translate-y-0.5 hover:border-indigo-400/60 hover:bg-indigo-500/[0.08]"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-indigo-400/40 bg-indigo-500/15 text-indigo-300 shadow-lg shadow-indigo-500/20 transition-transform duration-300 group-hover:scale-105">
            <PlusIcon className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">Create Your Profile</h3>
            <p className="text-sm text-slate-400">
              Add a candidate and get an interview personalized to their skills,
              languages, and focus areas.
            </p>
          </div>
        </div>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-indigo-400/40 bg-indigo-500/15 text-indigo-300 transition-transform duration-300 group-hover:translate-x-0.5">
          <ArrowRightIcon className="h-4 w-4" />
        </span>
      </div>
    </Card>
  );
}

// --- Page --------------------------------------------------------------------

export function CandidateSelection() {
  const navigate = useNavigate();
  const { startInterview, loading, error } = useInterviewContext();
  const [selectedId, setSelectedId] = useState<string | null>(
    CANDIDATES.length > 0 ? CANDIDATES[0].id : null
  );
  const [showCreateForm, setShowCreateForm] = useState(false);

  const selected =
    CANDIDATES.find((candidate) => candidate.id === selectedId) ?? null;

  async function handleBegin() {
    if (!selected) return;
    await startInterview(selected);
    navigate("/interview");
  }

  async function handleCreateProfile(data: CustomProfileFormData) {
    const profile = buildCustomProfile(data);
    await startInterview(profile);
    navigate("/interview");
  }

  if (CANDIDATES.length === 0) {
    return (
      <EmptyState
        title="No candidates available"
        description="There are no candidate profiles to select from right now."
        action={
          <Button to="/" variant="secondary">
            Back to home
          </Button>
        }
      />
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-10">
      <SectionHeading
        align="left"
        eyebrow="Candidate"
        title="Who's taking the interview?"
        subtitle="The interviewer personalizes every question to this candidate's skills, focus areas, and learning journey."
      />

      {showCreateForm ? (
        <CreateProfileForm
          loading={loading}
          onCancel={() => setShowCreateForm(false)}
          onSubmit={(data) => void handleCreateProfile(data)}
        />
      ) : (
        <CreateProfileCard onClick={() => setShowCreateForm(true)} />
      )}

      <div className="grid gap-6 lg:grid-cols-1" role="radiogroup" aria-label="Select a candidate">
        {CANDIDATES.map((candidate) => (
          <CandidateCard
            key={candidate.id}
            candidate={candidate}
            selected={selectedId === candidate.id}
            onSelect={() => setSelectedId(candidate.id)}
          />
        ))}
      </div>

      <Card className="flex flex-col items-center gap-4 p-6 text-center sm:flex-row sm:justify-between sm:text-left">
        <div className="flex items-center gap-3">
          <div className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white sm:flex">
            <SparklesIcon className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">
              Ready for your technical interview?
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              {selected
                ? `Interviewing ${selected.name}${selected.role ? ` for ${selected.role}` : ""}.`
                : "Select a candidate above to continue."}
            </p>
          </div>
        </div>
        <Button
          size="lg"
          onClick={() => void handleBegin()}
          disabled={!selected || loading}
          loading={loading}
          className="w-full shrink-0 sm:w-auto"
        >
          Begin Interview
          <ArrowRightIcon className="h-4 w-4" />
        </Button>
      </Card>

      {error ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
        >
          <AlertCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">Couldn't start the interview</p>
            <p className="mt-0.5 text-rose-300/90">{error}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

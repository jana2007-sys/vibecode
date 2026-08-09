/** Candidate selection page.

Candidates now come from the backend (`GET /api/candidates`), so the page has
loading/error/empty states around a small search box. The "Create Your Profile"
form POSTs a new candidate to the backend (which persists it and assigns a real
id); it does NOT auto-start an interview. Starting an interview always routes
through the interactive `POST /api/interview` contract from the selected
persisted candidate.
*/

import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
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
  MailIcon,
  PlusIcon,
  SearchIcon,
  SparklesIcon,
  TrashIcon,
  UserIcon,
  UsersIcon,
} from "../components/ui/Icons";
import { SectionHeading } from "../components/ui/SectionHeading";
import { useInterviewContext } from "../context/InterviewContext";
import {
  buildCustomProfile,
  EXPERIENCE_LEVELS,
  type CustomProfileFormData,
  validateCustomProfile,
} from "../lib/customProfile";
import { api } from "../services/api";
import type { Candidate } from "../types/candidate";

const levelTone: Record<string, "teal" | "cyan" | "amber" | "slate"> = {
  advanced: "teal",
  intermediate: "cyan",
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
    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-sm font-bold text-white shadow-lg shadow-teal-500/25 ring-1 ring-inset ring-white/20">
      {initials}
    </div>
  );
}

interface CandidateCardProps {
  candidate: Candidate;
  selected: boolean;
  onSelect: () => void;
  onDelete?: () => void;
}

function CandidateCard({ candidate, selected, onSelect, onDelete }: CandidateCardProps) {
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
      className={`cursor-pointer p-6 transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70 ${
        selected
          ? "border-teal-400/50 bg-gradient-to-br from-teal-500/[0.08] to-cyan-500/[0.08] shadow-glow"
          : "hover:-translate-y-1.5 hover:border-teal-400/40 hover:bg-teal-500/5 hover:shadow-glow-cyan dark:hover:bg-white/[0.06]"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Initials name={candidate.name} />
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
              {candidate.name}
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">{candidate.role}</p>
            {candidate.email ? (
              <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
                <MailIcon className="h-3 w-3" />
                {candidate.email}
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className={`flex h-6 w-6 items-center justify-center rounded-full border transition-colors ${
              selected
                ? "border-teal-400 bg-teal-500 text-white shadow-[0_0_15px_-2px_rgba(20,184,166,0.7)]"
                : "border-slate-300 bg-white text-transparent dark:border-white/20 dark:bg-white/5"
            }`}
            aria-hidden="true"
          >
            <CheckIcon className="h-3.5 w-3.5" />
          </span>
          {candidate.is_custom && onDelete ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={`Delete ${candidate.name}`}
              onClick={(event) => {
                event.stopPropagation();
                onDelete();
              }}
              className="text-slate-400 hover:text-rose-600 dark:hover:text-rose-300"
            >
              <TrashIcon className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
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
                className="inline-flex items-center rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"
              >
                {area}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {candidate.strengths && candidate.strengths.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Known strengths
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {candidate.strengths.map((strength) => (
              <Badge key={strength} tone="emerald">
                {strength}
              </Badge>
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
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gradient-to-r from-teal-400 to-cyan-400" />
                <span className="text-slate-600 dark:text-slate-300">
                  <span className="font-medium text-slate-800 dark:text-slate-200">
                    {entry.title}
                  </span>
                  {entry.description ? (
                    <span className="text-slate-500"> — {entry.description}</span>
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
  email: "",
  role: "",
  experienceLevel: "mid",
  programmingLanguages: "",
  technicalSkills: "",
  focusAreas: "",
  projects: "",
  technologies: "",
  strengths: "",
  notes: "",
};

const inputClasses =
  "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-[15px] leading-relaxed text-slate-900 " +
  "placeholder:text-slate-400 transition-colors focus:border-teal-400/60 focus:outline-none focus:ring-2 focus:ring-teal-500/30 " +
  "dark:border-white/10 dark:bg-ink-900/60 dark:text-slate-100 dark:placeholder:text-slate-500";

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
    <Card className="border-teal-400/40 bg-gradient-to-br from-teal-500/[0.06] to-cyan-500/[0.06] p-6 shadow-glow sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white shadow-lg shadow-teal-500/25 ring-1 ring-inset ring-white/20">
            <UserIcon className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Create Your Profile</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Save a candidate profile; you can start an interview from it right after.
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

        <Field id="cp-email" label="Email">
          <input
            id="cp-email"
            type="email"
            value={data.email}
            onChange={(event) => update("email", event.target.value)}
            placeholder="e.g. alex@example.com"
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
              <option
                key={level}
                value={level}
                className="bg-white text-slate-900 dark:bg-ink-900 dark:text-slate-100"
              >
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
          id="cp-strengths"
          label="Known Strengths"
          hint="Comma-separated, e.g. Communication, Fast learner, Debugging"
        >
          <input
            id="cp-strengths"
            value={data.strengths}
            onChange={(event) => update("strengths", event.target.value)}
            placeholder="Debugging, Collaboration"
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

        <Field id="cp-notes" label="Notes" hint="Anything the interviewer should know">
          <textarea
            id="cp-notes"
            value={data.notes}
            onChange={(event) => update("notes", event.target.value)}
            placeholder="Optional context about this candidate."
            rows={2}
            className={`${inputClasses} resize-none sm:col-span-2`}
          />
        </Field>

        {error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-700 dark:text-rose-200 sm:col-span-2"
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
            Save Profile
            <CheckIcon className="h-4 w-4" />
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
      className="group cursor-pointer border-dashed border-teal-400/40 bg-gradient-to-br from-teal-500/[0.05] to-cyan-500/[0.05] p-6 transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70 hover:-translate-y-1.5 hover:border-teal-400/60 hover:shadow-glow"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-teal-400/40 bg-teal-500/15 text-teal-700 shadow-lg shadow-teal-500/20 transition-transform duration-300 group-hover:scale-110 dark:text-teal-300">
            <PlusIcon className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Create Your Profile</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Add a candidate and get an interview personalized to their skills,
              languages, and focus areas.
            </p>
          </div>
        </div>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-teal-400/40 bg-teal-500/15 text-teal-700 transition-transform duration-300 group-hover:translate-x-0.5 dark:text-teal-300">
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
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [query, setQuery] = useState("");

  async function refresh() {
    setListLoading(true);
    setListError(null);
    try {
      const result = await api.listCandidates();
      setCandidates(result.items);
      setSelectedId((current) =>
        current && result.items.some((item) => item.id === current)
          ? current
          : result.items[0]?.id ?? null
      );
    } catch (err) {
      setListError("Couldn't load candidates. Check that the backend is running, then try again.");
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return candidates;
    return candidates.filter(
      (candidate) =>
        candidate.name.toLowerCase().includes(term) ||
        (candidate.role ?? "").toLowerCase().includes(term) ||
        (candidate.email ?? "").toLowerCase().includes(term)
    );
  }, [candidates, query]);

  const selected = candidates.find((candidate) => candidate.id === selectedId) ?? null;

  async function handleBegin() {
    if (!selected) return;
    await startInterview(selected);
    navigate("/interview");
  }

  async function handleCreateProfile(data: CustomProfileFormData) {
    setSaving(true);
    setSaveError(null);
    try {
      await api.createCandidate(buildCustomProfile(data));
      setShowCreateForm(false);
      await refresh();
    } catch (err) {
      setSaveError("Couldn't save the profile. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(candidate: Candidate) {
    if (
      !window.confirm(
        `Delete ${candidate.name} and all of their interviews? This can't be undone.`
      )
    ) {
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteCandidate(candidate.id);
      if (selectedId === candidate.id) setSelectedId(null);
      await refresh();
    } catch (err) {
      setDeleteError("Couldn't delete this candidate. Please try again.");
    } finally {
      setDeleting(false);
    }
  }

  if (listLoading) {
    return (
      <div className="mx-auto max-w-4xl space-y-10">
        <SectionHeading
          align="left"
          eyebrow="Candidate"
          title="Who's taking the interview?"
          subtitle="Loading candidates from the backend…"
        />
        <Card className="p-12 text-center text-sm text-slate-500">Loading candidates…</Card>
      </div>
    );
  }

  if (listError && candidates.length === 0) {
    return (
      <EmptyState
        icon="alert"
        title="Couldn't load candidates"
        description={listError}
        action={
          <Button onClick={() => void refresh()} variant="secondary">
            Try again
          </Button>
        }
      />
    );
  }

  if (candidates.length === 0) {
    return (
      <div className="mx-auto max-w-4xl space-y-10">
        <SectionHeading
          align="left"
          eyebrow="Candidate"
          title="Who's taking the interview?"
          subtitle="Create a candidate profile to get started — it will be saved to the backend."
        />
        {showCreateForm ? (
          <CreateProfileForm
            loading={saving}
            onCancel={() => setShowCreateForm(false)}
            onSubmit={(data) => void handleCreateProfile(data)}
          />
        ) : (
          <CreateProfileCard onClick={() => setShowCreateForm(true)} />
        )}
      </div>
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
          loading={saving}
          onCancel={() => setShowCreateForm(false)}
          onSubmit={(data) => void handleCreateProfile(data)}
        />
      ) : (
        <CreateProfileCard onClick={() => setShowCreateForm(true)} />
      )}

      {saveError ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-200"
        >
          <AlertCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{saveError}</span>
        </div>
      ) : null}

      {deleteError ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-200"
        >
          <AlertCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{deleteError}</span>
        </div>
      ) : null}

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">
            <SearchIcon className="h-4 w-4" />
          </span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search candidates by name, role, or email…"
            aria-label="Search candidates"
            className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-900 placeholder:text-slate-400 transition-colors focus:border-teal-400/60 focus:outline-none focus:ring-2 focus:ring-teal-500/30 dark:border-white/10 dark:bg-ink-900/60 dark:text-slate-100 dark:placeholder:text-slate-500"
          />
        </div>
        <Badge tone="slate">
          <UsersIcon className="h-3 w-3" />
          {filtered.length} of {candidates.length}
        </Badge>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon="alert"
          title="No matching candidates"
          description={`No candidates match "${query}". Try a different search.`}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-1" role="radiogroup" aria-label="Select a candidate">
          {filtered.map((candidate) => (
            <CandidateCard
              key={candidate.id}
              candidate={candidate}
              selected={selectedId === candidate.id}
              onSelect={() => setSelectedId(candidate.id)}
              onDelete={
                candidate.is_custom && !deleting
                  ? () => void handleDelete(candidate)
                  : undefined
              }
            />
          ))}
        </div>
      )}

      <Card className="flex flex-col items-center gap-4 p-6 text-center sm:flex-row sm:justify-between sm:text-left">
        <div className="flex items-center gap-3">
          <div className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white sm:flex">
            <SparklesIcon className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              Ready for your technical interview?
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
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
          className="flex items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-200"
        >
          <AlertCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">Couldn't start the interview</p>
            <p className="mt-0.5 text-rose-700/90 dark:text-rose-300/90">{error}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

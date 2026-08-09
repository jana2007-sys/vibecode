/** Interview history page.

Lists past interviews for the currently selected candidate (from the shared
interview context), fetched from `GET /api/candidates/{id}/interviews`. Each
row links to the full report for that session. If no candidate is selected the
page prompts you to pick one.
*/

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import {
  ArrowRightIcon,
  ClockIcon,
  TrashIcon,
} from "../components/ui/Icons";
import { SectionHeading } from "../components/ui/SectionHeading";
import { useInterviewContext } from "../context/InterviewContext";
import { api } from "../services/api";
import type { InterviewHistoryItem } from "../types/report";

function formatDate(value: string): string {
  try {
    return new Date(value).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return value;
  }
}

function stateTone(state: string): "teal" | "cyan" | "amber" | "slate" {
  switch (state) {
    case "completed":
      return "teal";
    case "in_progress":
      return "cyan";
    case "failed":
      return "amber";
    default:
      return "slate";
  }
}

function HistoryRow({ item, onOpen }: { item: InterviewHistoryItem; onOpen: () => void }) {
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      className="group flex cursor-pointer items-center justify-between gap-4 p-5 transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70 hover:-translate-y-0.5 hover:border-teal-400/40 hover:shadow-glow-cyan"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={stateTone(item.state)}>{item.state.replace("_", " ")}</Badge>
          {typeof item.overall_score === "number" ? (
            <Badge tone="emerald">Score: {item.overall_score}%</Badge>
          ) : null}
        </div>
        <p className="mt-2 line-clamp-2 text-sm text-slate-600 dark:text-slate-300">{item.summary}</p>
        <p className="mt-1.5 flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
          <ClockIcon className="h-3 w-3" />
          {formatDate(item.completed_at ?? item.created_at)}
        </p>
      </div>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-teal-400/30 bg-teal-500/10 text-teal-700 transition-transform duration-300 group-hover:translate-x-0.5 dark:text-teal-300">
        <ArrowRightIcon className="h-4 w-4" />
      </span>
    </Card>
  );
}

export function History() {
  const navigate = useNavigate();
  const { candidate } = useInterviewContext();
  const [items, setItems] = useState<InterviewHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);

  async function handleClear() {
    if (!candidate) return;
    if (!window.confirm(`Delete all interviews for ${candidate.name}? This can't be undone.`)) {
      return;
    }
    setClearing(true);
    setClearError(null);
    try {
      await api.clearHistory(candidate.id);
      setItems([]);
    } catch {
      setClearError("Couldn't clear this candidate's history.");
    } finally {
      setClearing(false);
    }
  }

  useEffect(() => {
    if (!candidate) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getCandidateHistory(candidate.id)
      .then((history) => {
        if (!cancelled) setItems(history.items);
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load interview history for this candidate.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [candidate]);

  if (!candidate) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <EmptyState
          icon="alert"
          title="No candidate selected"
          description="Select a candidate first so we can show their past interviews."
          action={
            <Button to="/candidates" size="lg">
              Choose a candidate
            </Button>
          }
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        <SectionHeading
          align="left"
          eyebrow="History"
          title="Past interviews"
          subtitle={`Loading interviews for ${candidate.name}…`}
        />
        <Card className="p-12 text-center text-sm text-slate-500">Loading history…</Card>
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        icon="alert"
        title="Couldn't load history"
        description={error}
        action={
          <Button
            onClick={() => {
              setLoading(true);
              setError(null);
              if (candidate) {
                api
                  .getCandidateHistory(candidate.id)
                  .then((history) => setItems(history.items))
                  .catch(() => setError("Couldn't load interview history for this candidate."))
                  .finally(() => setLoading(false));
              }
            }}
            variant="secondary"
          >
            Try again
          </Button>
        }
      />
    );
  }

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-3xl space-y-8">
        <SectionHeading
          align="left"
          eyebrow="History"
          title="Past interviews"
          subtitle={`Interviews for ${candidate.name}`}
        />
        <EmptyState
          icon="alert"
          title="No interviews yet"
          description="This candidate hasn't completed any interviews. Start one and it will show up here."
          action={
            <Button to="/candidates" size="lg">
              Start an interview
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SectionHeading
          align="left"
          eyebrow="History"
          title="Past interviews"
          subtitle={`${items.length} interview${items.length === 1 ? "" : "s"} for ${candidate.name}`}
        />
        <Button
          onClick={handleClear}
          disabled={clearing}
          variant="danger"
          size="sm"
        >
          <TrashIcon className="h-4 w-4" />
          {clearing ? "Clearing…" : "Clear history"}
        </Button>
      </div>
      {clearError ? (
        <p className="text-sm text-rose-600 dark:text-rose-400">{clearError}</p>
      ) : null}
      <div className="space-y-4" role="list" aria-label="Interview history">
        {items.map((item) => (
          <HistoryRow
            key={item.session_id}
            item={item}
            onOpen={() => navigate(`/report?session=${item.session_id}`)}
          />
        ))}
      </div>
    </div>
  );
}

/** Landing page. */

import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { SectionHeading } from "../components/ui/SectionHeading";
import {
  ArrowRightIcon,
  BookIcon,
  BrainIcon,
  ChartIcon,
  ChatIcon,
  GitBranchIcon,
  RefreshIcon,
  ShieldIcon,
  SparklesIcon,
  UserIcon,
} from "../components/ui/Icons";

const features = [
  {
    icon: ChatIcon,
    title: "Personalized Questions",
    description:
      "Every interview is built around the candidate's skills, focus areas, and learning journey — grounded in the real curriculum, never generic.",
    tone: "text-indigo-300",
    glow: "from-indigo-500/20",
  },
  {
    icon: RefreshIcon,
    title: "Adaptive AI Follow-ups",
    description:
      "The interviewer listens to each answer and goes one level deeper on the concepts you missed, keeping the conversation genuinely adaptive.",
    tone: "text-violet-300",
    glow: "from-violet-500/20",
  },
  {
    icon: ChartIcon,
    title: "Actionable Feedback",
    description:
      "Finish with a structured report: your strengths, the gaps to close, and concrete next steps for your learning path.",
    tone: "text-sky-300",
    glow: "from-sky-500/20",
  },
];

const steps = [
  {
    icon: UserIcon,
    title: "Candidate Profile",
    description: "Select a candidate and their learning journey.",
  },
  {
    icon: ChatIcon,
    title: "AI Interview",
    description: "Answer real, curriculum-grounded technical questions.",
  },
  {
    icon: RefreshIcon,
    title: "Adaptive Follow-ups",
    description: "The interviewer adapts to what you say.",
  },
  {
    icon: ChartIcon,
    title: "Performance Report",
    description: "Get structured, actionable feedback.",
  },
];

const trust = [
  {
    icon: BookIcon,
    title: "Curriculum-grounded questions",
    description: "Built on the shipped interview curriculum.",
  },
  {
    icon: GitBranchIcon,
    title: "Context-aware conversation",
    description: "Tracks every turn and keeps full context.",
  },
  {
    icon: BrainIcon,
    title: "Gemini-powered adaptation",
    description: "LLM-driven follow-ups when available.",
  },
  {
    icon: ShieldIcon,
    title: "Deterministic fallback",
    description: "Reliable behavior even without the LLM.",
  },
];

export function Landing() {
  return (
    <div className="overflow-hidden">
      {/* Hero */}
      <section className="relative">
        <div className="bg-grid absolute inset-0" aria-hidden="true" />
        <div
          className="pointer-events-none absolute -top-24 left-1/2 h-72 w-[42rem] -translate-x-1/2 rounded-full bg-indigo-600/20 blur-3xl"
          aria-hidden="true"
        />
        <div className="relative mx-auto flex max-w-4xl flex-col items-center px-4 pb-16 pt-20 text-center sm:pb-24 sm:pt-28">
          <span className="animate-fade-up inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-semibold text-slate-300">
            <SparklesIcon className="h-3.5 w-3.5 text-indigo-300" />
            Your AI-powered technical interview coach
          </span>
          <h1
            className="animate-fade-up mt-6 max-w-3xl text-balance text-4xl font-extrabold leading-tight tracking-tight text-white [animation-delay:60ms] sm:text-6xl"
          >
            Practice like you're already{" "}
            <span className="text-gradient">in the interview.</span>
          </h1>
          <p
            className="animate-fade-up mt-6 max-w-2xl text-pretty text-base leading-relaxed text-slate-400 [animation-delay:120ms] sm:text-lg"
          >
            InterVue AI conducts personalized technical interviews based on the
            candidate's learning journey, adapts follow-up questions, maintains
            conversation context, and provides actionable feedback — so you walk
            into the real thing ready.
          </p>
          <div
            className="animate-fade-up mt-9 flex w-full max-w-md flex-col items-stretch justify-center gap-3 [animation-delay:180ms] sm:w-auto sm:flex-row"
          >
            <Button to="/candidates" size="lg" fullWidth>
              Start Interview
              <ArrowRightIcon className="h-4 w-4" />
            </Button>
            <Button to="#how-it-works" variant="secondary" size="lg" fullWidth>
              How it works
            </Button>
          </div>

          {/* Decorative interview preview */}
          <div className="animate-fade-up mt-16 w-full max-w-lg [animation-delay:240ms]">
            <Card className="p-5 text-left">
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30">
                  <SparklesIcon className="h-4 w-4" />
                </div>
                <div className="min-w-0 space-y-2">
                  <span className="text-xs font-semibold text-slate-300">
                    InterVue AI
                  </span>
                  <p className="rounded-2xl rounded-tl-md border border-white/10 bg-white/[0.06] px-4 py-3 text-sm leading-relaxed text-slate-100">
                    Explain the difference between a list and a tuple in Python.
                    Then tell me when you'd reach for one over the other.
                  </p>
                </div>
              </div>
              <div className="mt-3 flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-gradient-to-br from-indigo-500 to-violet-600 px-4 py-3 text-sm leading-relaxed text-white">
                  A list is mutable, a tuple is immutable — so I'd use a tuple
                  when the data shouldn't change, like a fixed set of
                  coordinates.
                </div>
              </div>
            </Card>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <SectionHeading
          eyebrow="Why InterVue AI"
          title="Built for real interview pressure"
          subtitle="A conversation that reads you, adapts to you, and then shows you exactly how to improve."
        />
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {features.map((feature) => (
            <Card
              key={feature.title}
              className="group relative overflow-hidden p-6 transition-all duration-300 hover:-translate-y-1 hover:border-white/20 hover:bg-white/[0.06]"
            >
              <div
                className={`pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-gradient-to-br to-transparent ${feature.glow} blur-2xl`}
                aria-hidden="true"
              />
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                <feature.icon className={`h-5 w-5 ${feature.tone}`} />
              </div>
              <h3 className="mt-4 text-lg font-semibold text-white">
                {feature.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">
                {feature.description}
              </p>
            </Card>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="mx-auto max-w-5xl scroll-mt-24 px-4 py-16 sm:px-6 sm:py-20">
        <SectionHeading
          eyebrow="How it works"
          title="From profile to report in four steps"
          subtitle="No spreadsheets, no calibration calls — just a focused, adaptive conversation."
        />
        <ol className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step, index) => (
            <li key={step.title} className="relative flex flex-col items-center text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-indigo-300">
                <step.icon className="h-6 w-6" />
              </div>
              <span className="mt-4 text-xs font-bold uppercase tracking-wider text-slate-500">
                Step {index + 1}
              </span>
              <h3 className="mt-1 text-base font-semibold text-white">
                {step.title}
              </h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-400">
                {step.description}
              </p>
            </li>
          ))}
        </ol>
      </section>

      {/* Trust / technology */}
      <section className="mx-auto max-w-7xl px-4 pb-20 sm:px-6 lg:px-8">
        <Card className="p-6 sm:p-10">
          <div className="flex flex-col gap-3 text-center">
            <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              What powers the interviewer
            </h2>
            <p className="mx-auto max-w-xl text-sm leading-relaxed text-slate-400">
              Adaptive and reliable — the conversation is grounded in real
              content and never loses context.
            </p>
          </div>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {trust.map((item) => (
              <div key={item.title} className="flex flex-col items-center text-center">
                <item.icon className="h-6 w-6 text-indigo-300" />
                <h3 className="mt-3 text-sm font-semibold text-white">
                  {item.title}
                </h3>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </Card>
      </section>

      {/* Final CTA */}
      <section className="relative mx-auto max-w-3xl px-4 pb-24 text-center">
        <div
          className="pointer-events-none absolute left-1/2 top-1/2 h-40 w-96 -translate-x-1/2 -translate-y-1/2 rounded-full bg-violet-600/15 blur-3xl"
          aria-hidden="true"
        />
        <div className="relative">
          <h2 className="text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl">
            Ready to get comfortable with the uncomfortable?
          </h2>
          <div className="mt-8 flex justify-center">
            <Button to="/candidates" size="lg">
              Start Interview
              <ArrowRightIcon className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

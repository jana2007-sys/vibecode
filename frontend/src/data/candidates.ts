/** Frontend-safe candidate selection data.

Derived from `backend/app/data/candidate.json` (the actual hackathon candidate
source). Only public profile data is included — no secrets, no credentials.
There is no candidate-list API endpoint, so selection uses this local copy and
sends the chosen profile straight to `POST /api/interview`.

The curriculum identifier is the real one used by the backend engine
(`curriculum-001`); we never invent a new identifier.
*/

import type { CandidateProfile } from "../types/candidate";

export const CURRICULUM_ID = "curriculum-001";

export const CANDIDATES: CandidateProfile[] = [
  {
    id: "candidate-001",
    name: "Alex Rivera",
    role: "Backend Engineer",
    years_of_experience: 2.0,
    skills: [
      { name: "Python", level: "intermediate" },
      { name: "SQL", level: "beginner" },
      { name: "Django", level: "intermediate" },
      { name: "Docker", level: "beginner" },
      { name: "System Design", level: "beginner" },
    ],
    learning_journey: [
      {
        type: "course",
        title: "Python for Everybody",
        description:
          "Completed an introductory Python course covering core language features.",
      },
      {
        type: "project",
        title: "RESTful Blog API",
        description:
          "Built a Django REST API with JWT auth and a small SQLite database.",
      },
      {
        type: "practice",
        title: "LeetCode / Codewars",
        description:
          "Regular practice on algorithm and data-structure problems, easy-to-medium.",
      },
    ],
    preferred_languages: ["Python", "JavaScript"],
    focus_areas: ["Backend API design", "Databases", "Testing"],
    notes:
      "Prefers practical examples over theory; learning SQL depth and system design next.",
  },
  {
    id: "candidate-002",
    name: "Ava Thompson",
    role: "Frontend Engineer",
    years_of_experience: 1.5,
    skills: [
      { name: "JavaScript", level: "intermediate" },
      { name: "React", level: "intermediate" },
      { name: "TypeScript", level: "beginner" },
      { name: "CSS", level: "advanced" },
    ],
    learning_journey: [
      {
        type: "course",
        title: "The Odin Project",
        description:
          "Completed the foundations and JavaScript track covering HTML, CSS, and ES6.",
      },
      {
        type: "project",
        title: "Dashboard UI",
        description:
          "Built a data-dashboard interface in React with client-side state management.",
      },
      {
        type: "practice",
        title: "Frontend Mentor",
        description:
          "Regular challenges focused on responsive layout and accessibility.",
      },
    ],
    preferred_languages: ["JavaScript", "TypeScript"],
    focus_areas: ["Component architecture", "Accessibility", "State management"],
    notes:
      "Strong on visual detail and CSS; learning TypeScript and testing next.",
  },
  {
    id: "candidate-003",
    name: "Leo Park",
    role: "Data Engineer",
    years_of_experience: 3.0,
    skills: [
      { name: "Python", level: "advanced" },
      { name: "SQL", level: "intermediate" },
      { name: "Spark", level: "beginner" },
      { name: "Airflow", level: "beginner" },
    ],
    learning_journey: [
      {
        type: "course",
        title: "Data Engineering Zoomcamp",
        description:
          "Completed coursework on batch and streaming pipelines with Docker and Postgres.",
      },
      {
        type: "project",
        title: "ELT Pipeline",
        description:
          "Built an ELT pipeline ingesting application events into a warehouse with dbt.",
      },
      {
        type: "book",
        title: "Designing Data-Intensive Applications",
        description:
          "Reading through distributed-systems and storage fundamentals.",
      },
    ],
    preferred_languages: ["Python", "SQL"],
    focus_areas: ["Data pipelines", "Warehousing", "Streaming"],
    notes:
      "Comfortable with pandas and SQL; learning Spark and streaming next.",
  },
  {
    id: "candidate-004",
    name: "Maya Chen",
    role: "Full-Stack Engineer",
    years_of_experience: 4.0,
    skills: [
      { name: "Python", level: "advanced" },
      { name: "React", level: "intermediate" },
      { name: "Node.js", level: "intermediate" },
      { name: "Docker", level: "beginner" },
    ],
    learning_journey: [
      {
        type: "project",
        title: "E-commerce Platform",
        description:
          "Built a full-stack storefront with a Django API, React client, and Postgres.",
      },
      {
        type: "course",
        title: "System Design Primer",
        description:
          "Studied scalability and reliability patterns for web applications.",
      },
      {
        type: "practice",
        title: "LeetCode",
        description:
          "Regular algorithm practice at medium difficulty across common patterns.",
      },
    ],
    preferred_languages: ["Python", "JavaScript"],
    focus_areas: ["API design", "Reliability", "Performance"],
    notes:
      "Solid full-stack foundation; learning distributed systems and container orchestration next.",
  },
];

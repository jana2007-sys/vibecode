"""Candidate answer evaluation.

Scores a candidate's answer for a given question against the curriculum's
``expects`` concepts, producing a structured per-question evaluation and
persisting a 0-10 score through the existing ScoreRepository. The deterministic
score is fully explainable; when Gemini is enabled (``GEMINI_ENABLED=true``) a
semantic evaluation is layered on top and can judge correctness rather than
keyword coverage, always with a deterministic fallback.

Deterministic scoring strategy
------------------------------

For a question with ``N`` expected concepts:

    score = 10.0 * coverage * length_factor

where

* ``coverage`` is how well the answer addresses the expected concepts:
  ``sum(degrees) / N`` (exactly ``1.0`` when there is nothing to test). Each
  concept's ``degree`` is ``1.0`` when the answer contains every token of the
  concept -- or of any of its recognized alternative phrasings -- and otherwise
  the best fraction of one phrasing's tokens that the answer contains, so a
  correct answer that touches part of ``memory address`` without the exact word
  ``address`` still earns partial credit.
* ``length_factor`` is ``min(1.0, unique_content_tokens / MIN_ANSWER_TOKENS)``,
  a penalty for extremely short answers so that naming a concept label without
  any elaboration cannot earn full marks. It is computed over *unique* tokens,
  so repeating the same word never inflates the score.

A concept is "matched" when every alphanumeric token of the concept -- or of
any of its recognized alternative phrasings in :data:`CONCEPT_ALIASES` --
appears in the answer, case-insensitively and stem-aware. Tokens count as equal
when they share a Porter stem, so ``performs`` matches ``performance``,
``caching`` matches ``cache``, and ``balancing`` matches ``balancer``; multi-
word concepts require all their tokens. Empty or blank answers score ``0.0``.
The same ``(answer, expects)`` input always produces the same result.

Semantic (AI) evaluation
-----------------------

When ``_try_ai_evaluate`` runs it sends the question, expected concepts, the
candidate's actual answer, and the deterministic coverage signal to the AI
layer. When a multi-AI verifier panel is configured (``AI_VERIFIER_MODELS``),
every configured model independently verifies whether the answer is correct
and awards its own 0-10 mark; the consensus verdict and score are adopted.
Without a panel, a single Gemini call adopts its 0-10 score, reasoning, and
feedback. The model(s) judge correctness, not keyword matching, so a correct
answer phrased differently from the expected vocabulary is credited.
AI-suggested covered/missing concepts are accepted only when they name an
expected concept exactly, so the LLM can never invent curriculum facts. Every
AI failure degrades to the deterministic result.

Limitations: the deterministic heuristic is a lexical coverage heuristic, not
comprehension. It cannot judge whether an answer is *correct* or how well the
candidate reasoned; it rewards answers that mention the expected vocabulary and
penalizes impoverished/absent ones. Semantic correctness and reasoning signals
are intentionally left out of the deterministic evaluator
(``AnswerEvaluation.reasoning`` is ``None`` there).

Collaborators: GeminiService, ScoreRepository, MessageRepository, PromptBuilder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.models.common import new_uuid, utc_now
from app.services.gemini_service import GeminiService
from app.services.prompt_builder import EVALUATION_SCHEMA, PromptBuilder
from app.services.verification_service import (
    VERDICT_CORRECT,
    AIVerifierEnsemble,
    Verification,
)
from app.utils.errors import ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

_TOKENS_PATTERN = re.compile(r"[a-z0-9]+")

#: Answers with fewer than this many *unique* content tokens are too brief to
#: earn full marks even when they name every expected concept.
MIN_ANSWER_TOKENS = 4

#: Completeness labels used by :class:`AnswerEvaluation`.
COMPLETENESS_EMPTY = "empty"
COMPLETENESS_UNSATISFACTORY = "unsatisfactory"
COMPLETENESS_PARTIAL = "partial"
COMPLETENESS_COMPLETE = "complete"


def _tokens(text: str) -> set[str]:
    """Return the normalized lowercase alphanumeric tokens of ``text``."""
    return set(_TOKENS_PATTERN.findall(text.lower()))


class _PorterStemmer:
    """Canonical Porter (1980) stemmer.

    Deterministic and side-effect-free per call; operates on lowercase
    a-z words. Implemented so concept matching is inflection-aware (e.g.
    ``performs``/``performance`` share the stem ``perform``).
    """

    def __init__(self) -> None:
        self.b = ""
        self.j = 0
        self.k = 0

    def _cons(self, i: int) -> bool:
        ch = self.b[i]
        if ch in "aeiou":
            return False
        if ch == "y":
            return True if i == 0 else not self._cons(i - 1)
        return True

    def _m(self) -> int:
        n = 0
        i = 0
        while True:
            if i > self.j:
                return n
            if not self._cons(i):
                break
            i += 1
        i += 1
        while True:
            while True:
                if i > self.j:
                    return n
                if self._cons(i):
                    break
                i += 1
            i += 1
            n += 1
            while True:
                if i > self.j:
                    return n
                if not self._cons(i):
                    break
                i += 1
            i += 1

    def _vowel_in_stem(self) -> bool:
        return any(not self._cons(i) for i in range(self.j + 1))

    def _doublec(self, j: int) -> bool:
        return j >= 1 and self.b[j] == self.b[j - 1] and self._cons(j)

    def _cvc(self, i: int) -> bool:
        if i < 2:
            return False
        if not self._cons(i) or self._cons(i - 1) or not self._cons(i - 2):
            return False
        return self.b[i] not in "wxy"

    def _ends(self, s: str) -> bool:
        length = len(s)
        if s[-1] != self.b[self.k]:
            return False
        if length > self.k + 1:
            return False
        if self.b[self.k - length + 1:self.k + 1] != s:
            return False
        self.j = self.k - length
        return True

    def _setto(self, s: str) -> None:
        self.b = self.b[:self.j + 1] + s
        self.k = len(self.b) - 1

    def _r(self, s: str) -> None:
        if self._m() > 0:
            self._setto(s)

    def _step1ab(self) -> None:
        if self.b[self.k] == "s":
            if self._ends("sses"):
                self.k -= 2
            elif self._ends("ies"):
                self._setto("i")
            elif self.b[self.k - 1] != "s":
                self.k -= 1
        if self._ends("eed"):
            if self._m() > 0:
                self.k -= 1
        elif (self._ends("ed") or self._ends("ing")) and self._vowel_in_stem():
            self.k = self.j
            if self._ends("at"):
                self._setto("ate")
            elif self._ends("bl"):
                self._setto("ble")
            elif self._ends("iz"):
                self._setto("ize")
            elif self._doublec(self.k):
                self.k -= 1
                if self.b[self.k] in "lsz":
                    self.k += 1
            elif self._m() == 1 and self._cvc(self.k):
                self._setto("e")

    def _step1c(self) -> None:
        if self._ends("y") and self._vowel_in_stem():
            self.b = self.b[:self.k] + "i"

    def _step2(self) -> None:
        if self.b[self.k] == "a":
            if self._ends("ational"):
                self._r("ate")
            elif self._ends("tional"):
                self._r("tion")
        elif self.b[self.k] == "c":
            if self._ends("enci"):
                self._r("ence")
            elif self._ends("anci"):
                self._r("ance")
        elif self.b[self.k] == "e":
            if self._ends("izer"):
                self._r("ize")
        elif self.b[self.k] == "l":
            if self._ends("abli"):
                self._r("able")
            elif self._ends("alli"):
                self._r("al")
            elif self._ends("entli"):
                self._r("ent")
            elif self._ends("eli"):
                self._r("e")
            elif self._ends("ousli"):
                self._r("ous")
        elif self.b[self.k] == "o":
            if self._ends("ization"):
                self._r("ize")
            elif self._ends("ation"):
                self._r("ate")
            elif self._ends("ator"):
                self._r("ate")
        elif self.b[self.k] == "s":
            if self._ends("alism"):
                self._r("al")
            elif self._ends("iveness"):
                self._r("ive")
            elif self._ends("fulness"):
                self._r("ful")
            elif self._ends("ousness"):
                self._r("ous")
        elif self.b[self.k] == "t":
            if self._ends("aliti"):
                self._r("al")
            elif self._ends("iviti"):
                self._r("ive")
            elif self._ends("biliti"):
                self._r("ble")
        elif self.b[self.k] == "g":
            if self._ends("logi"):
                self._r("log")

    def _step3(self) -> None:
        if self.b[self.k] == "e":
            if self._ends("icate"):
                self._r("ic")
            elif self._ends("ative"):
                self._r("")
            elif self._ends("alize"):
                self._r("al")
        elif self.b[self.k] == "i":
            if self._ends("iciti"):
                self._r("ic")
        elif self.b[self.k] == "l":
            if self._ends("ical"):
                self._r("ic")
            elif self._ends("ful"):
                self._r("")
        elif self.b[self.k] == "s":
            if self._ends("ness"):
                self._r("")

    def _step4(self) -> None:
        ch = self.b[self.k]
        matched = False
        if ch == "a":
            if self._ends("al"):
                matched = True
        elif ch == "c":
            if self._ends("ance") or self._ends("ence"):
                matched = True
        elif ch == "e":
            if self._ends("er"):
                matched = True
        elif ch == "i":
            if self._ends("ic"):
                matched = True
        elif ch == "l":
            if self._ends("able") or self._ends("ible"):
                matched = True
        elif ch == "n":
            if self._ends("ant") or self._ends("ement") or self._ends("ment") or self._ends("ent"):
                matched = True
        elif ch == "o":
            if (self._ends("ion") and self.b[self.j] in "st") or self._ends("ou"):
                matched = True
        elif ch == "s":
            if self._ends("ism"):
                matched = True
        elif ch == "t":
            if self._ends("ate") or self._ends("iti"):
                matched = True
        elif ch == "u":
            if self._ends("ous"):
                matched = True
        elif ch == "v":
            if self._ends("ive"):
                matched = True
        elif ch == "z":
            if self._ends("ize"):
                matched = True
        if matched and self._m() > 1:
            self.k = self.j

    def _step5(self) -> None:
        self.j = self.k
        if self.b[self.k] == "e":
            a = self._m()
            if a > 1 or (a == 1 and not self._cvc(self.k - 1)):
                self.k -= 1
        if self.b[self.k] == "l" and self._doublec(self.k) and self._m() > 1:
            self.k -= 1

    def stem(self, word: str) -> str:
        w = word.lower()
        if len(w) <= 2:
            return w
        self.b = w
        self.k = len(w) - 1
        self._step1ab()
        self._step1c()
        self._step2()
        self._step3()
        self._step4()
        self._step5()
        return self.b[:self.k + 1]


_PORTER = _PorterStemmer()


def _stem(word: str) -> str:
    """Return the Porter stem of a lowercase a-z token."""
    return _PORTER.stem(word)


def _word_forms(word: str) -> set[str]:
    """Return every form of ``word`` that can satisfy concept matching.

    A word contributes itself, its Porter stem, and (for stems ending in ``e``)
    the same stem without the trailing ``e``, so ``cache`` matches ``caching``
    and ``scale`` matches ``scaling``.
    """
    forms = {word}
    stem = _stem(word)
    forms.add(stem)
    if stem.endswith("e"):
        forms.add(stem[:-1])
    return forms


def _match_tokens(text: str) -> set[str]:
    """Return the union of :func:`_word_forms` over every token of ``text``."""
    forms: set[str] = set()
    for token in _tokens(text):
        forms.update(_word_forms(token))
    return forms


#: Alternative phrasings that satisfy an expected concept. Matching is per
#: concept: the concept counts as covered when ALL tokens of the concept OR of
#: any one of its aliases appear in the answer (stem-aware). Aliases let a
#: correct answer phrased in ordinary language score, not just answers that
#: echo the curriculum vocabulary verbatim.
CONCEPT_ALIASES: dict[str, list[str]] = {
    # Python Fundamentals
    "immutable": ["cannot change", "cannot be changed", "cannot be modified", "fixed", "unchangeable", "not mutable", "can't change", "can't be changed", "can't be modified", "cannot be altered", "read only", "read-only", "never change", "never changes", "does not change", "doesn't change"],
    "mutable": ["can change", "can be changed", "changeable", "modifiable", "modify", "can be modified", "can be altered"],
    "performance": ["perform", "fast", "faster", "speed", "efficient", "efficiency", "quicker", "less memory", "uses less memory", "takes less memory", "lower memory", "memory efficient", "smaller", "memory footprint"],
    "hashable": ["hash", "hashing", "hashed", "can be hashed", "usable as a key", "used as keys", "used as a key", "dict key", "dictionary key", "keys in a dictionary", "keys in dictionaries"],
    "global interpreter lock": ["gil", "interpreter lock"],
    "thread safety": ["thread safe", "thread-safe", "safety of threads", "safe for concurrent threads", "safe to share between threads"],
    "io-bound": ["i/o bound", "io bound", "input/output bound", "input output bound", "io intensive"],
    "cpu-bound": ["cpu bound", "processor bound", "cpu intensive", "cpu heavy", "compute bound"],
    "key-value pairs": ["key value", "key/value", "keys and values", "key value pair"],
    "ordered": ["keeps order", "maintains order", "insertion order", "order preserved"],
    "lookup": ["look up", "search", "access", "retrieval"],
    "except": ["exception handler", "catch", "exception handling", "error handling", "handle errors", "handling errors", "try and except"],
    "higher-order function": ["higher order function", "function that takes a function", "function returning a function"],
    "wrapper": ["wraps", "wrapping", "wrap", "wrapped function"],
    "syntax sugar": ["syntactic sugar", "sugar"],
    "identity": ["same object", "same reference", "is operator", "same object in memory", "object identity", "identical"],
    "equality": ["equal", "same value", "equal value", "value equality", "compares values", "value comparison"],
    "memory address": ["address", "location in memory", "in memory", "memory location", "same address"],
    "reference counting": ["refcount", "reference count", "ref counting", "count of references", "count references", "counts references"],
    "cycle detection": ["cycle", "detect cycles", "cycles", "detecting cycles"],
    "generational": ["generation", "gen", "generational collection"],
    "event loop": ["eventloop", "event-driven", "asyncio"],
    "concurrency": ["concurrent", "parallelism", "parallel"],
    "blocking": ["block", "blocked", "waits"],
    "concise": ["compact", "shorter"],
    "readability": ["readable", "clear"],
    "closure": ["closures", "enclosed scope"],
    "memoization": ["memoize", "memoised", "memoized"],
    "cache key": ["cache", "caching", "key"],
    "tuple unpacking": ["unpacking", "unpack a tuple", "destructuring"],
    "multiple assignment": ["multi assignment", "assign several"],
    "sequence": ["iterable"],
    "shallow copy": ["shallow", "copies references"],
    "deep copy": ["deep", "copies values", "recursive copy"],
    "nested objects": ["nested", "nested structures"],
    "caching": ["cache", "memoization", "store results"],
    "algorithmic complexity": ["complexity", "big o", "big-o", "time complexity"],
    "profiling": ["profile", "benchmark", "measure performance"],
    # Databases & SQL
    "unique": ["uniquely", "no duplicates", "cannot repeat", "can't repeat", "distinct"],
    "referential integrity": ["referential", "reference integrity", "referencing", "references", "references another table", "references a row", "foreign key references"],
    "relationship": ["relates", "relation", "links to another table"],
    "logarithmic": ["log", "log n", "logarithm"],
    "tree structure": ["tree", "b-tree", "btree", "b+ tree"],
    "selectivity": ["selective", "filters", "narrows the rows", "reduces the rows", "filters out rows"],
    "matching rows": ["matched rows", "matching records", "matching entries"],
    "nulls": ["null", "null values", "no match"],
    "join type": ["join", "type of join"],
    "lookup speed": ["lookup", "search speed", "query speed", "faster access"],
    "structure": ["data structure", "index structure"],
    "storage": ["space", "memory", "disk", "storage overhead"],
    "redundancy": ["duplicate", "duplication", "redundant data"],
    "integrity": ["data integrity", "consistency of data"],
    "read performance": ["read speed", "reads faster", "read throughput", "performance"],
    "atomicity": ["atomic"],
    "consistency": ["consistent", "eventual consistency"],
    "isolation": ["isolated", "concurrent transactions"],
    "durability": ["durable", "persistent", "persisted"],
    "schema flexibility": ["flexible schema", "schemaless", "dynamic schema", "no fixed schema"],
    "scaling": ["scale", "scale out", "scale horizontally", "horizontal scaling"],
    "explain plan": ["explain", "execution plan", "explain analyze"],
    "index": ["indexes", "indexing", "indexed"],
    "query plan": ["plan", "query planner", "planner"],
    "precompiled": ["compiled", "pre-compiled", "compiled once", "compiled ahead of time", "prepared once"],
    "virtual table": ["view", "virtual"],
    "permissions": ["permission", "access control", "grants", "grant"],
    "partition key": ["shard key", "partition", "partitioning key"],
    "distribution": ["distribute", "spread", "distributed"],
    "hotspots": ["hotspot", "hot spots", "skew", "skewed"],
    "primary key": ["primary"],
    "null": ["null values", "allow null"],
    "index maintenance": ["maintaining indexes", "maintain indexes", "index upkeep"],
    "write amplification": ["write overhead", "extra writes", "more writes", "amplified writes"],
    "tradeoff": ["trade off", "trade-off", "tradeoffs", "trade-offs"],
    "sharding": ["shard", "shards", "shard the database"],
    "partitioning": ["partition", "partition the data"],
    "write throughput": ["throughput", "writes per second", "write volume", "write rate", "inserts per second", "many writes"],
    # System Design
    "hash function": ["hashing", "hash", "hash the url"],
    "database": ["db", "data store", "storage"],
    "load balancer": ["load balancing", "load-balancer", "load balance", "balancer"],
    "http": ["https", "protocol"],
    "request": ["requests", "client request"],
    "response": ["responses", "server response"],
    "more machines": ["adding machines", "more servers", "add more machines", "scale out", "horizontal scaling", "multiple machines"],
    "more resources": ["bigger machine", "more cpu", "more memory", "bigger server", "scale up", "vertical scaling", "more power"],
    "bottlenecks": ["bottleneck", "limited by", "constraints"],
    "eviction": ["evict", "evicted", "least recently used", "lru", "removing old entries", "remove old entries", "drops the oldest"],
    "invalidation": ["invalidate", "stale", "cache invalidation", "clearing stale entries", "updating the cache"],
    "health checks": ["health check", "health", "health status"],
    "algorithm": ["round robin", "least connections", "hashing", "policy"],
    "availability": ["available", "uptime", "high availability", "failover", "stays up", "no downtime"],
    "replication": ["replicate", "replicas", "replica", "copies of data", "multiple copies"],
    "stale reads": ["stale", "eventually consistent"],
    "endpoints": ["endpoint", "urls", "routes", "api endpoints"],
    "query flexibility": ["flexible queries", "flexibility", "complex queries"],
    "overfetching": ["over-fetching", "extra data", "unneeded data", "fetching extra"],
    "read replicas": ["replicas", "read-only replicas", "replication", "read replica"],
    "load balancing": ["load balancer", "load balance", "load-balanced"],
    "producer": ["producers", "publisher", "publishers", "sender"],
    "consumer": ["consumers", "subscriber", "subscribers", "receiver"],
    "edge caching": ["cache at the edge", "caching at the edge", "edge cache"],
    "latency": ["lower latency", "reduce latency", "faster delivery", "speed"],
    "non-blocking": ["non blocking", "nonblocking", "async", "asynchronous", "does not wait"],
    "response time": ["response", "wait time", "latency", "turnaround"],
    "token bucket": ["tokens", "bucket", "leaky bucket", "token"],
    "quota": ["quotas", "limit", "rate limit", "per-user limit", "throttle"],
    "client identity": ["client", "user id", "ip address", "api key", "per client"],
    "feature store": ["features", "feature", "feature data"],
    "batch pipeline": ["batch", "pipeline", "batch processing", "offline pipeline"],
    # Algorithms & Data Structures
    "contiguous memory": ["contiguous", "consecutive memory", "contiguously", "adjacent memory", "next to each other", "one block"],
    "pointers": ["pointer", "links", "references", "node references"],
    "traversal": ["traverse", "iterating", "iterate", "following links", "walk", "walking", "visiting each node"],
    "hashing": ["hash", "hash function", "hashed"],
    "buckets": ["bucket", "slots", "bins", "bucket index"],
    "average case": ["average", "amortized", "on average", "expected case", "typically"],
    "sorted input": ["sorted", "sorted array", "sorted list", "sorted data"],
    "hashmap": ["hash map", "hash table", "hash-map", "dictionary"],
    "counting": ["count", "counts", "frequency", "frequencies", "freq"],
    "linear time": ["linear", "o(n)", "one pass", "single pass", "single scan", "scales linearly", "in one go"],
    "base case": ["base cases", "base", "base condition", "stopping condition", "terminating condition"],
    "call stack": ["stack", "stack depth", "call frames", "stack frames", "stack of calls"],
    "stack overflow": ["overflow", "depth limit", "recursion depth", "too deep recursion"],
    "pivot": ["pivot element", "pivots", "choose a pivot"],
    "divide and conquer": ["divide-and-conquer", "splitting"],
    "floyd's algorithm": ["floyd", "floyds", "tortoise and hare", "hare and tortoise", "cycle detection algorithm"],
    "slow and fast pointers": ["slow pointer", "fast pointer", "two pointers", "two-pointer", "two pointer technique"],
    "lifo": ["last in first out", "last-in-first-out"],
    "fifo": ["first in first out", "first-in-first-out"],
    "operations": ["operation", "push and pop", "push pop", "enqueue dequeue", "enqueue and dequeue"],
    "balanced": ["balance", "self balancing", "balanced tree"],
    "node ordering": ["node order", "ordering", "ordering of nodes", "left and right children"],
    "log n": ["logarithmic", "log", "o(log n)"],
    "queue": ["fifo", "first in first out", "first-in-first-out"],
    "stack": ["lifo", "last in first out", "last-in-first-out"],
    "ordering": ["order", "order of visitation", "visit order"],
    "uniqueness": ["unique", "no duplicates", "no duplicate values", "unique values"],
    "membership": ["contains", "lookup", "in set"],
    "hash map": ["hashmap", "hash table", "hash-map", "dictionary"],
    "two-sum": ["two sum", "2sum", "2-sum", "pair"],
    "complement": ["difference", "remainder", "target minus"],
    "doubly linked list": ["doubly-linked list", "linked list", "doubly linked", "double linked list", "doubly-linked"],
}


def _concept_phrases(concept: str) -> list[str]:
    """Return ``(concept, *aliases)`` candidate phrasings to match against."""
    return [concept, *CONCEPT_ALIASES.get(concept, [])]


def _string_list(values) -> list[str]:
    """Return non-blank string items from ``values`` (or an empty list)."""
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        text = str(value).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _match_expects(concept: str, expects: list[str]) -> str | None:
    """Return the curriculum-spelled concept matching ``concept`` (case-insensitive).

    ``None`` when no expected concept matches, so LLM-suggested concepts that
    the curriculum never supplied are dropped rather than trusted.
    """
    if not concept:
        return None
    lowered = concept.strip().lower()
    for expected in expects or []:
        if expected.strip().lower() == lowered:
            return expected
    return None


@dataclass(frozen=True)
class AnswerEvaluation:
    """Structured, deterministic evaluation of a single answer.

    Every concept field is grounded in the curriculum's ``expects`` data;
    nothing is invented by the evaluator.
    """

    score: float
    matched_concepts: list[str] = field(default_factory=list)
    missing_concepts: list[str] = field(default_factory=list)
    expected_concepts: int = 0
    coverage: float = 0.0
    completeness: str = COMPLETENESS_UNSATISFACTORY
    reasoning: str | None = None
    feedback: str = ""


class EvaluationEngine:
    """Evaluates candidate answers and persists scores."""

    def __init__(
        self,
        gemini_service: GeminiService,
        score_repository: ScoreRepository,
        message_repository: MessageRepository,
        prompt_builder: PromptBuilder | None = None,
        verifier: AIVerifierEnsemble | None = None,
    ) -> None:
        self._gemini = gemini_service
        self._scores = score_repository
        self._messages = message_repository
        self._builder = prompt_builder
        self._verifier = verifier

    # --- Deterministic concept coverage --------------------------------------

    def concept_coverage(self, answer: str, expects: list[str]) -> tuple[list[str], list[str]]:
        """Return ``(covered_concepts, missing_concepts)`` for an answer.

        A concept counts as covered when every token of the concept -- or of
        any of its :data:`CONCEPT_ALIASES` phrasings -- appears in the answer,
        case-insensitively and stem-aware (see :func:`_match_tokens`). Empty/
        blank concepts are ignored so they never skew the score or trigger a
        follow-up.
        """
        answer_forms = _match_tokens(answer)
        covered: list[str] = []
        missing: list[str] = []
        for concept in expects or []:
            if not _tokens(concept):
                continue
            if self._concept_covered(concept, answer_forms):
                covered.append(concept)
            else:
                missing.append(concept)
        return covered, missing

    def _concept_degrees(self, answer: str, expects: list[str]) -> list[float]:
        """Return a match degree (0..1) per non-blank expected concept.

        Parallel to the covered/missing lists from :meth:`concept_coverage`:
        blank concepts are skipped exactly the same way so the lists always
        align. Used by the deterministic score to credit correct answers that
        address a multi-word concept without echoing every word verbatim.
        """
        answer_forms = _match_tokens(answer)
        degrees: list[float] = []
        for concept in expects or []:
            if not _tokens(concept):
                continue
            degrees.append(self._concept_match_degree(concept, answer_forms))
        return degrees

    @staticmethod
    def _concept_match_degree(concept: str, answer_forms: set[str]) -> float:
        """Return the match degree of ``concept`` in the answer (0..1).

        ``1.0`` when the answer contains every token of the concept or of any
        of its :data:`CONCEPT_ALIASES` phrasings (all-or-nothing for aliases).
        Otherwise the degree is the fraction of the concept's *own* tokens
        present in the answer, so ``memory address`` earns ``0.5`` for an
        answer that says ``in memory`` but never the word ``address``. Partial
        credit is deliberately limited to the curriculum's own wording: alias
        phrasings are pre-approved alternatives and only count in full, so a
        stray word like ``not`` inside ``not mutable`` can never grant an
        ``immutable`` match.
        """
        canonical = _tokens(concept)
        if canonical and all(
            _word_forms(token) & answer_forms for token in canonical
        ):
            return 1.0
        for phrase in CONCEPT_ALIASES.get(concept, []):
            phrase_tokens = _tokens(phrase)
            if phrase_tokens and all(
                _word_forms(token) & answer_forms for token in phrase_tokens
            ):
                return 1.0
        if canonical:
            matched = sum(
                1 for token in canonical if _word_forms(token) & answer_forms
            )
            return matched / len(canonical)
        return 0.0

    @staticmethod
    def _concept_covered(concept: str, answer_forms: set[str]) -> bool:
        """Return True when any phrasing of ``concept`` is fully present.

        A phrasing matches when every one of its tokens shares at least one
        form (:func:`_word_forms`) with the answer, so ``caching`` matches
        ``caches`` and ``balancer`` matches ``balancing`` without requiring the
        exact spelling.
        """
        for phrase in _concept_phrases(concept):
            phrase_tokens = _tokens(phrase)
            if not phrase_tokens:
                continue
            if all(_word_forms(token) & answer_forms for token in phrase_tokens):
                return True
        return False

    # --- Structured evaluation -----------------------------------------------

    def evaluate_answer_detail(
        self,
        session_id: str,
        topic_id: str,
        question_id: str,
        answer: str,
        expects: list[str] | None = None,
        *,
        persist: bool = True,
        question: dict | None = None,
    ) -> AnswerEvaluation:
        """Evaluate an answer, optionally persist its score, and return the detail.

        Always starts from the deterministic evaluation. When Gemini is enabled
        and a prompt builder is wired, a semantic evaluation is layered on top
        (``_try_ai_evaluate``); any failure degrades gracefully to the
        deterministic result, so the LLM can never break scoring. Persists via
        the existing :class:`ScoreRepository` (the score and the human-readable
        feedback in ``rationale``), then returns the structured
        :class:`AnswerEvaluation`. Set ``persist=False`` when the answer should
        inform the conversation and report but must not be counted as its own
        score row — follow-up answers are scored against the same question as
        their primary and must not be double-counted in the overall/topic
        averages. ``question`` (the plan question with its ``text``/``expects``)
        is passed through to the semantic evaluator for grounding.
        """
        matched, missing = self.concept_coverage(answer, expects or [])
        degrees = self._concept_degrees(answer, expects or [])
        deterministic = self._evaluate(matched, missing, degrees, answer)
        evaluation = self._try_ai_evaluate(
            session_id, answer, expects or [], question, deterministic
        )
        if evaluation is None:
            evaluation = deterministic
        if not persist:
            return evaluation
        self._scores.create(
            score_id=new_uuid(),
            session_id=session_id,
            topic_id=topic_id,
            question_id=question_id,
            score=evaluation.score,
            rationale=evaluation.feedback,
            created_at=utc_now(),
        )
        logger.info(
            "Scored answer for %s/%s: %.2f (%d/%d concepts)",
            session_id,
            question_id,
            evaluation.score,
            len(evaluation.matched_concepts),
            len(evaluation.matched_concepts) + len(evaluation.missing_concepts),
        )
        return evaluation

    def _try_ai_evaluate(
        self,
        session_id: str,
        answer: str,
        expects: list[str],
        question: dict | None,
        deterministic: AnswerEvaluation,
    ) -> AnswerEvaluation | None:
        """Return an AI-backed evaluation, or ``None`` to keep deterministic.

        Called only when an AI layer is available; every failure (disabled, no
        builder, LLM error, malformed or ungrounded JSON) degrades gracefully to
        ``None`` so the AI can never break scoring. An empty answer is never sent
        to the model. When a multi-AI verifier panel is wired it owns the
        verdict; otherwise a single Gemini semantic evaluation is used.
        """
        if not answer.strip():
            return None

        deterministic_signal = {
            "covered": deterministic.matched_concepts,
            "missing": deterministic.missing_concepts,
        }
        if self._verifier is not None and self._verifier.enabled:
            verification = self._verifier.verify(
                session_id,
                question or {},
                answer,
                deterministic_signal,
            )
            if verification is not None:
                evaluation = self._from_verification(verification, expects, answer, deterministic)
                logger.info(
                    "Verified answer for %s: %.2f/10 (%d/%d models agree)",
                    session_id,
                    evaluation.score,
                    verification.agreed,
                    verification.total,
                )
                return evaluation

        if not self._gemini.enabled:
            return None
        if self._builder is None:
            logger.warning("Gemini enabled but no prompt builder wired; using deterministic score.")
            return None
        try:
            prompt = self._builder.build_evaluation_prompt(
                session_id=session_id,
                question=question or {},
                answer=answer,
                deterministic=deterministic_signal,
            )
            result = self._gemini.generate_json(prompt, EVALUATION_SCHEMA)
            evaluation = self._normalize_ai_evaluation(result, expects, answer, deterministic)
            logger.info(
                "AI evaluation for %s: %.2f/10 (grounded %d/%d concepts)",
                session_id,
                evaluation.score,
                len(evaluation.matched_concepts),
                len(evaluation.missing_concepts),
            )
            return evaluation
        except Exception as exc:  # noqa: BLE001 - never let Gemini break scoring
            logger.warning(
                "Gemini evaluation unavailable for %s; using deterministic score (%s)",
                session_id,
                type(exc).__name__,
            )
            return None

    @classmethod
    def _from_verification(
        cls,
        verification: Verification,
        expects: list[str],
        answer: str,
        deterministic: AnswerEvaluation,
    ) -> AnswerEvaluation:
        """Convert the verifier panel's consensus into an :class:`AnswerEvaluation`.

        The score is the panel's consensus mark (clamped/rounded). Covered and
        missing concepts come from the deterministic signal, which is already
        grounded to the curriculum's ``expects``.
        """
        score = round(max(0.0, min(10.0, verification.score)), 2)
        total = len(expects)
        covered = list(deterministic.matched_concepts)
        missing = list(deterministic.missing_concepts)
        coverage = round(len(covered) / total, 2) if total else 1.0
        reasoning = verification.reasoning or None
        feedback = verification.feedback or deterministic.feedback
        if verification.verdict == VERDICT_CORRECT and not feedback:
            feedback = (
                f"{verification.agreed} of {verification.total} AI models "
                "verified this answer as correct."
            )
        return AnswerEvaluation(
            score=score,
            matched_concepts=covered,
            missing_concepts=missing,
            expected_concepts=total,
            coverage=coverage,
            completeness=cls._ai_completeness(answer, score),
            reasoning=reasoning,
            feedback=feedback,
        )

    @classmethod
    def _normalize_ai_evaluation(
        cls,
        result: dict,
        expects: list[str],
        answer: str,
        deterministic: AnswerEvaluation,
    ) -> AnswerEvaluation:
        """Convert the raw Gemini payload into a grounded :class:`AnswerEvaluation`.

        The score is clamped to 0-10 and rounded. ``covered``/``missing`` are
        accepted only when they name an expected concept exactly (case-
        insensitive), so the LLM can never invent curriculum concepts.
        """
        raw_score = result.get("score")
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            raise ValidationError("Evaluation score must be a number.")
        score = round(max(0.0, min(10.0, float(raw_score))), 2)

        covered: list[str] = []
        for concept in _string_list(result.get("covered")):
            grounded = _match_expects(concept, expects)
            if grounded is not None and grounded not in covered:
                covered.append(grounded)
        missing: list[str] = []
        for concept in _string_list(result.get("missing")):
            grounded = _match_expects(concept, expects)
            if grounded is not None and grounded not in covered and grounded not in missing:
                missing.append(grounded)

        reasoning = str(result.get("reasoning") or "").strip() or None
        feedback = str(result.get("feedback") or "").strip() or deterministic.feedback
        total = len(expects)
        coverage = round(len(covered) / total, 2) if total else 1.0
        completeness = cls._ai_completeness(answer, score)
        return AnswerEvaluation(
            score=score,
            matched_concepts=covered,
            missing_concepts=missing,
            expected_concepts=total,
            coverage=coverage,
            completeness=completeness,
            reasoning=reasoning,
            feedback=feedback,
        )

    @staticmethod
    def _ai_completeness(answer: str, score: float) -> str:
        """Label AI-evaluated completeness from the semantic score."""
        if not answer.strip():
            return COMPLETENESS_EMPTY
        if score >= 8.0:
            return COMPLETENESS_COMPLETE
        if score > 0.0:
            return COMPLETENESS_PARTIAL
        return COMPLETENESS_UNSATISFACTORY

    def evaluate_answer(
        self,
        session_id: str,
        topic_id: str,
        question_id: str,
        answer: str,
        expects: list[str] | None = None,
    ) -> float:
        """Score a single answer on a 0-10 scale and persist the result.

        Convenience wrapper around :meth:`evaluate_answer_detail` that returns
        only the numeric score (kept for backward compatibility).
        """
        return self.evaluate_answer_detail(
            session_id, topic_id, question_id, answer, expects
        ).score

    def evaluate_topic(self, session_id: str, topic_id: str) -> float:
        """Aggregate per-question scores into a topic score.

        Averages every recorded score for the topic in the session; returns
        0.0 when the topic has no scores yet.
        """
        rows = [row for row in self._scores.list_by_session(session_id) if row["topic_id"] == topic_id]
        if not rows:
            return 0.0
        return round(sum(float(row["score"]) for row in rows) / len(rows), 2)

    # --- Deterministic scoring -----------------------------------------------

    @staticmethod
    def _evaluate(
        matched: list[str],
        missing: list[str],
        degrees: list[float],
        answer: str,
    ) -> AnswerEvaluation:
        """Derive the structured evaluation from concept coverage.

        See the module docstring for the exact scoring formula. This is a pure
        function of ``(answer, expects)``: the same input always yields the
        same evaluation. ``degrees`` carries each concept's partial-match
        degree (see :meth:`_concept_degrees`), so ``coverage`` credits correct
        answers that address a multi-word concept without echoing every word.
        """
        total = len(matched) + len(missing)
        if total == 0:
            return AnswerEvaluation(
                score=10.0,
                matched_concepts=[],
                missing_concepts=[],
                expected_concepts=0,
                coverage=1.0,
                completeness=COMPLETENESS_COMPLETE,
                reasoning=None,
                feedback="No evaluable concepts; nothing to test.",
            )

        coverage = sum(degrees) / len(degrees) if degrees else len(matched) / total
        unique_tokens = len(_tokens(answer))
        length_factor = min(1.0, unique_tokens / MIN_ANSWER_TOKENS)
        score = round(10.0 * coverage * length_factor, 2)
        completeness = EvaluationEngine._completeness(answer, coverage, length_factor)
        return AnswerEvaluation(
            score=score,
            matched_concepts=list(matched),
            missing_concepts=list(missing),
            expected_concepts=total,
            coverage=coverage,
            completeness=completeness,
            reasoning=None,
            feedback=EvaluationEngine._feedback(matched, missing, completeness),
        )

    @staticmethod
    def _completeness(answer: str, coverage: float, length_factor: float) -> str:
        """Label answer completeness from coverage and substance."""
        if not answer.strip():
            return COMPLETENESS_EMPTY
        if coverage >= 1.0 and length_factor >= 1.0:
            return COMPLETENESS_COMPLETE
        if coverage > 0.0:
            return COMPLETENESS_PARTIAL
        return COMPLETENESS_UNSATISFACTORY

    @staticmethod
    def _feedback(matched: list[str], missing: list[str], completeness: str) -> str:
        """Build candidate-facing feedback from the evaluation signals."""
        parts: list[str] = []
        if matched:
            parts.append("Covered: " + ", ".join(matched))
        if missing:
            parts.append("Missing: " + ", ".join(missing))
        if completeness == COMPLETENESS_EMPTY:
            parts.append("Answer is empty.")
        elif completeness == COMPLETENESS_COMPLETE:
            parts.append("Answer addresses every expected concept.")
        elif completeness == COMPLETENESS_PARTIAL:
            parts.append("Answer is only partial; elaborate on the expected concepts.")
        else:
            parts.append("Answer does not address the expected concepts.")
        return "; ".join(parts)

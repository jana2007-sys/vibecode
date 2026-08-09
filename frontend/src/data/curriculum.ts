/** Frontend-safe subset of the curriculum used for UI labeling only.

Mirrors `backend/app/data/curriculum.json`. The frontend uses these topic titles
and question texts purely to label the conversation (current topic, "Question X
of Y", and follow-up vs. new-question) by matching the authoritative backend
reply against the real question set. No questions are generated here and the
backend response is never second-guessed.
*/

export interface CurriculumTopic {
  id: string;
  title: string;
  questions: { id: string; text: string }[];
}

export interface CurriculumData {
  id: string;
  title: string;
  topics: CurriculumTopic[];
}

export const CURRICULUM_ID = "curriculum-001";

export const CURRICULUM: CurriculumData = {
  id: "curriculum-001",
  title: "Full-Stack Engineering Interview Path",
  topics: [
    {
      id: "topic-python",
      title: "Python Fundamentals",
      questions: [
        {
          id: "py-001",
          text: "Explain the difference between a list and a tuple in Python.",
        },
        {
          id: "py-002",
          text: "Describe how Python's GIL affects multithreaded programs.",
        },
        {
          id: "py-003",
          text: "What is the difference between a list and a dictionary in Python?",
        },
        {
          id: "py-004",
          text: "How do you handle exceptions in Python?",
        },
        {
          id: "py-005",
          text: "What is a decorator and how does it work?",
        },
        {
          id: "py-006",
          text: "Explain the difference between the `is` operator and `==` in Python.",
        },
        {
          id: "py-007",
          text: "How does Python's garbage collection work?",
        },
        {
          id: "py-008",
          text: "Describe the differences between async/await and threads in Python.",
        },
        {
          id: "py-009",
          text: "What is a list comprehension and when would you use one?",
        },
        {
          id: "py-010",
          text: "How would you design a decorator that caches function results?",
        },
        {
          id: "py-011",
          text: "How do you unpack a tuple into separate variables in Python?",
        },
        {
          id: "py-012",
          text: "What is the difference between a shallow copy and a deep copy?",
        },
        {
          id: "py-013",
          text: "How would you optimize a Python function that runs in a hot loop?",
        },
      ],
    },
    {
      id: "topic-databases",
      title: "Databases & SQL",
      questions: [
        {
          id: "db-001",
          text: "Explain the differences between a primary key and a foreign key.",
        },
        {
          id: "db-002",
          text: "How does a B-tree index speed up query lookups?",
        },
        {
          id: "db-003",
          text: "What is the difference between an inner join and a left join?",
        },
        {
          id: "db-004",
          text: "What is an index and why does it matter for query performance?",
        },
        {
          id: "db-005",
          text: "Explain the difference between normalization and denormalization.",
        },
        {
          id: "db-006",
          text: "What is a transaction and what does ACID stand for?",
        },
        {
          id: "db-007",
          text: "When would you choose a NoSQL store over a relational database?",
        },
        {
          id: "db-008",
          text: "How would you diagnose and fix a slow query?",
        },
        {
          id: "db-009",
          text: "What is the difference between a stored procedure and a view?",
        },
        {
          id: "db-010",
          text: "How would you design a database schema to support sharding?",
        },
        {
          id: "db-011",
          text: "What is the difference between a primary key and a unique constraint?",
        },
        {
          id: "db-012",
          text: "How does database indexing affect INSERT and UPDATE performance?",
        },
        {
          id: "db-013",
          text: "How would you design a database to handle millions of writes per second?",
        },
      ],
    },
    {
      id: "topic-systems",
      title: "System Design",
      questions: [
        {
          id: "sd-001",
          text: "Design a URL shortener. What are the key components?",
        },
        {
          id: "sd-002",
          text: "Explain what an API endpoint is.",
        },
        {
          id: "sd-003",
          text: "What is the difference between horizontal and vertical scaling?",
        },
        {
          id: "sd-004",
          text: "How would you design a caching layer for a web application?",
        },
        {
          id: "sd-005",
          text: "How does a load balancer distribute traffic?",
        },
        {
          id: "sd-006",
          text: "What is eventual consistency and when is it acceptable?",
        },
        {
          id: "sd-007",
          text: "What is the difference between REST and GraphQL?",
        },
        {
          id: "sd-008",
          text: "How would you scale a read-heavy web service?",
        },
        {
          id: "sd-009",
          text: "Design a message queue for decoupling two services.",
        },
        {
          id: "sd-010",
          text: "What is a CDN and why would you use one?",
        },
        {
          id: "sd-011",
          text: "What is the difference between synchronous and asynchronous communication?",
        },
        {
          id: "sd-012",
          text: "How would you design an API rate limiter?",
        },
        {
          id: "sd-013",
          text: "Design a system that serves personalized recommendations at scale.",
        },
      ],
    },
    {
      id: "topic-algorithms",
      title: "Algorithms & Data Structures",
      questions: [
        {
          id: "al-001",
          text: "Explain the difference between an array and a linked list.",
        },
        {
          id: "al-002",
          text: "What is a hash map and why is lookup usually constant time?",
        },
        {
          id: "al-003",
          text: "Explain the time complexity of a binary search.",
        },
        {
          id: "al-004",
          text: "How would you find the most frequent element in a list?",
        },
        {
          id: "al-005",
          text: "What is recursion and what are the risks of using it?",
        },
        {
          id: "al-006",
          text: "Explain how quicksort works and its average-case complexity.",
        },
        {
          id: "al-007",
          text: "How would you detect a cycle in a linked list?",
        },
        {
          id: "al-008",
          text: "What is the difference between a stack and a queue?",
        },
        {
          id: "al-009",
          text: "How would you implement a binary search tree and what is its lookup time?",
        },
        {
          id: "al-010",
          text: "Explain breadth-first versus depth-first traversal.",
        },
        {
          id: "al-011",
          text: "What is the difference between a hash set and a hash map?",
        },
        {
          id: "al-012",
          text: "How would you find two numbers in an array that sum to a target?",
        },
        {
          id: "al-013",
          text: "Explain how you would implement a least-recently-used (LRU) cache.",
        },
      ],
    },
  ],
};

/** The topic that owns the earliest question text found inside a reply. */
export function matchQuestion(reply: string): {
  topicId: string;
  topicTitle: string;
  questionId: string;
  text: string;
} | null {
  for (const topic of CURRICULUM.topics) {
    for (const question of topic.questions) {
      if (reply.includes(question.text)) {
        return {
          topicId: topic.id,
          topicTitle: topic.title,
          questionId: question.id,
          text: question.text,
        };
      }
    }
  }
  return null;
}

/** Parse "You will be asked N questions" from the interview intro reply. */
export function parseQuestionCount(reply: string): number | null {
  const match = /you will be asked (\d+) questions?/i.exec(reply);
  return match ? Number.parseInt(match[1], 10) : null;
}

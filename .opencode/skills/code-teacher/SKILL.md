---
name: code-teacher
description: Use when a user wants to learn or understand code rather than just have it written or fixed — e.g. they ask "I don't understand this function," "why does this work this way," "walk me through this codebase," or "teach me X" about a piece of code. Do not use for pure implementation requests where no explanation was asked for, or when the user explicitly wants code written/fixed without discussion.
---

## Rules

1. **Translate after technical terms and concepts** — When introducing any technical term (class, SSBO, pointer, slot, hash, contiguous block, etc.), immediately follow with "This means:" and a concrete, codebase-independent explanation of what it actually is in plain language. The pattern: [technical statement] → "This means: [plain version]." Do not assume the learner connects the term to the thing. No analogies — explain code in terms of what it is and does, not what it resembles.

## Steps

1. **Assess the learner's level**
   - Prefer using the learner's own code. If unavailable, use a minimal representative example.
   - Ask an open-ended question: "what parts here are unfamiliar to you?" OR "what could you do with this code?"
   - Based on their answer, decide where to start explaining.

   If their own code is too complex, use a minimal 1–5 line example instead.
   Example:
   - Show `int x = 5;` → "what do you think this line does?"

2. **Ground in the codebase** -- Verify against the actual code -- grep and read the file -- before describing how something works. Cite the real location: "here it is: path/to/file.py:42," not "there's probably a function that..." This gives a correct answer and models how to find answers on their own next time.


## Do Not

- Do not use analogies or paraphrase when explaining code
- Do not assume prior knowledge

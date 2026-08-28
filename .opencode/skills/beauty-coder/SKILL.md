---
name: beauty-coder
description: Use when writing, editing, refactoring, implementing, or reviewing ANY code across the project. Produce expert-level code that is readable, expressive, and learner-friendly — never cryptic or jargon-heavy. Preserves existing functionality and behavior unless explicitly instructed otherwise.
compatibility: opencode
---


## What I do

- Write code that reads like prose to another human.
- Preserve existing functionality and behavior unless explicitly instructed otherwise.
- Write code that reads like prose to another human.
- Add comments only for non-obvious intent, constraints, or tradeoffs
- Favor explicitness over hidden magic
- Write modern code that is still easy to follow

## How I write

- Avoid jargon-heavy or cryptic code
- Keep logic readable
- Add comments only for non-obvious intent, constraints, or tradeoffs
- Use consistent naming that a code learner can understand
- Break overly-complex logic into helper functions
- **No cryptic abbreviations in variable names.** Spell out what it is: `group_idx` not `gi`, `compiled_group` not `cg`, `validated_node` not `vn`. Single-letter loop variables (`i`, `j`) and short names in tight local scopes are acceptable. Variables with wider scope or appearing in generated output, logs, or errors must use full words.
- **Prefer human-readable English over paper/math jargon.** If a paper or math symbol is used (`mu, t, param, S, Si`), wrap it in plain English first: `endpoint` not `p`, `reference_stroke` not `S`, `neighbor_stroke` not `Si`, `position_on_segment` not `t`, `position_along_stroke` not `param`, `distance_to_neighbor` not `mu`, `nearest_distance` not `min_dist`. Keep the paper symbol only in a trailing comment `// mu` if needed for cross-reference — never as the primary name. Code must read like a sentence to a newbie without the paper.
- **Balance: concise but clear beats verbose.** `max_connection_dist` is preferred over `maximum_connection_distance` when meaning stays obvious. Short forms like `dist` for `distance` are fine if the surrounding name already says what it is (`connection_dist`, `fallback_dist`, `dist_difference`). Don't pad names to win a length contest — keep them short enough to scan, long enough to not need the paper.
- **Don't over-shorten.** `initial` must stay `initial`, not `init` — This means: `init` reads as "initialize" (verb), not "initial stroke" (noun). Same for `target` vs `tgt`. Shorten `distance→dist`, `connection→connection` is already fine, but keep domain nouns intact.


## When to use me

Before touching any code, proactively explore the codebase to build context relevant to the task, until you have a complete picture of how the affected code works and what depends on it and or what it is dependent on. Do not begin editing until you understand the blast radius.
Use this skill when writing or refactoring code that should be:
- production-ready
- modern
- advanced but approachable
- easy to maintain
- easy to learn from

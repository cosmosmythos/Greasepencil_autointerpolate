# AI Agent Skill Reference

This document is the reusable reference companion for `SKILL.md`.

## Purpose

Use this as the long-form template for testing, verifying, troubleshooting, or smoke-testing an addon inside a live host application through an agent bridge.

It is designed to be adapted across multiple addons without mentioning addon-specific APIs or internal names.

## What the skill covers

- Live host testing through an agent bridge
- Read-only inspection before mutation
- Controlled fresh-setup testing
- Update / dispatch / wait / readback loops
- Non-destructive verification patterns
- Error reporting and output validation

## General pattern

A test usually follows this shape:

1. Find the target state
2. Build or inspect state
3. Trigger update or dispatch
4. Wait for completion
5. Read back the result

Many addons are event-driven or async, so a test is rarely a single call. It is usually a sequence of state changes, host updates, and verification steps.

## Mode A — Verify what is already open

When the user already has a setup open:

1. Inspect the current state with a read-only tool or script.
2. Summarize what is currently present.
3. Ask a quick clarifying question if the intent is still ambiguous.
4. State the plan before making any changes.
5. Prefer non-destructive actions.
6. Verify the result after the update.

Do not guess when the setup is non-trivial.

## Mode B — Build a fresh test setup

When nothing useful is open, or the test needs a controlled environment:

1. Start from a clean or fresh setup.
2. Build only the pieces needed for the test.
3. Trigger the addon or host update.
4. Wait for completion.
5. Confirm the output with a concrete readback signal.

## Bridge assumptions

These are the general assumptions to use unless a specific project overrides them:

- Code execution happens in a fresh namespace per call.
- The code runs in the live host process, often on the main thread.
- Standard output is usually the primary reporting channel.
- The current UI or editor context belongs to the user, not the script.
- Some operations are asynchronous and require polling or delayed verification.
- A connection or bridge may need to be enabled before testing can begin.

## Safe patterns

- Prefer direct APIs over UI-dependent operators when possible.
- Use context overrides only when necessary.
- Snapshot state before making mutations.
- Restore any values you sweep or modify.
- Avoid destructive cleanup unless the user confirms it is safe.
- Treat “accepted” as different from “completed.”
- Verify the actual output, not only the absence of errors.

## Common pitfalls

- Assuming the script can change active UI state by writing internal properties alone
- Forgetting that code execution may start from a clean namespace
- Treating a successful dispatch as proof that the final result is ready
- Ignoring internal error state when output looks blank or incomplete
- Mutating the user’s current setup before confirming the task
- Relying on a single input or output path when the addon exposes multiple

## Bundled script categories

A reusable skill often includes scripts such as:

- a resolver helper for locating the addon package
- a smoke test for load / initialization
- a read-only introspection script
- a controlled build script
- a parameter sweep script
- a bake / export / end-to-end verification script

Adapt these scripts rather than copying them blindly.

## Reporting results

After a test, report:

- which script or action ran
- what passed and what failed
- any internal error string or traceback
- any useful version, generation, or dispatch number
- readback details such as dimensions, counts, or statistics
- whether any mutation was performed during Mode A

Do not claim verification unless the final readback or equivalent proof step produced non-trivial output.

---
name: blender-mcp
description: Test, verify, and troubleshoot addons inside a live host application through an agent bridge
---

# AI Agent Skill

## What I do

Use this skill when testing, verifying, troubleshooting, or smoke-testing an addon inside a live host application through an agent bridge.

This skill supports two modes:

- **Mode A — Verify what is already open:** inspect the current setup first, ask a quick clarifying question if needed, and avoid mutating anything until the task is confirmed.
- **Mode B — Build a fresh test setup:** create a controlled setup from scratch when no useful state is open or when the test requires one.

## How to use it

Follow the reusable patterns in the reference document alongside this skill. The reference holds the longer instructions, examples, and test flow details.

## Core rules

- Prefer live, end-to-end verification over assuming behavior.
- Treat code execution in the host as fresh each time unless the bridge explicitly preserves state.
- Use the host’s supported context, update, and readback mechanisms instead of relying on internal state changes alone.
- Prefer non-destructive checks when the user already has work open.
- Report concrete results, including errors, output state, and any readback statistics.

## When to use me

- After changing addon code and deploying it
- When verifying a new tool, command, UI element, or workflow
- When sweeping a parameter or control to confirm an update
- When checking the user’s current setup
- When reproducing a bug that depends on live host context or async processing
- When smoke-testing export, bake, render, generation, or sync flows

## When not to use me

- Pure library logic covered by unit tests
- Core engine logic that does not require the live host
- Anything better covered by an offline test suite
- Low-level internals that do not depend on host context or async dispatch

## Reference

See `ai-agent-skill-reference.md` for the full reusable template, testing loop, pitfalls, and reporting guidance.

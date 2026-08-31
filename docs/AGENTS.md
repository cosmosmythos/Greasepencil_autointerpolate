# Docs — Project Documentation

## Purpose

Private and public documentation for the GP Auto Interpolate project. Holds research-paper reading copies, implementation guides, and supplemental notes that support the `Executable/` (FTP-SC) and `Addon/` (Blender integration) work. This folder is **not** published as part of the Blender extension.

## Ownership

| File | Role |
|------|------|
| `Yang18-SCA.md` | Private readable markdown of Yang et al. SCA 2018 FTP-SC paper — personal study copy, **gitignored**, do not publish (copyrighted) |
| `Yang18-SCA.bak.md` | Backup of raw conversion before formatting — gitignored |
| `schneider_bezier_explained.html` | Public visual guide to Schneider 1990 polyline → Bezier fitting (faithful to `Executable/src/bezier_fit.cpp`, interactive canvas, 3D BU) |
| `bezier-fit-curve-master/` | Vendored JS reference `soswow/fit-curve` (MIT) — upstream for comparison only, not runtime |
| `*.private.md` | Any future private paper copies — gitignored |

Public docs (commit-safe) should use distinct names without the `Yang18-SCA` prefix or be summarized in own words.

## Local Contracts

- **Copyright rule:** Verbatim copies of copyrighted papers (e.g., `Yang18-SCA.pdf`) must remain **private and gitignored**. Only summaries, outlines, or short fair-use excerpts (<90 chars with citation) may be committed.
- **Source of truth for FTP-SC reference is `C:/Users/User/Downloads/Yang18-SCA.pdf`.** `docs/Yang18-SCA.md` is a derived, formatted reading copy for convenience.
- **Formatting is derived, not authoritative.** Do not edit the PDF via markdown — treat markdown as read-only view. Algorithm changes belong in `Executable/src/` and `Addon/core/`.
- **No AGENTS.md chain violation:** Docs do not shadow code contracts. Engine docs reference `Executable/AGENTS.md` and `Addon/core/AGENTS.md` for implementation details.
- **Units contract:** All docs/examples for stroke fitting use **Blender Units (meters, 3D cartesian)**. Never document tolerances in px for Grease Pencil strokes.

## Work Guidance

- Keep markdown human-readable: TOC at top, `##` for numbered sections (1., 2., 3.), `###` for subsections (3.1, 3.2), `**Figure N:**` for captions, proper paragraph flow (no `# Page N` markers, no `-\n` hyphenation).
- Preserve Unicode (α, μ, Θ, →) with UTF-8. Do not save as cp1252.
- Regeneration: `python -m pymupdf` → `get_text()` → regex cleanup (`(\w+)-\n(\w+)` → `\1\2`) → heading detection → write UTF-8 to `docs/Yang18-SCA.md`. Script lives in `C:/Users/User/AppData/Local/Temp/opencode/` (ephemeral).
- Prefer summaries for committed docs: `docs/ftpsc_implementation_guide.md`, `docs/code_analysis_*.md` are examples of commit-safe notes.

## Verification

- `Get-Content docs/Yang18-SCA.md -Encoding UTF8 | Select-Object -First 20` shows `# FTP-SC` + `## Contents` TOC, no `# Page` markers.
- `git check-ignore -v docs/Yang18-SCA.md` returns `.gitignore` entry (private).
- `python -c "import pathlib; p=pathlib.Path('docs/Yang18-SCA.md'); t=p.read_text(encoding='utf-8'); assert '## Abstract' in t and '## References' in t"` passes.

## Child DOX Index

| Child | Scope |
|-------|-------|
| `vendor/schneider/` | Vendored Schneider 1990 polyline → Bezier reference (MIT, 3D BU) |

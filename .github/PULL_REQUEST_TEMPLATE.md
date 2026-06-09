<!--
PRs must follow the branch-per-milestone rule in CLAUDE.md (project-local).
For milestone PRs, quote the ROADMAP "Exit when" line and link the green CI run.
-->

## Scope

<!-- Which milestone (Mx) or which docs/chore change. One sentence. -->

## What changed

<!-- Bullet list of the meaningful changes. -->

## Exit gate (milestone PRs only)

> _quote the "Exit when" line from docs/ROADMAP.md_

- [ ] Contract / integration tests prove the gate
- [ ] CI green: <link>
- [ ] No layer-rule violations (`uv run lint-imports`)
- [ ] No new public API outside what PRD §5.4 / LLD §2 allow

## Notes for review

<!-- Anything reviewers should pay extra attention to: tricky concurrency, fail-open semantics, lua-script changes, etc. -->

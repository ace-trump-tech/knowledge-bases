# Contributing to knowledge-bases

This repository is a maintained index of independently versioned knowledge bases. The goal is reproducible research infrastructure: every change should make a source easier to find, verify, update, or use.

## Before opening an issue

Please search existing issues first. Use the most specific Issue Form and include a concrete reproduction, affected submodule, commit or version, expected behavior, and relevant primary source links. Blank issues are disabled.

AI may assist with search, translation, or formatting, but AI-only or unverifiable submissions are not accepted. The author must personally verify every claim, provide evidence, and answer maintainer follow-up questions. A report may be closed as `needs-more-info` when it cannot be reproduced or explained.

For corrections that you can implement, prefer a pull request over an issue.

## Pull requests

1. Fork the repository and create a focused branch.
2. Keep each PR limited to one knowledge base, workflow, or documentation concern.
3. For submodule updates, explain the upstream commit and summarize the user-visible change.
4. Update the index or README when adding or renaming a source.
5. Run `./scripts/bootstrap.sh --check`, `python3 scripts/validate_catalog.py`, and `git diff --check` before submitting.
6. Write the PR description yourself and disclose material AI assistance. AI-generated text is not a substitute for testing, source verification, or technical ownership.

We welcome contributions from researchers, students, and engineers. A useful PR is small, sourced, reproducible, and maintainable; popularity or volume is not a substitute for evidence.

## Updating submodules

```bash
git submodule update --remote --merge
git add .gitmodules bases
git commit -m "chore: update knowledge base snapshots"
```

Submodule repositories retain their own licenses and contribution rules. Follow those rules when changing their contents.

## Maintainer standard

Changes are reviewed for provenance, reproducibility, link stability, licensing, and long-term maintenance cost. We may decline unsourced bulk imports, generated content, duplicate reports, or changes that make a clean checkout harder to reproduce.

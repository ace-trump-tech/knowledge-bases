# arxiv-daily

Daily arXiv ingestion pipeline that opens draft PRs against the
`ace-trump-tech` knowledge-base submodules. Designed to comply with the
hub's `CONTRIBUTING.md`: every change is a *draft* that the author must
personally review and merge.

## What it does

1. **`arxiv-daily fetch`** — for each KB config (`config/*.yaml`), pull
   recent arXiv papers in the configured categories, classify them by
   subtopic (keyword + optional LLM vote), rank them (citation count,
   influential citations, recency, novelty), and write:
   - `arxiv-daily/<date>/<subtopic>/<year>_<title>_<summary|deep>.md`
   - `arxiv-daily/<date>/manifest.{json,md}` (the PR body source)
   - `arxiv-daily/state.json` (dedup index, SHA-256 per arxiv_id)

2. **`arxiv-daily summarize`** — run **locally** (not in CI) to call a
   local `ollama` instance and fill in the markdown bodies of the
   `_待人工补_` placeholders. The author reviews, edits, then pushes.

3. **`arxiv-daily publish`** — push the resulting branch to the KB repo
   and open a draft PR labelled `arxiv-daily` + `needs-author-review`.

## Why two stages?

GitHub-hosted runners have no GPU and ~7 GB RAM, which is not enough to
run a 14B-parameter LLM. To respect that constraint and still get
end-to-end automation, the pipeline is split:

| Stage | Where | What it needs |
| --- | --- | --- |
| `fetch` + `publish` | GitHub Actions (or local) | Network to arXiv + GitHub; `gh` CLI; `SEMANTIC_SCHOLAR_KEY` (optional) |
| `summarize` | Local machine | `ollama` running, model pulled (default `qwen2.5:14b`) |

## Installation

```bash
# 1. install the package
pip install -e /Users/tuozhongyao/Downloads/knowledge-bases/scripts/arxiv-daily

# 2. (optional) install ollama and pull a model
brew install ollama
ollama serve &
ollama pull qwen2.5:14b

# 3. (optional) get a Semantic Scholar API key for higher rate limits
#    visit https://www.semanticscholar.org/product/api
export SEMANTIC_SCHOLAR_KEY=...

# 4. (optional) configure gh CLI for publish
gh auth login
```

## Daily workflow (author)

```bash
# A. review yesterday's drafts
arxiv-daily status
arxiv-daily summarize --all --date 2026-09-02

# B. tweak summaries, add missing citations, then publish
arxiv-daily publish --all --date 2026-09-02 --token-env GH_TOKEN

# C. visit each PR, edit the body if needed, click "Ready for review"
#    then merge.
```

## Dry-run

```bash
arxiv-daily fetch --all --output-root /tmp/arxiv-test --date 2026-09-02
cat /tmp/arxiv-test/2026-09-02/manifest.md
```

## Tests

```bash
cd /Users/tuozhongyao/Downloads/knowledge-bases/scripts/arxiv-daily
pip install pytest
python -m pytest tests/ -v
```

22 tests cover arXiv parsing, state dedup, classification, ranking,
rendering, CLI, and config loading.

## Required GitHub secrets

In `ace-trump-tech/knowledge-bases` → Settings → Secrets and variables →
 Actions:

| Secret | Required | Purpose |
| --- | --- | --- |
| `SUBMODULE_PUSH_TOKEN` | yes | Fine-grained PAT with `contents:write` + `pull-requests:write` on driver-kb, embodied-ai-kb, uav-gwm-kb |
| `SEMANTIC_SCHOLAR_KEY` | optional | Higher rate limit; without it we fall back to the slower public endpoint |
| `GITHUB_TOKEN` | auto-provided | Not used for pushes, only for non-PR API calls (logging) |

To rotate `SUBMODULE_PUSH_TOKEN`:

1. Go to <https://github.com/settings/tokens?type=beta>
3. Resource owner: `ace-trump-tech`
4. Repository access: select the 3 submodules only
5. Permissions: `Contents` → `Read and write`, `Pull requests` → `Read and write`
6. Copy token, paste into the repo's `SUBMODULE_PUSH_TOKEN` secret

## Output tree (within each KB submodule)

```
bases/<kb-name>/
└── arxiv-daily/
    ├── state.json
    ├── 2026-09-02/
    │   ├── manifest.json
    │   ├── manifest.md
    │   ├── 01_unified_perception_planning/
    │   │   ├── 2024_method_summary.md
    │   │   └── 2024_method_deep.md     # only if score ≥ deep_review_threshold
    │   ├── 02_world_model/...
    │   └── unclassified/                # papers the classifier was unsure about
```

After author review:

```bash
cd bases/<kb-name>
mkdir -p idea/01_unified_perception_planning
mv arxiv-daily/2026-09-02/01_unified_perception_planning/*.md idea/01_unified_perception_planning/
rm -rf arxiv-daily/2026-09-02
```

## License

MIT, same as the parent `knowledge-bases` hub.
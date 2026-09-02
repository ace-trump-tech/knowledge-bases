"""Command-line entry: ``arxiv-daily fetch | summarize | publish | status``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable

from . import __version__
from .config import load_config
from .fetch import run_fetch
from .providers.ollama import OllamaClient
from .providers.semantic_scholar import SemanticScholarClient

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _default_configs() -> list[Path]:
    if not CONFIG_DIR.exists():
        return []
    return sorted(CONFIG_DIR.glob("*.yaml"))


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arxiv-daily",
        description="Daily arxiv ingestion for ace-trump-tech knowledge bases.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # fetch
    p_fetch = sub.add_parser("fetch", help="fetch + classify + rank + render")
    p_fetch.add_argument("--config", action="append", type=Path,
                         help="path to a kb config yaml; can be repeated")
    p_fetch.add_argument("--all", action="store_true",
                         help="use every yaml in the bundled config/ dir")
    p_fetch.add_argument("--date", help="ISO date (default: today UTC)")
    p_fetch.add_argument("--output-root", type=Path,
                         default=Path("./_arxiv_daily_out"),
                         help="where to write manifests + per-day content")
    p_fetch.add_argument("--dry-run", action="store_true",
                         help="skip Semantic Scholar + ollama; don't update state.json")
    p_fetch.add_argument("--s2-cache", type=Path,
                         default=Path("./_arxiv_daily_out/.s2_cache.json"))

    # summarize
    p_sum = sub.add_parser("summarize", help="use ollama to fill markdown bodies in-place")
    p_sum.add_argument("--config", action="append", type=Path)
    p_sum.add_argument("--all", action="store_true")
    p_sum.add_argument("--date", required=True)
    p_sum.add_argument("--output-root", type=Path, default=Path("./_arxiv_daily_out"))
    p_sum.add_argument("--ollama-model", default="qwen2.5:14b")
    p_sum.add_argument("--language", choices=("zh", "en"), default="zh")

    # publish
    p_pub = sub.add_parser("publish", help="open / update draft PRs against KB repos")
    p_pub.add_argument("--config", action="append", type=Path)
    p_pub.add_argument("--all", action="store_true")
    p_pub.add_argument("--date", required=True)
    p_pub.add_argument("--output-root", type=Path, default=Path("./_arxiv_daily_out"))
    p_pub.add_argument("--base-branch", default="main")
    p_pub.add_argument("--commit-message", default="arxiv-daily: draft daily digest")
    p_pub.add_argument("--label", action="append", default=["arxiv-daily", "needs-author-review"])
    p_pub.add_argument("--token-env", default="ARXIV_DAILY_GH_TOKEN")

    # status
    p_status = sub.add_parser("status", help="show what would be fetched for each KB")
    p_status.add_argument("--config", action="append", type=Path)
    p_status.add_argument("--all", action="store_true")

    return parser


def _resolve_configs(args) -> list[Path]:
    explicit: list[Path] = list(getattr(args, "config", None) or [])
    use_all = bool(getattr(args, "all", False))
    if not explicit and not use_all:
        raise SystemExit("provide --config <yaml>... or --all")
    seen: set[Path] = set()
    out: list[Path] = []
    for p in explicit:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    if use_all:
        for p in _default_configs():
            if p.resolve() not in seen:
                seen.add(p.resolve())
                out.append(p)
    return out


# -- fetch ------------------------------------------------------------------


def cmd_fetch(args) -> int:
    configs = _resolve_configs(args)
    s2_cache = getattr(args, "s2_cache", None)
    s2 = None if args.dry_run else SemanticScholarClient(
        api_key=os.environ.get("SEMANTIC_SCHOLAR_KEY"),
        cache_path=s2_cache,
    )
    rc = 0
    for cfg_path in configs:
        try:
            cfg = load_config(cfg_path)
        except Exception as exc:    # noqa: BLE001 - surface to user
            print(f"[!] {cfg_path}: {exc}", file=sys.stderr)
            rc = 1
            continue
        result = run_fetch(
            cfg,
            output_root=args.output_root,
            iso_date=args.date,
            dry_run=args.dry_run,
            ollama=None,
            s2=s2,
        )
        print(
            f"[{cfg.name}] {result.iso_date}: "
            f"new={result.new_count} skipped={result.skipped_duplicates} "
            f"manifest={result.manifest_md_path}"
        )
    return rc


# -- summarize -------------------------------------------------------------


def cmd_summarize(args) -> int:
    from . import summarize as sm

    configs = _resolve_configs(args)
    client = OllamaClient(model=args.ollama_model)
    if not client.is_available():
        print(
            "ollama not reachable at http://localhost:11434 — start it with "
            "`ollama serve` and pull a model (e.g. `ollama pull qwen2.5:14b`).",
            file=sys.stderr,
        )
        return 2

    rc = 0
    for cfg_path in configs:
        try:
            cfg = load_config(cfg_path)
        except Exception as exc:    # noqa: BLE001
            print(f"[!] {cfg_path}: {exc}", file=sys.stderr)
            rc = 1
            continue
        day_root = args.output_root / args.date
        if not day_root.exists():
            print(f"[{cfg.name}] no draft for {args.date} at {day_root}", file=sys.stderr)
            continue
        template_dir = cfg.kb_local_path / "idea" / "_templates"
        if not template_dir.exists():
            print(f"[{cfg.name}] no template dir at {template_dir}", file=sys.stderr)
            continue

        for sub_dir in day_root.iterdir():
            if not sub_dir.is_dir() or sub_dir.name == "unclassified":
                continue
            for md_file in sub_dir.glob("*.md"):
                _enrich_file(md_file, cfg, sm, client, args.language)

    return rc


def _enrich_file(md_file: Path, cfg, sm, client: OllamaClient, language: str) -> None:
    """Read the manifest entry for the paper, fill in the body sections."""
    text = md_file.read_text(encoding="utf-8")
    if "## 方法\n_待人工补_\n" not in text and "## 方法\n" in text:
        return  # already enriched (heuristic)
    paper_meta = _paper_from_markdown(text)
    if paper_meta is None:
        return

    body = sm.generate_summary(paper_meta, ollama=client, language=language)
    if md_file.name.endswith("_deep.md"):
        body = sm.generate_deep_review(paper_meta, ollama=client, language=language)
    # Replace from `## 问题` onward
    new = text.split("## 问题", 1)[0] + body.lstrip("\n")
    md_file.write_text(new, encoding="utf-8")
    print(f"  - enriched {md_file.relative_to(md_file.parents[2])}")


def _paper_from_markdown(text: str):
    """Reconstruct a minimal ArxivPaper-like object from the rendered md."""
    from .providers.arxiv import ArxivPaper
    from datetime import datetime, timezone

    import re

    m_id = re.search(r"\*\*arXiv\*\*：(\S+)", text)
    m_title = re.search(r"# (.+)", text)
    m_pdf = re.search(r"\*\*PDF\*\*：(\S+)", text)
    m_abs = re.search(r"\*\*abs\*\*：(\S+)", text)
    if not (m_id and m_title):
        return None
    return ArxivPaper(
        arxiv_id=m_id.group(1),
        title=m_title.group(1).strip(),
        authors=[],
        abstract="",
        categories=[],
        primary_category="",
        published=datetime.now(tz=timezone.utc),
        updated=datetime.now(tz=timezone.utc),
        pdf_url=m_pdf.group(1) if m_pdf else "",
        abs_url=m_abs.group(1) if m_abs else "",
    )


# -- publish ---------------------------------------------------------------


def cmd_publish(args) -> int:
    from . import github_pr

    token = os.environ.get(args.token_env)
    if not token:
        print(
            f"missing GitHub token in env var {args.token_env!r}; aborting.",
            file=sys.stderr,
        )
        return 2

    configs = _resolve_configs(args)
    rc = 0
    for cfg_path in configs:
        try:
            cfg = load_config(cfg_path)
        except Exception as exc:    # noqa: BLE001
            print(f"[!] {cfg_path}: {exc}", file=sys.stderr)
            rc = 1
            continue

        kb_local = cfg.kb_local_path
        if not kb_local.exists():
            print(f"[{cfg.name}] local path missing: {kb_local}", file=sys.stderr)
            rc = 1
            continue

        branch = f"arxiv-daily/{args.date}"
        github_pr.create_branch(branch, workdir=kb_local, base=args.base_branch)

        day_root = args.output_root / args.date
        if not day_root.exists():
            print(f"[{cfg.name}] no draft for {args.date}", file=sys.stderr)
            continue

        files: list[Path] = []
        for path in day_root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(args.output_root)
                target = kb_local / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
                files.append(target)

        if not files:
            print(f"[{cfg.name}] no files to commit", file=sys.stderr)
            continue

        github_pr.commit_files(
            files,
            message=args.commit_message,
            workdir=kb_local,
        )
        github_pr.push_branch(branch, workdir=kb_local, token=token)

        title = f"[arxiv-daily] {cfg.name} {args.date}"
        body = (day_root / "manifest.md").read_text(encoding="utf-8")
        pr = github_pr.open_or_update_pr(
            repo=cfg.kb_repo,
            title=title,
            body=body,
            head_branch=branch,
            base_branch=args.base_branch,
            draft=True,
            labels=args.label,
            token=token,
            workdir=kb_local,
        )
        print(f"[{cfg.name}] PR #{pr.number}: {pr.url}")
    return rc


# -- status ----------------------------------------------------------------


def cmd_status(args) -> int:
    configs = _resolve_configs(args)
    for cfg_path in configs:
        try:
            cfg = load_config(cfg_path)
        except Exception as exc:    # noqa: BLE001
            print(f"[!] {cfg_path}: {exc}", file=sys.stderr)
            return 1
        print(
            f"[{cfg.name}] repo={cfg.kb_repo} local={cfg.kb_local_path} "
            f"categories={','.join(cfg.arxiv_categories)} "
            f"subtopics={len(cfg.subtopics)} top_n={cfg.top_n_per_subtopic}"
        )
    return 0


# -- entry ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.command == "fetch":
        return cmd_fetch(args)
    if args.command == "summarize":
        return cmd_summarize(args)
    if args.command == "publish":
        return cmd_publish(args)
    if args.command == "status":
        return cmd_status(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":    # pragma: no cover
    raise SystemExit(main())
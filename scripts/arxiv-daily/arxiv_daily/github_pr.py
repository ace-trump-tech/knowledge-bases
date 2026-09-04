"""Open / update draft PRs against KB submodules.

We deliberately support two backends so this works in both
``actions`` (with ``ARXIV_DAILY_GH_TOKEN`` set) and locally (when the user
has ``gh auth login`` configured).
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .exceptions import GitHubAuthError

LOGGER = logging.getLogger(__name__)


@dataclass
class PRInfo:
    number: int
    url: str
    title: str
    head: str
    base: str


def ensure_labels(
    *,
    repo: str,
    labels: Iterable[str],
    token: Optional[str] = None,
    workdir: Optional[Path] = None,
) -> None:
    """Create labels on ``repo`` if they don't exist (idempotent).

    Fine-grained PATs without ``administration:write`` scope can't create repo
    labels via ``gh label create``. We try anyway because the user's token
    is typically scoped to the kb repos and may include ``issues``-level
    write; if it does, this is a no-op.

    Failures are logged but never raised — the caller will still attempt the
    ``gh pr create --label ...`` which fails loudly if a label truly doesn't
    exist and can't be created.
    """
    workdir = workdir or Path.cwd()
    env = None
    if token:
        env = {"GH_TOKEN": token}
    for label in labels:
        cmd = ["gh", "label", "create", label, "--repo", repo,
               "--color", "cccccc", "--description",
               f"Managed by arxiv-daily pipeline"]
        try:
            _run(cmd, env=env, cwd=workdir)
            LOGGER.info("created label %r on %s", label, repo)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").lower()
            if "already exists" in stderr:
                continue  # idempotent — label is what we wanted
            LOGGER.warning("could not create %r on %s: %s", label, repo,
                           (exc.stderr or "").strip())


def open_or_update_pr(
    *,
    repo: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
    draft: bool = True,
    labels: Iterable[str] = (),
    token: Optional[str] = None,
    workdir: Optional[Path] = None,
) -> PRInfo:
    """Open a draft PR or update the body of an existing one with the same head.

    Strategy:
      1. ``gh pr create`` first; if it already exists for ``head``, fall back to
         ``gh pr edit`` to refresh labels + body.
    """
    workdir = workdir or Path.cwd()
    label_args = [a for lab in labels for a in ("--label", lab)]
    common = [
        "--repo", repo,
        "--head", head_branch,
        "--base", base_branch,
        "--title", title,
        "--body", body,
    ]
    if draft:
        common.append("--draft")
    common.extend(label_args)

    env = None
    if token:
        env = {"GH_TOKEN": token}

    # try create
    create_cmd = ["gh", "pr", "create", *common]
    try:
        out = _run(create_cmd, env=env, cwd=workdir)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").lower()
        if "already exists" in stderr or "a pull request already exists" in stderr:
            LOGGER.info("PR already exists for %s; editing instead", head_branch)
            edit_cmd = ["gh", "pr", "edit", head_branch, *common]
            edit_cmd = [c for c in edit_cmd if c != "--draft"]
            out = _run(edit_cmd, env=env, cwd=workdir)
        else:
            raise

    return _parse_pr_output(out, head_branch=head_branch, base_branch=base_branch)


def push_branch(branch: str, *, workdir: Path, token: Optional[str] = None) -> None:
    """Push a local branch to ``origin`` with token auth if provided.

    The submodule's remote is an unauthenticated ``https://github.com/<org>/<repo>.git``
    URL; the GitHub Actions runner has no global credential helper for it, so
    without help ``git push`` is rejected with HTTP 401/403.

    We install a one-shot credential helper via ``git -c credential.helper=...``
    so the token never enters the URL itself (avoids quoting issues with
    fine-grained PATs that may contain ``+`` and ``/``).
    """
    cmd = ["git", "push", "-u", "origin", branch]
    if token:
        # Inline credential helper: echo user/pass when invoked. Use single
        # quotes around the password so any token chars survive shell parsing.
        helper = (
            f"!f() {{ echo username=x-access-token; echo password='{token}'; }}; f"
        )
        cmd = [
            "git", "-c", f"credential.helper={helper}", "push", "-u", "origin", branch,
        ]
    _run(cmd, cwd=workdir)


def commit_files(
    paths: Iterable[Path],
    *,
    message: str,
    workdir: Path,
    author_name: str = "arxiv-daily bot",
    author_email: str = "arxiv-daily@users.noreply.github.com",
) -> None:
    """Stage ``paths`` (relative to ``workdir``) and create a commit."""
    rel = [str(p.relative_to(workdir)) for p in paths]
    _run(["git", "add", "--", *rel], cwd=workdir)
    _run(
        [
            "git",
            "-c", f"user.name={author_name}",
            "-c", f"user.email={author_email}",
            "commit",
            "-m", message,
        ],
        cwd=workdir,
    )


def create_branch(branch: str, *, workdir: Path, base: str = "main") -> None:
    """Create (or reset to origin/base) a working branch; no-op if already there.

    Stashes any in-progress edits in the submodule's worktree before switching
    branches — the parent workflow may have rsync'd new files into the
    submodule between runs and ``git checkout`` refuses to clobber them.
    """
    _run(["git", "fetch", "origin", base], cwd=workdir, check=False)
    existing = _run(
        ["git", "branch", "--list", branch], cwd=workdir, check=False
    ).stdout.strip()
    # Stash any dirty edits so checkout doesn't abort. Keep index clean.
    dirty = _run(
        ["git", "status", "--porcelain"], cwd=workdir, check=False
    ).stdout.strip()
    if dirty:
        _run(["git", "stash", "--include-untracked"], cwd=workdir, check=False)
    try:
        if existing:
            _run(["git", "checkout", branch], cwd=workdir)
        else:
            _run(["git", "checkout", "-b", branch, f"origin/{base}"], cwd=workdir)
    finally:
        # Pop the stash so the new files we just copied land in the worktree.
        stash_list = _run(
            ["git", "stash", "list"], cwd=workdir, check=False
        ).stdout.strip()
        if stash_list:
            _run(["git", "stash", "pop"], cwd=workdir, check=False)


# -- internals --------------------------------------------------------------


def _run(cmd: list[str], *, env: dict | None = None, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    import os

    full_env = {**os.environ, **(env or {})}
    try:
        return subprocess.run(
            cmd, env=full_env, cwd=str(cwd), text=True,
            capture_output=True, check=check,
        )
    except FileNotFoundError as exc:
        if cmd and cmd[0] == "gh":
            raise GitHubAuthError(
                "`gh` CLI not found; install via `brew install gh` or "
                "https://cli.github.com/manual/installation"
            ) from exc
        raise


def _parse_pr_output(out: subprocess.CompletedProcess, *, head_branch: str, base_branch: str) -> PRInfo:
    text = out.stdout.strip()
    # gh returns the PR URL on stdout; parse last URL-looking token.
    url = ""
    for token in reversed(text.split()):
        if token.startswith("https://github.com/") and "/pull/" in token:
            url = token.rstrip("/")
            break
    if not url:
        raise GitHubAuthError(f"could not parse PR URL from `gh` output: {text!r}")
    number = int(url.rsplit("/", 1)[-1])
    return PRInfo(
        number=number,
        url=url,
        title="",            # filled by caller context
        head=head_branch,
        base=base_branch,
    )


__all__ = ["PRInfo", "open_or_update_pr", "push_branch", "commit_files",
           "create_branch", "ensure_labels"]
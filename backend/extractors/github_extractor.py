"""GitHub extractor.

Either pulls live data via PyGithub (using GITHUB_TOKEN) or reads a pre-fetched
JSON snapshot for the demo.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from backend.config import CLAUDE_EXTRACTION_MODEL, GITHUB_TOKEN
from backend.extractors._claude import call_claude_json
from backend.models.schemas import DecisionType, Entity, SourceType

log = logging.getLogger(__name__)


EXTRACTION_PROMPT = """You are analyzing GitHub repository activity for team "{team}".
Repository: "{repo_name}"

Activity:
{activity}

Extract ALL entities representing decisions, plans, and technical changes.
Focus on what the code ACTUALLY DOES — this will be compared against
what teams SAY in meetings to detect contradictions.

Pay special attention to:
- BREAKING CHANGE commits or PRs
- New service / module creation
- API changes (REST to GraphQL, endpoint deprecation, version bumps)
- Dependency additions or removals
- Files that indicate architectural decisions (auth/, payments/, notifications/, etc.)

For each entity:
- name: Short specific identifier (e.g., "Migrate user endpoints to GraphQL")
- description: 1-2 sentences
- decision_type: One of [decision, plan, commitment, concern, dependency]
- speaker: Author / PR opener if visible (else null)
- confidence: 0.0 to 1.0 (merged > open > draft)
- raw_text: PR title or commit message

Return ONLY valid JSON array."""


# ---------------------------------------------------------------------------
# Live fetching
# ---------------------------------------------------------------------------
def fetch_repo_activity(
    repo_full_name: str,
    max_prs: int = 10,
    max_commits: int = 20,
    exclude_pr_numbers: Optional[set[int]] = None,
    exclude_commit_shas: Optional[set[str]] = None,
) -> tuple[str, set[int], set[str], Optional[str]]:
    """Fetch recent PRs + commits from GitHub.

    Returns ``(formatted_text, included_pr_numbers, included_commit_shas,
    latest_activity_iso)``. Items whose id is in the exclude sets are skipped
    (used for delta syncs). ``latest_activity_iso`` is the most recent
    ``pr.updated_at`` / ``commit.committer.date`` seen in this fetch — used
    by the dashboard to show "last activity X ago" per repo.
    """
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set")
    from github import Github

    excluded_prs = exclude_pr_numbers or set()
    excluded_shas = exclude_commit_shas or set()

    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(repo_full_name)

    latest_iso: Optional[str] = None

    def consider(ts) -> None:
        """Track the most-recent timestamp seen across PRs and commits."""
        nonlocal latest_iso
        if ts is None:
            return
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        if not isinstance(ts, str) or not ts:
            return
        if latest_iso is None or ts > latest_iso:
            latest_iso = ts

    # Pull requests — degrade gracefully so a single bad PR doesn't kill the
    # whole sync (the same applies to commits below). Manual iteration with
    # a break instead of ``[:max_prs]`` because PyGithub's PaginatedList
    # slicing raises IndexError on empty result sets.
    pr_numbers: set[int] = set()
    pr_lines = ["## Pull Requests"]
    try:
        seen = 0
        for pr in repo.get_pulls(state="all", sort="updated", direction="desc"):
            if seen >= max_prs:
                break
            seen += 1
            try:
                consider(getattr(pr, "updated_at", None))
                if pr.number in excluded_prs:
                    continue
                pr_numbers.add(pr.number)
                body = (pr.body or "").strip().replace("\n", " ")[:400]
                author = pr.user.login if pr.user else "?"
                pr_lines.append(
                    f"#{pr.number} [{pr.state}{', merged' if pr.merged else ''}] "
                    f"{pr.title}\n  by {author}\n  {body}"
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Skipping PR %s: %s", getattr(pr, "number", "?"), exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to fetch PRs for %s: %s", repo_full_name, exc)
        pr_lines.append(f"  (could not fetch PRs: {exc})")

    commit_shas: set[str] = set()
    commit_lines = ["## Commits"]
    try:
        seen = 0
        for commit in repo.get_commits():
            if seen >= max_commits:
                break
            seen += 1
            try:
                sha7 = commit.sha[:7]
                committed = (
                    commit.commit.committer.date if commit.commit.committer else None
                )
                consider(committed)
                if sha7 in excluded_shas:
                    continue
                commit_shas.add(sha7)
                raw_msg = (commit.commit.message or "").strip()
                msg_lines = raw_msg.splitlines()
                msg = msg_lines[0] if msg_lines else "(no message)"
                if commit.author and commit.author.login:
                    author = commit.author.login
                elif commit.commit.author and commit.commit.author.name:
                    author = commit.commit.author.name
                else:
                    author = "?"
                commit_lines.append(f"{sha7} {msg} (by {author})")
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Skipping commit %s: %s",
                    getattr(commit, "sha", "?")[:7],
                    exc,
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to fetch commits for %s: %s", repo_full_name, exc)
        commit_lines.append(f"  (could not fetch commits: {exc})")

    text = "\n".join(pr_lines + [""] + commit_lines)
    return text, pr_numbers, commit_shas, latest_iso


def fetch_repo_activity_from_json(
    json_path: str,
    exclude_pr_numbers: Optional[set[int]] = None,
    exclude_commit_shas: Optional[set[str]] = None,
) -> tuple[str, str, set[int], set[str], Optional[str]]:
    """Read a pre-fetched repo snapshot.

    Returns ``(formatted_text, repo_name, included_pr_numbers,
    included_commit_shas, latest_activity_iso)``.
    """
    with open(json_path) as f:
        data = json.load(f)

    excluded_prs = exclude_pr_numbers or set()
    excluded_shas = exclude_commit_shas or set()

    repo_name = data.get("repo_name", json_path)

    latest_iso: Optional[str] = None

    def consider(ts) -> None:
        nonlocal latest_iso
        if not ts or not isinstance(ts, str):
            return
        if latest_iso is None or ts > latest_iso:
            latest_iso = ts

    pr_numbers: set[int] = set()
    pr_lines = ["## Pull Requests"]
    for pr in data.get("pull_requests", []):
        num = pr.get("number")
        try:
            num_int = int(num)
        except (TypeError, ValueError):
            num_int = None
        consider(pr.get("updated_at"))
        if num_int is not None and num_int in excluded_prs:
            continue
        if num_int is not None:
            pr_numbers.add(num_int)
        files = ", ".join(pr.get("files", []))
        pr_lines.append(
            f"#{num} [{pr.get('state','?')}] {pr.get('title','')}\n"
            f"  description: {pr.get('description','')}\n"
            f"  files: {files}"
        )

    commit_shas: set[str] = set()
    commit_lines = ["## Commits"]
    for c in data.get("commits", []):
        sha7 = str(c.get("sha", ""))[:7]
        consider(c.get("date"))
        if sha7 and sha7 in excluded_shas:
            continue
        if sha7:
            commit_shas.add(sha7)
        commit_lines.append(
            f"{sha7} {c.get('message','')} "
            f"(by {c.get('author','?')} on {c.get('date','?')})"
        )

    text = "\n".join(pr_lines + [""] + commit_lines)
    return text, repo_name, pr_numbers, commit_shas, latest_iso


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def extract_entities_from_repo(
    activity: str, team: str, repo_name: str
) -> list[Entity]:
    if not activity.strip():
        return []
    prompt = EXTRACTION_PROMPT.format(team=team, repo_name=repo_name, activity=activity)
    raw = call_claude_json(prompt, max_tokens=3500, model=CLAUDE_EXTRACTION_MODEL)
    if not isinstance(raw, list):
        log.warning("GitHub extractor expected list, got %r", type(raw))
        return []

    now = datetime.utcnow()
    entities: list[Entity] = []
    for item in raw:
        try:
            decision_type = DecisionType(item.get("decision_type", "decision"))
        except ValueError:
            decision_type = DecisionType.DECISION
        entities.append(
            Entity(
                id=f"gh-{uuid.uuid4().hex[:10]}",
                name=str(item.get("name", "")).strip()[:200],
                description=str(item.get("description", "")).strip(),
                source_type=SourceType.GITHUB,
                source_id=repo_name,
                team=team,
                decision_type=decision_type,
                timestamp=now,
                speaker=item.get("speaker"),
                confidence=float(item.get("confidence", 0.9)),
                raw_text=str(item.get("raw_text", "")),
            )
        )
    return entities


def process_repo(
    *,
    repo_full_name: Optional[str] = None,
    json_path: Optional[str] = None,
    team: str,
    max_prs: int = 10,
    max_commits: int = 20,
    exclude_pr_numbers: Optional[set[int]] = None,
    exclude_commit_shas: Optional[set[str]] = None,
) -> tuple[list[Entity], set[int], set[str], str, Optional[str]]:
    """Fetch repo activity and extract entities.

    Returns ``(entities, included_pr_numbers, included_commit_shas,
    repo_name, latest_activity_iso)``. Pass exclude_* sets to skip
    already-seen items (delta sync).
    """
    if not repo_full_name and not json_path:
        raise ValueError("Either repo_full_name or json_path must be provided")

    if json_path:
        activity, repo_name, pr_nums, sha7s, latest_iso = (
            fetch_repo_activity_from_json(
                json_path,
                exclude_pr_numbers=exclude_pr_numbers,
                exclude_commit_shas=exclude_commit_shas,
            )
        )
    else:
        activity, pr_nums, sha7s, latest_iso = fetch_repo_activity(
            repo_full_name,  # type: ignore[arg-type]
            max_prs=max_prs,
            max_commits=max_commits,
            exclude_pr_numbers=exclude_pr_numbers,
            exclude_commit_shas=exclude_commit_shas,
        )
        repo_name = repo_full_name  # type: ignore[assignment]

    if not pr_nums and not sha7s:
        return [], set(), set(), repo_name, latest_iso  # nothing new

    entities = extract_entities_from_repo(activity, team, repo_name)
    return entities, pr_nums, sha7s, repo_name, latest_iso

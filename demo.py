"""Standalone end-to-end demo showcasing the new meeting-triggered flow.

Phase 1: feed the persistent memory with repos, tickets and Slack channels.
         No conflicts surface yet — those sources just keep the memory current.
Phase 2: ingest meetings one by one. Each meeting triggers a fresh analysis
         over the whole memory; the pair cache keeps Claude costs flat across
         repeat runs.

Usage:
    python demo.py                # full flow
    python demo.py --reset        # wipe data/store first
    python demo.py --skip-slack
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from backend.detection.conflict import classify_conflicts
from backend.detection.graph import build_graph, export_to_html, graph_stats
from backend.extractors.meeting import process_meeting
from backend.models.schemas import EntityEmbedding, IngestEvent, SourceType
from backend.semantic.embeddings import SemanticIndex, embed_entities
from backend.semantic.normalizer import normalize_pairs
from backend.storage import get_store
from backend.sync import sync_repo, sync_slack_channel, sync_ticket_file
from datetime import datetime
import uuid

ROOT = Path(__file__).parent
DATA = ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("synclayer.demo")

SEVERITY_ICON = {"critical": "🚨", "warning": "⚠️ ", "info": "ℹ️ "}
SOURCE_ICON = {"meeting": "🎙️", "github": "💻", "slack": "💬", "ticket": "🎫"}


def _print_section(title: str) -> None:
    print()
    print("─" * 78)
    print(f"  {title}")
    print("─" * 78)


def _ingest(store, entities, source_type, team, description) -> int:
    """Embed + add to store, record an event, return # newly added."""
    if not entities:
        print(f"  {SOURCE_ICON.get(source_type.value,'·')} {team:<8} {description} → 0 entities")
        return 0
    emb = embed_entities(entities)
    new = store.add_entities([e.entity for e in emb], [e.embedding for e in emb])
    store.record_event(
        IngestEvent(
            id=f"ev-{uuid.uuid4().hex[:8]}",
            source_type=source_type,
            team=team,
            description=description,
            entities_extracted=len(entities),
            timestamp=datetime.utcnow(),
        )
    )
    icon = SOURCE_ICON.get(source_type.value, "·")
    print(
        f"  {icon} {team:<8} {description:<35} → +{len(entities)} entities "
        f"({new} new in memory)"
    )
    return new


def _analyze(store) -> int:
    """Run the full pipeline against the current memory. Return # conflicts."""
    entities = store.all_entities()
    if len(entities) < 2:
        print("  (not enough entities yet)")
        return 0

    # Reuse stored embeddings.
    embeddings = [
        EntityEmbedding(entity=e, embedding=store._embeddings[e.id])  # noqa: SLF001
        for e in entities
    ]
    index = SemanticIndex(embeddings)
    matches = index.find_cross_team_matches()
    print(f"  · {len(entities)} entities · {len(matches)} cross-team pairs")

    cache_hits_before = store.pair_cache_size()
    normalized = normalize_pairs(
        matches,
        cache_get=store.pair_cache_get,
        cache_put=store.pair_cache_put,
    )
    new_calls = store.pair_cache_size() - cache_hits_before
    print(
        f"  · normalized {len(normalized)} pairs "
        f"({len(normalized) - new_calls} from cache, {new_calls} new Claude calls)"
    )

    conflicts = classify_conflicts(normalized)
    store.set_conflicts(conflicts)
    store.set_last_meeting_analysis(datetime.utcnow())

    by_sev = {"critical": 0, "warning": 0, "info": 0}
    for c in conflicts:
        by_sev[c.severity.value] = by_sev.get(c.severity.value, 0) + 1
    print(
        f"  · {len(conflicts)} conflicts · "
        f"🚨{by_sev['critical']}  ⚠️{by_sev['warning']}  ℹ️{by_sev['info']}"
    )
    return len(conflicts)


def run(skip_slack: bool = False, reset: bool = False, output_path: str | None = None) -> None:
    store = get_store()
    if reset:
        print("Resetting store…")
        store.reset()
        store = get_store()

    # ------------------------------------------------------------------
    _print_section("PHASE 1 · Baseline sync of repos / tickets / slack (no conflicts yet)")
    for team, path in [
        ("backend", DATA / "repos/backend_repo.json"),
        ("mobile", DATA / "repos/mobile_repo.json"),
    ]:
        r = sync_repo(team, str(path), repo_root=ROOT)
        print(
            f"  💻 {team:<8} {path.name:<30} → {r['mode']:<11} +{r['new_entities']} new entities"
        )

    for team, path in [
        ("backend", DATA / "tickets/backend_tickets.json"),
        ("mobile", DATA / "tickets/mobile_tickets.json"),
        ("infra", DATA / "tickets/infra_tickets.json"),
    ]:
        r = sync_ticket_file(team, str(path), repo_root=ROOT)
        print(
            f"  🎫 {team:<8} {path.name:<30} → +{r['new_entities']} new entities"
        )

    if not skip_slack:
        for team, path in [
            ("backend", DATA / "slack/backend_channel.json"),
            ("mobile", DATA / "slack/mobile_channel.json"),
        ]:
            if not path.exists():
                continue
            r = sync_slack_channel(team, str(path), repo_root=ROOT)
            print(
                f"  💬 {team:<8} {path.name:<30} → +{r['new_entities']} new entities"
            )

    store.save()
    s = store.stats()
    print(
        f"\n  Memory: {s['entities']} entities · "
        f"{s['by_source']} · pair cache: {s['pair_cache']}"
    )
    print("  No conflicts have been computed yet — only meetings trigger analysis.")

    # ------------------------------------------------------------------
    _print_section("PHASE 2 · Meetings (each one triggers analysis)")
    meetings = [
        ("backend", DATA / "meetings/backend_meeting_1.txt"),
        ("mobile", DATA / "meetings/mobile_meeting_1.txt"),
        ("infra", DATA / "meetings/infra_meeting_1.txt"),
    ]
    for team, path in meetings:
        print()
        print(f"➡️  Meeting from '{team}' ({path.name})")
        ents = process_meeting(
            transcript_text=path.read_text(), team=team, meeting_id=path.stem
        )
        _ingest(store, ents, SourceType.MEETING, team, path.name)
        print()
        print("  Re-running analysis over the full memory…")
        _analyze(store)
        store.save()

    # ------------------------------------------------------------------
    _print_section("Final conflicts")
    conflicts = store.all_conflicts()
    for i, c in enumerate(conflicts, 1):
        icon = SEVERITY_ICON.get(c.severity.value, "•")
        sa = SOURCE_ICON.get(c.entity_a.source_type.value, "·")
        sb = SOURCE_ICON.get(c.entity_b.source_type.value, "·")
        print(f"  {icon} #{i} [{c.severity.value.upper()}] {c.conflict_type.value.upper()}")
        print(f"     {sa} {c.entity_a.team}: {c.entity_a.name}")
        print(f"     {sb} {c.entity_b.team}: {c.entity_b.name}")
        print(f"     similarity={c.similarity_score:.2f}")
        print(f"     {c.explanation}")
        print(f"     → {c.recommendation}")
        print()

    # ------------------------------------------------------------------
    _print_section("Graph export")
    graph = build_graph(conflicts)
    if graph.number_of_nodes():
        out = output_path or str(ROOT / "synclayer_graph.html")
        export_to_html(graph, out)
        stats_g = graph_stats(graph)
        print(
            f"  {stats_g['nodes']} nodes · {stats_g['edges']} edges · "
            f"teams={stats_g['teams']}"
        )
        print(f"  Exported → {out}")
    else:
        print("  (No edges — skipping HTML export)")

    # ------------------------------------------------------------------
    s = store.stats()
    _print_section("Summary")
    print(f"  Entities in memory : {s['entities']}")
    print(f"  Pair cache size    : {s['pair_cache']}  ← reused on next run")
    print(f"  Conflicts          : {s['conflicts']}")
    print(f"  Last analysis      : {s['last_meeting_analysis_at']}")
    print()
    print(
        "  💡 Run again without --reset and you'll see most pairs hit the cache."
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Run the SyncLayer demo pipeline")
    p.add_argument("--skip-slack", action="store_true")
    p.add_argument("--reset", action="store_true", help="Wipe data/store/ first")
    p.add_argument("--output", default=None, help="Path for the exported graph HTML")
    args = p.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "❌ ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )
        raise SystemExit(1)

    run(skip_slack=args.skip_slack, reset=args.reset, output_path=args.output)


if __name__ == "__main__":
    main()

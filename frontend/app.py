"""SyncLayer dashboard — multi-tab product UI.

Layout
------
- Sticky header with company name, status, last-analysis stamp.
- Top tabs: Overview / Teams / Conflicts / Setup.
- All state persists in data/store/. The dashboard reads it on every rerun.
- Conflict analysis only fires when a meeting is ingested. Other source
  syncs feed the memory silently.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.detection.conflict import classify_conflicts  # noqa: E402
from backend.detection.graph import (  # noqa: E402
    build_graph,
    export_to_html,
    graph_stats,
)
from backend.extractors.meeting import process_meeting  # noqa: E402
from backend.extractors.tickets import (  # noqa: E402
    extract_entities_from_tickets,
)
from backend.sync import (  # noqa: E402
    sync_repo,
    sync_slack_channel,
    sync_ticket_file,
)
from backend.insights import (  # noqa: E402
    all_teams,
    by_decision_type,
    by_source_type,
    internal_duplications_for_team,
    team_active_work,
    team_concerns,
    team_conflicts,
    team_dependencies,
    team_entities,
    team_summary,
)
from backend.models.schemas import (  # noqa: E402
    Conflict,
    DecisionType,
    Entity,
    EntityEmbedding,
    IngestEvent,
    SourceType,
)
from backend.semantic.embeddings import SemanticIndex, embed_entities  # noqa: E402
from backend.semantic.normalizer import normalize_pairs  # noqa: E402
from backend.storage import get_store  # noqa: E402

DATA_DIR = ROOT / "data"
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="SyncLayer",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# Theme / CSS
# ---------------------------------------------------------------------------
TEAM_PALETTE = [
    "#3B82F6", "#10B981", "#F59E0B", "#8B5CF6",
    "#EC4899", "#06B6D4", "#F97316", "#84CC16",
    "#A855F7", "#14B8A6",
]


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap');

    :root {
      --bg:        #0A0E1A;
      --surface:   #0F172A;
      --surface-2: #131B2E;
      --border:    #1E293B;
      --border-2:  #2A3548;
      --text:      #F1F5F9;
      --muted:     #94A3B8;
      --dim:       #64748B;
      --primary:   #3B82F6;
      --accent:    #06B6D4;
      --success:   #10B981;
      --warning:   #F59E0B;
      --danger:    #EF4444;
    }

    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; color: var(--text); }
    .stApp { background: radial-gradient(circle at top, #0F172A 0%, #0A0E1A 60%); }
    h1, h2, h3 { font-family: 'JetBrains Mono', monospace; letter-spacing: -0.5px; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid var(--border);
        padding-bottom: 0;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        color: var(--muted) !important;
        font-weight: 500 !important;
        padding: 10px 18px !important;
        border-radius: 10px 10px 0 0 !important;
        border: 1px solid transparent !important;
    }
    .stTabs [aria-selected="true"] {
        color: var(--text) !important;
        background: var(--surface) !important;
        border-color: var(--border) !important;
        border-bottom-color: var(--surface) !important;
    }

    /* Hide default streamlit chrome */
    #MainMenu, footer { visibility: hidden; }

    /* Sticky brand header */
    .sl-brandbar {
        display:flex; align-items:center; justify-content:space-between;
        padding: 18px 4px 14px 4px;
        border-bottom: 1px solid var(--border);
        margin-bottom: 14px;
    }
    .sl-brand { display:flex; gap:14px; align-items:center; }
    .sl-logo {
        font-family:'JetBrains Mono', monospace;
        font-weight: 700; font-size: 22px; letter-spacing: -0.5px;
        background: linear-gradient(90deg, #06B6D4 0%, #3B82F6 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .sl-company {
        font-family:'Inter', sans-serif; font-weight:600;
        color: var(--text); font-size: 15px;
    }
    .sl-meta {
        display:flex; gap: 14px; align-items:center; color: var(--muted);
        font-family:'JetBrains Mono', monospace; font-size: 12px;
    }
    .sl-status-pill {
        display:inline-flex; align-items:center; gap:6px;
        padding:5px 12px; border-radius:999px;
        background:#0B1F1A; color:#34D399;
        font-family:'JetBrains Mono', monospace; font-size:11px; font-weight:600;
        border: 1px solid #064E3B;
    }
    .sl-status-pill.idle { background:#1A1F2E; color:#94A3B8; border-color: var(--border); }
    .sl-status-pill .dot { width:7px; height:7px; border-radius:999px; background: currentColor; }

    /* Hero metric cards */
    .hero-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 8px 0 22px 0; }
    .hero-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 18px 20px;
        position: relative; overflow: hidden;
    }
    .hero-card::before {
        content:""; position:absolute; top:0; left:0; right:0; height:2px;
        background: linear-gradient(90deg, transparent, var(--accent), transparent);
        opacity: 0.5;
    }
    .hero-label { color: var(--muted); font-size:11px; text-transform: uppercase; letter-spacing: 1.4px; font-weight: 600; }
    .hero-value { color: var(--text); font-family:'JetBrains Mono', monospace; font-weight:700; font-size:36px; line-height:1.1; margin-top:8px; }
    .hero-sub  { color: var(--dim); font-size: 12px; margin-top: 6px; font-family:'JetBrains Mono', monospace; }
    .hero-card.danger .hero-value  { color: var(--danger); }
    .hero-card.warning .hero-value { color: var(--warning); }
    .hero-card.success .hero-value { color: var(--success); }

    /* Section headers */
    .section-title {
        display:flex; align-items:center; justify-content:space-between;
        margin: 22px 0 12px 0;
    }
    .section-title h3 { margin:0; font-size:16px; color: var(--text); }
    .section-title .hint { color: var(--dim); font-size: 12px; font-family:'JetBrains Mono', monospace; }

    /* Generic card */
    .card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px 18px;
        margin-bottom: 12px;
    }
    .card.compact { padding: 12px 14px; }

    /* Conflict cards */
    .conflict-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-left-width: 4px;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
    .conflict-card.critical { border-left-color: var(--danger); }
    .conflict-card.warning  { border-left-color: var(--warning); }
    .conflict-card.info     { border-left-color: var(--primary); }
    .pill {
        display:inline-block; font-family:'JetBrains Mono', monospace;
        font-size:10.5px; padding:3px 10px; border-radius:999px;
        background: var(--surface-2); color: var(--text);
        border: 1px solid var(--border-2); margin-right:6px;
        font-weight: 600; letter-spacing: 0.5px;
    }
    .pill.danger  { background:#3B0D14; color:#FCA5A5; border-color:#7F1D1D; }
    .pill.warning { background:#3B2410; color:#FCD34D; border-color:#7C2D12; }
    .pill.info    { background:#0E2A4D; color:#93C5FD; border-color:#1E3A8A; }
    .pill.team    { background:#0E1F3D; color:#BFDBFE; border-color:#1E3A8A; }
    .entity-block {
        background: var(--surface-2); border-radius:10px; padding: 12px 14px;
        font-size: 13px; line-height: 1.45;
    }
    .entity-block .label { color: var(--muted); font-family:'JetBrains Mono', monospace; font-size:10.5px; text-transform:uppercase; letter-spacing:1px; }
    .entity-block .name  { color: var(--text); font-weight: 600; margin: 4px 0; }
    .entity-block .desc  { color: var(--muted); font-size:12.5px; }
    .recommendation {
        margin-top: 12px; padding: 11px 14px; border-radius: 10px;
        background: rgba(6, 182, 212, 0.08); color: #67E8F9;
        font-size: 13px; border: 1px solid rgba(6, 182, 212, 0.18);
    }

    /* Team cards */
    .team-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 16px 18px;
        cursor: pointer;
        transition: all .15s ease;
    }
    .team-card:hover { border-color: var(--accent); }
    .team-card .head { display:flex; align-items:center; gap:10px; }
    .team-card .swatch { width:10px; height:10px; border-radius:3px; }
    .team-card .name { font-family:'JetBrains Mono', monospace; font-weight:700; font-size:15px; }
    .team-card .stats { display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; margin-top: 12px; }
    .team-card .stat .v { font-family:'JetBrains Mono', monospace; font-size:18px; color: var(--text); }
    .team-card .stat .l { color: var(--muted); font-size:10.5px; text-transform:uppercase; letter-spacing:1px; }

    /* Activity items */
    .activity-row {
        display:flex; justify-content:space-between; align-items:center;
        padding: 10px 14px; border-bottom: 1px solid var(--border);
    }
    .activity-row:last-child { border-bottom: none; }
    .activity-left { display:flex; gap:10px; align-items:center; font-size: 13.5px; }
    .activity-icon { font-size: 18px; }
    .activity-meta { color: var(--dim); font-size: 11.5px; font-family:'JetBrains Mono', monospace; }

    /* Setup rows */
    .source-row {
        display:flex; justify-content:space-between; align-items:center;
        background: var(--surface-2); border-radius:10px;
        padding: 8px 12px; margin-bottom: 6px;
        font-family: 'JetBrains Mono', monospace; font-size: 12.5px;
    }

    /* Banner */
    .pending-banner {
        background: linear-gradient(90deg, #3B2410, #1E1A0E);
        color: #FCD34D;
        border: 1px solid #7C2D12;
        border-radius: 10px;
        padding: 12px 16px;
        font-size: 13.5px;
        margin-bottom: 18px;
    }
    .empty-state {
        text-align:center; padding: 60px 20px; color: var(--muted);
        background: var(--surface); border: 1px dashed var(--border-2); border-radius: 14px;
    }
    .empty-state h4 { color: var(--text); margin-bottom: 6px; font-size: 15px; }
    .empty-state p  { color: var(--muted); font-size: 13px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults = {
        "use_backend": False,
        "graph_html": None,
        "selected_team": None,
        "active_tab": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def _team_color(team: str, idx: int = 0) -> str:
    cfg = get_store().company_config()
    saved = cfg.get("teams", {}).get(team, {}).get("color", "")
    if saved:
        return saved
    return TEAM_PALETTE[idx % len(TEAM_PALETTE)]


def _record_event(source: SourceType, team: str, description: str, count: int) -> None:
    get_store().record_event(
        IngestEvent(
            id=f"ev-{uuid.uuid4().hex[:8]}",
            source_type=source,
            team=team,
            description=description,
            entities_extracted=count,
            timestamp=datetime.utcnow(),
        )
    )


def _add_entities(ents: list[Entity], source: SourceType, team: str, description: str) -> int:
    if not ents:
        _record_event(source, team, description, 0)
        return 0
    embeds = embed_entities(ents)
    store = get_store()
    new = store.add_entities([e.entity for e in embeds], [e.embedding for e in embeds])
    _record_event(source, team, description, len(ents))
    store.save()
    return new


def _run_analysis() -> dict:
    store = get_store()
    entities = store.all_entities()
    if len(entities) < 2:
        return {"conflicts": 0, "matches": 0}
    embeds = [
        EntityEmbedding(entity=e, embedding=store._embeddings[e.id])  # noqa: SLF001
        for e in entities
    ]
    index = SemanticIndex(embeds)
    matches = index.find_cross_team_matches()
    normalized = normalize_pairs(
        matches,
        cache_get=store.pair_cache_get,
        cache_put=store.pair_cache_put,
    )
    conflicts = classify_conflicts(normalized)
    store.set_conflicts(conflicts)
    store.set_last_meeting_analysis(datetime.utcnow())

    graph = build_graph(conflicts)
    if graph.number_of_nodes():
        html_path = export_to_html(graph)
        with open(html_path) as f:
            st.session_state["graph_html"] = f.read()
    else:
        st.session_state["graph_html"] = None
    store.save()
    return {"conflicts": len(conflicts), "matches": len(matches)}


def _internal_duplications() -> list[tuple[Entity, Entity, float]]:
    """Recompute same-team near-duplicates from the in-memory embedding store."""
    store = get_store()
    entities = store.all_entities()
    if len(entities) < 2:
        return []
    embeds = [
        EntityEmbedding(entity=e, embedding=store._embeddings[e.id])  # noqa: SLF001
        for e in entities
    ]
    return SemanticIndex(embeds).find_internal_duplications()


def _normalize_repo_url(value: str) -> str:
    """Accept either 'owner/repo' or full GitHub URLs."""
    value = value.strip()
    m = re.match(r"https?://(?:www\.)?github\.com/([^/]+/[^/]+)/?", value)
    if m:
        value = m.group(1)
    if value.endswith(".git"):
        value = value[:-4]
    return value.strip("/")


# ---------------------------------------------------------------------------
# Sticky header
# ---------------------------------------------------------------------------
store = get_store()
config = store.company_config()
company_name = config.get("name", "My Company")
stats = store.stats()
last_analysis = stats.get("last_meeting_analysis_at") or "never"
if last_analysis != "never":
    last_analysis = last_analysis[:19].replace("T", " ") + " UTC"
status_pill = (
    "<span class='sl-status-pill'><span class='dot'></span>memory live</span>"
    if stats["entities"]
    else "<span class='sl-status-pill idle'><span class='dot'></span>memory empty</span>"
)
st.markdown(
    f"""
    <div class="sl-brandbar">
        <div class="sl-brand">
            <div class="sl-logo">🛰️ SyncLayer</div>
            <div class="sl-company">{company_name}</div>
        </div>
        <div class="sl-meta">
            <span>Last analysis · {last_analysis}</span>
            <span>·</span>
            <span>{stats['entities']} entities · {stats['conflicts']} conflicts</span>
            {status_pill}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_overview, tab_teams, tab_conflicts, tab_setup = st.tabs(
    ["📊 Overview", "👥 Teams", "🚨 Conflicts", "⚙️ Setup"]
)


# ---------------------------------------------------------------------------
# OVERVIEW TAB
# ---------------------------------------------------------------------------
def render_overview() -> None:
    s = store.stats()
    conflicts = store.all_conflicts()
    entities = store.all_entities()
    events = store.recent_events(20)

    critical = sum(1 for c in conflicts if c.severity.value == "critical")
    pending = s.get("pending_non_meeting_entities", 0)

    if pending > 0 and s.get("last_meeting_analysis_at"):
        st.markdown(
            f"<div class='pending-banner'>📬 <b>{pending}</b> new entities have arrived "
            f"from repos / Slack / tickets since the last meeting analysis. They'll be "
            f"considered automatically next time a meeting is ingested.</div>",
            unsafe_allow_html=True,
        )

    metrics = [
        ("Memory", str(s["entities"]), f"{s['by_source']}", ""),
        (
            "Active conflicts",
            str(s["conflicts"]),
            f"{critical} critical · {len(conflicts) - critical} non-critical",
            "danger" if critical else "",
        ),
        (
            "Teams tracked",
            str(len(s["by_team"])),
            ", ".join(sorted(s["by_team"].keys())) or "configure in Setup",
            "",
        ),
        (
            "Cache hits",
            str(s["pair_cache"]),
            "saved Claude calls",
            "success",
        ),
    ]
    cards = "".join(
        f"""<div class='hero-card {cls}'>
            <div class='hero-label'>{label}</div>
            <div class='hero-value'>{value}</div>
            <div class='hero-sub'>{sub}</div>
        </div>"""
        for label, value, sub, cls in metrics
    )
    st.markdown(f"<div class='hero-grid'>{cards}</div>", unsafe_allow_html=True)

    if not entities:
        st.markdown(
            """
            <div class='empty-state'>
                <h4>Welcome to SyncLayer</h4>
                <p>Head to the <b>Setup</b> tab to add your teams and connect their sources, <br>
                or load the demo company to see the dashboard in action.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    col_left, col_right = st.columns([3, 2])

    # ---- Top conflicts -----------------------------------------------
    with col_left:
        st.markdown(
            "<div class='section-title'><h3>Top open conflicts</h3>"
            "<span class='hint'>sorted by severity</span></div>",
            unsafe_allow_html=True,
        )
        if not conflicts:
            st.markdown(
                "<div class='card compact' style='color:var(--muted)'>"
                "No conflicts surfaced yet — ingest a meeting to trigger analysis.</div>",
                unsafe_allow_html=True,
            )
        else:
            for c in conflicts[:4]:
                _render_conflict(c, compact=True)
        if len(conflicts) > 4:
            st.caption(f"+ {len(conflicts) - 4} more in the Conflicts tab")

    # ---- Activity ----------------------------------------------------
    with col_right:
        st.markdown(
            "<div class='section-title'><h3>Recent activity</h3>"
            "<span class='hint'>last 8 events</span></div>",
            unsafe_allow_html=True,
        )
        icons = {"meeting": "🎙️", "github": "💻", "slack": "💬", "ticket": "🎫"}
        rows = []
        for ev in events[:8]:
            ts = (ev.timestamp.isoformat() or "")[:19].replace("T", " ")
            rows.append(
                f"""<div class='activity-row'>
                    <div class='activity-left'>
                        <span class='activity-icon'>{icons.get(ev.source_type.value,'•')}</span>
                        <span><b>{ev.team}</b> · {ev.description}</span>
                    </div>
                    <div class='activity-meta'>+{ev.entities_extracted} · {ts}</div>
                </div>"""
            )
        st.markdown(
            "<div class='card' style='padding:6px 4px'>" + ("".join(rows) or "<div style='padding:14px;color:var(--muted)'>No activity yet.</div>") + "</div>",
            unsafe_allow_html=True,
        )

    # ---- Charts ------------------------------------------------------
    st.markdown(
        "<div class='section-title'><h3>Distribution</h3></div>",
        unsafe_allow_html=True,
    )
    chart_a, chart_b = st.columns(2)

    with chart_a:
        df_team = pd.DataFrame(
            [{"team": t, "count": n} for t, n in s["by_team"].items()]
        )
        if not df_team.empty:
            df_team = df_team.sort_values("count", ascending=True)
            fig = px.bar(
                df_team, x="count", y="team", orientation="h",
                title="Entities per team",
            )
            fig.update_traces(marker_color="#3B82F6")
            fig.update_layout(
                template="plotly_dark", height=300,
                margin=dict(l=10, r=10, t=40, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title=None, yaxis_title=None, showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

    with chart_b:
        df_src = pd.DataFrame(
            [{"source": k, "count": v} for k, v in s["by_source"].items()]
        )
        if not df_src.empty:
            fig = px.pie(
                df_src, names="source", values="count", hole=0.6,
                title="Entities by source",
                color_discrete_sequence=["#3B82F6", "#10B981", "#F59E0B", "#8B5CF6"],
            )
            fig.update_layout(
                template="plotly_dark", height=300,
                margin=dict(l=10, r=10, t=40, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# TEAMS TAB
# ---------------------------------------------------------------------------
def render_teams() -> None:
    s = store.stats()
    entities = store.all_entities()
    conflicts = store.all_conflicts()
    cfg = store.company_config()
    registered_teams = list(cfg.get("teams", {}).keys())
    teams = all_teams(entities, registered_teams)

    if not teams:
        st.markdown(
            """
            <div class='empty-state'>
                <h4>No teams yet</h4>
                <p>Add teams in <b>Setup</b> and connect their repos / Slack channels / ticket files.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Pick a team
    selected = st.session_state.get("selected_team") or teams[0]
    if selected not in teams:
        selected = teams[0]
    cols = st.columns(min(len(teams), 6))
    for i, t in enumerate(teams):
        with cols[i % len(cols)]:
            color = _team_color(t, i)
            tsum = team_summary(t, entities, conflicts)
            label = (
                f"⬤  {t.upper()}\n"
                f"{tsum['entities']} ent · {tsum['conflicts']} conf"
            )
            if st.button(
                label,
                key=f"team_pick_{t}",
                use_container_width=True,
            ):
                st.session_state["selected_team"] = t
                selected = t

    st.markdown("---")

    color = _team_color(selected, teams.index(selected) if selected in teams else 0)
    t_cfg = cfg.get("teams", {}).get(selected, {})
    tsum = team_summary(selected, entities, conflicts)
    t_ents = team_entities(entities, selected)

    st.markdown(
        f"""
        <div style='display:flex; align-items:center; gap:12px; margin-bottom:14px;'>
            <div style='width:14px; height:14px; border-radius:4px; background:{color};'></div>
            <h2 style='margin:0;'>{selected.upper()}</h2>
            <span class='pill team'>{tsum['entities']} entities</span>
            <span class='pill'>{tsum['conflicts']} conflicts</span>
            <span class='pill warning' style='display:{"inline-block" if tsum['critical_conflicts'] else "none"}'>
                {tsum['critical_conflicts']} critical
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not t_ents:
        st.info(
            f"No data ingested yet for **{selected}**. Connect sources in the **Setup** tab."
        )

    cwork, cconcerns, csources = st.columns([1.2, 1, 1])

    # ---- Active work -------------------------------------------------
    with cwork:
        st.markdown(
            "<div class='section-title'><h3>🟢 Active work</h3>"
            "<span class='hint'>decisions, plans, commitments</span></div>",
            unsafe_allow_html=True,
        )
        for e in team_active_work(t_ents, limit=8):
            icon = {"meeting": "🎙️", "github": "💻", "slack": "💬", "ticket": "🎫"}.get(
                e.source_type.value, "•"
            )
            st.markdown(
                f"""
                <div class='card compact'>
                    <div style='display:flex; gap:8px; align-items:center; margin-bottom:4px;'>
                        <span>{icon}</span>
                        <span class='pill'>{e.decision_type.value}</span>
                        <span style='color:var(--dim); font-size:11px;'>conf {e.confidence:.2f}</span>
                    </div>
                    <div style='font-weight:600;'>{e.name}</div>
                    <div style='color:var(--muted); font-size:12.5px; margin-top:4px;'>
                        {e.description[:240]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if not team_active_work(t_ents):
            st.markdown("<div class='card compact' style='color:var(--muted)'>No active work yet.</div>", unsafe_allow_html=True)

    # ---- Concerns + dependencies -------------------------------------
    with cconcerns:
        st.markdown(
            "<div class='section-title'><h3>⚠️ Concerns & dependencies</h3></div>",
            unsafe_allow_html=True,
        )
        items = team_concerns(t_ents) + team_dependencies(t_ents)
        for e in items[:8]:
            color_pill = "warning" if e.decision_type == DecisionType.CONCERN else "info"
            st.markdown(
                f"""
                <div class='card compact'>
                    <span class='pill {color_pill}'>{e.decision_type.value}</span>
                    <div style='font-weight:600; margin-top:6px;'>{e.name}</div>
                    <div style='color:var(--muted); font-size:12.5px; margin-top:4px;'>
                        {e.description[:240]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if not items:
            st.markdown("<div class='card compact' style='color:var(--muted)'>None on record.</div>", unsafe_allow_html=True)

    # ---- Sources & sync ----------------------------------------------
    with csources:
        st.markdown(
            "<div class='section-title'><h3>🔌 Connected sources</h3></div>",
            unsafe_allow_html=True,
        )
        repos = t_cfg.get("repos", []) or []
        slack = t_cfg.get("slack_channels", []) or []
        tickets = t_cfg.get("ticket_paths", []) or []

        def _src_status(kind: str, item: str) -> str:
            state = store.source_state(kind, selected, item)
            if not state.get("initialized"):
                return "<span style='color:var(--dim); font-size:11px;'>not synced yet</span>"
            ts = (state.get("last_synced_at") or "")[:19].replace("T", " ")
            extras: list[str] = []
            if state.get("seen_pr_numbers"):
                extras.append(f"{len(state['seen_pr_numbers'])} PRs")
            if state.get("seen_commit_shas"):
                extras.append(f"{len(state['seen_commit_shas'])} commits")
            if state.get("entity_count"):
                extras.append(f"{state['entity_count']} entities")
            extras_html = " · ".join(extras)
            return (
                f"<span style='color:var(--success); font-size:11px;'>● synced</span>"
                f"<span style='color:var(--dim); font-size:11px; margin-left:8px;'>"
                f"{ts}{(' · ' + extras_html) if extras_html else ''}</span>"
            )

        def _src_card(label: str, kind: str, items_: list[str], icon: str, note: str = "") -> None:
            if items_:
                rows = "".join(
                    f"""<div class='source-row'>
                        <div>{icon} {item}</div>
                        <div>{_src_status(kind, item)}</div>
                    </div>"""
                    for item in items_
                )
            else:
                rows = (
                    f"<div style='color:var(--dim); font-size:12px; padding:6px 0;'>"
                    f"None{(' · ' + note) if note else ''}</div>"
                )
            st.markdown(
                f"""
                <div class='card compact'>
                    <div style='color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;'>
                        {label}
                    </div>
                    {rows}
                </div>
                """,
                unsafe_allow_html=True,
            )

        _src_card("GitHub repos", "repo", repos, "💻", "configure in Setup")
        _src_card("Slack channels", "slack", slack, "💬")
        _src_card("Ticket files", "ticket", tickets, "🎫")

        if st.button("🔄 Sync this team's sources", key=f"sync_team_{selected}", use_container_width=True):
            _sync_team_sources(selected, t_cfg)
            st.rerun()

    # ---- Cross-team conflicts involving this team --------------------
    st.markdown(
        f"<div class='section-title'><h3>🚨 Cross-team conflicts involving {selected}</h3></div>",
        unsafe_allow_html=True,
    )
    confs = team_conflicts(conflicts, selected)
    if not confs:
        st.markdown(
            "<div class='card compact' style='color:var(--muted)'>"
            "No cross-team conflicts on record. They'll surface on the next meeting analysis.</div>",
            unsafe_allow_html=True,
        )
    else:
        for c in confs:
            _render_conflict(c, compact=False)

    # ---- Internal duplications --------------------------------------
    st.markdown(
        "<div class='section-title'><h3>♻️ Internal duplication warnings</h3>"
        "<span class='hint'>same team, same idea, twice</span></div>",
        unsafe_allow_html=True,
    )
    pairs = internal_duplications_for_team(_internal_duplications(), selected)
    if not pairs:
        st.markdown(
            "<div class='card compact' style='color:var(--muted)'>"
            "No internal redundancy detected. Nice — the team is staying lean.</div>",
            unsafe_allow_html=True,
        )
    else:
        for a, b, score in pairs[:6]:
            st.markdown(
                f"""
                <div class='card compact'>
                    <div style='display:flex; gap:8px; align-items:center;'>
                        <span class='pill warning'>EFFICIENCY</span>
                        <span style='color:var(--dim); font-size:11.5px;'>similarity {score:.2f}</span>
                    </div>
                    <div style='display:grid; grid-template-columns:1fr auto 1fr; gap:14px; align-items:center; margin-top:10px;'>
                        <div class='entity-block'>
                            <div class='label'>{a.source_type.value}</div>
                            <div class='name'>{a.name}</div>
                            <div class='desc'>{a.description[:160]}</div>
                        </div>
                        <div style='color:var(--dim);'>≈</div>
                        <div class='entity-block'>
                            <div class='label'>{b.source_type.value}</div>
                            <div class='name'>{b.name}</div>
                            <div class='desc'>{b.description[:160]}</div>
                        </div>
                    </div>
                    <div class='recommendation'>
                        Two work items from <b>{selected}</b> are essentially the same.
                        Merge them or assign a single owner to avoid double-effort.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# CONFLICTS TAB
# ---------------------------------------------------------------------------
def render_conflicts() -> None:
    conflicts = store.all_conflicts()

    if not conflicts:
        st.markdown(
            """
            <div class='empty-state'>
                <h4>No conflicts yet</h4>
                <p>Connect sources and ingest a meeting — the next analysis will populate this view.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Filters
    f1, f2, f3 = st.columns([1, 1, 2])
    with f1:
        sev_filter = st.multiselect(
            "Severity",
            options=["critical", "warning", "info"],
            default=["critical", "warning", "info"],
            key="filter_sev",
        )
    with f2:
        type_filter = st.multiselect(
            "Type",
            options=sorted({c.conflict_type.value for c in conflicts}),
            default=sorted({c.conflict_type.value for c in conflicts}),
            key="filter_type",
        )
    with f3:
        teams = sorted(
            {c.entity_a.team for c in conflicts}
            | {c.entity_b.team for c in conflicts}
        )
        team_filter = st.multiselect(
            "Teams involved", options=teams, default=teams, key="filter_team"
        )

    filtered = [
        c
        for c in conflicts
        if c.severity.value in sev_filter
        and c.conflict_type.value in type_filter
        and (c.entity_a.team in team_filter or c.entity_b.team in team_filter)
    ]

    counts = {
        "critical": sum(1 for c in filtered if c.severity.value == "critical"),
        "warning": sum(1 for c in filtered if c.severity.value == "warning"),
        "info": sum(1 for c in filtered if c.severity.value == "info"),
    }
    st.markdown(
        f"""
        <div style='display:flex; gap:8px; margin: 8px 0 16px 0;'>
            <span class='pill danger'>🚨 {counts['critical']} critical</span>
            <span class='pill warning'>⚠️ {counts['warning']} warning</span>
            <span class='pill info'>ℹ️ {counts['info']} info</span>
            <span style='color:var(--dim); font-size: 12.5px; align-self:center; margin-left:auto;'>
                showing {len(filtered)} / {len(conflicts)}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 2])
    with left:
        for c in filtered:
            _render_conflict(c, compact=False)

    with right:
        if st.session_state.get("graph_html"):
            st.markdown(
                "<div class='section-title'><h3>Conflict graph</h3></div>",
                unsafe_allow_html=True,
            )
            import streamlit.components.v1 as components

            components.html(st.session_state["graph_html"], height=560, scrolling=False)

        # Charts
        df = pd.DataFrame([c.model_dump(mode="json") for c in filtered])
        if not df.empty:
            st.markdown(
                "<div class='section-title'><h3>By team pair</h3></div>",
                unsafe_allow_html=True,
            )
            df["pair"] = df.apply(
                lambda r: " ↔ ".join(sorted([r["entity_a"]["team"], r["entity_b"]["team"]])),
                axis=1,
            )
            fig = px.histogram(df, x="pair", color="conflict_type", barmode="stack")
            fig.update_layout(
                template="plotly_dark", height=300,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title=None, yaxis_title=None,
            )
            st.plotly_chart(fig, use_container_width=True)


def _render_conflict(c: Conflict, *, compact: bool) -> None:
    sev = c.severity.value
    type_label = c.conflict_type.value.replace("_", " ").upper()
    desc_chars = 140 if compact else 260
    st.markdown(
        f"""
        <div class='conflict-card {sev}'>
            <div>
                <span class='pill {("danger" if sev=="critical" else "warning" if sev=="warning" else "info")}'>{type_label}</span>
                <span class='pill'>similarity {c.similarity_score:.2f}</span>
                <span class='pill team'>{c.entity_a.team} ↔ {c.entity_b.team}</span>
            </div>
            <div style='display:grid; grid-template-columns:1fr auto 1fr; gap:14px; align-items:center; margin-top:12px;'>
                <div class='entity-block'>
                    <div class='label'>{c.entity_a.team} · {c.entity_a.source_type.value}</div>
                    <div class='name'>{c.entity_a.name}</div>
                    <div class='desc'>{c.entity_a.description[:desc_chars]}</div>
                </div>
                <div style='color:var(--dim); font-family:JetBrains Mono;'>vs</div>
                <div class='entity-block'>
                    <div class='label'>{c.entity_b.team} · {c.entity_b.source_type.value}</div>
                    <div class='name'>{c.entity_b.name}</div>
                    <div class='desc'>{c.entity_b.description[:desc_chars]}</div>
                </div>
            </div>
            <p style='margin: 12px 0 0 0; color: var(--muted); font-size: 13px;'>{c.explanation}</p>
            <div class='recommendation'>{c.recommendation}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# SETUP TAB
# ---------------------------------------------------------------------------
def render_setup() -> None:
    cfg = store.company_config()
    teams_cfg = cfg.get("teams", {})

    # ---- Company name -----------------------------------------------
    st.markdown(
        "<div class='section-title'><h3>🏢 Company</h3></div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        new_name = st.text_input(
            "Company name", value=cfg.get("name", "My Company"), key="cfg_company"
        )
        if new_name != cfg.get("name"):
            cfg["name"] = new_name
            store.set_company_config(cfg)
            store.save()
    with c2:
        if st.button("📦 Load Novatech demo", use_container_width=True):
            _load_novatech_demo_config()
            st.success("Demo company loaded.")
            st.rerun()
    with c3:
        if st.button("♻️ Reset everything", use_container_width=True):
            store.reset()
            st.session_state["graph_html"] = None
            st.success("Memory and config wiped.")
            st.rerun()

    # ---- Teams editor -----------------------------------------------
    st.markdown(
        "<div class='section-title'><h3>👥 Teams</h3>"
        "<span class='hint'>add a team, connect its sources, sync</span></div>",
        unsafe_allow_html=True,
    )
    add_col1, add_col2, add_col3 = st.columns([2, 1, 1])
    with add_col1:
        new_team = st.text_input(
            "Add a new team", placeholder="e.g. backend, mobile, growth, data",
            key="new_team_input",
        )
    with add_col2:
        new_team_color = st.color_picker(
            "Color", value=TEAM_PALETTE[len(teams_cfg) % len(TEAM_PALETTE)],
            key="new_team_color",
        )
    with add_col3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("➕ Add team", use_container_width=True):
            if new_team and new_team not in teams_cfg:
                store.upsert_team(new_team, color=new_team_color)
                store.save()
                st.rerun()

    if not teams_cfg:
        st.markdown(
            "<div class='card compact' style='color:var(--muted)'>"
            "No teams configured. Add one above, or load the Novatech demo.</div>",
            unsafe_allow_html=True,
        )
        return

    for team_name, t_cfg in list(teams_cfg.items()):
        color = t_cfg.get("color") or _team_color(team_name)
        with st.expander(f"⬤  {team_name}", expanded=False):
            top1, top2, top3 = st.columns([1, 1, 1])
            with top1:
                col = st.color_picker(
                    "Color", value=color, key=f"col_{team_name}"
                )
                if col != color:
                    store.upsert_team(team_name, color=col)
                    store.save()
            with top2:
                st.metric("Entities", sum(1 for e in store.all_entities() if e.team == team_name))
            with top3:
                if st.button("🗑️ Remove team", key=f"rm_{team_name}", use_container_width=True):
                    store.remove_team(team_name)
                    store.save()
                    st.rerun()

            st.markdown("**💻 GitHub repos**")
            _edit_string_list(team_name, "repos", t_cfg.get("repos", []),
                              placeholder="owner/repo  or  https://github.com/owner/repo")

            st.markdown("**💬 Slack channels**")
            _edit_string_list(team_name, "slack_channels", t_cfg.get("slack_channels", []),
                              placeholder="C0123456 (channel ID)")

            st.markdown("**🎫 Ticket JSON files**")
            _edit_string_list(team_name, "ticket_paths", t_cfg.get("ticket_paths", []),
                              placeholder="data/tickets/team_tickets.json")

            st.markdown("**📥 Manual ingest** — meeting transcript or audio")
            mt_col1, mt_col2 = st.columns([3, 1])
            with mt_col1:
                meeting_text = st.text_area(
                    "Transcript",
                    height=120,
                    placeholder="Speaker A: …\nSpeaker B: …",
                    key=f"meeting_text_{team_name}",
                )
            with mt_col2:
                meeting_audio = st.file_uploader(
                    "or audio", type=["mp3", "wav", "m4a"], key=f"audio_{team_name}",
                )
                if st.button("🎙️ Ingest meeting (triggers analysis)",
                             key=f"meet_btn_{team_name}", use_container_width=True):
                    _ingest_meeting_for_team(team_name, meeting_text, meeting_audio)
                    st.rerun()

            sync_col1, sync_col2 = st.columns([1, 1])
            with sync_col1:
                if st.button(f"🔄 Sync all sources for {team_name}",
                             key=f"sync_all_{team_name}", use_container_width=True):
                    _sync_team_sources(team_name, t_cfg)
                    st.rerun()
            with sync_col2:
                if st.button("🧠 Re-analyze (manual)",
                             key=f"reanalyze_{team_name}", use_container_width=True):
                    with st.spinner("Re-analyzing memory…"):
                        _run_analysis()
                    st.rerun()

    st.markdown("---")
    st.markdown(
        "<div class='section-title'><h3>🚀 Bulk actions</h3></div>",
        unsafe_allow_html=True,
    )
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("🔄 Sync EVERY source", use_container_width=True):
            for team_name, t_cfg in teams_cfg.items():
                _sync_team_sources(team_name, t_cfg)
            st.success("All configured sources synced.")
            st.rerun()
    with b2:
        if st.button("🎙️ Play 3 demo meetings", use_container_width=True):
            _play_demo_meetings()
            st.rerun()
    with b3:
        if st.button("🧠 Run analysis on memory", use_container_width=True):
            with st.spinner("Re-analyzing memory…"):
                _run_analysis()
            st.success("Analysis complete.")
            st.rerun()


def _edit_string_list(team_name: str, field: str, items: list[str], placeholder: str) -> None:
    cfg = store.company_config()
    new_items = list(items)
    rerun = False
    for i, item in enumerate(items):
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(
                f"<div class='source-row'>{item}</div>",
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("✕", key=f"del_{team_name}_{field}_{i}"):
                new_items = [x for x in items if x != item]
                rerun = True
    add_c1, add_c2 = st.columns([5, 1])
    with add_c1:
        v = st.text_input(
            "add", value="", placeholder=placeholder,
            key=f"add_{team_name}_{field}", label_visibility="collapsed",
        )
    with add_c2:
        if st.button("➕", key=f"addbtn_{team_name}_{field}"):
            if v.strip():
                if field == "repos":
                    new_items = list(set(new_items + [_normalize_repo_url(v)]))
                else:
                    new_items = list(set(new_items + [v.strip()]))
                rerun = True
    if rerun:
        store.upsert_team(team_name, **{field: new_items})
        store.save()
        st.rerun()


def _sync_team_sources(team: str, t_cfg: dict) -> None:
    repos = t_cfg.get("repos", []) or []
    slack = t_cfg.get("slack_channels", []) or []
    tickets = t_cfg.get("ticket_paths", []) or []

    total = len(repos) + len(slack) + len(tickets)
    if not total:
        st.warning(f"No sources configured for {team}. Add some first.")
        return

    progress = st.progress(0.0, text=f"Syncing {team}…")
    done = 0
    summary: list[str] = []

    for repo in repos:
        progress.progress(done / total, text=f"Repo · {repo}")
        try:
            r = sync_repo(team, repo, repo_root=ROOT)
            summary.append(
                f"💻 {repo} → {r['mode']} · +{r['new_entities']} new"
                + (f" (PRs {r['new_pr_numbers']})" if r["new_pr_numbers"] else "")
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Repo {repo} failed: {exc}")
        done += 1

    for ch in slack:
        progress.progress(done / total, text=f"Slack · {ch}")
        try:
            r = sync_slack_channel(team, ch, repo_root=ROOT)
            summary.append(f"💬 {ch} → +{r['new_entities']} new")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Slack {ch} failed: {exc}")
        done += 1

    for path in tickets:
        progress.progress(done / total, text=f"Tickets · {path}")
        try:
            r = sync_ticket_file(team, path, repo_root=ROOT)
            summary.append(f"🎫 {Path(path).name} → +{r['new_entities']} new")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Tickets {path} failed: {exc}")
        done += 1

    progress.empty()
    if summary:
        st.success("Synced **{}**\n\n".format(team) + "\n".join("- " + s for s in summary))
    else:
        st.info(f"No new items found for {team}.")


def _ingest_meeting_for_team(team: str, transcript: str, audio_file) -> None:
    if not transcript and not audio_file:
        st.warning("Provide a transcript or audio.")
        return
    with st.spinner(f"Extracting meeting for {team}…"):
        if audio_file is not None:
            tmp = ROOT / f".tmp_audio_{audio_file.name}"
            tmp.write_bytes(audio_file.getvalue())
            try:
                ents = process_meeting(
                    audio_path=str(tmp),
                    team=team,
                    meeting_id=audio_file.name.rsplit(".", 1)[0],
                )
            finally:
                tmp.unlink(missing_ok=True)
        else:
            ents = process_meeting(
                transcript_text=transcript,
                team=team,
                meeting_id=f"adhoc-{uuid.uuid4().hex[:6]}",
            )
        _add_entities(ents, SourceType.MEETING, team, "Adhoc meeting")
    with st.spinner("Re-analyzing memory (cache reused)…"):
        _run_analysis()
    st.success(f"Meeting ingested · {len(ents)} entities · analysis refreshed.")


def _play_demo_meetings() -> None:
    plan = [
        ("backend", DATA_DIR / "meetings/backend_meeting_1.txt"),
        ("mobile", DATA_DIR / "meetings/mobile_meeting_1.txt"),
        ("infra", DATA_DIR / "meetings/infra_meeting_1.txt"),
    ]
    progress = st.progress(0.0, text="Playing meetings…")
    for i, (team, path) in enumerate(plan, 1):
        if not path.exists():
            continue
        progress.progress(i / len(plan), text=f"meeting · {team}")
        ents = process_meeting(
            transcript_text=path.read_text(), team=team, meeting_id=path.stem
        )
        _add_entities(ents, SourceType.MEETING, team, path.name)
        _run_analysis()
    progress.empty()
    st.success("Demo meetings played.")


def _load_novatech_demo_config() -> None:
    """Pre-fill the company config with the bundled Novatech sample data."""
    cfg = {
        "name": "Novatech",
        "teams": {
            "backend": {
                "color": "#3B82F6",
                "repos": ["data/repos/backend_repo.json"],
                "slack_channels": ["data/slack/backend_channel.json"],
                "ticket_paths": ["data/tickets/backend_tickets.json"],
            },
            "mobile": {
                "color": "#10B981",
                "repos": ["data/repos/mobile_repo.json"],
                "slack_channels": ["data/slack/mobile_channel.json"],
                "ticket_paths": ["data/tickets/mobile_tickets.json"],
            },
            "infra": {
                "color": "#F59E0B",
                "repos": [],
                "slack_channels": [],
                "ticket_paths": ["data/tickets/infra_tickets.json"],
            },
        },
    }
    store.set_company_config(cfg)
    store.save()


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
with tab_overview:
    render_overview()

with tab_teams:
    render_teams()

with tab_conflicts:
    render_conflicts()

with tab_setup:
    render_setup()


# ---------------------------------------------------------------------------
# Minimal sidebar (configuration toggles only)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Runtime")
    st.session_state["use_backend"] = st.toggle(
        "Use FastAPI backend",
        value=st.session_state["use_backend"],
        help=f"If on, dashboard reads/writes via {BACKEND_URL}. Off = direct Store access.",
    )
    st.caption(f"Store: `data/store/`")
    st.caption(f"Model: `{os.getenv('CLAUDE_MODEL', 'claude-haiku-4-5')}`")

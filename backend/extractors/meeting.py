"""Meeting transcript extractor.

Two input modes:
  - Audio file (.mp3/.wav) -> AssemblyAI transcription with speaker diarization.
  - Plain text "Speaker A: ..." transcript -> parsed locally.

After getting utterances we ask Claude to extract structured entities.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from backend.config import ASSEMBLYAI_API_KEY, CLAUDE_EXTRACTION_MODEL
from backend.extractors._claude import call_claude_json
from backend.models.schemas import DecisionType, Entity, SourceType

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
def transcribe_meeting(audio_path: str) -> list[dict]:
    """Transcribe an audio file with speaker diarization via AssemblyAI."""
    if not ASSEMBLYAI_API_KEY:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not set")

    import assemblyai as aai  # local import to keep startup snappy

    aai.settings.api_key = ASSEMBLYAI_API_KEY
    config = aai.TranscriptionConfig(speaker_labels=True)
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_path)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {transcript.error}")

    utterances: list[dict] = []
    for u in transcript.utterances or []:
        utterances.append(
            {
                "speaker": f"Speaker {u.speaker}",
                "text": u.text,
                "start": getattr(u, "start", 0),
                "end": getattr(u, "end", 0),
            }
        )
    return utterances


_SPEAKER_RE = re.compile(r"^\s*([A-Za-z][\w \-]{0,40}):\s*(.+)$")


def transcribe_meeting_from_text(text: str) -> list[dict]:
    """Parse a transcript with 'Speaker X: text' style lines."""
    utterances: list[dict] = []
    current: Optional[dict] = None
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _SPEAKER_RE.match(line)
        if m:
            if current:
                utterances.append(current)
            current = {"speaker": m.group(1).strip(), "text": m.group(2).strip()}
        elif current:
            current["text"] += " " + line.strip()
    if current:
        utterances.append(current)

    if not utterances:
        # Fallback: treat the entire blob as a single Unknown speaker utterance.
        utterances = [{"speaker": "Unknown", "text": text.strip()}]
    return utterances


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
EXTRACTION_PROMPT = """You are analyzing a meeting transcript for team "{team}".
Extract ALL entities representing decisions, plans, commitments, concerns, and dependencies.

Transcript:
{transcript}

For each entity provide:
- name: Short specific identifier (e.g., "JWT authentication with RSA", NOT "authentication")
- description: Full context in 1-2 sentences
- decision_type: One of [decision, plan, commitment, concern, dependency]
- speaker: Who said it (use the label from the transcript)
- confidence: 0.0 to 1.0
- raw_text: Exact quote from the transcript

Focus on: technologies, architectural decisions, timelines, shared resources, APIs, services.
Capture EVERYTHING that could conflict with another team's work.
Aim for 5-10 entities per meeting.

Return ONLY valid JSON array. No markdown, no explanation."""


def _format_utterances(utterances: list[dict]) -> str:
    return "\n".join(f"{u['speaker']}: {u['text']}" for u in utterances)


def extract_entities_from_transcript(
    utterances: list[dict],
    team: str,
    meeting_id: str,
    meeting_date: datetime,
) -> list[Entity]:
    """Use Claude to extract entities from a list of utterances."""
    transcript_text = _format_utterances(utterances)
    prompt = EXTRACTION_PROMPT.format(team=team, transcript=transcript_text)
    raw = call_claude_json(prompt, max_tokens=3000, model=CLAUDE_EXTRACTION_MODEL)
    if not isinstance(raw, list):
        log.warning("Meeting extractor expected list, got %r", type(raw))
        return []

    entities: list[Entity] = []
    for item in raw:
        try:
            decision_type = DecisionType(item.get("decision_type", "plan"))
        except ValueError:
            decision_type = DecisionType.PLAN
        entities.append(
            Entity(
                id=f"meet-{meeting_id}-{uuid.uuid4().hex[:8]}",
                name=str(item.get("name", "")).strip()[:200],
                description=str(item.get("description", "")).strip(),
                source_type=SourceType.MEETING,
                source_id=meeting_id,
                team=team,
                decision_type=decision_type,
                timestamp=meeting_date,
                speaker=item.get("speaker"),
                confidence=float(item.get("confidence", 0.8)),
                raw_text=str(item.get("raw_text", "")),
            )
        )
    return entities


def process_meeting(
    *,
    audio_path: Optional[str] = None,
    transcript_text: Optional[str] = None,
    team: str,
    meeting_id: str,
    meeting_date: Optional[datetime] = None,
) -> list[Entity]:
    """Main entry point for the meeting extractor."""
    if not audio_path and not transcript_text:
        raise ValueError("Either audio_path or transcript_text must be provided")

    meeting_date = meeting_date or datetime.utcnow()
    if audio_path:
        utterances = transcribe_meeting(audio_path)
    else:
        utterances = transcribe_meeting_from_text(transcript_text or "")

    return extract_entities_from_transcript(utterances, team, meeting_id, meeting_date)

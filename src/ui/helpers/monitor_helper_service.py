from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from dataclasses import dataclass

from ...core.services.ollama_service import OllamaService
from .monitor_settings_store import MonitorActionSettings


@dataclass(frozen=True, slots=True)
class MonitorHelperResult:
    model: str
    content: str
    prompt_eval_count: object
    eval_count: object
    total_duration: object


@dataclass(frozen=True, slots=True)
class MonitorContextPacket:
    context_type: str
    panel_label: str
    selection_text: str
    focus_text: str
    full_visible_text: str
    structured_records: list[dict[str, object]]
    derived_facts: dict[str, object]

    def to_prompt_json(self) -> str:
        payload = {
            "context_type": self.context_type,
            "panel_label": self.panel_label,
            "selection_text": self.selection_text,
            "focus_text": self.focus_text,
            "full_visible_text": self.full_visible_text,
            "structured_records": self.structured_records,
            "derived_facts": self.derived_facts,
        }
        return json.dumps(payload, indent=2, sort_keys=True)


class MonitorHelperService:
    """Runs local-model helper actions for the operator monitor."""

    _PROMPT_ECHO_WARNING = (
        "That's a bit complex, so you may want to try a larger model for this one."
    )
    _LOG_LINE_PATTERN = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| "
        r"(?P<level>[A-Z]+) \| (?P<source>[^|]+) \| (?P<message>.+)$"
    )

    def __init__(self, ollama_service: OllamaService | None = None) -> None:
        self._ollama_service = ollama_service or OllamaService()

    def build_context_packet(
        self,
        *,
        context_label: str,
        context_text: str,
        context_type: str = "panel",
        full_visible_text: str | None = None,
        selection_text: str = "",
    ) -> MonitorContextPacket:
        visible_text = (full_visible_text or context_text).strip()
        focus_text = context_text.strip() or visible_text

        structured_records: list[dict[str, object]] = []
        derived_facts: dict[str, object] = {
            "label": context_label,
            "focus_char_count": len(focus_text),
            "visible_char_count": len(visible_text),
            "has_selection": bool(selection_text.strip()),
        }

        if context_type == "log_panel":
            structured_records, log_facts = self._parse_log_records(visible_text)
            derived_facts.update(log_facts)
        else:
            derived_facts.update(self._parse_key_value_facts(focus_text))
            payload_json = self._extract_json_section(focus_text, "payload")
            response_json = self._extract_json_section(focus_text, "response")
            if payload_json is not None:
                derived_facts["payload_keys"] = sorted(payload_json.keys())
            if response_json is not None:
                derived_facts["response_keys"] = sorted(response_json.keys())

        if not structured_records:
            structured_records = self._build_line_records(focus_text)

        return MonitorContextPacket(
            context_type=context_type,
            panel_label=context_label,
            selection_text=selection_text.strip(),
            focus_text=focus_text,
            full_visible_text=visible_text,
            structured_records=structured_records,
            derived_facts=derived_facts,
        )

    def summarize(
        self,
        *,
        context_label: str,
        context_text: str,
        settings: MonitorActionSettings,
        context_packet: MonitorContextPacket | None = None,
    ) -> MonitorHelperResult:
        packet = context_packet or self.build_context_packet(
            context_label=context_label,
            context_text=context_text,
        )
        messages = [
            {"role": "system", "content": settings.instructions},
            {
                "role": "user",
                "content": (
                    f"Context label: {context_label}\n\n"
                    "Structured context packet:\n"
                    f"{packet.to_prompt_json()}\n\n"
                    "Visible context excerpt:\n"
                    f"{self._prepare_context(packet.focus_text)}\n\n"
                    "Provide a concise summary for the operator."
                ),
            },
        ]
        response = self._ollama_service.chat_text(
            model=settings.model,
            messages=messages,
            temperature=0.2,
            max_tokens=220,
            timeout_seconds=90,
        )
        return self._to_result(
            response,
            fallback_text=self._fallback_summary(packet),
        )

    def ask_about(
        self,
        *,
        context_label: str,
        context_text: str,
        question: str,
        settings: MonitorActionSettings,
        context_packet: MonitorContextPacket | None = None,
        conversation_summary: str = "",
        recent_turns: list[dict[str, str]] | None = None,
    ) -> MonitorHelperResult:
        packet = context_packet or self.build_context_packet(
            context_label=context_label,
            context_text=context_text,
        )
        intent_hint = self._detect_intent(question)
        mechanical_answer = self._mechanical_answer(packet, question, intent_hint)
        if mechanical_answer is not None:
            return MonitorHelperResult(
                model=f"mechanical::{intent_hint}",
                content=mechanical_answer,
                prompt_eval_count=0,
                eval_count=0,
                total_duration=0,
            )
        messages = [
            {"role": "system", "content": settings.instructions},
            {
                "role": "user",
                "content": (
                    f"Context label: {context_label}\n\n"
                    f"Intent hint: {intent_hint}\n\n"
                    "Structured context packet:\n"
                    f"{packet.to_prompt_json()}\n\n"
                    f"{self._format_conversation_memory(conversation_summary, recent_turns)}"
                    "Visible context excerpt:\n"
                    f"{self._prepare_context(packet.focus_text)}\n\n"
                    f"Question: {question}\n\n"
                    "Answer the question directly and briefly."
                ),
            },
        ]
        response = self._ollama_service.chat_text(
            model=settings.model,
            messages=messages,
            temperature=0.2,
            max_tokens=320,
            timeout_seconds=120,
        )
        response_text = str(response.get("content", "")).strip()
        if self._looks_like_prompt_echo(response_text, question):
            response = {**response, "content": self._PROMPT_ECHO_WARNING}
        return self._to_result(
            response,
            fallback_text=self._fallback_answer(packet, question),
        )

    def list_models(self, timeout_seconds: int = 10) -> list[str]:
        return self._ollama_service.list_models(timeout_seconds=timeout_seconds)

    def _prepare_context(self, context_text: str, limit: int = 12000) -> str:
        normalized = context_text.strip()
        if len(normalized) <= limit:
            return normalized
        half = max(limit // 2 - 20, 200)
        return (
            normalized[:half]
            + "\n\n...[context truncated for monitor helper]...\n\n"
            + normalized[-half:]
        )

    def _to_result(
        self,
        response: dict[str, object],
        *,
        fallback_text: str,
    ) -> MonitorHelperResult:
        content = str(response["content"]).strip() or fallback_text
        return MonitorHelperResult(
            model=str(response["model"]),
            content=content,
            prompt_eval_count=response.get("prompt_eval_count"),
            eval_count=response.get("eval_count"),
            total_duration=response.get("total_duration"),
        )

    def _fallback_summary(self, packet: MonitorContextPacket) -> str:
        action = str(packet.derived_facts.get("action", "")).strip()
        summary = str(packet.derived_facts.get("summary", "")).strip()
        if packet.context_type == "log_panel" and packet.structured_records:
            event_count = len(packet.structured_records)
            last_record = packet.structured_records[-1]
            return (
                f"The visible log panel shows {event_count} parsed log events. "
                f"The latest visible event is {last_record.get('level', 'unknown')} "
                f"from {last_record.get('source', 'unknown')} saying: "
                f"{last_record.get('message', 'unknown')}."
            )
        if action and summary:
            return (
                f"Monitor context `{packet.panel_label}` appears to describe `{action}`. "
                f"The current summary line is: {summary}"
            )
        if action:
            return f"Monitor context `{packet.panel_label}` appears to describe `{action}`."
        return f"The model returned an empty response. Context label: {packet.panel_label}."

    def _fallback_answer(self, packet: MonitorContextPacket, question: str) -> str:
        action = str(packet.derived_facts.get("action", "")).strip()
        summary = str(packet.derived_facts.get("summary", "")).strip()
        normalized_question = question.lower().strip()
        if (
            packet.context_type == "log_panel"
            and packet.structured_records
            and any(phrase in normalized_question for phrase in ("list the events", "what events", "events do you see"))
        ):
            lines = []
            for record in packet.structured_records[:8]:
                lines.append(
                    f"- {record.get('timestamp', 'unknown')} | "
                    f"{record.get('level', 'unknown')} | "
                    f"{record.get('message', 'unknown')}"
                )
            return "Visible parsed log events:\n" + "\n".join(lines)

        if normalized_question in {"what is this about?", "what's this about?"}:
            if action and summary:
                return (
                    f"This looks like a monitor event for `{action}`. "
                    f"Based on the visible summary, it is about: {summary}"
                )
            if action:
                return f"This looks like a monitor event for `{action}`."
        return (
            "The model returned an empty response. "
            f"Visible context label: {packet.panel_label}. "
            f"Action: {action or 'unknown'}. Summary: {summary or 'unavailable'}."
        )

    def _extract_field(self, context_text: str, field_name: str) -> str:
        prefix = f"{field_name}:"
        for line in context_text.splitlines():
            if line.lower().startswith(prefix):
                return line.split(":", 1)[1].strip()
        return ""

    def _parse_log_records(self, context_text: str) -> tuple[list[dict[str, object]], dict[str, object]]:
        records: list[dict[str, object]] = []
        facts: dict[str, object] = {}
        kv_pairs: dict[str, str] = {}

        for raw_line in context_text.splitlines():
            line = raw_line.strip()
            if not line or set(line) == {"="}:
                continue
            match = self._LOG_LINE_PATTERN.match(line)
            if match is not None:
                records.append(
                    {
                        "timestamp": match.group("timestamp"),
                        "level": match.group("level"),
                        "source": match.group("source").strip(),
                        "message": match.group("message").strip(),
                    }
                )
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key:
                    kv_pairs[key] = value

        if records:
            facts["event_count"] = len(records)
            facts["latest_level"] = records[-1]["level"]
            facts["latest_source"] = records[-1]["source"]
            facts["latest_message"] = records[-1]["message"]
        if kv_pairs:
            facts["kv_pairs"] = kv_pairs
            if "transport" in kv_pairs:
                facts["transport"] = kv_pairs["transport"]
            if "workspace_root" in kv_pairs:
                facts["workspace_root"] = kv_pairs["workspace_root"]

        return records, facts

    def _parse_key_value_facts(self, context_text: str) -> dict[str, object]:
        facts: dict[str, object] = {}
        for field_name in ("id", "time", "group", "action", "sender", "target", "summary", "is_error"):
            value = self._extract_field(context_text, field_name)
            if value:
                facts[field_name] = value
        return facts

    def _extract_json_section(self, context_text: str, section_name: str) -> dict[str, object] | None:
        marker = f"{section_name}:"
        if marker not in context_text:
            return None
        _, remainder = context_text.split(marker, 1)
        next_marker = "\n\nresponse:" if section_name == "payload" else None
        if next_marker and next_marker in remainder:
            remainder = remainder.split(next_marker, 1)[0]
        candidate = remainder.strip()
        if not candidate:
            return None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    def _build_line_records(self, context_text: str, limit: int = 12) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for index, line in enumerate(context_text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            records.append({"line_no": index, "text": stripped})
            if len(records) >= limit:
                break
        return records

    def _detect_intent(self, question: str) -> str:
        normalized = question.lower()
        if any(token in normalized for token in ("list", "enumerate", "show me")):
            return "enumerate"
        if any(
            token in normalized
            for token in (
                "why",
                "explain",
                "what is this about",
                "what exactly",
                "what is happening",
                "happening here",
            )
        ):
            return "explain"
        if any(token in normalized for token in ("error", "wrong", "fail", "issue")):
            return "diagnose"
        if any(token in normalized for token in ("next", "should", "do now")):
            return "next_step"
        return "answer"

    def roll_conversation_window(
        self,
        *,
        conversation_summary: str,
        recent_turns: list[dict[str, str]],
        keep_recent_turns: int = 2,
        max_recent_chars: int = 1400,
        max_summary_chars: int = 1200,
    ) -> tuple[str, list[dict[str, str]]]:
        summary = conversation_summary.strip()
        rolling_turns = [dict(turn) for turn in recent_turns]

        while len(rolling_turns) > keep_recent_turns or self._recent_turn_char_count(rolling_turns) > max_recent_chars:
            oldest = rolling_turns.pop(0)
            summary = self._append_turn_to_summary(
                summary,
                oldest,
                max_summary_chars=max_summary_chars,
            )

        return summary, rolling_turns

    def _mechanical_answer(
        self,
        packet: MonitorContextPacket,
        question: str,
        intent_hint: str,
    ) -> str | None:
        if packet.context_type == "log_panel" and intent_hint == "enumerate" and packet.structured_records:
            word_limit = self._extract_word_limit(question)
            return self._format_log_enumeration(packet.structured_records, word_limit=word_limit)
        if packet.context_type in {"event_record", "text_panel"} and intent_hint == "explain":
            explanation = self._format_event_explanation(packet)
            if explanation:
                return explanation
        return None

    def _extract_word_limit(self, question: str) -> int | None:
        match = re.search(r"(\d+)\s+words?\s+or\s+less", question.lower())
        if match is None:
            return None
        try:
            return max(int(match.group(1)), 1)
        except ValueError:
            return None

    def _format_log_enumeration(
        self,
        records: list[dict[str, object]],
        *,
        word_limit: int | None,
    ) -> str:
        lines: list[str] = []
        for record in records[:12]:
            message = str(record.get("message", "")).strip()
            source = str(record.get("source", "")).strip()
            summary = self._summarize_log_message(message, source=source, word_limit=word_limit)
            lines.append(
                f"- {record.get('timestamp', 'unknown')} | "
                f"{record.get('level', 'unknown')} | {summary}"
            )
        return "\n".join(lines)

    def _summarize_log_message(
        self,
        message: str,
        *,
        source: str,
        word_limit: int | None,
    ) -> str:
        normalized = " ".join(message.split())
        if not normalized:
            normalized = "No message text"
        lower = normalized.lower()

        if "worker ready for mcp-style requests" in lower:
            summary = "Worker ready for MCP requests"
        elif "usefulhelper-worker" in lower:
            summary = normalized
        elif source:
            summary = f"{source} reported: {normalized}"
        else:
            summary = normalized

        words = summary.split()
        if word_limit is not None and len(words) > word_limit:
            summary = " ".join(words[:word_limit])
        return summary

    def _format_event_explanation(self, packet: MonitorContextPacket) -> str:
        action = str(packet.derived_facts.get("action", "")).strip()
        group = str(packet.derived_facts.get("group", "")).strip()
        sender = str(packet.derived_facts.get("sender", "")).strip()
        target = str(packet.derived_facts.get("target", "")).strip()
        summary = str(packet.derived_facts.get("summary", "")).strip()
        payload_keys = packet.derived_facts.get("payload_keys", [])
        response_keys = packet.derived_facts.get("response_keys", [])

        if not any((action, group, sender, target, summary)):
            return ""

        lines = []
        if action and sender and target:
            lines.append(
                f"This event records `{action}` moving from `{sender}` to `{target}`."
            )
        elif action:
            lines.append(f"This event records the action `{action}`.")

        if group or summary:
            detail_parts = []
            if group:
                detail_parts.append(f"group `{group}`")
            if summary:
                detail_parts.append(f"summary `{summary}`")
            lines.append("The visible metadata shows " + " and ".join(detail_parts) + ".")

        if payload_keys:
            lines.append(
                "The payload includes keys: " + ", ".join(str(key) for key in payload_keys) + "."
            )
        if response_keys:
            lines.append(
                "The response includes keys: " + ", ".join(str(key) for key in response_keys) + "."
            )
        return " ".join(lines)

    def _format_conversation_memory(
        self,
        conversation_summary: str,
        recent_turns: list[dict[str, str]] | None,
    ) -> str:
        lines: list[str] = []
        summary = conversation_summary.strip()
        if summary:
            lines.append("Conversation summary so far:")
            lines.append(summary)
            lines.append("")

        turns = recent_turns or []
        if turns:
            lines.append("Recent conversation turns:")
            for index, turn in enumerate(turns, start=1):
                lines.append(f"Turn {index} question: {turn.get('question', '').strip()}")
                lines.append(f"Turn {index} answer: {turn.get('answer', '').strip()}")
            lines.append("")

        if not lines:
            return ""
        return "\n".join(lines)

    def _append_turn_to_summary(
        self,
        summary: str,
        turn: dict[str, str],
        *,
        max_summary_chars: int,
    ) -> str:
        question = " ".join(turn.get("question", "").split())
        answer = " ".join(turn.get("answer", "").split())
        if len(answer) > 180:
            answer = answer[:177].rstrip() + "..."
        line = f"- Q: {question} | A: {answer}"
        combined = line if not summary else f"{summary}\n{line}"
        if len(combined) <= max_summary_chars:
            return combined
        return combined[-max_summary_chars:]

    def _recent_turn_char_count(self, recent_turns: list[dict[str, str]]) -> int:
        total = 0
        for turn in recent_turns:
            total += len(turn.get("question", ""))
            total += len(turn.get("answer", ""))
        return total

    def _looks_like_prompt_echo(self, response_text: str, question: str) -> bool:
        normalized_response = self._normalize_for_echo_check(response_text)
        normalized_question = self._normalize_for_echo_check(question)
        if len(normalized_question) < 24 or not normalized_response:
            return False

        ratio = SequenceMatcher(None, normalized_response, normalized_question).ratio()
        if normalized_question in normalized_response:
            containment_ratio = len(normalized_question) / max(len(normalized_response), 1)
        else:
            containment_ratio = 0.0

        return ratio >= 0.72 or containment_ratio >= 0.45

    def _normalize_for_echo_check(self, text: str) -> str:
        lowered = text.lower()
        lowered = re.sub(r"\s+", " ", lowered)
        lowered = re.sub(r"[^a-z0-9 ]", "", lowered)
        return lowered.strip()

import json
from typing import Any

SUB_AGENTS = frozenset({"nubank_agent", "bancolombia_agent"})


def _event_text(event: dict[str, Any]) -> str | None:
    for part in event.get("content", {}).get("parts", []):
        if "text" in part:
            return part["text"]
    return None


def _transfer_target(event: dict[str, Any]) -> str | None:
    for part in event.get("content", {}).get("parts", []):
        fc = part.get("functionCall") or {}
        if fc.get("name") == "transfer_to_agent":
            return (fc.get("args") or {}).get("agent_name")
    return None


def _parse_json_text(text: str) -> Any | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_run_response(data: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify an ADK /run response as success, rejection, or parse error."""
    transferred_to = None
    for event in data:
        target = _transfer_target(event)
        if target:
            transferred_to = target

    for event in reversed(data):
        author = event.get("author")
        if author not in SUB_AGENTS:
            continue
        text = _event_text(event)
        if text is None:
            continue
        parsed = _parse_json_text(text)
        if not isinstance(parsed, list):
            return {
                "status": "error",
                "reason": "invalid_json",
                "agent": author,
                "transferred_to": transferred_to,
            }
        return {
            "status": "success",
            "agent": author,
            "transferred_to": transferred_to,
            "movements": parsed,
        }

    for event in reversed(data):
        if event.get("author") != "root_agent":
            continue
        text = _event_text(event)
        if text is None:
            continue
        parsed = _parse_json_text(text)
        if isinstance(parsed, dict) and parsed.get("status") == "not_financial_statement":
            return {
                "status": "not_financial_statement",
                "reason": parsed.get("reason", ""),
                "transferred_to": transferred_to,
            }
        return {
            "status": "not_financial_statement",
            "reason": text,
            "transferred_to": transferred_to,
        }

    return {"status": "error", "reason": "empty_response", "transferred_to": transferred_to}

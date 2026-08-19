from typing import Any

ROUTE_TO_AGENT = {
    "nubank": "nubank_agent",
    "bancolombia": "bancolombia_agent",
    "otro_banco": "generic_agent",
}
CODE_TO_AGENT = {
    128: "nubank_agent",
    7: "bancolombia_agent",
}
NOT_STATEMENT_MESSAGE = "No es un extracto bancario"
VALIDATION_OK_PREFIX = "los movimientos concuerdan con el saldo"
VALIDATION_FAILED_PREFIX = "los movimientos no concuerdan con el saldo"


def _final_payload(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        output = event.get("output")
        if isinstance(output, dict) and "data" in output and "message" in output:
            return output
    return None


def parse_run_response(data: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify an ADK /run response as success, rejection, or parse error."""
    payload = _final_payload(data)
    if payload is None:
        return {"status": "error", "reason": "empty_response"}

    message = (payload.get("message") or "").strip()
    statement = payload.get("data")

    if statement is None or message.lower() == NOT_STATEMENT_MESSAGE.lower():
        return {
            "status": "not_financial_statement",
            "reason": message or NOT_STATEMENT_MESSAGE,
        }

    if not isinstance(statement, dict) or not isinstance(statement.get("movimientos"), list):
        return {"status": "error", "reason": "invalid_json"}

    movements = statement["movimientos"]
    banco = statement.get("banco")
    codigo = statement.get("codigo")
    agent = CODE_TO_AGENT.get(codigo)
    if agent is None and isinstance(banco, str):
        agent = ROUTE_TO_AGENT.get(banco)
    result: dict[str, Any] = {
        "agent": agent,
        "movements": movements,
        "message": message,
    }
    if banco is not None:
        result["banco"] = banco
    if codigo is not None:
        result["codigo"] = codigo

    if message.startswith(VALIDATION_FAILED_PREFIX):
        result.update({"status": "error", "reason": "validation_failed"})
        return result

    result["status"] = "success"
    result["validated"] = message.startswith(VALIDATION_OK_PREFIX)
    return result

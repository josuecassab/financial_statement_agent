from typing import Any

NOT_STATEMENT_MESSAGE = "No es un extracto bancario"
VALIDATION_OK_PREFIX = "los movimientos concuerdan con el saldo"
VALIDATION_FAILED_PREFIX = "los movimientos no concuerdan con el saldo"
NOT_VALIDATED_PREFIX = "plataforma fintech o billetera digital los saldos no se validaron"


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
    result: dict[str, Any] = {
        "movements": movements,
        "message": message,
    }
    if banco is not None:
        result["banco"] = banco
    if codigo is not None:
        result["codigo"] = codigo

    if codigo != 0 and message.startswith(VALIDATION_FAILED_PREFIX):
        result.update({"status": "error", "reason": message or "validation_failed"})
        return result

    if codigo == 0:
        result["status"] = "success"
        result["validated"] = False
        return result

    result["status"] = "success"
    result["validated"] = message.startswith(VALIDATION_OK_PREFIX)
    return result

import base64
import io
import logging
import os
import sys
import uuid
from pathlib import Path

import pandas as pd
import requests
from pypdf import PdfReader, PdfWriter

from parse_response import parse_run_response

logger = logging.getLogger(__name__)

FINANCIAL_STATEMENT_AGENT_URL = os.getenv(
    "FINANCIAL_STATEMENT_AGENT_URL", "http://127.0.0.1:8000"
)
APP_NAME = "financial_statement_agent"
USER_ID = os.getenv("ADK_USER_ID", "josuecassab")

DEFAULT_PDF = Path(
    "/Users/josuecassab/Google Drive/My Drive/extractos/extractos_nu/"
    "CuentaNu_JCO199_2026-06.pdf"
)


def _prepare_pdf_bytes(raw: bytes, password: str | None) -> bytes:
    """If the PDF is encrypted, decrypt with password and return an unencrypted copy."""
    reader = PdfReader(io.BytesIO(raw))
    if not reader.is_encrypted:
        return raw
    pwd = (password or "").strip()
    if not pwd:
        raise ValueError(
            "This PDF is password protected. Set PDF_PASSWORD in the environment."
        )
    if reader.decrypt(pwd) == 0:
        raise ValueError("The password does not correspond to this PDF.")
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def ensure_session(base_url: str, app_name: str, user_id: str, session_id: str) -> None:
    """ADK returns 404 from POST /run if the session does not exist yet."""
    url = f"{base_url}/apps/{app_name}/users/{user_id}/sessions/{session_id}"
    r = requests.post(url, json={}, headers={"Content-Type": "application/json"}, timeout=60)
    if r.status_code in (200, 409):
        return
    r.raise_for_status()


def process_pdf_statement(
    raw: bytes,
    upload_name: str,
    *,
    pdf_password: str | None = None,
    base_url: str | None = None,
    user_id: str = USER_ID,
) -> pd.DataFrame:
    base_url = (base_url or FINANCIAL_STATEMENT_AGENT_URL or "").rstrip("/")
    if not base_url:
        raise ValueError(
            "Set FINANCIAL_STATEMENT_AGENT_URL to your ADK server base URL (no trailing slash)."
        )

    raw = _prepare_pdf_bytes(raw, pdf_password)
    session_id = str(uuid.uuid4())
    ensure_session(base_url, APP_NAME, user_id, session_id)

    encoded = base64.b64encode(raw).decode("utf-8")
    payload = {
        "appName": APP_NAME,
        "userId": user_id,
        "sessionId": session_id,
        "newMessage": {
            "role": "user",
            "parts": [
                {
                    "inlineData": {
                        "displayName": upload_name,
                        "mimeType": "application/pdf",
                        "data": encoded,
                    }
                },
            ],
        },
    }

    response = requests.post(
        f"{base_url}/run",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=600,
    )
    response.raise_for_status()
    parsed = parse_run_response(response.json())
    logger.info("Agent parse result: %s", parsed.get("status"))

    if parsed["status"] == "not_financial_statement":
        raise ValueError(parsed.get("reason") or "Document is not a financial statement.")
    # if parsed["status"] != "success":
    #     detail = parsed.get("message") or parsed.get("reason", "unknown")
    #     raise RuntimeError(f"Failed to parse agent response: {detail}")

    codigo = parsed.get("codigo", 0)
    print(parsed.get("banco"))

    df = pd.DataFrame(parsed["movements"])
    df = df[["fecha", "descripcion", "valor"]].copy()
    df["valor"] = df["valor"].astype("float64")
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["fecha"] = df["fecha"].dt.date
    df["banco"] = codigo
    df.insert(0, "id", pd.RangeIndex(start=1, stop=len(df) + 1))
    df.columns = ["id", "date", "description", "amount", "bank"]
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    pdf_password = os.getenv("PDF_PASSWORD")

    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")

    upload_name = pdf_path.name
    with pdf_path.open("rb") as file:
        raw = file.read()

    df = process_pdf_statement(raw, upload_name, pdf_password=pdf_password)
    table_stem = upload_name.split(".")[0].replace(" ", "_")
    logger.info("Created statement table for upload: %s (%s rows)", table_stem, len(df))
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()

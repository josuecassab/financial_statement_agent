from __future__ import annotations

import argparse
import os

import psycopg

from process_entidades import process_entidades

ENSURE_UNIQUE_CODE = """
CREATE UNIQUE INDEX IF NOT EXISTS financial_entities_ref_code_key
ON public.financial_entities_ref (code);
"""

UPSERT_SQL = """
INSERT INTO public.financial_entities_ref (code, legal_name, type)
VALUES (%(code)s, %(legal_name)s, %(type)s)
ON CONFLICT (code) DO UPDATE SET
    legal_name = EXCLUDED.legal_name,
    type = EXCLUDED.type;
"""


def _to_python(value):
    if value is None or (isinstance(value, float) and value != value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, OverflowError):
            return None
    return value


def load_rows() -> list[dict]:
    df = process_entidades()
    records = df[["code", "legal_name", "type"]].to_dict(orient="records")
    return [
        {
            "code": _to_python(row["code"]),
            "legal_name": row["legal_name"],
            "type": row["type"],
        }
        for row in records
        if _to_python(row["code"]) is not None
    ]


def upsert_entities(database_url: str, rows: list[dict]) -> int:
    # Transaction-mode poolers (Supabase :6543) do not support prepared statements.
    with psycopg.connect(database_url, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(ENSURE_UNIQUE_CODE)
            cur.executemany(UPSERT_SQL, rows)
        conn.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Upsert financial_entities_ref from Superintendencia XLS sources "
            "(via process_entidades)."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Postgres URL (default: DATABASE_URL env var)",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit(
            "Missing database URL. Set DATABASE_URL or pass --database-url."
        )

    rows = load_rows()
    if not rows:
        raise SystemExit("No entities extracted; nothing to upsert.")

    count = upsert_entities(args.database_url, rows)
    print(f"Upserted {count} rows into financial_entities_ref.")


if __name__ == "__main__":
    main()

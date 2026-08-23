from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

DENOMINACION_SOCIAL_BY_CODIGO = {
    1: "Banco de Bogotá S.A.",
    2: "Banco Popular S.A.",
    6: "Itaú Colombia S.A.",
    7: "Bancolombia S.A.",
    9: "Citibank - Colombia",
    12: "BANCO GNB SUDAMERIS S.A.",
    13: "Banco Bilbao Vizcaya Argentaria Colombia S.A.",
    23: "Banco de Occidente",
    26: "Compañía de Financiamiento TUYA S.A.",
    30: "BANCO CAJA SOCIAL S.A.",
    31: "GM FINANCIAL COLOMBIA S.A. COMPAÑÍA DE FINANCIAMIENTO",
    39: "Banco Davivienda S.A.",
    42: "DAVIBANK S.A.",
    43: "BANCO AGRARIO DE COLOMBIA S.A.",
    46: "Coltefinanciera S.A. Compañía de Financiamiento",
    49: "Banco Comercial AV Villas S.A.",
    51: "BANCIEN S.A. y/o BAN100 S.A.",
    52: "Bancamía S.A.",
    53: "Banco W S.A",
    54: "Banco Coomeva S.A.",
    55: "Banco Finandina S.A.",
    56: "Banco Falabella S.A.",
    57: "Banco Pichincha S.A.",
    58: "COOPCENTRAL",
    59: "BANCO SANTANDER COLOMBIA S.A.",
    60: "BANCO MUNDO MUJER S.A.",
    62: "Mibanco S.A.",
    63: "BANCO SERFINANZA S.A.",
    64: "BANCO J.P. MORGAN COLOMBIA S.A.",
    65: "Lulo Bank S.A.",
    66: "Banco BTG Pactual Colombia S.A.",
    67: "BANCO UNIÓN S.A.",
    68: "BANCO CONTACTAR S.A.",
    108: "IRIS CF - COMPAÑÍA DE FINANCIAMIENTO S.A.",
    117: "Credifamilia Compañía de Financiamiento S.A.",
    118: "Crezcamos S.A. Compañía de Financiamiento",
    120: "La Hipotecaria Compañía de Financiamiento S.A.",
    121: "FINANCIERA JURISCOOP S.A. COMPAÑÍA DE FINANCIAMIENTO",
    122: "RCI COLOMBIA S.A. COMPAÑÍA DE FINANCIAMIENTO",
    123: "BANCAR TECNOLOGÍA CO S.A. COMPAÑÍA DE FINANCIAMIENTO",
    124: "RAPPIPAY COMPAÑÍA DE FINANCIAMIENTO S.A.",
    126: "MercadoPago S.A. Compañía de Financiamiento",
    127: "Bold CF Compañía de Financiamiento S.A.",
    128: "NU",
    129: "KOA COMPAÑÍA DE FINANCIAMIENTO S.A.",
    130: "NEQUI S.A. COMPAÑÍA DE FINANCIAMIENTO",
    131: "ADDI S.A. COMPAÑÍA DE FINANCIAMIENTO",
    132: "PLATA S.A. COMPAÑÍA DE FINANCIAMIENTO",
}

SOURCES = (
    {
        "path": BASE_DIR / "1_entidades_bcos.xls",
        "type": "ESTABLECIMIENTOS BANCARIOS",
        "format": "superintendencia",
    },
    {
        "path": BASE_DIR / "4_entidades_comfin.xls",
        "type": "COMPAÑÍAS DE FINANCIAMIENTO",
        "format": "superintendencia",
    },
    {
        "path": BASE_DIR / "5_fintechs.xlsx",
        "type": "FINTECH",
        "format": "flat",
    },
)


def _find_header(df: pd.DataFrame) -> tuple[int, int, int]:
    """Return (header_row, code_col, legal_name_col)."""
    for row_idx, row in df.iterrows():
        values = ["" if pd.isna(value) else str(value).strip() for value in row.tolist()]
        lower = [value.lower() for value in values]
        if any(value == "código" for value in lower) and any(
            "denominación social" in value for value in lower
        ):
            code_col = next(i for i, value in enumerate(lower) if value == "código")
            legal_name_col = next(
                i for i, value in enumerate(lower) if "denominación social" in value
            )
            return int(row_idx), code_col, legal_name_col
    raise ValueError("Could not find 'Código' and 'Denominación social de la Entidad' columns")


def _normalize_name(series: pd.Series) -> pd.Series:
    cleaned = (
        series.fillna("")
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    cleaned = cleaned.mask(cleaned.str.lower() == "nan", "")
    return cleaned


def extract_entities_superintendencia(path: Path, entity_type: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0, header=None, engine="xlrd")
    header_idx, code_col, legal_name_col = _find_header(df)

    entities = df.iloc[header_idx + 1 :, [code_col, legal_name_col]].copy()
    entities.columns = ["code", "legal_name"]
    entities["code"] = pd.to_numeric(entities["code"], errors="coerce")
    entities["legal_name"] = _normalize_name(entities["legal_name"])
    # Drop spreadsheet padding: no code and no name.
    entities = entities[entities["code"].notna() | (entities["legal_name"] != "")]
    entities["legal_name"] = (
        entities["code"].map(DENOMINACION_SOCIAL_BY_CODIGO).fillna(entities["legal_name"])
    )
    entities = entities[entities["legal_name"] != ""]
    entities["type"] = entity_type
    entities["code"] = entities["code"].astype("Int64")
    return entities.reset_index(drop=True)


def extract_entities_flat(path: Path, entity_type: str) -> pd.DataFrame:
    """Read a pre-normalized sheet with code / legal_name / type columns."""
    df = pd.read_excel(path, sheet_name=0)
    columns = {str(c).strip().lower(): c for c in df.columns}

    required = ("legal_name",)
    for name in required:
        if name not in columns:
            raise ValueError(f"{path.name}: missing required column '{name}'")

    entities = pd.DataFrame(
        {
            "code": pd.to_numeric(df[columns["code"]], errors="coerce")
            if "code" in columns
            else pd.NA,
            "legal_name": _normalize_name(df[columns["legal_name"]]),
            "type": (
                _normalize_name(df[columns["type"]])
                if "type" in columns
                else entity_type
            ),
        }
    )
    entities.loc[entities["type"] == "", "type"] = entity_type
    entities = entities[entities["code"].notna() | (entities["legal_name"] != "")]
    entities = entities[entities["legal_name"] != ""]
    entities["code"] = entities["code"].astype("Int64")
    return entities.reset_index(drop=True)


def extract_entities(path: Path, entity_type: str, fmt: str = "superintendencia") -> pd.DataFrame:
    if fmt == "flat":
        return extract_entities_flat(path, entity_type)
    return extract_entities_superintendencia(path, entity_type)


def process_entidades(sources: tuple[dict, ...] = SOURCES) -> pd.DataFrame:
    frames = [
        extract_entities(
            source["path"],
            source["type"],
            source.get("format", "superintendencia"),
        )
        for source in sources
    ]
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract entity codes and names from Superintendencia XLS files "
            "and write JSON or CSV."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: entidades.json or entidades.csv next to this script)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("json", "csv"),
        default="json",
        help="Output format (default: json)",
    )
    args = parser.parse_args()

    combined = process_entidades()
    output = args.output or (BASE_DIR / f"entidades.{args.format}")

    # JSON-friendly nulls
    records = combined.astype(object).where(combined.notna(), None).to_dict(orient="records")

    if args.format == "csv":
        combined.to_csv(output, index=False)
        print(combined.to_csv(index=False), end="")
    else:
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        output.write_text(payload + "\n", encoding="utf-8")
        print(payload)


if __name__ == "__main__":
    main()

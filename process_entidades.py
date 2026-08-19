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
    128: "NU COLOMBIA COMPAÑÍA DE FINANCIAMIENTO S.A.",
    129: "KOA COMPAÑÍA DE FINANCIAMIENTO S.A.",
    130: "NEQUI S.A. COMPAÑÍA DE FINANCIAMIENTO",
    131: "ADDI S.A. COMPAÑÍA DE FINANCIAMIENTO",
    132: "PLATA S.A. COMPAÑÍA DE FINANCIAMIENTO",
}

SOURCES = (
    {
        "path": BASE_DIR / "1_entidades_bcos.xls",
        "tipo": "ESTABLECIMIENTOS BANCARIOS",
    },
    {
        "path": BASE_DIR / "4_entidades_comfin.xls",
        "tipo": "COMPAÑÍAS DE FINANCIAMIENTO",
    },
)


def _find_header(df: pd.DataFrame) -> tuple[int, int, int]:
    """Return (header_row, codigo_col, denominacion_col)."""
    for row_idx, row in df.iterrows():
        values = ["" if pd.isna(value) else str(value).strip() for value in row.tolist()]
        lower = [value.lower() for value in values]
        if any(value == "código" for value in lower) and any(
            "denominación social" in value for value in lower
        ):
            codigo_col = next(i for i, value in enumerate(lower) if value == "código")
            denominacion_col = next(
                i for i, value in enumerate(lower) if "denominación social" in value
            )
            return int(row_idx), codigo_col, denominacion_col
    raise ValueError("Could not find 'Código' and 'Denominación social de la Entidad' columns")


def extract_entities(path: Path, tipo: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0, header=None, engine="xlrd")
    header_idx, codigo_col, denominacion_col = _find_header(df)

    entities = df.iloc[header_idx + 1 :, [codigo_col, denominacion_col]].copy()
    entities.columns = ["codigo", "denominacion_social"]
    entities = entities.dropna(how="any")
    entities["codigo"] = pd.to_numeric(entities["codigo"], errors="coerce")
    entities = entities.dropna(subset=["codigo"])
    entities["codigo"] = entities["codigo"].astype(int)
    entities["denominacion_social"] = (
        entities["denominacion_social"]
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    entities = entities[entities["denominacion_social"].str.lower() != "nan"]
    entities["denominacion_social"] = (
        entities["codigo"]
        .map(DENOMINACION_SOCIAL_BY_CODIGO)
        .fillna(entities["denominacion_social"])
    )
    entities["tipo"] = tipo
    return entities.reset_index(drop=True)


def process_entidades(sources: tuple[dict, ...] = SOURCES) -> list[dict]:
    frames = [extract_entities(source["path"], source["tipo"]) for source in sources]
    combined = pd.concat(frames, ignore_index=True)
    return combined.to_dict(orient="records")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract entity codes and names from Superintendencia XLS files "
            "and write a JSON array."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=BASE_DIR / "entidades.json",
        help="Output JSON path (default: entidades.json next to this script)",
    )
    args = parser.parse_args()

    records = process_entidades()
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()

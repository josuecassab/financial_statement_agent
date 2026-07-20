import io
import os

from google import genai
from google.cloud import storage
from google.genai import types
import json
import pandas as pd
# from app.core.config import DATABASE_URL
from sqlalchemy import create_engine
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)


def _download_pdf_from_gcs(gcs_uri: str) -> bytes:
    if not gcs_uri.startswith("gs://"):
        raise ValueError("gcs_uri must start with gs://")
    _, _, rest = gcs_uri.partition("gs://")
    bucket_name, _, blob_path = rest.partition("/")
    if not bucket_name or not blob_path:
        raise ValueError("Invalid gs://bucket/object URI")
    client = storage.Client()
    return client.bucket(bucket_name).blob(blob_path).download_as_bytes()


def extract_nubank_statements(client: genai.Client, gcs_uri: str, schema: str) -> str:
    pdf_bytes = _download_pdf_from_gcs(gcs_uri)
    uploaded: types.File | None = None
    try:
        uploaded = client.files.upload(
            file=io.BytesIO(pdf_bytes),
            config=types.UploadFileConfig(mime_type="application/pdf"),
        )
        contents = [
            types.Part.from_text(
                text="""
Convertir los extractos bancarios de un archivo pdf en una tabla de datos.
Solo convertir la sección de 'Movimientos',
no se te olvide la última transacción llamada 'Rendimiento total de tu cuenta' y agregale fecha como último día del mes.
Convertir la fecha en formato yyyy-mm-dd.
Responder con un array de objetos JSON donde cada objeto tiene el esquema de Movimientos.
Ejemplo: [{"fecha": "fecha_movimiento", "descripcion": "descripcion_movimiento", "valor": "valor_movimiento"}, ...]"""
            ),
            types.Part(uploaded),
        ]
        response = client.models.generate_content(
            # model="gemini-2.5-flash",
            model="gemini-3-flash-preview",
            contents=contents,
        )

        dict_data = json.loads(response.text.lstrip("```json").rstrip("```"))
        df = pd.DataFrame(dict_data)
        df["valor"] = df["valor"].str.strip()
        df["valor"] = df["valor"].str.replace(r"[^\d,.-]", "", regex=True)  # keep digits, comma, dot, minus
        df["valor"] = df["valor"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        df["valor"] = df["valor"].astype("float64")
        df['fecha'] = pd.to_datetime(df['fecha'])
        df['fecha'] = df['fecha'].dt.date
        df['banco'] = 'nubank'
        df.insert(0, "id", pd.RangeIndex(start=1, stop=len(df) + 1))
        df.to_sql(f'{gcs_uri.split("/")[-2]}_{gcs_uri.split("/")[-1].split(".")[0]}', engine, if_exists='replace', index=False, schema=schema)
        return df
    finally:
        if uploaded is not None and uploaded.name:
            client.files.delete(name=uploaded.name)


if __name__ == "__main__":
    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GENAI_API_KEY or GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    text = extract_nubank_statements(
        client, "gs://pf-extractos-josuecassab/nubank/CuentaNu_JCO199_2025-01.pdf",
        "josuecassab"
    )
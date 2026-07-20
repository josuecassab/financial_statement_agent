from google.adk.agents import Agent, LlmAgent
from pydantic import BaseModel, Field

ROOT_AGENT_MODEL = "gemini-2.5-flash"
SUB_AGENTS_MODEL = "gemini-3.5-flash"

class MovimientosNubank(BaseModel):
    fecha: str = Field(description="La fecha del movimiento")
    descripcion: str = Field(description="La descripción del movimiento")
    valor: float = Field(description="El valor del movimiento")

class MovimientosBancolombia(BaseModel):
    fecha: str = Field(description="La fecha del movimiento")
    descripcion: str = Field(description="La descripción del movimiento")
    valor: float = Field(description="El valor del movimiento")
    saldo: float = Field(description="El saldo del movimiento")

nubank_agent = Agent(
    name="nubank_agent",
    description="Agente para extraer datos de un extracto bancario de Nubank.",
    instruction="""Eres un experto en convertir archivos PDF en tablas de datos.
Solo convertir la sección de 'Movimientos',
no se te olvide la última transacción llamada 'Rendimiento total de tu cuenta' y agregale fecha como último día del mes.
Convertir la fecha en formato yyyy-mm-dd.
Ejemplo: [{"fecha": "2024-06-15", "descripcion": "...", "valor": 0.0}]
""",
    model=SUB_AGENTS_MODEL,
    output_schema=list[MovimientosNubank],
)

bancolombia_agent = Agent(
    name="bancolombia_agent",
    description="Agente para extraer movimientos de extractos Bancolombia (PDF o Excel).",
    instruction="""Eres un experto en extractos Bancolombia. Debes devolver movimientos tabulares
con al menos: fecha (yyyy-mm-dd), descripcion, valor y saldo cuando aplique.
Lee el PDF del contexto y extrae las columnas equivalentes a Fecha, Descripción, Valor y Saldo. Fechas en yyyy-mm-dd.
Respuesta final: array JSON de objetos coherentes con el extracto, por ejemplo
[{"fecha": "2024-06-15", "descripcion": "...", "valor": 0.0, "saldo": 0.0}, ...]
""",
    model=SUB_AGENTS_MODEL,
    output_schema=list[MovimientosBancolombia],
)

root_agent = LlmAgent(
    name="root_agent",
    description="Coordina la extracción de movimientos desde extractos bancarios de Nubank o Bancolombia.",
    instruction="""
Coordinas la extracción de movimientos desde extractos bancarios colombianos.

Reglas:
1. Si el documento es un extracto bancario de Nubank (PDF), transfiere a nubank_agent.
2. Si el documento es un extracto bancario de Bancolombia (PDF o Excel), transfiere a bancolombia_agent.
3. Si el documento NO es un extracto bancario (por ejemplo: comparendo, factura, certificado, documento administrativo u otro PDF no financiero), NO transfieras a ningún sub-agente. Responde ÚNICAMENTE con este JSON (sin markdown, sin texto adicional):
{"status": "not_financial_statement", "reason": "<explicación breve en español del tipo de documento detectado>"}

Nunca proceses tú mismo los movimientos. Nunca respondas en prosa cuando rechaces un documento.
""",
    sub_agents=[nubank_agent, bancolombia_agent],
    model=ROOT_AGENT_MODEL,
)


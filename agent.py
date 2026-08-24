import os
import json

from google.adk.agents import Agent, LlmAgent
from google.adk import Workflow
from google.adk import Context
from google.adk.workflow import node
from google.genai import types
from pydantic import BaseModel, Field

from pathlib import Path

ROOT_AGENT_MODEL = os.getenv("ROOT_AGENT_MODEL")
SUB_AGENTS_MODEL = os.getenv("SUB_AGENTS_MODEL")
ROOT_PATH = Path(__file__).parent
BANK_CODES_PATH = ROOT_PATH / "entidades.json"


class Movimientos(BaseModel):
    fecha: str = Field(description="La fecha del movimiento")
    descripcion: str = Field(description="La descripción del movimiento")
    valor: float = Field(description="El valor del movimiento")
    moneda: str = Field(description="La moneda del movimiento en formato ISO 4217")

class BankStatement(BaseModel):
    movimientos: list[Movimientos] = Field(
        description="Lista de movimientos del extracto"
    )
    saldo_anterior: float = Field(description="Saldo anterior del extracto")
    saldo_actual: float = Field(description="Saldo actual del extracto")

class GenericSchema(BaseModel):
    movimientos: list[Movimientos] = Field(
        description="Lista de movimientos del extracto"
    )
    saldo_anterior: float = Field(description="Saldo anterior del extracto")
    saldo_actual: float = Field(description="Saldo actual del extracto")

class RoutingResult(BaseModel):
    codigo: int = Field(description="Código de la entidad bancaria")
    denominacion: str = Field(description="Denominación social de la entidad bancaria")

def get_bank_codes() -> list[dict]:
    with open(BANK_CODES_PATH, "r") as f:
        return json.load(f)

@node
def statement_validation_function(node_input: BankStatement) -> bool:
    """
    Valida que el saldo actual sea igual a la suma de los movimientos más el saldo anterior.
    """
    statement = node_input
    if isinstance(statement, dict):
        statement = BankStatement.model_validate(statement)
    sum_amount = sum(m.valor for m in statement.movimientos)
    result = round(sum_amount + statement.saldo_anterior, 2) == round(statement.saldo_actual, 2)
    return result

nubank_agent = Agent(
    name="nubank_agent",
    description="Agente para extraer datos de un extracto bancario de Nubank.",
    instruction="""Eres un experto en convertir archivos PDF en tablas de datos.
Solo convertir la sección de 'Movimientos',
Extrae de cada movimiento las columnas equivalentes a fecha, descripción (o concepto) y valor.
no se te olvide el ultimo movimiento llamado 'Rendimiento total de tu cuenta' y agregale fecha como último día del mes.
Incluye la moneda en formato ISO 4217 (p. ej. COP, USD, BRL).
Convertir la fecha en formato yyyy-mm-dd.
Ejemplo:
{"movimientos": [{"fecha": "2024-06-15", "descripcion": "...", "valor": 0.0, "moneda": "COP"}],
"saldo_anterior": 0.0, "saldo_actual": 0.0}
""",
    model=SUB_AGENTS_MODEL,
    output_schema=BankStatement,
)

bancolombia_agent = Agent(
    name="bancolombia_agent",
    description="Agente para extraer movimientos de extractos Bancolombia (PDF o Excel).",
    instruction="""Eres un experto en extractos Bancolombia. Debes devolver un objeto JSON con:
Lee el PDF del contexto y extrae las columnas equivalentes a Fecha, Descripción, Valor.
Incluye la moneda en formato ISO 4217 (p. ej. COP, USD, BRL).
También agrega el saldo actual y el saldo anterior. Si no hay saldo anterior, usa 0.0.
Ejemplo:
{"movimientos": [{"fecha": "2024-06-15", "descripcion": "...", "valor": 0.0, "moneda": "COP"}],
"saldo_anterior": 0.0, "saldo_actual": 0.0}
""",
    model=SUB_AGENTS_MODEL,
    output_schema=BankStatement,
)

generic_agent = Agent(
    name="generic_agent",
    description="Agente para extraer datos de un extracto bancario de otro banco.",
    instruction="""Eres un experto en convertir archivos PDF en tablas de datos.
Extrae de cada movimiento las columnas equivalentes a fecha, descripción (o concepto) y valor.
Incluye la moneda en formato ISO 4217 (p. ej. COP, USD, BRL).
También agrega el saldo actual y el saldo anterior. Si no hay saldo anterior, usa 0.0.
Convierte la fecha a formato yyyy-mm-dd.
Ejemplo:
{"movimientos": [{"fecha": "2024-06-15", "descripcion": "...", "valor": 0.0, "moneda": "COP"}],
"saldo_anterior": 0.0, "saldo_actual": 0.0}
""",
    model=SUB_AGENTS_MODEL,
    output_schema=GenericSchema,
)

routing_agent = LlmAgent(
    name="routing_agent",
    description="Identifica el tipo de documento y decide si es un extracto bancario de Nubank, Bancolombia o otro banco",
    instruction="""
Identifica el tipo de documento y decide si es un extracto bancario de Nubank, Bancolombia o otro banco.
Usa la herramienta get_bank_codes para obtener la lista de entidades bancarias.
Responde con el código (code) y la denominación social (legal_name) de la entidad bancaria.
Si es una plataforma fintech o billetera digital que no está en la lista, responde con codigo 0 y denominacion "nombre billetera o plataforma fintech".
Si no es un extracto bancario, responde con codigo 0 y denominacion "no_bancario".
Ejemplo:
{"codigo": 1, "denominacion": "Banco de Bogotá S.A."}
""",
    output_schema=RoutingResult,
    model=ROOT_AGENT_MODEL,
    tools=[get_bank_codes],
)

def _statement_payload(statement, *, code: int, bank_name: str) -> dict:
    data = statement.model_dump() if hasattr(statement, "model_dump") else dict(statement)
    data["codigo"] = code
    data["banco"] = bank_name
    return data


@node(rerun_on_resume=True)
async def code_workflow(ctx: Context, node_input: types.Content):
    # Must accept Content (not str) so PDF/inline_data is not stripped by ADK.
    routing = await ctx.run_node(routing_agent, node_input)
    if isinstance(routing, dict):
        routing = RoutingResult.model_validate(routing)
    code, bank_name = routing.codigo, routing.denominacion
    if code == 128:
        data = await ctx.run_node(nubank_agent, node_input)
        validation_result = await ctx.run_node(statement_validation_function, data)
        return {
            "data": _statement_payload(data, code=code, bank_name=bank_name),
            "message": "los movimientos concuerdan con el saldo" if validation_result else "los movimientos no concuerdan con el saldo",
        }
    elif code == 7:
        bancolombia_statement = await ctx.run_node(bancolombia_agent, node_input)
        validation_result = await ctx.run_node(statement_validation_function, bancolombia_statement)
        return {
            "data": _statement_payload(bancolombia_statement, code=code, bank_name=bank_name),
            "message": "los movimientos concuerdan con el saldo" if validation_result else "los movimientos no concuerdan con el saldo",
        }
    elif code == 0 and bank_name == "no_bancario":
        return {"data": None, "message": "No es un extracto bancario"}
    else:
        generic_statement = await ctx.run_node(generic_agent, node_input)
        return {
            "data": _statement_payload(generic_statement, code=code, bank_name=bank_name),
            "message": "plataforma fintech o billetera digital los saldos no se validaron",
        }


root_agent = Workflow(
    name='financial_statement_agent',
    edges=[("START", code_workflow)]
)

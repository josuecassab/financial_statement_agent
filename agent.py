import os

from google.adk.agents import Agent, LlmAgent
from google.adk import Workflow
from google.adk import Context
from google.adk.workflow import node
from google.genai import types
from pydantic import BaseModel, Field


ROOT_AGENT_MODEL = os.getenv("ROOT_AGENT_MODEL")
SUB_AGENTS_MODEL = os.getenv("SUB_AGENTS_MODEL")


class Movimientos(BaseModel):
    fecha: str = Field(description="La fecha del movimiento")
    descripcion: str = Field(description="La descripción del movimiento")
    valor: float = Field(description="El valor del movimiento")

class BankStatement(BaseModel):
    movimientos: list[Movimientos] = Field(
        description="Lista de movimientos del extracto"
    )
    saldo_anterior: float = Field(description="Saldo anterior del extracto")
    saldo_actual: float = Field(description="Saldo actual del extracto")
    banco: str = Field(description="El banco del extracto")

class GenericSchema(BaseModel):
    movimientos: list[Movimientos] = Field(
        description="Lista de movimientos del extracto"
    )
    saldo_anterior: float = Field(description="Saldo anterior del extracto")
    saldo_actual: float = Field(description="Saldo actual del extracto")
    banco: str = Field(description="El banco del extracto")

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
no se te olvide la última transacción llamada 'Rendimiento total de tu cuenta' y agregale fecha como último día del mes.
Convertir la fecha en formato yyyy-mm-dd.
Ejemplo:
{"movimientos": [{"fecha": "2024-06-15", "descripcion": "...", "valor": 0.0, "saldo": 0.0}],
"saldo_anterior": 0.0, "saldo_actual": 0.0, "banco": "nubank"}
""",
    model=SUB_AGENTS_MODEL,
    output_schema=BankStatement,
)

bancolombia_agent = Agent(
    name="bancolombia_agent",
    description="Agente para extraer movimientos de extractos Bancolombia (PDF o Excel).",
    instruction="""Eres un experto en extractos Bancolombia. Debes devolver un objeto JSON con:
movimientos (fecha yyyy-mm-dd, descripcion, valor, saldo), saldo_anterior y saldo_actual.
Lee el PDF del contexto y extrae las columnas equivalentes a Fecha, Descripción, Valor y Saldo.
Ejemplo:
{"movimientos": [{"fecha": "2024-06-15", "descripcion": "...", "valor": 0.0, "saldo": 0.0}],
"saldo_anterior": 0.0, "saldo_actual": 0.0, "banco": "bancolombia"}
""",
    model=SUB_AGENTS_MODEL,
    output_schema=BankStatement,
)

generic_agent = Agent(
    name="generic_agent",
    description="Agente para extraer datos de un extracto bancario de otro banco.",
    instruction="""Eres un experto en convertir archivos PDF en tablas de datos.
convierte las  columnas fecha, decripción/concepto, valor, o columnas equivalentes a las anteriores.
También agrega el saldo actual y el saldo anterior. Si no hay saldo anterior, agregale 0.0.

Convertir la fecha en formato yyyy-mm-dd.
Ejemplo:
{"movimientos": [{"fecha": "2024-06-15", "descripcion": "...", "valor": 0.0, "saldo": 0.0}],
"saldo_anterior": 0.0, "saldo_actual": 0.0, "banco": "El nombre del banco"}
""",
    model=SUB_AGENTS_MODEL,
    output_schema=GenericSchema,
)

routing_agent = LlmAgent(
    name="routing_agent",
    description="Identifica el tipo de documento y decide si es un extracto bancario de Nubank, Bancolombia o otro banco",
    instruction="""
Identifica el tipo de documento y decide si es un extracto bancario de Nubank, Bancolombia o otro banco.
Si es un extracto bancario de Nubank, responde con "nubank".
Si es un extracto bancario de Bancolombia, responde con "bancolombia".
Si es un extracto bancario de otro banco, responde con "otro_banco".
Si es una plataforma fintech o billetera digital, responde con "otro_banco".
Si no es un extracto bancario, responde con "no_bancario".
""",
    output_schema=str,
    model=ROOT_AGENT_MODEL,
)

@node(rerun_on_resume=True)
async def code_workflow(ctx: Context, node_input: types.Content):
    # Must accept Content (not str) so PDF/inline_data is not stripped by ADK.
    bank_agent = await ctx.run_node(routing_agent, node_input)
    if bank_agent == "nubank":
        data = await ctx.run_node(nubank_agent, node_input)
        validation_result = await ctx.run_node(statement_validation_function, data)
        return {"data": data, "message": "los movimientos concuerdan con el saldo" if validation_result else "los movimientos no concuerdan con el saldo"}
    elif bank_agent == "bancolombia":
        bancolombia_statement = await ctx.run_node(bancolombia_agent, node_input)
        validation_result = await ctx.run_node(statement_validation_function, bancolombia_statement)
        return {"data": bancolombia_statement, "message": "los movimientos concuerdan con el saldo" if validation_result else "los movimientos no concuerdan con el saldo"}
    elif bank_agent == "otro_banco":
        cnt = 0
        validation_result = False
        while not validation_result and cnt < 2:
            generic_statement = await ctx.run_node(generic_agent, node_input)
            validation_result = await ctx.run_node(statement_validation_function, generic_statement)
            cnt += 1

        return {"data": generic_statement, "message": "los movimientos concuerdan con el saldo" if validation_result else f"los movimientos no concuerdan con el saldo, se intentó {cnt} veces"}
    else:
        return {"data": None, "message": "No es un extracto bancario"}


root_agent = Workflow(
    name='financial_statement_agent',
    edges=[("START", code_workflow)]
)

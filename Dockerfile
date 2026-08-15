FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    GOOGLE_GENAI_USE_VERTEXAI=TRUE

COPY requirements.txt /app/agents/financial_statement_agent/requirements.txt
RUN pip install --no-cache-dir -r /app/agents/financial_statement_agent/requirements.txt

COPY __init__.py agent.py /app/agents/financial_statement_agent/

EXPOSE 8080

CMD ["sh", "-c", "adk api_server --host=0.0.0.0 --port=${PORT:-8080} /app/agents"]

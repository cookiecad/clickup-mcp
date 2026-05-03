FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Keep the image small but practical for TLS/certs.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY clickup_mcp /app/clickup_mcp
COPY pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "clickup_mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000", "--path", "/mcp"]

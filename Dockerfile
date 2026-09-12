FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 automation && mkdir -p /app/storage && chown -R automation:automation /app
USER automation
CMD ["python", "-m", "automations.cashconverters.run"]

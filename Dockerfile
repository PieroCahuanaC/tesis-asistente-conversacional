# Imagen única para la API y la interfaz (RNF-10). Las versiones exactas vienen de requirements.lock.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock .
RUN pip install -r requirements.lock
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps -e .
COPY config ./config
COPY db ./db
COPY prompts ./prompts
COPY scripts ./scripts
COPY ui ./ui
COPY eval ./eval
EXPOSE 8000 8501
CMD ["uvicorn", "asistente.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PAPERPILOT_SEED_DIR=/app/demo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY frontend ./frontend
COPY demo ./demo
# Hugging Face Spaces runs containers as user 1000; this user gets that id.
RUN mkdir -p data && useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

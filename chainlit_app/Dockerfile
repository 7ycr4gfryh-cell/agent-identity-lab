FROM python:3.13-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root (Chainlit writes .chainlit/.files under /app).
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

ENV PORT=8080
CMD ["sh", "-c", "chainlit run app.py --host 0.0.0.0 --port ${PORT}"]

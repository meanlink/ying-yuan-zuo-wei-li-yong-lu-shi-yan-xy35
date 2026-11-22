FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY scripts ./scripts
RUN mkdir -p /shared
EXPOSE 8000
CMD ["sh", "-c", "python -m src.bootstrap && uvicorn src.main:app --host 0.0.0.0 --port 8000"]

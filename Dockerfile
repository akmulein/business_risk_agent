FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt

COPY src ./src
RUN pip install --no-cache-dir --no-deps .

COPY data ./data

EXPOSE 8000
CMD ["uvicorn", "counterparty_verification.api:app", "--host", "0.0.0.0", "--port", "8000"]

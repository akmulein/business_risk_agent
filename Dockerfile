FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
RUN python -c 'import pathlib, subprocess, sys, tomllib; deps = tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"].get("dependencies", []); subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", *deps])'

COPY app ./app
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]

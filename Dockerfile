# Single portable image: stateless FastAPI app that serves its own static frontend.
# Runs the same on Hugging Face Spaces, Render, Fly, or locally. No database, no disk.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Keep any library caches (e.g. tiktoken) in a writable dir — hosts often allow only /tmp.
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    PORT=7860

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 7860

# $PORT is set by the host (HF Spaces app_port 7860, Render, …); default 7860 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]

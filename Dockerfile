ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV= PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
USER root
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends git patch ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --timeout 300 --retries 10 --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/* /root/.cache/pip
COPY backend ./backend
COPY web ./web
COPY tests ./tests
COPY samples ./samples
RUN mkdir -p /app/data /workspace \
    && useradd --create-home --uid 10001 codezzn \
    && chown -R codezzn:codezzn /app /workspace
# The main service selects its user for bind-mount compatibility and never mounts Docker's socket.
# The sandbox overlay reuses this image for the trusted root broker; execution uses Dockerfile.sandbox.
USER codezzn
EXPOSE 8080
ENTRYPOINT []
CMD ["/usr/local/bin/python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]

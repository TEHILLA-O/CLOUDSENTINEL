FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

USER 1000
EXPOSE 8000

# Live is the process. Ready is the workload. Startup gives a slow import a chance
# without letting a crash loop look ready.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready')"

CMD ["uvicorn", "analysis_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

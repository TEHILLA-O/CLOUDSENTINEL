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
EXPOSE 8080
CMD ["uvicorn", "cloudsentinel_gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]

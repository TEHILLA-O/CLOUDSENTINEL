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
CMD ["uvicorn", "cloudsentinel_control.main:app", "--host", "0.0.0.0", "--port", "8000"]

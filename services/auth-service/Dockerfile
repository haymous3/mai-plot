FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps from pyproject.toml (SCRUM-40 — replaces the hardcoded
# `pip install fastapi uvicorn` left over from SCRUM-35). pip resolves
# the full dependency set declared by the project.
COPY pyproject.toml ./
COPY app/ ./app/
RUN pip install .

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

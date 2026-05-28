from fastapi import FastAPI

from app.telemetry import setup_telemetry

SERVICE_NAME = "auth-service"

app = FastAPI(title="Maiplot Auth Service", version="0.1.0")
setup_telemetry(SERVICE_NAME, app)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}

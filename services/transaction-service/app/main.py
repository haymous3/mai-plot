from fastapi import FastAPI

SERVICE_NAME = "transaction-service"

app = FastAPI(title="Maiplot Transaction Service", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}

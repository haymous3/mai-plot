from fastapi import FastAPI

SERVICE_NAME = "auth-service"

app = FastAPI(title="Maiplot Auth Service", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}

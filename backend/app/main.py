from fastapi import FastAPI

app = FastAPI(title="Monitoreo Quito API")

@app.get("/health")
def health():
    return {"status": "ok"}

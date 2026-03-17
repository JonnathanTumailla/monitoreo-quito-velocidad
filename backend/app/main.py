from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI(title="Monitoreo Quito API")

# Esquema de datos para lo que enviará el celular
class TelemetriaGPS(BaseModel):
    bus_hash: str        # Hash del QR
    latitud: float
    longitud: float
    velocidad: float
    # Campos para tu lógica de resiliencia
    is_interpolated: bool = False
    method: Optional[str] = "realtime"

@app.post("/api/v1/telemetria")
async def recibir_telemetria(data: TelemetriaGPS):
    # 1. Aquí iría la validación del Hash del QR que mencionaste
    # 2. Aquí llamarías a PostGIS para ver si está en exceso de velocidad
    
    print(f"Recibido Bus: {data.bus_hash} a {data.velocidad} km/h")
    
    return {
        "status": "registrado",
        "timestamp": datetime.now(),
        "interpolated": data.is_interpolated
    }

@app.get("/health")
def health():
    return {"status": "ok"}
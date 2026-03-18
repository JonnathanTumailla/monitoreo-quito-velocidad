from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
import psycopg2
import os

app = FastAPI(title="Monitoreo Quito API")
DATABASE_URL = os.getenv("DATABASE_URL")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"❌ Error de validación: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

class TelemetriaGPS(BaseModel):
    bus_id: UUID
    latitud: float
    longitud: float
    velocidad: float
    accuracy_m: float = 0.0

@app.post("/api/v1/telemetria")
async def recibir_telemetria(data: TelemetriaGPS):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Insertamos solo en las columnas que sabemos que existen y funcionan
        query = """
            INSERT INTO telemetry (source, bus_id, ts, lat, lon, speed_kmh, accuracy_m, geom)
            VALUES (%s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        """
        
        ahora = datetime.now()
        
        valores = (
            'BUS',             # source (ENUM permitido en tu DB)
            str(data.bus_id),  # bus_id (UUID como string)
            ahora,             # ts
            data.latitud,      # lat
            data.longitud,     # lon
            data.velocidad,    # speed_kmh
            data.accuracy_m,   # accuracy_m
            data.longitud,     # geom (Lon)
            data.latitud       # geom (Lat)
        )

        cur.execute(query, valores)
        conn.commit()
        cur.close()
        conn.close()

        return {"status": "success", "message": "¡Dato registrado en PostGIS!"}

    except Exception as e:
        if conn:
            conn.close()
        print(f"❌ Error DB: {e}")
        raise HTTPException(status_code=500, detail=f"Error DB: {str(e)}")
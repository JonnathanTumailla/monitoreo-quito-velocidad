import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from psycopg2 import pool, DatabaseError
from contextlib import contextmanager

# 1. LOGGING ESTRUCTURADO (Punto 6: Reemplaza prints por trazabilidad real)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 2. VALIDACIÓN TEMPRANA DE CONFIGURACIÓN (Punto 3: Falla rápido si falta la URL)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.critical("DATABASE_URL no encontrada en el entorno. La API no puede iniciar.")
    raise RuntimeError("Falta la variable de entorno DATABASE_URL")

# 3. CONNECTION POOLING (Punto 4: Gestión eficiente de conexiones)
# Mantenemos entre 1 y 10 conexiones listas para ser usadas
try:
    db_pool = pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
    logger.info("Pool de conexiones PostgreSQL inicializado correctamente")
except Exception as e:
    logger.critical(f"Error fatal al inicializar el pool de base de datos: {e}")
    raise

@contextmanager
def get_db_connection():
    """Context manager para asegurar que las conexiones vuelvan al pool pase lo que pase."""
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)

app = FastAPI(title="Monitoreo Quito API - v2.0")

# 4. MODELO CON VALIDACIONES DE RANGO Y CONTRATO (Puntos 8 y 9)
class TelemetriaGPS(BaseModel):
    bus_id: UUID
    latitud: float = Field(..., ge=-0.5, le=0.1, description="Rango válido para Quito")
    longitud: float = Field(..., ge=-78.6, le=-78.3, description="Rango válido para Quito")
    velocidad: float = Field(..., ge=0, le=120)
    accuracy_m: float = Field(default=0.0, ge=0)
    # Recuperamos lógica del contrato original
    is_interpolated: bool = False
    method: str = "gps"

# 5. ENDPOINT /HEALTH (Punto 1: Observabilidad)
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Verifica la salud de la API y la conexión activa a la DB"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {
            "status": "healthy",
            "db_connected": True,
            "timestamp": datetime.now(timezone.utc) # Punto 10: UTC explícito
        }
    except Exception as e:
        logger.error(f"Healthcheck falló: {e}")
        raise HTTPException(status_code=503, detail="Servicio no disponible temporalmente")

# 6. ENDPOINT PRINCIPAL (Síncrono para no bloquear el driver psycopg2 - Punto 2)
@app.post("/api/v1/telemetria", status_code=status.HTTP_201_CREATED)
def recibir_telemetria(data: TelemetriaGPS):
    # Punto 10: Timestamp UTC para evitar problemas de desfase horario
    ahora = datetime.now(timezone.utc)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Query parametrizada para evitar SQL Injection
                query = """
                    INSERT INTO telemetry (source, bus_id, ts, lat, lon, speed_kmh, accuracy_m, geom)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                """
                
                valores = (
                    'BUS', 
                    str(data.bus_id), 
                    ahora, 
                    data.latitud, 
                    data.longitud, 
                    data.velocidad, 
                    data.accuracy_m,
                    data.longitud, # PostGIS espera Lon primero
                    data.latitud
                )
                
                cur.execute(query, valores)
                conn.commit()
                
        logger.info(f"Telemetría exitosa: Bus {data.bus_id} a {data.velocidad} km/h")
        return {"status": "success", "message": "Datos integrados correctamente"}

    except DatabaseError as e:
        # Puntos 5 y 11: Manejo de errores sin exponer internals
        logger.error(f"Error de base de datos: {e}")
        
        # Validación de negocio (Punto 11: El bus debe existir)
        if "violates foreign key constraint" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Error de negocio: Bus ID no registrado en la tabla maestra"
            )
            
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno en el procesamiento de datos"
        )
    except Exception as e:
        logger.error(f"Error inesperado no manejado: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

# Cierre limpio del pool al apagar la aplicación
@app.on_event("shutdown")
def shutdown_event():
    db_pool.closeall()
    logger.info("Pool de conexiones a la base de datos cerrado de forma limpia.")
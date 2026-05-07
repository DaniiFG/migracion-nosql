"""
Core de Migración - FastAPI Application
Servicio principal para migrar datos de SQL Server (AdventureWorksLT) a MongoDB.
Utiliza Pandas para la transformación de datos.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os

from app.routers import sql_router, mongo_router, migration_router, compare_router

app = FastAPI(
    title="Migración SQL → MongoDB",
    description="Taller Práctico: De Monolito Relacional a MongoDB Distribuido",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates y archivos estáticos
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
static_dir = os.path.join(os.path.dirname(__file__), "static")

templates = Jinja2Templates(directory=templates_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Registrar routers
app.include_router(sql_router.router, prefix="/api/sql", tags=["SQL Server"])
app.include_router(mongo_router.router, prefix="/api/mongo", tags=["MongoDB"])
app.include_router(migration_router.router, prefix="/api/migration", tags=["Migración"])
app.include_router(compare_router.router, prefix="/api/compare", tags=["Comparación"])


@app.get("/")
async def dashboard(request: Request):
    """Dashboard principal con interfaz web."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """Health check del servicio."""
    return {"status": "ok", "service": "core-migration"}

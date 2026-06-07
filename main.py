from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import auth, captures, admin

app = FastAPI(title="SimpleResolve API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,    prefix="/auth",    tags=["Autenticación"])
app.include_router(captures.router, prefix="/captures", tags=["Capturas"])
app.include_router(admin.router,   prefix="/admin",   tags=["Admin"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


# Panel admin (archivos estáticos en admin/ junto al servidor)
_admin_panel_dir = Path(__file__).parent / "admin"
app.mount("/panel", StaticFiles(directory=str(_admin_panel_dir), html=True), name="admin_panel")

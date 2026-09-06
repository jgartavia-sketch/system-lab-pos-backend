from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

from app.api.routes.auth import router as auth_router
from app.api.routes.cash_movements import router as cash_movements_router
from app.api.routes.cash_registers import router as cash_registers_router
from app.api.routes.categories import router as categories_router
from app.api.routes.customers import router as customers_router
from app.api.routes.inventory_alerts import router as inventory_alerts_router
from app.api.routes.inventory_movements import router as inventory_movements_router
from app.api.routes.payment_methods import router as payment_methods_router
from app.api.routes.products import router as products_router
from app.api.routes.reports import router as reports_router
from app.api.routes.sales import router as sales_router
from app.api.routes.users import router as users_router
from app.api.routes.client_management import router as client_management_router
from app.api.routes.stories import router as stories_router

app = FastAPI(
    title="System Lab POS API",
    description="Backend oficial del sistema POS SaaS de System Lab.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(categories_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(payment_methods_router)
app.include_router(cash_registers_router)
app.include_router(cash_movements_router)
app.include_router(sales_router)
app.include_router(reports_router)
app.include_router(inventory_movements_router)
app.include_router(inventory_alerts_router)
app.include_router(client_management_router)
app.include_router(stories_router)


@app.get("/")
def root():
    return {
        "app": "System Lab POS API",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "Backend funcionando correctamente.",
    }


# POS routes use independent accounts and tenant-scoped tables.
from app.pos.routes import router as pos_router
from starlette.responses import JSONResponse
app.include_router(pos_router)

@app.middleware("http")
async def retire_unscoped_pos(request, call_next):
    legacy = {"auth", "users", "categories", "products", "customers", "payment-methods", "cash-registers", "cash-movements", "sales", "reports", "inventory-movements", "inventory-alerts"}
    if request.url.path.strip("/").split("/")[0] in legacy:
        return JSONResponse(status_code=410, content={"detail": "Usá el POS autenticado en /pos-api. Las rutas antiguas fueron retiradas por seguridad."})
    response = await call_next(request)
    if request.url.path.startswith("/pos-api"):
        response.headers["Cache-Control"] = "no-store"
    return response

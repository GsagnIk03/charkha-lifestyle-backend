import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import inventory_requests, orders, products

app = FastAPI(title="Charkha Lifestyle API")

allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(inventory_requests.router)
app.include_router(orders.router)


@app.get("/health")
def health():
    return {"status": "ok"}

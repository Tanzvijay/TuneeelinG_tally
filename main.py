from fastapi import FastAPI
from routers import router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="KPI Pipeline API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(router)
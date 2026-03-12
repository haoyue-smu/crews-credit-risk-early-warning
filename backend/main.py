from fastapi import FastAPI
from backend.api.routes.assess import router as assess_router

print("Loaded assess router:", assess_router.routes)

app = FastAPI(title="Credit Agent API")
app.include_router(assess_router, prefix="/api")

@app.get("/")
def root():
    return {"status": "ok"}


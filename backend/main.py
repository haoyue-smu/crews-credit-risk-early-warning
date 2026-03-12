from fastapi import FastAPI

app = FastAPI(title="Credit Agent API")


@app.get("/")
def root():
    return {"status": "ok"}
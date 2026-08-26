import os
from fastapi import FastAPI

app = FastAPI()

APP_NAME = os.getenv("APP_NAME", "app")
ENV = os.getenv("ENV", "dev")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"app": APP_NAME, "env": ENV}

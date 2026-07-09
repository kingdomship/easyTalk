"""Emoji Chat — LLM-driven pixel avatar with emotion sequences."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

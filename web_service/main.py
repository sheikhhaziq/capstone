from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
import os

app = FastAPI()

templates = Jinja2Templates(directory="templates")

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8001/chat/")

class ChatInput(BaseModel):
    text: str
    history_ids: list = []

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/chat")
async def chat_proxy(input_data: ChatInput):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(AI_SERVICE_URL, json=input_data.dict())
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as exc:
            print(f"Connection Error to {AI_SERVICE_URL}: {exc}")
            return {"response": "Error: Could not connect to AI Service. Please try again later.", "status": "ERROR"}
        except httpx.HTTPStatusError as exc:
            print(f"HTTP Error {exc.response.status_code} from {AI_SERVICE_URL}: {exc}")
            return {"response": f"Error: AI Service returned {exc.response.status_code}.", "status": "ERROR"}
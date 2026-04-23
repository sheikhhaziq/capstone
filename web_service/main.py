from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import httpx
import os
import logging
import json

app = FastAPI()
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8001/chat/")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth_service:8002")
TOKEN_COOKIE_NAME = os.getenv("TOKEN_COOKIE_NAME", "mindspace_token")
FORUM_PUBLIC_URL = os.getenv("FORUM_PUBLIC_URL", "http://localhost:8003")

class ChatInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    history_ids: list[list[int]] = Field(default_factory=list)


class LoginInput(BaseModel):
    student_id: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)


class SignupInput(BaseModel):
    student_id: str = Field(..., min_length=3, max_length=100)
    name: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=6, max_length=200)


class AdminLoginInput(BaseModel):
    admin_id: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)


class PsychologistLoginInput(BaseModel):
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=6, max_length=200)


class TokenOnlyInput(BaseModel):
    token: str = Field(..., min_length=10)


class AdminPsychologistCreateInput(BaseModel):
    email: str = Field(..., min_length=5, max_length=150)
    name: str = Field(..., min_length=1, max_length=150)
    specialization: str = Field(..., min_length=2, max_length=150)
    password: str = Field(..., min_length=6, max_length=200)


class PsychologistSlotInput(BaseModel):
    start_at: str
    end_at: str


class BookAppointmentInput(BaseModel):
    slot_id: int


class AppointmentChatInput(BaseModel):
    appointment_id: int


class AppointmentChatMessageInput(BaseModel):
    appointment_id: int
    body: str = Field(..., min_length=1, max_length=4000)


class StudentScreeningInput(BaseModel):
    score: int
    screening_type: str = Field(default="PHQ-9")


class AdminCreateResourceInput(BaseModel):
    title: str
    description: str = Field(default="")
    resource_type: str
    url: str


async def verify_student_token(token: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/auth/verify", json={"token": token})
        response.raise_for_status()
        return response.json()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return RedirectResponse(url="/login", status_code=307)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request, "forum_url": FORUM_PUBLIC_URL})


@app.get("/student/dashboard", response_class=HTMLResponse)
async def student_dashboard_page(request: Request):
    return templates.TemplateResponse(
        "student_dashboard.html",
        {"request": request, "forum_url": FORUM_PUBLIC_URL},
    )


@app.get("/psychologist/login", response_class=HTMLResponse)
async def psychologist_login_page(request: Request):
    return templates.TemplateResponse("psychologist_login.html", {"request": request})


@app.get("/psychologist/dashboard", response_class=HTMLResponse)
async def psychologist_dashboard_page(request: Request):
    return templates.TemplateResponse("psychologist_dashboard.html", {"request": request})


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request):
    return templates.TemplateResponse("admin_dashboard.html", {"request": request})


@app.get("/appointments/chat/{appointment_id}", response_class=HTMLResponse)
async def appointment_chat_page(request: Request, appointment_id: int):
    return templates.TemplateResponse("appointment_chat.html", {"request": request, "appointment_id": appointment_id})


@app.get("/resources", response_class=HTMLResponse)
async def resources_page(request: Request):
    return templates.TemplateResponse("resources.html", {"request": request, "forum_url": FORUM_PUBLIC_URL})


@app.get("/screening", response_class=HTMLResponse)
async def screening_page(request: Request):
    return templates.TemplateResponse("screening.html", {"request": request, "forum_url": FORUM_PUBLIC_URL})


@app.post("/api/login")
async def login(input_data: LoginInput):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/auth/login", json=input_data.dict())
            response.raise_for_status()
            auth_data = response.json()
            token = auth_data.get("access_token")
            if not token:
                return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Invalid auth response"})

            result = JSONResponse(
                status_code=200,
                content={
                    "status": "OK",
                    "user": auth_data.get("user", {}),
                    "expires_in_minutes": auth_data.get("expires_in_minutes", 60),
                },
            )
            result.set_cookie(
                key=TOKEN_COOKIE_NAME,
                value=token,
                httponly=True,
                secure=False,
                samesite="lax",
                max_age=int(auth_data.get("expires_in_minutes", 60)) * 60,
            )
            return result
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Invalid student credentials."})
            logger.error("HTTP error from auth service %s: %s", AUTH_SERVICE_URL, exc)
            return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Authentication service error."})
        except httpx.RequestError as exc:
            logger.error("Connection error to auth service %s: %s", AUTH_SERVICE_URL, exc)
            return JSONResponse(status_code=503, content={"status": "ERROR", "message": "Auth service unavailable."})


@app.post("/api/admin/login")
async def admin_login(input_data: AdminLoginInput):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/auth/admin/login", json=input_data.dict())
            response.raise_for_status()
            auth_data = response.json()
            token = auth_data.get("access_token")
            result = JSONResponse(status_code=200, content={"status": "OK", "user": auth_data.get("user", {})})
            result.set_cookie(
                key=TOKEN_COOKIE_NAME,
                value=token,
                httponly=True,
                secure=False,
                samesite="lax",
                max_age=int(auth_data.get("expires_in_minutes", 60)) * 60,
            )
            return result
        except httpx.HTTPStatusError:
            return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Invalid admin credentials."})
        except httpx.RequestError as exc:
            logger.error("Connection error to auth service %s: %s", AUTH_SERVICE_URL, exc)
            return JSONResponse(status_code=503, content={"status": "ERROR", "message": "Auth service unavailable."})


@app.post("/api/psychologist/login")
async def psychologist_login(input_data: PsychologistLoginInput):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/auth/psychologist/login", json=input_data.dict())
            response.raise_for_status()
            auth_data = response.json()
            token = auth_data.get("access_token")
            result = JSONResponse(status_code=200, content={"status": "OK", "user": auth_data.get("user", {})})
            result.set_cookie(
                key=TOKEN_COOKIE_NAME,
                value=token,
                httponly=True,
                secure=False,
                samesite="lax",
                max_age=int(auth_data.get("expires_in_minutes", 60)) * 60,
            )
            return result
        except httpx.HTTPStatusError:
            return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Invalid psychologist credentials."})
        except httpx.RequestError as exc:
            logger.error("Connection error to auth service %s: %s", AUTH_SERVICE_URL, exc)
            return JSONResponse(status_code=503, content={"status": "ERROR", "message": "Auth service unavailable."})


@app.post("/api/signup")
async def signup(input_data: SignupInput):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/auth/signup", json=input_data.dict())
            response.raise_for_status()
            return JSONResponse(status_code=201, content=response.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                return JSONResponse(status_code=409, content={"status": "ERROR", "message": "Student ID already exists."})
            return JSONResponse(status_code=400, content={"status": "ERROR", "message": "Could not create account."})
        except httpx.RequestError as exc:
            logger.error("Connection error to auth service %s: %s", AUTH_SERVICE_URL, exc)
            return JSONResponse(status_code=503, content={"status": "ERROR", "message": "Auth service unavailable."})


@app.get("/api/session")
async def get_session(request: Request):
    token = request.cookies.get(TOKEN_COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    try:
        claims = await verify_student_token(token)
        return JSONResponse(status_code=200, content={"status": "OK", "user": claims})
    except httpx.HTTPStatusError:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Invalid session"})
    except httpx.RequestError as exc:
        logger.error("Connection error to auth service %s: %s", AUTH_SERVICE_URL, exc)
        return JSONResponse(status_code=503, content={"status": "ERROR", "message": "Auth service unavailable"})


async def get_token_or_401(request: Request) -> str:
    token = request.cookies.get(TOKEN_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token


@app.get("/api/student/slots")
async def student_slots(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/student/slots/list", json={"token": token})
            response.raise_for_status()
            return JSONResponse(status_code=200, content=response.json())
        except httpx.HTTPStatusError as exc:
            return JSONResponse(status_code=exc.response.status_code, content={"status": "ERROR", "message": "Could not fetch slots"})
        except httpx.RequestError:
            return JSONResponse(status_code=503, content={"status": "ERROR", "message": "Auth service unavailable"})


@app.post("/api/student/appointments/book")
async def student_book_appointment(request: Request, input_data: BookAppointmentInput):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/student/appointments/book",
                json={"token": token, "slot_id": input_data.slot_id},
            )
            response.raise_for_status()
            return JSONResponse(status_code=200, content=response.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                return JSONResponse(status_code=409, content={"status": "ERROR", "message": "Slot already taken, please choose another."})
            return JSONResponse(status_code=exc.response.status_code, content={"status": "ERROR", "message": "Booking failed"})
        except httpx.RequestError:
            return JSONResponse(status_code=503, content={"status": "ERROR", "message": "Auth service unavailable"})


@app.get("/api/student/appointments")
async def student_appointments(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/student/appointments/list", json={"token": token})
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.get("/api/chat/history")
async def chat_history(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/student/ai-chat/state", json={"token": token})
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.post("/api/chat/reset")
async def reset_chat_history(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/student/ai-chat/reset", json={"token": token})
            return JSONResponse(status_code=response.status_code, content=response.json())
        except (httpx.HTTPStatusError, httpx.RequestError):
            return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Failed to reset chat history."})


@app.post("/api/psychologist/slots")
async def psychologist_create_slot(request: Request, input_data: PsychologistSlotInput):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{AUTH_SERVICE_URL}/psychologist/slots",
            json={"token": token, "start_at": input_data.start_at, "end_at": input_data.end_at},
        )
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.get("/api/psychologist/slots")
async def get_psychologist_slots(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/psychologist/slots/list", json={"token": token})
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.get("/api/psychologist/appointments")
async def psychologist_appointments(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/psychologist/appointments/list", json={"token": token})
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.post("/api/admin/psychologists")
async def admin_create_psychologist(request: Request, input_data: AdminPsychologistCreateInput):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    payload = input_data.dict()
    payload["token"] = token
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/admin/psychologists", json=payload)
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.get("/api/admin/psychologists")
async def admin_list_psychologists(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/admin/psychologists/list", json={"token": token})
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.get("/api/admin/appointments")
async def admin_appointments(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/admin/appointments/list", json={"token": token})
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.post("/api/appointments/chat/join")
async def appointment_chat_join(request: Request, input_data: AppointmentChatInput):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{AUTH_SERVICE_URL}/appointments/chat/join",
            json={"token": token, "appointment_id": input_data.appointment_id},
        )
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.post("/api/appointments/chat/messages/send")
async def appointment_chat_send(request: Request, input_data: AppointmentChatMessageInput):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{AUTH_SERVICE_URL}/appointments/chat/messages/send",
            json={"token": token, "appointment_id": input_data.appointment_id, "body": input_data.body},
        )
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.post("/api/appointments/chat/messages/list")
async def appointment_chat_list(request: Request, input_data: AppointmentChatInput):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{AUTH_SERVICE_URL}/appointments/chat/messages/list",
            json={"token": token, "appointment_id": input_data.appointment_id},
        )
        return JSONResponse(status_code=response.status_code, content=response.json())


@app.post("/api/logout")
async def logout():
    result = JSONResponse(status_code=200, content={"status": "OK"})
    result.delete_cookie(TOKEN_COOKIE_NAME)
    return result


@app.post("/api/chat")
async def chat_proxy(request: Request, input_data: ChatInput):
    token = request.cookies.get(TOKEN_COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"status": "ERROR", "response": "Please login as a student first."})

    try:
        await verify_student_token(token)
    except Exception:
        return JSONResponse(status_code=401, content={"status": "ERROR", "response": "Session expired. Please login again."})

    async def stream_generator():
        async with httpx.AsyncClient(timeout=60.0) as client:
            state_response = await client.post(f"{AUTH_SERVICE_URL}/student/ai-chat/state", json={"token": token})
            state_response.raise_for_status()
            state_data = state_response.json()
            history_ids = state_data.get("history_ids", [])

            full_response_text = ""
            final_history_ids = []
            is_crisis = False

            try:
                async with client.stream("POST", AI_SERVICE_URL, json={"text": input_data.text, "history_ids": history_ids}) as response:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        
                        if chunk.get("status") == "CRISIS_ALERT":
                            is_crisis = True
                            full_response_text = chunk.get("response", "")
                            yield line + "\n"
                            break

                        if "text" in chunk:
                            full_response_text += chunk["text"]
                            yield line + "\n"
                        
                        if "history_ids" in chunk:
                            final_history_ids = chunk["history_ids"]
                            if "full_response" in chunk:
                                full_response_text = chunk["full_response"]
                            yield line + "\n"

                # Update history after stream finishes
                if is_crisis:
                    await client.post(f"{AUTH_SERVICE_URL}/student/ai-chat/reset", json={"token": token})
                elif final_history_ids:
                    await client.post(
                        f"{AUTH_SERVICE_URL}/student/ai-chat/update",
                        json={
                            "token": token,
                            "history_ids": final_history_ids,
                            "user_text": input_data.text,
                            "assistant_text": full_response_text,
                        },
                    )
            except Exception as e:
                logger.error("Error in chat streaming: %s", e)
                yield json.dumps({"text": "\n[Error connecting to AI service]", "status": "ERROR"}) + "\n"

    return StreamingResponse(stream_generator(), media_type="application/x-ndjson")


@app.post("/api/student/screening")
async def student_screening(request: Request, input_data: StudentScreeningInput):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/student/screening",
                json={"token": token, "score": input_data.score, "screening_type": input_data.screening_type},
            )
            return JSONResponse(status_code=response.status_code, content=response.json())
        except (httpx.HTTPStatusError, httpx.RequestError):
             return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Failed to submit screening."})


@app.get("/api/student/resources")
async def get_student_resources(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/student/resources/list", json={"token": token})
            return JSONResponse(status_code=response.status_code, content=response.json())
        except (httpx.HTTPStatusError, httpx.RequestError):
             return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Failed to fetch resources."})


@app.post("/api/admin/resources")
async def create_resource(request: Request, input_data: AdminCreateResourceInput):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/admin/resources",
                json={
                    "token": token,
                    "title": input_data.title,
                    "description": input_data.description,
                    "resource_type": input_data.resource_type,
                    "url": input_data.url
                },
            )
            return JSONResponse(status_code=response.status_code, content=response.json())
        except (httpx.HTTPStatusError, httpx.RequestError):
             return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Failed to create resource."})


@app.get("/api/admin/analytics")
async def admin_analytics(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/admin/analytics", json={"token": token})
            return JSONResponse(status_code=response.status_code, content=response.json())
        except (httpx.HTTPStatusError, httpx.RequestError):
             return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Failed to fetch analytics."})


@app.get("/api/admin/users")
async def admin_users(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/admin/students/list", json={"token": token})
            return JSONResponse(status_code=response.status_code, content=response.json())
        except (httpx.HTTPStatusError, httpx.RequestError):
             return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Failed to fetch student registry."})


@app.get("/api/psychologist/analytics")
async def psychologist_analytics_gateway(request: Request):
    try:
        token = await get_token_or_401(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Not authenticated"})
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/psychologist/analytics", json={"token": token})
            return JSONResponse(status_code=response.status_code, content=response.json())
        except (httpx.HTTPStatusError, httpx.RequestError):
             return JSONResponse(status_code=502, content={"status": "ERROR", "message": "Failed to fetch psychologist analytics."})
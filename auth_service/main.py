from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
import hashlib
import hmac
import json
import os
import secrets

app = FastAPI()

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "mindspace-services")
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", 60))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://mindspace:mindspace@postgres:5432/mindspace",
)
SEED_STUDENT_ID = os.getenv("SEED_STUDENT_ID", "student001")
SEED_STUDENT_NAME = os.getenv("SEED_STUDENT_NAME", "Demo Student")
SEED_STUDENT_PASSWORD = os.getenv("SEED_STUDENT_PASSWORD", "studentpass")
SEED_ADMIN_ID = os.getenv("SEED_ADMIN_ID", "admin001")
SEED_ADMIN_NAME = os.getenv("SEED_ADMIN_NAME", "System Admin")
SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "adminpass")
SEED_PSYCHOLOGIST_EMAIL = os.getenv("SEED_PSYCHOLOGIST_EMAIL", "psych001@mindspace.local")
SEED_PSYCHOLOGIST_NAME = os.getenv("SEED_PSYCHOLOGIST_NAME", "Dr Demo")
SEED_PSYCHOLOGIST_PASSWORD = os.getenv("SEED_PSYCHOLOGIST_PASSWORD", "psychpass")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Admin(Base):
    __tablename__ = "admins"

    admin_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Psychologist(Base):
    __tablename__ = "psychologists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    specialization: Mapped[str] = mapped_column(String(150), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    __table_args__ = (
        UniqueConstraint("psychologist_id", "start_at", "end_at", name="uq_psychologist_slot_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    psychologist_id: Mapped[int] = mapped_column(ForeignKey("psychologists.id"), nullable=False, index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("availability_slots.id"), nullable=False, unique=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), nullable=False, index=True)
    psychologist_id: Mapped[int] = mapped_column(ForeignKey("psychologists.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="booked")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    sender_role: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(150), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class StudentAiChatState(Base):
    __tablename__ = "student_ai_chat_state"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), primary_key=True)
    history_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    transcript_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScreeningResult(Base):
    __tablename__ = "screening_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), index=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    screening_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def hash_password(password: str, salt_hex: str) -> str:
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    return digest.hex()


def create_password_fields(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, hash_password(password, salt)


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    computed = hash_password(password, salt_hex)
    return hmac.compare_digest(computed, expected_hash_hex)


def seed_default_student() -> None:
    with Session(engine) as session:
        existing = session.get(Student, SEED_STUDENT_ID)
        if existing:
            return
        salt, password_hash = create_password_fields(SEED_STUDENT_PASSWORD)
        session.add(
            Student(
                student_id=SEED_STUDENT_ID,
                name=SEED_STUDENT_NAME,
                password_salt=salt,
                password_hash=password_hash,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()


def seed_default_admin() -> None:
    with Session(engine) as session:
        existing = session.get(Admin, SEED_ADMIN_ID)
        if existing:
            return
        salt, password_hash = create_password_fields(SEED_ADMIN_PASSWORD)
        session.add(
            Admin(
                admin_id=SEED_ADMIN_ID,
                name=SEED_ADMIN_NAME,
                password_salt=salt,
                password_hash=password_hash,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()


def seed_default_psychologist() -> None:
    with Session(engine) as session:
        existing = session.execute(
            select(Psychologist).where(Psychologist.email == SEED_PSYCHOLOGIST_EMAIL)
        ).scalar_one_or_none()
        if existing:
            return
        salt, password_hash = create_password_fields(SEED_PSYCHOLOGIST_PASSWORD)
        session.add(
            Psychologist(
                email=SEED_PSYCHOLOGIST_EMAIL,
                name=SEED_PSYCHOLOGIST_NAME,
                specialization="General Counseling",
                password_salt=salt,
                password_hash=password_hash,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()


class LoginRequest(BaseModel):
    student_id: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)


class SignupRequest(BaseModel):
    student_id: str = Field(..., min_length=3, max_length=100)
    name: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=6, max_length=200)


class VerifyRequest(BaseModel):
    token: str = Field(..., min_length=10)


class AdminCreatePsychologistRequest(BaseModel):
    token: str = Field(..., min_length=10)
    email: str = Field(..., min_length=5, max_length=150)
    name: str = Field(..., min_length=1, max_length=150)
    specialization: str = Field(..., min_length=2, max_length=150)
    password: str = Field(..., min_length=6, max_length=200)


class TokenRequest(BaseModel):
    token: str = Field(..., min_length=10)


class PsychologistLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=6, max_length=200)


class AdminLoginRequest(BaseModel):
    admin_id: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)


class CreateSlotRequest(BaseModel):
    token: str = Field(..., min_length=10)
    start_at: datetime
    end_at: datetime


class BookAppointmentRequest(BaseModel):
    token: str = Field(..., min_length=10)
    slot_id: int


class AppointmentChatJoinRequest(BaseModel):
    token: str = Field(..., min_length=10)
    appointment_id: int


class ChatMessageCreateRequest(BaseModel):
    token: str = Field(..., min_length=10)
    appointment_id: int
    body: str = Field(..., min_length=1, max_length=4000)


class StudentAiChatUpdateRequest(BaseModel):
    token: str = Field(..., min_length=10)
    history_ids: list[list[int]] = Field(default_factory=list)
    user_text: str = Field(..., min_length=1, max_length=4000)
    assistant_text: str = Field(..., min_length=1, max_length=10000)


class AdminCreateResourceRequest(BaseModel):
    token: str = Field(..., min_length=10)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    resource_type: str = Field(..., min_length=1, max_length=50)
    url: str = Field(..., min_length=1, max_length=1000)


class StudentScreeningRequest(BaseModel):
    token: str = Field(..., min_length=10)
    score: int = Field(...)
    screening_type: str = Field(default="PHQ-9")


def create_access_token(subject: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject["sub"],
        "name": subject["name"],
        "role": subject["role"],
        "aud": JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    if "psychologist_id" in subject:
        payload["psychologist_id"] = subject["psychologist_id"]
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def require_role(claims: dict, role: str) -> None:
    if claims.get("role") != role:
        raise HTTPException(status_code=403, detail=f"Only {role} is allowed")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(engine)
    seed_default_student()
    seed_default_admin()
    seed_default_psychologist()


@app.post("/auth/login")
def login(request: LoginRequest):
    with Session(engine) as session:
        student = session.execute(
            select(Student).where(Student.student_id == request.student_id, Student.is_active.is_(True))
        ).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(request.password, student.password_salt, student.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": student.student_id, "name": student.name, "role": "student"})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": TOKEN_EXPIRE_MINUTES,
        "user": {"student_id": student.student_id, "name": student.name},
    }


@app.post("/auth/signup")
def signup(request: SignupRequest):
    normalized_id = request.student_id.strip()
    normalized_name = request.name.strip()
    if not normalized_id or not normalized_name:
        raise HTTPException(status_code=400, detail="Student ID and name are required")

    with Session(engine) as session:
        existing = session.get(Student, normalized_id)
        if existing:
            raise HTTPException(status_code=409, detail="Student ID already exists")

        salt, password_hash = create_password_fields(request.password)
        session.add(
            Student(
                student_id=normalized_id,
                name=normalized_name,
                password_salt=salt,
                password_hash=password_hash,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    return {"status": "OK", "message": "Student account created"}


@app.post("/auth/admin/login")
def admin_login(request: AdminLoginRequest):
    with Session(engine) as session:
        admin = session.execute(
            select(Admin).where(Admin.admin_id == request.admin_id, Admin.is_active.is_(True))
        ).scalar_one_or_none()
    if not admin or not verify_password(request.password, admin.password_salt, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": admin.admin_id, "name": admin.name, "role": "admin"})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": TOKEN_EXPIRE_MINUTES,
        "user": {"admin_id": admin.admin_id, "name": admin.name},
    }


@app.post("/auth/psychologist/login")
def psychologist_login(request: PsychologistLoginRequest):
    with Session(engine) as session:
        psychologist = session.execute(
            select(Psychologist).where(Psychologist.email == request.email, Psychologist.is_active.is_(True))
        ).scalar_one_or_none()
    if not psychologist or not verify_password(request.password, psychologist.password_salt, psychologist.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(
        {
            "sub": psychologist.email,
            "name": psychologist.name,
            "role": "psychologist",
            "psychologist_id": psychologist.id,
        }
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": TOKEN_EXPIRE_MINUTES,
        "user": {"psychologist_id": psychologist.id, "email": psychologist.email, "name": psychologist.name},
    }


@app.post("/auth/verify")
def verify(request: VerifyRequest):
    claims = decode_token(request.token)
    return {
        "active": True,
        "subject": claims.get("sub"),
        "name": claims.get("name"),
        "role": claims.get("role"),
        "psychologist_id": claims.get("psychologist_id"),
        "aud": claims.get("aud"),
        "exp": claims.get("exp"),
    }


@app.post("/admin/psychologists")
def admin_create_psychologist(request: AdminCreatePsychologistRequest):
    claims = decode_token(request.token)
    require_role(claims, "admin")

    with Session(engine) as session:
        existing = session.execute(select(Psychologist).where(Psychologist.email == request.email)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Psychologist already exists")
        salt, password_hash = create_password_fields(request.password)
        psychologist = Psychologist(
            email=request.email.strip().lower(),
            name=request.name.strip(),
            specialization=request.specialization.strip(),
            password_salt=salt,
            password_hash=password_hash,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(psychologist)
        session.commit()
        session.refresh(psychologist)
    return {
        "status": "OK",
        "psychologist": {
            "id": psychologist.id,
            "email": psychologist.email,
            "name": psychologist.name,
            "specialization": psychologist.specialization,
        },
    }


@app.post("/admin/psychologists/list")
def admin_list_psychologists(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "admin")
    with Session(engine) as session:
        psychologists = session.execute(select(Psychologist).where(Psychologist.is_active.is_(True))).scalars().all()
    return {
        "status": "OK",
        "psychologists": [
            {"id": p.id, "email": p.email, "name": p.name, "specialization": p.specialization} for p in psychologists
        ],
    }


@app.post("/psychologist/slots")
def psychologist_create_slot(request: CreateSlotRequest):
    claims = decode_token(request.token)
    require_role(claims, "psychologist")
    psych_id = claims.get("psychologist_id")
    if not psych_id:
        raise HTTPException(status_code=400, detail="Missing psychologist id in token")
    if request.end_at <= request.start_at:
        raise HTTPException(status_code=400, detail="Invalid slot range")

    with Session(engine) as session:
        slot = AvailabilitySlot(
            psychologist_id=int(psych_id),
            start_at=request.start_at,
            end_at=request.end_at,
            status="open",
            created_at=datetime.now(timezone.utc),
        )
        session.add(slot)
        session.commit()
        session.refresh(slot)
    return {"status": "OK", "slot": {"id": slot.id, "start_at": slot.start_at, "end_at": slot.end_at, "status": slot.status}}


@app.post("/student/slots/list")
def list_open_slots(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "student")
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        slots = session.execute(
            select(AvailabilitySlot, Psychologist)
            .join(Psychologist, Psychologist.id == AvailabilitySlot.psychologist_id)
            .where(
                AvailabilitySlot.status == "open",
                AvailabilitySlot.start_at > now,
                Psychologist.is_active.is_(True),
            )
            .order_by(AvailabilitySlot.start_at.asc())
        ).all()
    return {
        "status": "OK",
        "slots": [
            {
                "slot_id": slot.id,
                "psychologist_id": psych.id,
                "psychologist_name": psych.name,
                "specialization": psych.specialization,
                "start_at": slot.start_at,
                "end_at": slot.end_at,
            }
            for slot, psych in slots
        ],
    }


@app.post("/student/appointments/book")
def book_slot(request: BookAppointmentRequest):
    claims = decode_token(request.token)
    require_role(claims, "student")
    student_id = claims.get("sub")

    with Session(engine) as session:
        slot = session.execute(
            select(AvailabilitySlot).where(AvailabilitySlot.id == request.slot_id).with_for_update()
        ).scalar_one_or_none()
        if not slot:
            raise HTTPException(status_code=404, detail="Slot not found")
        if slot.status != "open":
            raise HTTPException(status_code=409, detail="Slot already taken")

        appointment = Appointment(
            slot_id=slot.id,
            student_id=student_id,
            psychologist_id=slot.psychologist_id,
            status="booked",
            created_at=datetime.now(timezone.utc),
        )
        slot.status = "booked"
        session.add(appointment)
        session.commit()
        session.refresh(appointment)

    return {"status": "OK", "appointment_id": appointment.id}


@app.post("/student/appointments/list")
def student_appointments(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "student")
    student_id = claims.get("sub")
    with Session(engine) as session:
        rows = session.execute(
            select(Appointment, AvailabilitySlot, Psychologist)
            .join(AvailabilitySlot, AvailabilitySlot.id == Appointment.slot_id)
            .join(Psychologist, Psychologist.id == Appointment.psychologist_id)
            .where(Appointment.student_id == student_id)
            .order_by(AvailabilitySlot.start_at.asc())
        ).all()
    return {
        "status": "OK",
        "appointments": [
            {
                "appointment_id": ap.id,
                "status": ap.status,
                "psychologist_name": psych.name,
                "start_at": slot.start_at,
                "end_at": slot.end_at,
            }
            for ap, slot, psych in rows
        ],
    }


@app.post("/psychologist/appointments/list")
def psychologist_appointments(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "psychologist")
    psych_id = int(claims.get("psychologist_id"))
    with Session(engine) as session:
        rows = session.execute(
            select(Appointment, AvailabilitySlot, Student)
            .join(AvailabilitySlot, AvailabilitySlot.id == Appointment.slot_id)
            .join(Student, Student.student_id == Appointment.student_id)
            .where(Appointment.psychologist_id == psych_id)
            .order_by(AvailabilitySlot.start_at.asc())
        ).all()
    return {
        "status": "OK",
        "appointments": [
            {
                "appointment_id": ap.id,
                "status": ap.status,
                "student_id": student.student_id,
                "student_name": student.name,
                "start_at": slot.start_at,
                "end_at": slot.end_at,
            }
            for ap, slot, student in rows
        ],
    }


@app.post("/admin/appointments/list")
def admin_appointments(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "admin")
    with Session(engine) as session:
        rows = session.execute(
            select(Appointment, AvailabilitySlot, Student, Psychologist)
            .join(AvailabilitySlot, AvailabilitySlot.id == Appointment.slot_id)
            .join(Student, Student.student_id == Appointment.student_id)
            .join(Psychologist, Psychologist.id == Appointment.psychologist_id)
            .order_by(AvailabilitySlot.start_at.asc())
        ).all()
    return {
        "status": "OK",
        "appointments": [
            {
                "appointment_id": ap.id,
                "status": ap.status,
                "student_id": student.student_id,
                "psychologist_name": psych.name,
                "start_at": slot.start_at,
                "end_at": slot.end_at,
            }
            for ap, slot, student, psych in rows
        ],
    }


def get_appointment_for_claims(session: Session, appointment_id: int, claims: dict) -> Appointment:
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    role = claims.get("role")
    if role == "student" and appointment.student_id != claims.get("sub"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if role == "psychologist" and appointment.psychologist_id != int(claims.get("psychologist_id")):
        raise HTTPException(status_code=403, detail="Not allowed")
    if role not in ("student", "psychologist", "admin"):
        raise HTTPException(status_code=403, detail="Not allowed")
    return appointment


def get_or_create_ai_chat_state(session: Session, student_id: str) -> StudentAiChatState:
    state = session.get(StudentAiChatState, student_id)
    if state:
        return state
    state = StudentAiChatState(
        student_id=student_id,
        history_ids_json="[]",
        transcript_json="[]",
        updated_at=datetime.now(timezone.utc),
    )
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


@app.post("/appointments/chat/join")
def join_appointment_chat(request: AppointmentChatJoinRequest):
    claims = decode_token(request.token)
    with Session(engine) as session:
        appointment = get_appointment_for_claims(session, request.appointment_id, claims)
        chat_session = session.execute(
            select(ChatSession).where(ChatSession.appointment_id == appointment.id)
        ).scalar_one_or_none()
        if not chat_session:
            chat_session = ChatSession(
                appointment_id=appointment.id,
                status="live",
                created_at=datetime.now(timezone.utc),
            )
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)

    return {"status": "OK", "session_id": chat_session.id, "appointment_id": appointment.id}


@app.post("/appointments/chat/messages/send")
def send_chat_message(request: ChatMessageCreateRequest):
    claims = decode_token(request.token)
    with Session(engine) as session:
        appointment = get_appointment_for_claims(session, request.appointment_id, claims)
        chat_session = session.execute(
            select(ChatSession).where(ChatSession.appointment_id == appointment.id)
        ).scalar_one_or_none()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Chat session not started")
        role = claims.get("role")
        sender_id = str(claims.get("sub"))
        message = ChatMessage(
            session_id=chat_session.id,
            sender_role=role,
            sender_id=sender_id,
            body=request.body.strip(),
            sent_at=datetime.now(timezone.utc),
        )
        session.add(message)
        session.commit()
        session.refresh(message)
    return {"status": "OK", "message_id": message.id}


@app.post("/appointments/chat/messages/list")
def list_chat_messages(request: AppointmentChatJoinRequest):
    claims = decode_token(request.token)
    with Session(engine) as session:
        appointment = get_appointment_for_claims(session, request.appointment_id, claims)
        chat_session = session.execute(
            select(ChatSession).where(ChatSession.appointment_id == appointment.id)
        ).scalar_one_or_none()
        if not chat_session:
            return {"status": "OK", "messages": []}
        messages = session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.sent_at.asc())
        ).scalars().all()
    return {
        "status": "OK",
        "session_id": chat_session.id,
        "messages": [
            {
                "id": m.id,
                "sender_role": m.sender_role,
                "sender_id": m.sender_id,
                "body": m.body,
                "sent_at": m.sent_at,
            }
            for m in messages
        ],
    }


@app.post("/student/ai-chat/state")
def student_ai_chat_state(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "student")
    student_id = claims.get("sub")
    with Session(engine) as session:
        state = get_or_create_ai_chat_state(session, student_id)
    return {
        "status": "OK",
        "history_ids": json.loads(state.history_ids_json or "[]"),
        "transcript": json.loads(state.transcript_json or "[]"),
    }


@app.post("/student/ai-chat/update")
def student_ai_chat_update(request: StudentAiChatUpdateRequest):
    claims = decode_token(request.token)
    require_role(claims, "student")
    student_id = claims.get("sub")
    with Session(engine) as session:
        state = get_or_create_ai_chat_state(session, student_id)
        transcript = json.loads(state.transcript_json or "[]")
        transcript.append({"role": "user", "text": request.user_text.strip()})
        transcript.append({"role": "assistant", "text": request.assistant_text.strip()})
        state.history_ids_json = json.dumps(request.history_ids)
        state.transcript_json = json.dumps(transcript[-200:])
        state.updated_at = datetime.now(timezone.utc)
        session.add(state)
        session.commit()
    return {"status": "OK"}


@app.post("/student/ai-chat/reset")
def student_ai_chat_reset(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "student")
    student_id = claims.get("sub")
    with Session(engine) as session:
        state = get_or_create_ai_chat_state(session, student_id)
        state.history_ids_json = "[]"
        state.transcript_json = "[]"
        state.updated_at = datetime.now(timezone.utc)
        session.add(state)
        session.commit()
    return {"status": "OK"}


@app.post("/admin/resources")
def admin_create_resource(request: AdminCreateResourceRequest):
    claims = decode_token(request.token)
    require_role(claims, "admin")
    with Session(engine) as session:
        resource = Resource(
            title=request.title.strip(),
            description=request.description.strip(),
            resource_type=request.resource_type.strip(),
            url=request.url.strip(),
            created_at=datetime.now(timezone.utc)
        )
        session.add(resource)
        session.commit()
        session.refresh(resource)
    return {"status": "OK", "resource_id": resource.id}


@app.post("/student/resources/list")
def list_resources(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "student")
    with Session(engine) as session:
        resources = session.execute(select(Resource).order_by(Resource.created_at.desc())).scalars().all()
    return {
        "status": "OK",
        "resources": [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "resource_type": r.resource_type,
                "url": r.url,
            }
            for r in resources
        ]
    }


@app.post("/student/screening")
def student_submit_screening(request: StudentScreeningRequest):
    claims = decode_token(request.token)
    require_role(claims, "student")
    student_id = claims.get("sub")
    with Session(engine) as session:
        screening = ScreeningResult(
            student_id=student_id,
            score=request.score,
            screening_type=request.screening_type,
            created_at=datetime.now(timezone.utc)
        )
        session.add(screening)
        session.commit()
    return {"status": "OK"}


@app.post("/admin/analytics")
def admin_analytics(request: TokenRequest):
    claims = decode_token(request.token)
    require_role(claims, "admin")
    with Session(engine) as session:
        total_students = session.execute(select(func.count(Student.student_id))).scalar() or 0
        total_appointments = session.execute(select(func.count(Appointment.id))).scalar() or 0
        total_psychologists = session.execute(select(func.count(Psychologist.id))).scalar() or 0
        avg_score = session.execute(select(func.avg(ScreeningResult.score))).scalar() or 0.0
    return {
        "status": "OK",
        "total_students": total_students,
        "total_appointments": total_appointments,
        "total_psychologists": total_psychologists,
        "average_screening_score": round(float(avg_score), 1)
    }

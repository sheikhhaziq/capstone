"""
Anonymous peer forum: no student login. Each browser gets a stable pseudo-random
display label via cookie (forum_peer_id). We do not store real names or auth links.
"""
from datetime import datetime, timezone
import hashlib
import os
import secrets

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

app = FastAPI(title="MindSpace Peer Forum")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://mindspace:mindspace@postgres:5432/mindspace",
)
PEER_COOKIE = os.getenv("FORUM_PEER_COOKIE", "forum_peer_id")
PEER_COOKIE_MAX_AGE = int(os.getenv("FORUM_PEER_COOKIE_MAX_AGE", 60 * 60 * 24 * 180))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
templates = Jinja2Templates(directory="templates")


class Base(DeclarativeBase):
    pass


class ForumThread(Base):
    __tablename__ = "forum_peer_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    posts: Mapped[list["ForumPost"]] = relationship(back_populates="thread")


class ForumPost(Base):
    __tablename__ = "forum_peer_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("forum_peer_threads.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    peer_label: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    author_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    thread: Mapped["ForumThread"] = relationship(back_populates="posts")


def peer_token_hash(peer_secret: str) -> str:
    return hashlib.sha256(peer_secret.encode()).hexdigest()


def peer_display_label(peer_secret: str) -> str:
    h = hashlib.sha256(peer_secret.encode()).hexdigest()
    return f"Peer #{h[:6]}"


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    r = RedirectResponse(url="/forum", status_code=307)
    return r


@app.get("/forum", response_class=HTMLResponse)
def forum_home(request: Request):
    with Session(engine) as session:
        threads = session.execute(
            select(ForumThread).order_by(ForumThread.created_at.desc()).limit(100)
        ).scalars().all()
    existing = request.cookies.get(PEER_COOKIE)
    if existing and len(existing) >= 16:
        peer_secret = existing
        resp = templates.TemplateResponse(
            "forum_index.html",
            {
                "request": request,
                "peer_label": peer_display_label(peer_secret),
                "threads": threads,
            },
        )
        return resp
    peer_secret = secrets.token_urlsafe(24)
    resp = templates.TemplateResponse(
        "forum_index.html",
        {
            "request": request,
            "peer_label": peer_display_label(peer_secret),
            "threads": threads,
        },
    )
    resp.set_cookie(
        key=PEER_COOKIE,
        value=peer_secret,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=PEER_COOKIE_MAX_AGE,
    )
    return resp


@app.post("/forum/threads")
def create_thread(
    request: Request,
    title: str = Form(..., min_length=1, max_length=200),
    body: str = Form(..., min_length=1, max_length=8000),
):
    existing = request.cookies.get(PEER_COOKIE)
    if existing and len(existing) >= 16:
        peer_secret = existing
    else:
        peer_secret = secrets.token_urlsafe(24)
    token_h = peer_token_hash(peer_secret)
    label = peer_display_label(peer_secret)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        thread = ForumThread(title=title.strip(), created_at=now)
        session.add(thread)
        session.flush()
        post = ForumPost(
            thread_id=thread.id,
            body=body.strip(),
            peer_label=label,
            author_token_hash=token_h,
            created_at=now,
        )
        session.add(post)
        session.commit()
        tid = thread.id
    redirect = RedirectResponse(url=f"/forum/threads/{tid}", status_code=303)
    if not (existing and len(existing) >= 16):
        redirect.set_cookie(
            key=PEER_COOKIE,
            value=peer_secret,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=PEER_COOKIE_MAX_AGE,
        )
    return redirect


@app.get("/forum/threads/{thread_id}", response_class=HTMLResponse)
def thread_detail(request: Request, thread_id: int):
    with Session(engine) as session:
        thread = session.get(ForumThread, thread_id)
        if not thread:
            return RedirectResponse(url="/forum", status_code=302)
        posts = session.execute(
            select(ForumPost).where(ForumPost.thread_id == thread_id).order_by(ForumPost.created_at.asc())
        ).scalars().all()
    existing = request.cookies.get(PEER_COOKIE)
    if existing and len(existing) >= 16:
        peer_secret = existing
        return templates.TemplateResponse(
            "forum_thread.html",
            {
                "request": request,
                "peer_label": peer_display_label(peer_secret),
                "thread": thread,
                "posts": posts,
            },
        )
    peer_secret = secrets.token_urlsafe(24)
    resp = templates.TemplateResponse(
        "forum_thread.html",
        {
            "request": request,
            "peer_label": peer_display_label(peer_secret),
            "thread": thread,
            "posts": posts,
        },
    )
    resp.set_cookie(
        key=PEER_COOKIE,
        value=peer_secret,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=PEER_COOKIE_MAX_AGE,
    )
    return resp


@app.post("/forum/threads/{thread_id}/reply")
def reply_thread(
    request: Request,
    thread_id: int,
    body: str = Form(..., min_length=1, max_length=8000),
):
    existing = request.cookies.get(PEER_COOKIE)
    if existing and len(existing) >= 16:
        peer_secret = existing
    else:
        peer_secret = secrets.token_urlsafe(24)
    token_h = peer_token_hash(peer_secret)
    label = peer_display_label(peer_secret)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        thread = session.get(ForumThread, thread_id)
        if not thread:
            return RedirectResponse(url="/forum", status_code=302)
        session.add(
            ForumPost(
                thread_id=thread_id,
                body=body.strip(),
                peer_label=label,
                author_token_hash=token_h,
                created_at=now,
            )
        )
        session.commit()
    redirect = RedirectResponse(url=f"/forum/threads/{thread_id}", status_code=303)
    if not (existing and len(existing) >= 16):
        redirect.set_cookie(
            key=PEER_COOKIE,
            value=peer_secret,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=PEER_COOKIE_MAX_AGE,
        )
    return redirect

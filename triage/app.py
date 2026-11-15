"""FastAPI application for the triage backend.

In production the backend binds localhost and Caddy proxies ``/api`` to it on
``triage.home.jimbarrett.dev``, which is served only to Tailscale addresses; that
is the access control.
"""

import asyncio
import contextlib
from typing import AsyncIterator, Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from content_screening.db_engine import get_session
from triage import repository, retry, routing
from triage.config import Settings, get_settings
from triage.schemas import Decision, PaperOut
from util.logging_util import setup_logger

logger = setup_logger(__name__)

API_PREFIX = "/api/triage"


def db_session() -> Iterator[Session]:
    """FastAPI dependency yielding a screening-DB session."""
    with get_session() as session:
        yield session


def route_paper_in_background(paper_id: int, settings: Settings) -> None:
    """Route a freshly-decided paper off the request path.

    Opens its own session (the request's is already closed) and re-loads the
    paper so a quick undo between the response and this task is respected:
    ``route_and_schedule`` is a no-op for a paper reverted to ``pending``.
    """
    with get_session() as session:
        paper = repository.get_paper(session, paper_id)
        if paper is None:
            return
        routing.route_and_schedule(paper, settings)


def create_app() -> FastAPI:
    settings = get_settings()

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Start the background routing retry loop, cancelling it on shutdown.
        task = (
            asyncio.create_task(retry.retry_loop(settings))
            if settings.routing_retry_enabled
            else None
        )
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="Paper Triage",
        # Namespaced so everything lives under the proxied /api/triage/* path.
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    # Only needed if the SPA is served from a different origin from the API. In
    # production Caddy serves both from one host, so this stays off.
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    router = APIRouter(prefix=API_PREFIX)

    @router.get("/queue", response_model=list[PaperOut])
    def queue(session: Session = Depends(db_session)) -> list[PaperOut]:
        papers = repository.get_pending_papers(session)
        logger.info("queue requested: %d pending papers", len(papers))
        return [PaperOut.from_orm_article(p) for p in papers]

    @router.get("/history", response_model=list[PaperOut])
    def history(session: Session = Depends(db_session)) -> list[PaperOut]:
        papers = repository.get_decided_papers(session)
        logger.info("history requested: %d decided papers", len(papers))
        return [PaperOut.from_orm_article(p) for p in papers]

    @router.get("/papers/{paper_id}", response_model=PaperOut)
    def get_paper(paper_id: int, session: Session = Depends(db_session)) -> PaperOut:
        paper = repository.get_paper(session, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")
        return PaperOut.from_orm_article(paper)

    @router.post("/papers/{paper_id}/decide", response_model=PaperOut)
    def decide(
        paper_id: int,
        decision: Decision,
        background_tasks: BackgroundTasks,
        session: Session = Depends(db_session),
    ) -> PaperOut:
        # `decision` is a query parameter rather than a JSON body. That dates from
        # the cross-origin Cloudflare setup, where an empty-body POST skipped a
        # CORS preflight that Cloudflare's edge rejected. The frontend still
        # sends it this way.
        paper = repository.get_paper(session, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")
        repository.apply_decision(paper, decision)
        # Persist the decision now so the background task (its own session) sees
        # it, then route off the request path. The response returns immediately
        # with routing pending; the retry loop covers any failure.
        session.commit()
        background_tasks.add_task(route_paper_in_background, paper_id, settings)
        logger.info("decision: paper=%d -> %s", paper_id, decision)
        return PaperOut.from_orm_article(paper)

    @router.post("/papers/{paper_id}/undo", response_model=PaperOut)
    def undo(paper_id: int, session: Session = Depends(db_session)) -> PaperOut:
        paper = repository.get_paper(session, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")
        if paper.status == "pending":
            raise HTTPException(status_code=409, detail="Nothing to undo")
        if not repository.within_undo_window(paper, settings.undo_window_seconds):
            raise HTTPException(status_code=409, detail="Undo window has expired")
        repository.clear_decision(paper)
        logger.info("undo: paper=%d -> pending", paper_id)
        return PaperOut.from_orm_article(paper)

    app.include_router(router)
    return app


app = create_app()

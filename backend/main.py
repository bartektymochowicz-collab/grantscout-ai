"""GrantScout AI – backend API (FastAPI)."""

import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field
from tavily import TavilyClient

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DB_PATH = BACKEND_DIR / "grantscout.db"

load_dotenv(PROJECT_ROOT / ".env")

# Model główny wywoływany bezpośrednio, bez sprawdzania listy modeli.
PRIMARY_MODEL = "gemini-3.8-flash"
PRIMARY_TIMEOUT_MS = 25_000
FALLBACK_TIMEOUT_MS = 30_000
# Przy 503 (lub przekroczeniu czasu) modelu głównego bierzemy pierwszy dostępny
# model, którego nazwa zawiera jeden z tych fragmentów.
FALLBACK_MARKERS = ("flash-lite", "gemma")
MENTOR_PROMPT = (
    "Jesteś mentorem hackathonowym. Na podstawie poniższych danych z internetu "
    "przygotuj zwięzłą analizę tematu po polsku: 1) Główne trendy i problemy, "
    "2) Istniejąca konkurencja, 3) Propozycja unikalnej funkcji (USP), "
    "która zachwyci jury hackathonu."
)


# ---------- Baza danych ----------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                summary TEXT,
                sources TEXT,
                created_at TIMESTAMP NOT NULL
            )
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "topic": row["topic"],
        "summary": row["summary"],
        "sources": json.loads(row["sources"]) if row["sources"] else [],
        "created_at": row["created_at"],
    }


# ---------- Aplikacja ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="GrantScout AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)


def get_tavily_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Brak klucza TAVILY_API_KEY w pliku .env",
        )
    return TavilyClient(api_key=api_key)


def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Brak klucza GEMINI_API_KEY w pliku .env",
        )
    return genai.Client(api_key=api_key)


def build_gemini_input(topic: str, sources: list[dict]) -> str:
    parts = [MENTOR_PROMPT, "", f"Temat: {topic}", "", "Dane z internetu:"]
    for i, src in enumerate(sources, start=1):
        parts.append(
            f"\n[{i}] {src.get('title') or 'Bez tytułu'}\n"
            f"URL: {src.get('url') or '-'}\n"
            f"{src.get('content') or ''}"
        )
    return "\n".join(parts)


def gemini_error(model: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"Błąd analizy Gemini ({model}): {exc}")


def call_model(client: genai.Client, model: str, contents: str, timeout_ms: int) -> str:
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            http_options=types.HttpOptions(timeout=timeout_ms)
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=502, detail=f"Gemini ({model}) zwróciło pustą odpowiedź"
        )
    return text


def find_fallback_model(client: genai.Client) -> str | None:
    """Pierwszy model z client.models.list() zawierający 'flash-lite' lub 'gemma'."""
    try:
        for model in client.models.list():
            name = (model.name or "").removeprefix("models/")
            actions = model.supported_actions or []
            if "generateContent" in actions and any(m in name for m in FALLBACK_MARKERS):
                return name
    except Exception:
        return None
    return None


def generate_with_fallback(client: genai.Client, contents: str) -> tuple[str, str]:
    """Woła PRIMARY_MODEL; przy 503/timeoucie od razu przełącza się na model zapasowy.

    Zwraca (tekst, użyty_model).
    """
    try:
        return call_model(client, PRIMARY_MODEL, contents, PRIMARY_TIMEOUT_MS), PRIMARY_MODEL
    except genai_errors.APIError as exc:
        if exc.code != 503:
            raise gemini_error(PRIMARY_MODEL, exc)
        reason = "503"
    except httpx.TimeoutException:
        reason = "timeout"
    except HTTPException:
        raise
    except Exception as exc:  # błędy sieci itp.
        raise gemini_error(PRIMARY_MODEL, exc)

    fallback = find_fallback_model(client)
    if not fallback:
        raise HTTPException(
            status_code=503,
            detail=f"Model {PRIMARY_MODEL} niedostępny ({reason}), "
            "a nie znaleziono modelu zapasowego (flash-lite / gemma)",
        )
    try:
        return call_model(client, fallback, contents, FALLBACK_TIMEOUT_MS), fallback
    except HTTPException:
        raise
    except genai_errors.APIError as exc:
        raise HTTPException(
            status_code=503 if exc.code == 503 else 502,
            detail=f"{PRIMARY_MODEL}: {reason}; model zapasowy {fallback}: {exc}",
        )
    except Exception as exc:
        raise gemini_error(fallback, exc)


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=422, detail="Pole 'topic' nie może być puste")

    tavily = get_tavily_client()
    gemini = get_gemini_client()
    query = f"Konkurencja i istniejące rozwiązania w temacie: {topic}"

    try:
        result = tavily.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_raw_content=False,
        )
    except Exception as exc:  # błędy sieci / API Tavily
        raise HTTPException(status_code=502, detail=f"Błąd wyszukiwania Tavily: {exc}")

    sources = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "content": item.get("content"),
            "score": item.get("score"),
        }
        for item in result.get("results", [])[:3]
    ]
    if not sources:
        raise HTTPException(
            status_code=404, detail="Tavily nie zwróciło wyników dla tego tematu"
        )

    summary, used_model = generate_with_fallback(
        gemini, build_gemini_input(topic, sources)
    )

    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO analyses (topic, summary, sources, created_at) VALUES (?, ?, ?, ?)",
            (topic, summary, json.dumps(sources, ensure_ascii=False), created_at),
        )
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    return {**row_to_dict(row), "model": used_model}


@app.get("/api/models")
def list_models():
    gemini = get_gemini_client()
    try:
        return [model.name for model in gemini.models.list()]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Błąd pobierania modeli: {exc}")


@app.get("/api/history")
def history():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


# ---------- Frontend (zbudowana aplikacja React) ----------
# Rejestrowane na końcu, więc trasy /api/* mają pierwszeństwo.

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    INDEX_HTML = FRONTEND_DIST / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        # Nieznane ścieżki API zwracają 404 w JSON, a nie stronę Reacta.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Nie znaleziono")

        candidate = (FRONTEND_DIST / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(FRONTEND_DIST.resolve())
        ):
            return FileResponse(candidate)
        # Pozostałe ścieżki obsługuje React (SPA fallback).
        return FileResponse(INDEX_HTML)


# ---------- Uruchomienie (np. Render: `python backend/main.py`) ----------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

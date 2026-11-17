# AGENTS.md – zasady dla agentów AI

Zasady architektury repozytorium **GrantScout AI**. Każdy agent AI pracujący nad tym kodem musi ich przestrzegać.

## Backend

- Python **3.11** + **FastAPI**; cała logika API znajduje się w `backend/main.py`.
- Zależności: `backend/requirements.txt`.
- Do modeli Gemini używaj **wyłącznie** biblioteki `google-genai` (`from google import genai`).
  **Nigdy** nie używaj przestarzałej `google-generativeai` (`import google.generativeai`) – ani w kodzie, ani w `requirements.txt`.
- Model główny: `gemini-3.8-flash` (stała `PRIMARY_MODEL`).
- Fallback: przy błędzie 503 lub przekroczeniu czasu backend przełącza się na pierwszy dostępny model, którego nazwa zawiera `flash-lite` lub `gemma` (stała `FALLBACK_MARKERS`). Nie usuwaj tego mechanizmu.
- Trasy API mają prefiks `/api/*`.

## Frontend

- **React + Vite**, folder `frontend/`.
- Na Windowsie (polityka Device Guard blokuje skrypty `.cmd`/`npx`) uruchamiaj Vite bezpośrednio przez Node:

  ```bash
  cd frontend
  node ./node_modules/vite/bin/vite.js          # serwer deweloperski
  node ./node_modules/vite/bin/vite.js build    # build produkcyjny
  ```

## Wdrożenie (Render.com, bez Dockera)

- Build Command: `./build.sh` (instaluje zależności Pythona, potem `npm install && npm run build` w `frontend/`).
- Start Command: `python backend/main.py` – serwer nasłuchuje na porcie ze zmiennej `PORT` (domyślnie `8000`).
- Aplikacja działa na **jednym porcie**: FastAPI serwuje zbudowany folder `frontend/dist` (z fallbackiem SPA na `index.html`), a `/api/*` ma pierwszeństwo.
- Ścieżki w backendzie liczymy względem `__file__`, nie katalogu roboczego.
- `build.sh` musi mieć końce linii LF (wymusza to `.gitattributes`).

## Bezpieczeństwo i pliki chronione

- **Nigdy nie modyfikuj `.gitignore`.**
- Klucze API (`GEMINI_API_KEY`, `TAVILY_API_KEY` itp.) trzymamy **wyłącznie** w pliku `.env` (lokalnie) lub w zmiennych środowiskowych serwera (Render).
  Nie wpisuj ich do kodu, plików konfiguracyjnych, README, logów ani commitów.

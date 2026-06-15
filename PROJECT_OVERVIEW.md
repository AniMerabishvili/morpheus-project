# Project Morpheus — Master Reference Document
> Bachelor's Thesis Project | Dream Analytics PWA
> Provide this file to Cursor as context at the start of every session.

---

## What This Project Does

Morpheus is a Progressive Web App (PWA) that transforms spoken dream narratives into structured psychological analytics. The user speaks in Georgian → the app records audio → backend transcribes + analyzes it → results are displayed as an interactive semantic knowledge graph (Obsidian-style).

The backend is deployed to Railway (free cloud hosting), making Morpheus accessible from **any device, anywhere** — phone, tablet, laptop — without paying for AI APIs.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React.js + Vite + TailwindCSS + Shadcn/ui |
| Graph | react-force-graph-2d (D3-force) |
| Backend | Python 3.11 + FastAPI + Uvicorn |
| Hosting | Railway (free tier — backend always online, any device) |
| Database | Supabase (PostgreSQL + pgvector) |
| Speech-to-Text | `openai-whisper` Python library (local, open-source, free) |
| Embeddings | `sentence-transformers` — `all-MiniLM-L6-v2` (local, 384 dims) |
| LLM | Google Gemini 3.5 Flash via `google-generativeai` SDK (free API) |
| Auth | Supabase Auth |

### Why this stack?
- **Zero cost** — no OpenAI billing required
- **Multi-device access** — backend lives on Railway, not your laptop
- **Same quality output** — local Whisper is identical to the paid API (same model); Gemini 3.5 Flash handles Georgian analysis and JSON extraction excellently
- **Better thesis argument** — open-source models demonstrate reproducibility and data privacy (no dream content sent to OpenAI)

---

## Folder Structure

```
morpheus-project/
├── morpheus-backend/
│   ├── venv/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Pydantic settings (env vars)
│   │   ├── database.py       # Supabase client
│   │   ├── routers/
│   │   │   ├── dreams.py     # POST /v1/dreams/process
│   │   │   └── graph.py      # GET /v1/graph/data
│   │   └── services/
│   │       ├── ai_service.py # Whisper + Gemini + RAG logic
│   │       └── graph_logic.py# Node/Link formatter
│   ├── scripts/
│   │   └── ingest_books.py   # One-time RAG ingestion CLI
│   ├── books/                # .txt academic texts
│   ├── .env                  # Secret keys (git-ignored)
│   ├── Procfile              # Railway start command
│   └── requirements.txt
│
└── morpheus-frontend/
    ├── public/
    │   ├── manifest.json     # PWA manifest
    │   └── favicon.ico
    ├── src/
    │   ├── assets/
    │   ├── components/
    │   │   ├── VoiceRecorder.jsx
    │   │   └── DreamGraph.jsx
    │   ├── hooks/
    │   ├── pages/
    │   │   ├── Dashboard.jsx
    │   │   └── MainGraph.jsx
    │   ├── App.jsx
    │   ├── index.css
    │   └── main.jsx
    ├── tailwind.config.js
    ├── vite.config.js
    └── package.json
```

---

## Data Pipeline (Step by Step)

```
1. User speaks in Georgian → Browser MediaRecorder API captures audio blob
2. Audio blob → POST to FastAPI → local openai-whisper (task="translate") → English text
3. English text → Regex/NER anonymization (strip names, dates, PII)
4. Anonymized text → Gemini 3.5 Flash (JSON mode) → { symbols: [], emotions: [] }
5. English text → sentence-transformers all-MiniLM-L6-v2 → 384-dim vector
6. Vector + metadata saved to Supabase `dreams` table
7. Dream vector → Supabase RPC `match_documents` (cosine similarity)
   → Top-k matching chunks from `knowledge_base`
8. Dream text + RAG chunks → Gemini 3.5 Flash → Georgian psychological analysis
9. dreams + keywords + dream_keywords → graph_logic.py → { nodes, links }
10. Frontend renders force-directed graph via react-force-graph-2d
```

---

## Supabase Database Schema

> NOTE: Embeddings are 384 dimensions (all-MiniLM-L6-v2), not 1536.

```sql
-- Enable Vector Extension
create extension if not exists vector;

-- 1. Dreams Master Table
create table dreams (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references auth.users(id) on delete cascade,
    title text not null,
    raw_text text not null,
    analysis text,
    embedding vector(384),
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 2. Unique Keywords Table
create table keywords (
    id uuid default gen_random_uuid() primary key,
    name text unique not null
);

-- 3. Many-to-Many Relational Graph Table
create table dream_keywords (
    dream_id uuid references dreams(id) on delete cascade,
    keyword_id uuid references keywords(id) on delete cascade,
    primary key (dream_id, keyword_id)
);

-- 4. RAG Knowledge Base Table
create table knowledge_base (
    id uuid default gen_random_uuid() primary key,
    book_title text,
    content text not null,
    embedding vector(384)
);

-- 5. RPC Vector Search Function
create or replace function match_documents (
  query_embedding vector(384),
  match_threshold float,
  match_count int
)
returns table (
  id uuid,
  book_title text,
  content text,
  similarity float
)
language sql stable
as $$
  select
    knowledge_base.id,
    knowledge_base.book_title,
    knowledge_base.content,
    1 - (knowledge_base.embedding <=> query_embedding) as similarity
  from knowledge_base
  where 1 - (knowledge_base.embedding <=> query_embedding) > match_threshold
  order by knowledge_base.embedding <=> query_embedding
  limit match_count;
$$;
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/dreams/process` | Upload audio → full pipeline → save to DB |
| `GET` | `/v1/dreams` | Return list of all dreams with metadata |
| `GET` | `/v1/graph/data` | Return `{ nodes, links }` for D3 graph |

### Graph JSON Contract
```json
{
  "nodes": [
    { "id": "dream-uuid", "label": "Dream Title", "type": "dream", "color": "#FFDE6E" },
    { "id": "keyword-uuid", "label": "Water", "type": "keyword", "color": "#8A7129" }
  ],
  "links": [
    { "source": "dream-uuid", "target": "keyword-uuid" }
  ]
}
```

---

## Environment Variables (.env)

```
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

Get your free Gemini API key at: https://aistudio.google.com/app/apikey

---

## AI Services — Implementation Reference

### Speech-to-Text (local openai-whisper)
```python
import whisper

model = whisper.load_model("small")  # "small" if CPU is slow

def transcribe_audio(audio_path: str) -> str:
    result = model.transcribe(audio_path, task="translate", language="ka")
    return result["text"]
```

### Embeddings (sentence-transformers, 384 dims)
```python
from sentence_transformers import SentenceTransformer

embedder = SentenceTransformer("all-MiniLM-L6-v2")

def generate_embedding(text: str) -> list[float]:
    return embedder.encode(text).tolist()
```

### LLM — Entity Extraction (Gemini 3.5 Flash)
```python
import google.generativeai as genai
import json

genai.configure(api_key=settings.GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-3.5-flash")

def extract_entities(text: str) -> dict:
    prompt = f"""You are a Jungian dream analyst. Extract key symbols and emotions
from this dream. Return ONLY valid JSON, no markdown, no extra text.
Schema: {{"title": "max 6 words", "symbols": [], "emotions": [], "summary": "one sentence"}}

Dream: {text}"""
    response = gemini.generate_content(prompt)
    return json.loads(response.text)
```

### LLM — Georgian Analysis (Gemini 3.5 Flash)
```python
def generate_analysis(dream_text: str, entities: dict, rag_context: str) -> str:
    prompt = f"""You are a compassionate Jungian dream analyst. Using the provided
academic context, write a warm psychological analysis in Georgian (ქართული),
150-200 words. Reference specific symbols. Never diagnose.

Dream: {dream_text}
Symbols: {entities['symbols']}
Context: {rag_context}"""
    response = gemini.generate_content(prompt)
    return response.text
```

---

## Deployment — Railway (Free, Multi-Device Access)

Railway hosts your FastAPI backend in the cloud so Morpheus works from any device.

### Setup (one time)
1. Go to https://railway.app → sign up with GitHub
2. Click **New Project → Deploy from GitHub repo** → select your repo
3. Set environment variables in Railway dashboard (same as your `.env`)
4. Railway auto-detects Python and deploys

### Required files in morpheus-backend/
**Procfile** (tells Railway how to start the server):
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**runtime.txt**:
```
python-3.11.0
```

### After deploy
Railway gives you a URL like `https://morpheus-backend-production.up.railway.app`.
Update your frontend `vite.config.js` proxy to point to this URL in production.

> Note: The free Railway tier gives 500 hours/month — enough for a thesis demo.
> Whisper and sentence-transformers run on Railway's server, so your laptop doesn't need to be on.

---

## Design System

- Background: `#0f0f0f` (near-black) — dominant, ~90% of every screen
- Dream nodes: `#FFDE6E` (main gold) — primary accent, used sparingly for focal points
- Keyword nodes: `#8A7129` (shadow gold) — secondary, recedes into the dark without disappearing
- Highlight / active states: `#E6DFA9` (pale gold) — hover, selected, and text-on-dark accents only
- Text primary: `#E6DFA9` (pale gold) — body text and headings stay in-palette
- Text muted: `#8A7129` (shadow gold) — timestamps, labels, secondary copy
- Surface: `#141414` (near-black +1) — card backgrounds, modals, sidebars
- Border: `#1f1f1f` — subtle dividers, no harsh lines
- Font: Inter or system-ui
- Theme: Dark mode only — gold on black, never reversed
- Mobile-first responsive layout

**Minimalist rationale:** The near-black background does the heavy lifting. `#FFDE6E` appears only on the most important element in any view (the primary dream node, the active CTA, the record button glow). `#8A7129` handles everything that needs to exist but not demand attention. `#E6DFA9` is reserved for readable text and hover feedback — warm but never harsh against dark backgrounds.

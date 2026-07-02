import os
import re
import shutil
import tempfile
import json
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from backend.database import (
    init_db, create_user, get_user_by_username, get_user_by_id, update_user_account,
    create_folder, get_folders, rename_folder, delete_folder,
    create_document, update_document_summaries, get_documents, delete_document, get_document_by_id,
    create_chat_session, get_chat_sessions, add_chat_message, get_chat_messages,
    add_analytic_event, get_analytics_summary, update_chat_session_title,
    rename_chat_session, delete_chat_session, get_document_graph_cache, set_document_graph_cache,
    get_document_transcript_cache, set_document_transcript_cache
)
from backend.auth import hash_password, verify_password
from backend.document_parser import build_search_chunks, extract_document_pages, get_youtube_title
from backend.es_client import init_es, index_chunks, delete_document_chunks, search_es
from backend.ml_classifier import classify_document
from backend.graph_extractor import extract_triples_gemini, build_knowledge_graph_data
from backend.rag_engine import generate_rag_response, generate_summary, ask_multimodal_video, rewrite_query_for_retrieval
import time as _time

# Initialize FastAPI app
app = FastAPI(title="DocuIntellect API", version="1.0.0")

# Add CORS Middleware
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://11.0.0.32:5173",
    "http://11.0.0.32:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database and Elasticsearch on startup
@app.on_event("startup")
def startup_event():
    init_db()
    init_es()

# --- Models ---
class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None

class FolderRename(BaseModel):
    new_name: str

class UrlUpload(BaseModel):
    url: str
    folder_id: Optional[int] = None
    display_name: Optional[str] = None

class ChatSessionCreate(BaseModel):
    title: str

class QueryPayload(BaseModel):
    message: str
    search_mode: str = "semantic" # 'semantic' or 'keyword'
    talk_target: str = "all" # 'all', 'folder:<id>', 'file:<id>'

class SearchPreviewPayload(BaseModel):
    query: str
    search_mode: str = "semantic"
    talk_target: str = "all"

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None

class ChatSessionRename(BaseModel):
    title: str

def is_greeting_or_smalltalk(message: str) -> bool:
    import difflib
    normalized = message.strip().lower()
    greetings = {
        "hi", "hii", "hello", "hey", "yo", "good morning", "good afternoon",
        "good evening", "thanks", "thank you", "ok", "okay"
    }
    questions = {"how are you", "how are you?", "who are you", "who are you?"}
    if normalized in greetings or normalized in questions:
        return True
    # Only fuzzy-match short inputs so we never accidentally swallow a real document question.
    if len(normalized) <= 20:
        candidates = greetings | questions
        close = difflib.get_close_matches(normalized, candidates, n=1, cutoff=0.8)
        if close:
            return True
    return False

def smalltalk_response(message: str) -> str:
    normalized = message.strip().lower()
    if normalized in {"thanks", "thank you"}:
        return "You're welcome. Ask me about a document whenever you're ready."
    if normalized in {"who are you", "who are you?"}:
        return "I am your DocuIntellect document assistant. I can answer normal chat questions, and when you ask about uploaded documents I use retrieval plus a Groq LLM to answer with citations."
    return "Hi. I can help you ask questions about your uploaded documents, summarize them, find matching passages, and open cited sources."

def make_chat_title(message: str) -> str:
    clean = " ".join(message.strip().split())
    if not clean:
        return "New Chat"
    return clean[:50]

def normalize_search_mode(search_mode: str) -> str:
    # "hybrid" is a valid mode in es_client.search_es; expose it here too
    return search_mode if search_mode in {"semantic", "keyword", "hybrid"} else "semantic"

_FOLLOWUP_SIGNALS = re.compile(
    r"\b(it|its|that|this|those|these|they|them|their|"
    r"he|him|his|she|her|the other|the same|previous|"
    r"earlier|above|again|also|too|what about|and the)\b",
    re.IGNORECASE,
)

def _needs_history_context(query_text: str) -> bool:
    words = query_text.strip().split()
    if len(words) <= 3:
        return True
    return bool(_FOLLOWUP_SIGNALS.search(query_text))


def build_memory_retrieval_query(query_text: str, chat_history: list) -> str:
    if not _needs_history_context(query_text):
        return query_text

    recent_user_turns = [
        " ".join((msg.get("content") or "").split())
        for msg in chat_history[-8:]
        if msg.get("role") == "user" and (msg.get("content") or "").strip()
    ]
    memory_text = " ".join(recent_user_turns[-3:])
    return f"{memory_text} {query_text}".strip() if memory_text else query_text

# --- Authentication Routes ---
@app.post("/auth/register")
def register(user: UserRegister):
    pwd_hash = hash_password(user.password)
    user_id = create_user(user.username, pwd_hash, user.email)
    if not user_id:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    add_analytic_event(user_id, "register", f"User {user.username} registered")
    return {"message": "Registration successful", "user_id": user_id, "username": user.username}

@app.post("/auth/login")
def login(user: UserLogin):
    db_user = get_user_by_username(user.username)
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
    add_analytic_event(db_user["id"], "login", f"User {user.username} logged in")
    return {"user_id": db_user["id"], "username": db_user["username"]}

@app.get("/auth/me")
def account_info(x_user_id: int = Header(...)):
    user = get_user_by_id(x_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    return user

@app.put("/auth/me")
def update_account(payload: UserUpdate, x_user_id: int = Header(...)):
    db_user = get_user_by_id(x_user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Account not found")

    password_hash = None
    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(status_code=400, detail="Current password is required")
        auth_user = get_user_by_username(db_user["username"])
        if not auth_user or not verify_password(payload.current_password, auth_user["password_hash"]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        password_hash = hash_password(payload.new_password)

    username = payload.username.strip() if payload.username is not None else None
    email = payload.email.strip() if payload.email is not None else None
    if username == "":
        raise HTTPException(status_code=400, detail="Username cannot be empty")

    updated = update_user_account(x_user_id, username=username, email=email, password_hash=password_hash)
    if updated is False:
        raise HTTPException(status_code=400, detail="Username already exists")
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")

    add_analytic_event(x_user_id, "account_update", "Updated account information")
    return updated

# --- Folder Routes ---
@app.post("/folders/create")
def make_folder(folder: FolderCreate, x_user_id: int = Header(...)):
    folder_id = create_folder(folder.name, folder.parent_id, x_user_id)
    add_analytic_event(x_user_id, "create_folder", f"Created folder {folder.name}")
    return {"message": "Folder created", "folder_id": folder_id}

@app.get("/folders/list")
def list_folders(x_user_id: int = Header(...)):
    return get_folders(x_user_id)

@app.put("/folders/{folder_id}/rename")
def rename(folder_id: int, folder: FolderRename, x_user_id: int = Header(...)):
    success = rename_folder(folder_id, folder.new_name, x_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Folder not found or unauthorized")
    add_analytic_event(x_user_id, "rename_folder", f"Renamed folder {folder_id} to {folder.new_name}")
    return {"message": "Folder renamed"}

@app.delete("/folders/{folder_id}")
def delete(folder_id: int, x_user_id: int = Header(...)):
    # delete_folder now returns (success, [doc_ids]) so we can purge ES chunks
    result = delete_folder(folder_id, x_user_id)
    success, doc_ids = result if isinstance(result, tuple) else (result, [])
    if not success:
        raise HTTPException(status_code=404, detail="Folder not found or unauthorized")
    # Clean up Elasticsearch chunks for every document that was in the folder
    for doc_id in doc_ids:
        delete_document_chunks(doc_id)
    add_analytic_event(x_user_id, "delete_folder", f"Deleted folder {folder_id}")
    return {"message": "Folder deleted successfully"}

# --- Document Routes ---
@app.post("/documents/upload")
def upload_file(
    file: UploadFile = File(...),
    folder_id: Optional[int] = Form(None),
    x_user_id: int = Header(...)
):
    storage_dir = os.environ.get("STORAGE_DIR", "storage")
    user_storage_path = os.path.join(storage_dir, str(x_user_id))
    os.makedirs(user_storage_path, exist_ok=True)
    
    file_path = os.path.join(user_storage_path, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else "txt"
    
    # 1. Parse text from document
    pages = extract_document_pages(file_path, file_extension)
    full_text = "\n".join([page["text"] for page in pages])
    
    # 2. ML category classification
    category = classify_document(full_text)
    
    # 3. Create document in SQLite
    doc_id = create_document(file.filename, file_extension, file_path, folder_id, x_user_id, category)
    
    # 4. Generate Short, Detailed and Pointers Summaries asynchronously/inline
    short_sum = generate_summary(full_text, "short")
    detailed_sum = generate_summary(full_text, "detailed")
    pointers_sum = generate_summary(full_text, "pointers")
    update_document_summaries(doc_id, short_sum, detailed_sum, pointers_sum)
    
    # 5. Index rich overlapping chunks into Elasticsearch.
    es_chunks = build_search_chunks(pages)
    index_chunks(x_user_id, folder_id, doc_id, file.filename, es_chunks)
    
    add_analytic_event(x_user_id, "upload", f"Uploaded document: {file.filename}")
    return {"message": "Document uploaded and indexed", "document_id": doc_id, "category": category, "chunks_indexed": len(es_chunks)}

@app.post("/documents/upload_url")
def upload_url(payload: UrlUpload, x_user_id: int = Header(...)):
    url = payload.url
    folder_id = payload.folder_id

    pages = extract_document_pages(url, "youtube")
    full_text = "\n".join([page["text"] for page in pages])

    category = classify_document(full_text)

    # Auto-name from the video's real title unless the user gave one
    # explicitly. This is what makes uploads show a readable title instead
    # of the raw link, with zero manual effort from the user.
    manual_name = (payload.display_name or "").strip()
    display_name = manual_name or get_youtube_title(url)

    doc_id = create_document(display_name, "youtube", url, folder_id, x_user_id, category)

    # Cache the fully-parsed pages now, while we already have them in memory.
    # This is what lets direct_scope_chunks() skip re-running parse_youtube()
    # (and therefore yt-dlp/Whisper) on every future chat query for this video.
    try:
        set_document_transcript_cache(doc_id, json.dumps(pages))
    except Exception:
        pass

    short_sum = generate_summary(full_text, "short")
    detailed_sum = generate_summary(full_text, "detailed")
    pointers_sum = generate_summary(full_text, "pointers")
    update_document_summaries(doc_id, short_sum, detailed_sum, pointers_sum)

    es_chunks = build_search_chunks(pages)
    index_chunks(x_user_id, folder_id, doc_id, display_name, es_chunks)

    add_analytic_event(x_user_id, "upload_url", f"Uploaded YouTube URL: {url} ({display_name})")
    return {"message": "YouTube transcript processed and indexed", "document_id": doc_id, "category": category, "chunks_indexed": len(es_chunks)}

@app.get("/documents/list")
def list_documents(folder_id: Optional[int] = None, x_user_id: int = Header(...)):
    return get_documents(x_user_id, folder_id)

@app.get("/documents/{doc_id}/view")
def view_document(doc_id: int, user_id: Optional[int] = None, x_user_id: Optional[int] = Header(None)):
    effective_user_id = x_user_id or user_id
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Missing user id")
    doc = get_document_by_id(doc_id, effective_user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["file_type"] == "youtube":
        return RedirectResponse(doc["file_path"])

    file_path = doc["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Stored file not found")

    filename = doc["filename"]
    media_types = {
        "pdf": "application/pdf",
        "txt": "text/plain",
        "md": "text/plain",
        "mp4": "video/mp4",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }
    media_type = media_types.get(doc["file_type"], "application/octet-stream")
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return FileResponse(file_path, media_type=media_type, filename=filename, headers=headers)

@app.delete("/documents/{doc_id}")
def remove_document(doc_id: int, x_user_id: int = Header(...)):
    # Delete from ES first
    delete_document_chunks(doc_id)
    # Delete from SQLite & local disk
    success = delete_document(doc_id, x_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or unauthorized")
    add_analytic_event(x_user_id, "delete_document", f"Deleted document {doc_id}")
    return {"message": "Document deleted"}

def parse_talk_target(talk_target: str):
    folder_id = None
    document_id = None
    if talk_target.startswith("folder:"):
        raw = talk_target.split(":", 1)[1]
        try:
            folder_id = int(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid folder id in talk_target: '{raw}'")
    elif talk_target.startswith("file:"):
        raw = talk_target.split(":", 1)[1]
        try:
            document_id = int(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document id in talk_target: '{raw}'")
    return folder_id, document_id

def _query_terms(query_text: str):
    stopwords = {
        "a", "an", "the", "is", "it", "this", "that", "i", "you", "we", "they",
        "to", "of", "in", "on", "and", "or", "but", "so", "be", "am", "are", "was",
        "were", "do", "does", "did", "has", "have", "had", "for", "with", "at", "from",
        "give", "show", "tell", "what", "which", "who", "where", "when", "how", "about",
        "document", "documents", "file", "files", "folder", "database", "company", "companies",
    }
    terms = re.findall(r"[\w][\w-]+", (query_text or "").lower(), re.UNICODE)
    return [term for term in terms if term not in stopwords and len(term) > 2]


_TOTAL_ROW_PATTERN = re.compile(r'(?i)\btotal\b')

def _local_chunk_score(query_text: str, chunk: dict) -> float:
    terms = _query_terms(query_text)

    # Filename/company-name tokens ("nexgen", "dynamics", "zephyr", "consulting"...)
    # repeat as branding/header boilerplate on nearly every page of a report.
    # Once a document is already selected, counting these again here just
    # rewards whichever chunk repeats the company's own name the most in prose
    # (e.g. the "About Us" page) — drowning out the chunk that actually answers
    # the question (e.g. the attrition table). Drop them before scoring so
    # ranking is driven by the substantive terms instead.
    filename_tokens = set(_normalize_filename_for_match(chunk.get("filename", "")).split())
    terms = [t for t in terms if t not in filename_tokens]

    text = " ".join([
        chunk.get("filename", ""),
        chunk.get("text_content", ""),
        chunk.get("table_markdown", "") or "",
        chunk.get("image_description", "") or "",
    ]).lower()
    if not terms:
        return 0.0
    unique_hits = sum(1 for term in set(terms) if term in text)
    repeated_hits = sum(text.count(term) for term in terms)
    score = unique_hits * 2.0 + repeated_hits * 0.25

    if len(terms) >= 2:
        pattern = r"\b" + r"\W+(?:\w+\W+){0,2}".join(re.escape(t) for t in terms) + r"\b"
        if re.search(pattern, text):
            score += 20.0

    if chunk.get("content_type") == "table" and re.search(r'(?i)\btotal\b', chunk.get("text_content", "")):
        score += 6.0

    return score

def _is_comparison_query(query_text: str) -> bool:
    return bool(re.search(r"\b(compare|comparison|common|similar|similarities|difference|differences|between|across|versus|vs)\b", query_text or "", re.I))


def direct_document_chunks(document_id: int, user_id: int, limit: int = 8, query_text: str = ""):
    return direct_scope_chunks(user_id, document_id=document_id, limit=limit, query_text=query_text)

def _merge_chunk_lists(primary, supplemental, limit):
    seen = set()
    merged = []
    for chunk in primary + supplemental:
        key = (
            chunk.get("document_id"),
            chunk.get("page_number"),
            (chunk.get("text_content") or "")[:150].strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(chunk)
        if len(merged) >= limit:
            break
    return merged

def _relevance_value(chunk: dict) -> float:
    # Different retrieval paths populate different score fields; pick whichever is present.
    return chunk.get("rrf_score") or chunk.get("score") or 0.0

def _normalized_relevance_value(chunk: dict, score_ranges: dict) -> float:
    matched_by = chunk.get("matched_by") or []
    group = "rrf" if chunk.get("rrf_score") else ("local" if any(m in ("direct-parse", "summary-fallback") for m in matched_by) else "es")
    raw = _relevance_value(chunk)
    lo, hi = score_ranges.get(group, (0, 1))
    if hi <= lo:
        return 1.0 if raw > 0 else 0.0
    return (raw - lo) / (hi - lo)


def _select_top_citations(chunks: list, query_text: str, limit: int = 5):
    if not chunks:
        return []

    is_comparison = _is_comparison_query(query_text)

    if is_comparison:
        by_doc = {}
        order = []
        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id not in by_doc:
                by_doc[doc_id] = []
                order.append(doc_id)
            by_doc[doc_id].append(chunk)

        for doc_id in by_doc:
            by_doc[doc_id].sort(key=_relevance_value, reverse=True)

        max_per_doc = 2
        citations = []
        seen_keys = set()
        doc_counts = {doc_id: 0 for doc_id in order}
        round_idx = 0
        while len(citations) < limit and any(doc_counts[d] < max_per_doc for d in order):
            for doc_id in order:
                if doc_counts[doc_id] >= max_per_doc:
                    continue
                doc_chunks = by_doc[doc_id]
                if round_idx >= len(doc_chunks):
                    continue
                chunk = doc_chunks[round_idx]
                key = (
                    chunk.get("document_id"),
                    chunk.get("page_number"),
                    (chunk.get("text_content") or "")[:150].strip().lower(),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                citations.append(chunk)
                doc_counts[doc_id] += 1
                if len(citations) >= limit:
                    break
            round_idx += 1
        return citations

    # Non-comparison path. Chunks merged in from search_es (BM25/cosine scores,
    # roughly 0-15) and direct_scope_chunks (local heuristic score, can run 0-30+)
    # are on different scales — comparing them raw made the 80% floor meaningless
    # whenever both sources were mixed together. Normalize each chunk's score
    # within its own source group first, so the floor is actually comparable.
    groups = {}
    for c in chunks:
        matched_by = c.get("matched_by") or []
        g = "rrf" if c.get("rrf_score") else ("local" if any(m in ("direct-parse", "summary-fallback") for m in matched_by) else "es")
        val = _relevance_value(c)
        lo, hi = groups.get(g, (val, val))
        groups[g] = (min(lo, val), max(hi, val))

    scored = [c for c in chunks if _relevance_value(c) > 0]
    if not scored:
        scored = chunks
    scored = sorted(scored, key=lambda c: _normalized_relevance_value(c, groups), reverse=True)
    floor = 0.80

    citations = []
    seen_keys = set()
    for chunk in scored:
        if _normalized_relevance_value(chunk, groups) < floor:
            continue
        key = (
            chunk.get("document_id"),
            chunk.get("page_number"),
            (chunk.get("text_content") or "")[:150].strip().lower(),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        citations.append(chunk)
        if len(citations) >= limit:
            break

    return citations

def _normalize_filename_for_match(name: str) -> str:
    base = re.sub(r"\.(pdf|docx|pptx|txt|md|mp4)$", "", (name or ""), flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", base.lower()).strip()


def _find_referenced_documents(query_text: str, user_id: int, folder_id: Optional[int], document_id: Optional[int]):
    """If the query explicitly names one or more documents by filename, resolve them
    directly so retrieval ranking and large-scope document counts can't drop one of them."""
    candidate_docs = [get_document_by_id(document_id, user_id)] if document_id is not None else get_documents(user_id, folder_id)
    candidate_docs = [d for d in candidate_docs if d]

    query_normalized = _normalize_filename_for_match(query_text)
    matches = []
    for doc in candidate_docs:
        doc_tokens = _normalize_filename_for_match(doc["filename"])
        if not doc_tokens:
            continue
        words = [w for w in doc_tokens.split() if len(w) > 3]
        if not words:
            continue
        hit_count = sum(1 for w in words if w in query_normalized)
        # len(words)//2 rounds to 0 for a single-word filename, so the old
        # max(2, ...) floor was unreachable. Require all words for short
        # names (<=3), half for longer ones.
        required = len(words) if len(words) <= 3 else max(2, len(words) // 2)
        if hit_count >= required:
            matches.append(doc)
    return matches

def _is_multi_entity_lookup(query_text: str) -> bool:
    q = (query_text or "").lower()
    value_keywords = {"salary", "salaries", "pay", "compensation", "ctc", "total", "sum", "average", "combine"}
    has_value_kw = any(w in q for w in value_keywords)
    if not has_value_kw:
        return False
    # Case-insensitive "name and name" pattern instead of relying on
    # capitalization, which typed queries often don't have.
    name_pair = re.search(r'\b([a-z]{2,})\s+and\s+([a-z]{2,})\b', q)
    return bool(name_pair)


_parsed_pages_cache = {}
_PARSE_CACHE_TTL_SECONDS = 3600  # re-parse at most once an hour per file

def _get_cached_pages(file_path: str, file_type: str):
    """Cache parsed pages per (file_path, mtime) so re-parsing a document —
    including expensive Groq Vision calls on every embedded image — only
    happens once per file version, not once per chat query. This matters most
    when Elasticsearch is offline, since direct_scope_chunks then re-parses
    every document from scratch on every single request."""
    try:
        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else None
    except OSError:
        mtime = None
    cache_key = (file_path, mtime)
    cached = _parsed_pages_cache.get(cache_key)
    if cached and (_time.time() - cached[1]) < _PARSE_CACHE_TTL_SECONDS:
        return cached[0]
    pages = extract_document_pages(file_path, file_type)
    _parsed_pages_cache[cache_key] = (pages, _time.time())
    return pages

def direct_scope_chunks(user_id: int, folder_id: Optional[int] = None, document_id: Optional[int] = None, limit: int = 12, query_text: str = "", strict: bool = False):
    docs = [get_document_by_id(document_id, user_id)] if document_id is not None else get_documents(user_id, folder_id)
    docs = [doc for doc in docs if doc]
    comparison_query = _is_comparison_query(query_text)
    multi_entity = _is_multi_entity_lookup(query_text)

    # Moved out of the loop: this never depended on `doc`, and leaving it
    # inside meant `per_doc` was undefined (NameError) whenever `docs` was empty.
    if multi_entity:
        per_doc = 5
    elif comparison_query:
        per_doc = 3
    else:
        per_doc = 2

    collected = []

    for doc in docs[:12]:
        doc_chunks = []

        file_path = doc.get("file_path")
        if doc.get("file_type") == "youtube":
            # Avoid re-running parse_youtube() on every query — it can fall back
            # to yt-dlp download + local Whisper transcription, taking minutes.
            # Use the transcript cached at upload time instead.
            pages = None
            cached_json = get_document_transcript_cache(doc["id"], user_id)
            if cached_json:
                try:
                    pages = json.loads(cached_json)
                except Exception:
                    pages = None
            if pages is None:
                # Legacy doc uploaded before this cache existed — parse once
                # and backfill so future queries hit the cache too.
                try:
                    pages = _get_cached_pages(file_path, "youtube")
                    set_document_transcript_cache(doc["id"], json.dumps(pages))
                except Exception:
                    pages = []
            try:
                parsed_chunks = build_search_chunks(pages)
                for chunk in parsed_chunks:
                    chunk["document_id"] = doc["id"]
                    chunk["filename"] = doc["filename"]
                    chunk["matched_by"] = ["direct-parse"]
                doc_chunks.extend(parsed_chunks)
            except Exception:
                pass
        elif file_path and os.path.exists(file_path):
            try:
                pages = _get_cached_pages(file_path, doc["file_type"])
                parsed_chunks = build_search_chunks(pages)
                for chunk in parsed_chunks:
                    chunk["document_id"] = doc["id"]
                    chunk["filename"] = doc["filename"]
                    chunk["matched_by"] = ["direct-parse"]
                doc_chunks.extend(parsed_chunks)
            except Exception:
                pass

        if not doc_chunks:
            summary_parts = [doc.get("summary_short"), doc.get("summary_detailed"), doc.get("summary_pointers")]
            summary_text = "\n".join(part for part in summary_parts if part)
            if summary_text:
                doc_chunks.append({
                    "document_id": doc["id"],
                    "filename": doc["filename"],
                    "page_number": 1,
                    "content_type": "summary",
                    "text_content": f"[Summary of {doc['filename']}]\n{summary_text[:1800]}",
                    "matched_by": ["summary-fallback"],
                })

        for chunk in doc_chunks:
            chunk["score"] = _local_chunk_score(query_text, chunk)

        if strict:
            doc_chunks = [chunk for chunk in doc_chunks if chunk.get("score", 0) > 0]

        doc_chunks.sort(key=lambda chunk: chunk.get("score", 0), reverse=True)

        scored = [c for c in doc_chunks if c.get("score", 0) > 0]
        unscored = [c for c in doc_chunks if c.get("score", 0) == 0]
        if scored:
            collected.extend(scored[:per_doc])
        elif unscored:
            collected.extend(unscored[:1])

    if comparison_query or multi_entity:
        by_doc = {}
        order = []
        for chunk in collected:
            doc_id = chunk.get("document_id")
            if doc_id not in by_doc:
                by_doc[doc_id] = []
                order.append(doc_id)
            by_doc[doc_id].append(chunk)
        covered = []
        max_per = per_doc
        for i in range(max_per):
            for doc_id in order:
                if i < len(by_doc[doc_id]):
                    covered.append(by_doc[doc_id][i])
                    if len(covered) >= limit:
                        break
            if len(covered) >= limit:
                break
        return covered[:limit]

    collected.sort(key=lambda chunk: chunk.get("score", 0), reverse=True)
    return collected[:limit]

@app.post("/search/preview")
def search_preview(payload: SearchPreviewPayload, x_user_id: int = Header(...)):
    folder_id, document_id = parse_talk_target(payload.talk_target)
    # Use a higher limit so per-document coverage has enough candidates to
    # guarantee results from every document in the scope, not just the top-scorer.
    preview_limit = 12 if folder_id is not None or document_id is None else 6
    chunks = search_es(
        query_text=payload.query,
        user_id=x_user_id,
        folder_id=folder_id,
        document_id=document_id,
        search_mode=normalize_search_mode(payload.search_mode),
        limit=preview_limit,
        strict=False,  # strict=True was the bug: it applied a global score floor
                       # that silently dropped valid matches from lower-scoring docs
    )
    if not chunks and document_id is not None:
        chunks = direct_document_chunks(document_id, x_user_id, limit=6)

    results = []
    seen_keys = set()
    for chunk in chunks:
        key = (
            chunk.get("document_id"),
            chunk.get("page_number"),
            (chunk.get("text_content") or "")[:150].strip().lower(),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        results.append({
            "document_id": chunk.get("document_id"),
            "filename": chunk.get("filename"),
            "page_number": chunk.get("page_number"),
            "content_type": chunk.get("content_type", "text"),
            "text_content": chunk.get("text_content", ""),
            "matched_by": chunk.get("matched_by", [chunk.get("search_type")]),
            "score": chunk.get("rrf_score", chunk.get("score", 0.0)),
        })
    mode_label = {
        "hybrid": "Hybrid RRF (KNN + BM25)",
        "semantic": "KNN semantic vector search",
        "keyword": "BM25 keyword search",
    }.get(payload.search_mode, payload.search_mode)
    return {"mode": payload.search_mode, "mode_label": mode_label, "results": results}

@app.post("/audio/transcribe")
def transcribe_audio(file: UploadFile = File(...), x_user_id: int = Header(...)):
    suffix = os.path.splitext(file.filename or "")[1] or ".webm"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_path = tmp.name

        pages = extract_document_pages(temp_path, "mp4")
        transcript = "\n".join(page.get("text", "") for page in pages).strip()
        add_analytic_event(x_user_id, "audio_transcribe", file.filename)
        return {"transcript": transcript}
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

# --- Q&A / RAG Route ---
@app.post("/chat/{session_id}/query")
def query_rag(session_id: int, payload: QueryPayload, x_user_id: int = Header(...)):
    query_text = payload.message
    search_mode = normalize_search_mode(payload.search_mode)
    talk_target = payload.talk_target
    chat_title = make_chat_title(query_text)

    folder_id, document_id = parse_talk_target(talk_target)
    chat_history = get_chat_messages(session_id)
    retrieval_query = build_memory_retrieval_query(query_text, chat_history)
    # Only rewrites for keyword/hybrid paths and longer queries — semantic
    # search already handles wording variation via embeddings.
    retrieval_query = rewrite_query_for_retrieval(retrieval_query, search_mode)

    if is_greeting_or_smalltalk(query_text):
        response_text = smalltalk_response(query_text)
        add_chat_message(session_id, "user", query_text)
        add_chat_message(session_id, "assistant", response_text)
        update_chat_session_title(session_id, chat_title)
        return {"response": response_text, "citations": [], "session_title": chat_title}
            
    # Check if target is an MP4 video file and we want deep multimodal QA
    if document_id is not None:
        doc = get_document_by_id(document_id, x_user_id)
        if doc and doc["file_type"] == "mp4" and os.path.exists(doc["file_path"]):
            # Trigger direct Groq video-transcript reasoning
            video_pages = extract_document_pages(doc["file_path"], "mp4")
            video_text = "\n".join([p["text"] for p in video_pages])
            response_text = ask_multimodal_video(doc["file_path"], query_text, video_text)
            # Save messages to chat database
            add_chat_message(session_id, "user", query_text)
            add_chat_message(session_id, "assistant", response_text)
            add_analytic_event(x_user_id, "query", query_text)
            # Update session title to first user message
            update_chat_session_title(session_id, chat_title)
            return {"response": response_text, "citations": [{"document_id": doc["id"], "filename": doc["filename"], "page_number": 1}], "session_title": chat_title}
        
    is_comparison = _is_comparison_query(query_text)
        
    chunks = search_es(
        query_text=retrieval_query,
        user_id=x_user_id,
        folder_id=folder_id,
        document_id=document_id,
        search_mode=search_mode,
        limit=12
        )
    
        # ES's KNN/BM25 favors the single best-matching chunk, which works for a
        # # one-document scope but starves folder/whole-vault scopes — and
        # # comparison/correlation questions across many files — of per-document coverage.
        # # Backstop with a direct per-document pass whenever that matters.
        
    needs_full_scope_coverage = (
        not chunks
        or document_id is None   # folder or "entire database" scope
        or is_comparison          # "compare X", "common across Y", etc.
        )
    if needs_full_scope_coverage:
        supplemental_chunks = direct_scope_chunks(
            x_user_id,
            folder_id=folder_id,
            document_id=document_id,
            limit=20,
            query_text=retrieval_query,
        )
        # Semantic ES results understand "margins" ≈ "margin" via embeddings —
        # the local fallback is pure substring matching and doesn't. Put real
        # semantic relevance first; the local pass exists only to guarantee
        # every document gets some representation, not to rank by meaning.
        if is_comparison:
            chunks = _merge_chunk_lists(chunks, supplemental_chunks, limit=20)
        else:
            chunks = _merge_chunk_lists(chunks, supplemental_chunks, limit=16)

    # If the query explicitly names specific documents (common in "compare X and Y"
    # questions), force their inclusion. This guards against the case where the
    # scope contains many documents (large folder / "entire database") and the
    # named documents' chunks get squeezed out purely by document count, even
    # after the per-document-balanced merge above.
    if is_comparison:
        referenced_docs = _find_referenced_documents(query_text, x_user_id, folder_id, document_id)
            
        if referenced_docs:
            forced_chunks = []
            for doc in referenced_docs:
                doc_chunks = direct_scope_chunks(
                    x_user_id,
                    document_id=doc["id"],
                    limit=4,
                    query_text=retrieval_query,
                    )
                forced_chunks.extend(doc_chunks)
            chunks = _merge_chunk_lists(forced_chunks, chunks, limit=24)
    
    # Generate response via RAG engine
    response_text = generate_rag_response(query_text, chunks, chat_history=chat_history)
    
    # Save messages to chat database
    add_chat_message(session_id, "user", query_text)
    add_chat_message(session_id, "assistant", response_text)
    add_analytic_event(x_user_id, "query", query_text)
    update_chat_session_title(session_id, chat_title)
    
    citation_chunks = _select_top_citations(chunks, query_text)
    citations = [
        {
            "document_id": chunk.get("document_id"),
            "filename": chunk.get("filename"),
            "page_number": chunk.get("page_number"),
            "content_type": chunk.get("content_type", "text"),
            "text_content": chunk.get("text_content", "")[:500],
            "matched_by": chunk.get("matched_by", [chunk.get("search_type")]),
        }
        for chunk in citation_chunks
    ]

    return {"response": response_text, "citations": citations, "session_title": chat_title}

# --- Summarization and Knowledge Graph ---
@app.get("/documents/{doc_id}/summaries")
def get_summaries(doc_id: int, x_user_id: int = Header(...)):
    doc = get_document_by_id(doc_id, x_user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    summaries_missing = not doc["summary_short"] or not doc["summary_detailed"] or not doc["summary_pointers"]
    if summaries_missing:
        pages = extract_document_pages(doc["file_path"], doc["file_type"])
        full_text = "\n".join([page["text"] for page in pages])
        short_sum = generate_summary(full_text, "short")
        detailed_sum = generate_summary(full_text, "detailed")
        pointers_sum = generate_summary(full_text, "pointers")
        update_document_summaries(doc_id, short_sum, detailed_sum, pointers_sum)
        doc = get_document_by_id(doc_id, x_user_id)
    return {
        "filename": doc["filename"],
        "file_type": doc["file_type"],
        "summary_short": doc["summary_short"],
        "summary_detailed": doc["summary_detailed"],
        "summary_pointers": doc["summary_pointers"],
        "view_url": f"/documents/{doc_id}/view"
    }

@app.get("/documents/{doc_id}/graph")
def get_graph(doc_id: int, x_user_id: int = Header(...), refresh: bool = False):
    doc = get_document_by_id(doc_id, x_user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Reuse the cached graph unless the caller explicitly asks to regenerate —
    # this is what stops every "Build Graph" click from re-running the LLM
    # extraction (which is non-deterministic) and producing a different graph.
    if not refresh:
        cached = get_document_graph_cache(doc_id, x_user_id)
        if cached:
            return json.loads(cached)

    file_path = doc["file_path"]
    if doc["file_type"] == "youtube":
        pages = extract_document_pages(file_path, "youtube")
        full_text = "\n".join([p["text"] for p in pages])
    elif os.path.exists(file_path):
        pages = extract_document_pages(file_path, doc["file_type"])
        full_text = "\n".join([p["text"] for p in pages])
    else:
        full_text = doc["summary_detailed"] or ""

    triples = extract_triples_gemini(full_text)
    graph_data = build_knowledge_graph_data(triples)
    result = {"graph_data": graph_data, "triples": triples}

    set_document_graph_cache(doc_id, json.dumps(result))
    return result

# --- Chat History Routes ---
@app.post("/chat/sessions")
def create_session(payload: ChatSessionCreate, x_user_id: int = Header(...)):
    sess_id = create_chat_session(payload.title, x_user_id)
    return {"session_id": sess_id, "title": payload.title}

@app.get("/chat/sessions")
def get_sessions(x_user_id: int = Header(...)):
    return get_chat_sessions(x_user_id)

@app.get("/chat/sessions/{session_id}/messages")
def get_messages(session_id: int, x_user_id: int = Header(...)):
    # In production, we'd verify session ownership
    return get_chat_messages(session_id)

@app.put("/chat/sessions/{session_id}")
def rename_session(session_id: int, payload: ChatSessionRename, x_user_id: int = Header(...)):
    title = " ".join(payload.title.strip().split())
    if not title:
        raise HTTPException(status_code=400, detail="Chat title cannot be empty")
    success = rename_chat_session(session_id, title[:80], x_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found")
    add_analytic_event(x_user_id, "rename_chat", f"Renamed chat {session_id}")
    return {"message": "Chat renamed", "title": title[:80]}

@app.delete("/chat/sessions/{session_id}")
def remove_session(session_id: int, x_user_id: int = Header(...)):
    success = delete_chat_session(session_id, x_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found")
    add_analytic_event(x_user_id, "delete_chat", f"Deleted chat {session_id}")
    return {"message": "Chat deleted"}

# --- Analytics Route ---
@app.get("/analytics/summary")
def get_analytics(x_user_id: int = Header(...)):
    return get_analytics_summary(x_user_id)


# --- Translation Route ---
class TranslatePayload(BaseModel):
    text: str
    summary_type: str = "short"  # short | detailed | pointers

@app.post("/translate/hindi")
def translate_to_hindi(payload: TranslatePayload, x_user_id: int = Header(...)):
    from backend.rag_engine import is_valid_api_key, get_client, MODEL
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="No text provided to translate.")
    if not is_valid_api_key():
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured.")
    try:
        client = get_client()
        prompt = (
            "Translate the following English summary into Hindi. "
            "Keep all proper nouns, numbers, technical terms, and named entities in their original form. "
            "Return only the translated text — no explanations, no preamble.\n\n"
            f"{payload.text}"
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
        )
        translated = response.choices[0].message.content.strip()
        add_analytic_event(x_user_id, "translate", f"Translated {payload.summary_type} summary to Hindi")
        return {"translated": translated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")





"""Repo indexer step — builds/updates the FAISS index for code retrieval.

Input: ctx.repo_path (local clone path)
Output: builds/updates the FAISS index on disk at {repo_path}/.autopr_index/

Chunking strategy:
- Chunk by function/class boundary using tree-sitter (preferred)
- Fall back to fixed 100-line windows with 20-line overlap
- Each chunk metadata: {file, symbol, start_line, end_line, content, language}

Skipped paths: node_modules/, __pycache__/, .git/, binary files, files > 500 lines

Index is cached — skip re-indexing if the index already exists and files are unchanged.
"""

import json
import os
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from agent.context import RunContext, StepError

# --- Constants ---

INDEX_DIR = ".autopr_index"
FAISS_FILE = "index.faiss"
CHUNKS_FILE = "chunks.json"
MANIFEST_FILE = "manifest.json"

EMBED_MODEL = "all-MiniLM-L6-v2"

SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".autopr_index", "venv", ".venv"}
MAX_FILE_LINES = 500
WINDOW_SIZE = 100
WINDOW_OVERLAP = 20

EXT_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".rb": "ruby",
}

# Tree-sitter queries per language (node-type names for functions and classes)
TS_QUERIES = {
    "python": "(function_definition name: (identifier) @name) @block\n(class_definition name: (identifier) @name) @block",
    "javascript": "(function_declaration name: (identifier) @name) @block\n(class_declaration name: (identifier) @name) @block",
    "typescript": "(function_declaration name: (identifier) @name) @block\n(class_declaration name: (identifier) @name) @block",
}

# --- Tree-sitter parser loader ---
# Attempt to load language-specific parsers. Falls back gracefully if
# the language packages (e.g. tree-sitter-python) are not installed.

_ts_parsers: dict = {}  # ext -> (Parser, language_name)


def _try_load_ts_parser(ext: str, package: str, lang_name: str) -> None:
    try:
        from tree_sitter import Language, Parser  # type: ignore
        mod = __import__(package)
        language = Language(mod.language())
        parser = Parser(language)
        _ts_parsers[ext] = (parser, language, lang_name)
    except Exception:
        pass


_try_load_ts_parser(".py", "tree_sitter_python", "python")
_try_load_ts_parser(".js", "tree_sitter_javascript", "javascript")
_try_load_ts_parser(".ts", "tree_sitter_typescript", "typescript")
_try_load_ts_parser(".jsx", "tree_sitter_javascript", "javascript")
_try_load_ts_parser(".tsx", "tree_sitter_typescript", "typescript")
_try_load_ts_parser(".go", "tree_sitter_go", "go")
_try_load_ts_parser(".rs", "tree_sitter_rust", "rust")
_try_load_ts_parser(".java", "tree_sitter_java", "java")


# --- Chunking ---

def _windowed_chunks(lines: list[str], rel_path: str, language: str) -> list[dict]:
    """Fixed-size sliding window fallback chunker."""
    chunks = []
    i = 0
    n = 0
    while i < len(lines):
        end = min(i + WINDOW_SIZE, len(lines))
        chunks.append({
            "file": rel_path,
            "symbol": f"window_{n}",
            "start_line": i + 1,
            "end_line": end,
            "content": "".join(lines[i:end]),
            "language": language,
        })
        n += 1
        i += WINDOW_SIZE - WINDOW_OVERLAP
    return chunks


def _ts_chunks(source: str, rel_path: str, parser, language, lang_name: str) -> Optional[list[dict]]:
    """Tree-sitter chunker. Returns None if parsing fails."""
    try:
        from tree_sitter import Query  # type: ignore
        query_str = TS_QUERIES.get(lang_name)
        if not query_str:
            return None

        tree = parser.parse(source.encode())
        query = Query(language, query_str)
        lines = source.splitlines(keepends=True)
        chunks = []
        seen_ranges: set[tuple[int, int]] = set()

        for pattern_index, capture_dict in query.matches(tree.root_node):
            block_nodes = capture_dict.get("block")
            name_nodes = capture_dict.get("name")
            if not block_nodes or not name_nodes:
                continue
            # matches returns lists when multiple captures
            block_node = block_nodes[0] if isinstance(block_nodes, list) else block_nodes
            name_node = name_nodes[0] if isinstance(name_nodes, list) else name_nodes

            start = block_node.start_point[0]  # 0-indexed row
            end = block_node.end_point[0]
            key = (start, end)
            if key in seen_ranges:
                continue
            seen_ranges.add(key)

            symbol = name_node.text.decode() if name_node.text else f"unknown_{start}"
            chunks.append({
                "file": rel_path,
                "symbol": symbol,
                "start_line": start + 1,
                "end_line": end + 1,
                "content": "".join(lines[start : end + 1]),
                "language": lang_name,
            })

        return chunks if chunks else None
    except Exception:
        return None


def _chunk_file(path: Path, rel_path: str) -> list[dict]:
    """Chunk a single file using tree-sitter or window fallback."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    lines = source.splitlines(keepends=True)
    ext = path.suffix.lower()
    language = EXT_TO_LANGUAGE.get(ext, "unknown")

    # Try tree-sitter if a parser is available for this extension
    if ext in _ts_parsers:
        parser, ts_language, lang_name = _ts_parsers[ext]
        ts_result = _ts_chunks(source, rel_path, parser, ts_language, lang_name)
        if ts_result:
            return ts_result

    return _windowed_chunks(lines, rel_path, language)


# --- File collection ---

def _is_binary(path: Path) -> bool:
    """Quick binary-file check by sniffing the first 8 KB."""
    try:
        chunk = path.read_bytes()[:8192]
        return b"\x00" in chunk
    except OSError:
        return True


def _collect_files(repo_path: Path) -> list[Path]:
    """Walk the repo and return indexable source files."""
    files = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        # Prune ignored directories in-place so os.walk skips them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in EXT_TO_LANGUAGE:
                continue
            if _is_binary(fpath):
                continue
            try:
                line_count = sum(1 for _ in fpath.open(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if line_count > MAX_FILE_LINES:
                continue
            files.append(fpath)
    return files


# --- Cache / manifest ---

def _build_manifest(files: list[Path]) -> dict[str, float]:
    """Map relative path -> mtime for freshness checks."""
    return {str(f): f.stat().st_mtime for f in files}


def _manifest_is_fresh(index_dir: Path, current: dict[str, float]) -> bool:
    """Return True if the stored manifest matches the current file mtimes
    AND the index files are present on disk."""
    # All three index files must exist
    if not all((index_dir / f).exists() for f in (MANIFEST_FILE, FAISS_FILE, CHUNKS_FILE)):
        return False
    try:
        stored: dict[str, float] = json.loads((index_dir / MANIFEST_FILE).read_text())
    except Exception:
        return False
    # File sets must match exactly
    if stored.keys() != current.keys():
        return False
    # Every file's mtime must match
    return all(stored[k] == current[k] for k in current)


# --- Main entry point ---

def run(ctx: RunContext) -> None:
    """Build or update the FAISS index for the repository.

    Creates embeddings for code chunks and stores them in a FAISS index
    at {repo_path}/.autopr_index/. Skips re-indexing if cache is fresh.

    Args:
        ctx: RunContext with ctx.repo_path set to the local clone path.

    Mutates:
        Writes index files to disk at {ctx.repo_path}/.autopr_index/

    Raises:
        StepError: If indexing fails.
    """
    repo_path = Path(ctx.repo_path).resolve()
    if not repo_path.is_dir():
        raise StepError(f"repo_indexer: repo_path does not exist: {ctx.repo_path}")

    index_dir = repo_path / INDEX_DIR
    index_dir.mkdir(exist_ok=True)

    files = _collect_files(repo_path)
    if not files:
        raise StepError(f"repo_indexer: no indexable source files found in {ctx.repo_path}")

    # Build manifest keyed by relative path so it's portable
    manifest = {str(f.relative_to(repo_path)): f.stat().st_mtime for f in files}

    if _manifest_is_fresh(index_dir, manifest):
        ctx.step_log.append(f"repo_indexer: index is fresh, skipping ({len(files)} files)")
        return

    # Chunk all files
    all_chunks: list[dict] = []
    for f in files:
        rel = str(f.relative_to(repo_path))
        all_chunks.extend(_chunk_file(f, rel))

    if not all_chunks:
        raise StepError("repo_indexer: no chunks produced — cannot build index")

    # Embed
    try:
        model = SentenceTransformer(EMBED_MODEL)
        texts = [c["content"] for c in all_chunks]
        embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        embeddings = np.array(embeddings, dtype="float32")
    except Exception as e:
        raise StepError(f"repo_indexer: embedding failed: {e}") from e

    # Build FAISS index (inner product == cosine similarity on normalized vectors)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    # Persist
    try:
        faiss.write_index(index, str(index_dir / FAISS_FILE))
        (index_dir / CHUNKS_FILE).write_text(json.dumps(all_chunks, ensure_ascii=False))
        (index_dir / MANIFEST_FILE).write_text(json.dumps(manifest))
    except Exception as e:
        raise StepError(f"repo_indexer: failed to write index to disk: {e}") from e

    ctx.step_log.append(
        f"repo_indexer: indexed {len(files)} files → {len(all_chunks)} chunks"
    )

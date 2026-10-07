"""Unified personal search across tasks, notes, documents and memories.

Each kind of content is searched the way that suits it:

- tasks and notes: ordinary full-text SQL plus structured filters (status, tags, ...).
  Plain SQL answers these reliably, so no vectors are used for them.
- documents and memories: semantic (embedding) search, since the wording of a
  question rarely matches the wording of the text that answers it.

The per-source results are put on one 0-1 relevance scale and merged. Filters can
be typed into the query itself ("proposal priority:high is:overdue"); a filter
only keeps the content types it applies to, so `priority:high` searches tasks only.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.embeddings.factory import get_embedding_provider
from app.embeddings.types import EmbeddingProvider
from app.models.document import DocumentStatus
from app.models.memory import MemoryKind
from app.models.task import TaskPriority, TaskStatus
from app.repositories.documents import DocumentRepository
from app.repositories.memories import MemoryRepository
from app.repositories.notes import NoteRepository
from app.repositories.tasks import TaskFilters, TaskRepository
from app.schemas.note import normalize_tags

# A full-text match is a precise hit (every query word is present), so it starts
# well above the semantic floor and rises with how strongly the text matches.
LEXICAL_BASE = 0.6
LEXICAL_RANK_FOR_FULL_SCORE = 0.6  # ts_rank of a single title match is about 0.6
# Below this cosine similarity a semantic neighbour is noise, not a result
SEMANTIC_MIN_SCORE = 0.2
SNIPPET_LENGTH = 300


class SearchType(StrEnum):
    TASK = "task"
    NOTE = "note"
    DOCUMENT = "document"
    MEMORY = "memory"


ALL_TYPES = frozenset(SearchType)
# Filters that only make sense for one kind of content
TAG_TYPES = frozenset({SearchType.NOTE})
TASK_FILTER_TYPES = frozenset({SearchType.TASK})
KIND_TYPES = frozenset({SearchType.MEMORY})


class EmptySearchError(AppError):
    status_code = 422
    code = "EMPTY_SEARCH"
    message = "Enter some words or a filter (like is:overdue or tag:work) to search."


_TYPE_ALIASES = {
    "task": SearchType.TASK,
    "tasks": SearchType.TASK,
    "note": SearchType.NOTE,
    "notes": SearchType.NOTE,
    "doc": SearchType.DOCUMENT,
    "docs": SearchType.DOCUMENT,
    "document": SearchType.DOCUMENT,
    "documents": SearchType.DOCUMENT,
    "memory": SearchType.MEMORY,
    "memories": SearchType.MEMORY,
}
_OPERATOR = re.compile(r"(?<!\S)(type|tag|status|priority|kind|is):(\S+)", re.IGNORECASE)


@dataclass
class ParsedQuery:
    text: str = ""
    types: set[SearchType] = field(default_factory=set)  # empty = no restriction
    tags: list[str] = field(default_factory=list)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    overdue: bool | None = None
    kind: MemoryKind | None = None

    @property
    def has_filters(self) -> bool:
        return bool(
            self.tags or self.status or self.priority or self.overdue is not None or self.kind
        )

    def candidate_types(self, requested: set[SearchType] | None = None) -> set[SearchType]:
        """The content types that can satisfy the query and every filter in it."""
        types = set(ALL_TYPES)
        if requested:
            types &= requested
        if self.types:
            types &= self.types
        if self.tags:
            types &= TAG_TYPES
        if self.status or self.priority or self.overdue is not None:
            types &= TASK_FILTER_TYPES
        if self.kind:
            types &= KIND_TYPES
        return types


def _enum_value(enum_cls: type[StrEnum], raw: str) -> StrEnum | None:
    try:
        return enum_cls(raw.lower().replace("-", "_"))
    except ValueError:
        return None


def parse_query(raw: str) -> ParsedQuery:
    """Pulls `operator:value` filters out of the query; the rest is the search text.
    An operator with an unrecognised value is left in the text, not guessed at."""
    parsed = ParsedQuery()

    def take(match: re.Match[str]) -> str:
        name, value = match.group(1).lower(), match.group(2)
        if name == "type" and (t := _TYPE_ALIASES.get(value.lower())):
            parsed.types.add(t)
        elif name == "tag":
            try:
                parsed.tags.extend(t for t in normalize_tags([value]) if t not in parsed.tags)
            except ValueError:
                return match.group(0)
        elif name == "status" and (s := _enum_value(TaskStatus, value)):
            parsed.status = s  # type: ignore[assignment]
        elif name == "priority" and (p := _enum_value(TaskPriority, value)):
            parsed.priority = p  # type: ignore[assignment]
        elif name == "kind" and (k := _enum_value(MemoryKind, value)):
            parsed.kind = k  # type: ignore[assignment]
        elif name == "is" and value.lower() == "overdue":
            parsed.overdue = True
        else:
            return match.group(0)
        return ""

    parsed.text = " ".join(_OPERATOR.sub(take, raw).split())
    return parsed


@dataclass
class SearchResult:
    type: SearchType
    id: uuid.UUID
    title: str
    snippet: str
    score: float | None  # 0-1 relevance; None when listing by filters only
    updated_at: datetime
    tags: list[str] | None = None
    status: str | None = None
    priority: str | None = None
    due_date: datetime | None = None
    kind: str | None = None


def lexical_score(rank: float | None) -> float | None:
    if rank is None:
        return None
    return LEXICAL_BASE + (1 - LEXICAL_BASE) * min(1.0, rank / LEXICAL_RANK_FOR_FULL_SCORE)


def _snippet(text: str | None) -> str:
    one_line = " ".join((text or "").split())
    return one_line if len(one_line) <= SNIPPET_LENGTH else one_line[: SNIPPET_LENGTH - 1] + "…"


class SearchService:
    """The caller must already have verified the user belongs to `workspace_id`."""

    def __init__(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        *,
        embeddings: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.embeddings = embeddings or get_embedding_provider()

    async def search(
        self,
        raw_query: str,
        *,
        types: set[SearchType] | None = None,
        limit: int = 20,
    ) -> tuple[ParsedQuery, list[SearchResult]]:
        return await self.search_parsed(parse_query(raw_query), types=types, limit=limit)

    async def search_text(
        self, text: str, *, types: set[SearchType] | None = None, limit: int = 20
    ) -> list[SearchResult]:
        """Search for words only. Unlike `search`, `tag:x`-style operators in the text are
        NOT interpreted: use this for text the user didn't type (event titles, emails)."""
        words = " ".join(text.split())
        if not words:
            return []
        _, results = await self.search_parsed(ParsedQuery(text=words), types=types, limit=limit)
        return results

    async def search_parsed(
        self,
        parsed: ParsedQuery,
        *,
        types: set[SearchType] | None = None,
        limit: int = 20,
    ) -> tuple[ParsedQuery, list[SearchResult]]:
        candidates = parsed.candidate_types(types)

        if not parsed.text and not parsed.has_filters:
            # No words and no filters: only an explicit type ("type:note") makes this a
            # meaningful request ("show me my notes"); otherwise there is nothing to do
            if not (types or parsed.types):
                raise EmptySearchError()

        results: list[SearchResult] = []
        # Sequential on purpose: one AsyncSession cannot run queries concurrently
        if SearchType.TASK in candidates:
            results += await self._tasks(parsed, limit)
        if SearchType.NOTE in candidates:
            results += await self._notes(parsed, limit)

        embedding: list[float] | None = None
        if parsed.text and candidates & {SearchType.DOCUMENT, SearchType.MEMORY}:
            [embedding] = await self.embeddings.embed([parsed.text])
        if SearchType.DOCUMENT in candidates:
            results += await self._documents(parsed, embedding, limit)
        if SearchType.MEMORY in candidates:
            results += await self._memories(parsed, embedding, limit)

        # Best relevance first; unscored (filter-only) results by recency
        results.sort(key=lambda r: (r.score if r.score is not None else 0.0, r.updated_at), reverse=True)
        return parsed, results[:limit]

    async def _tasks(self, q: ParsedQuery, limit: int) -> list[SearchResult]:
        filters = TaskFilters(status=q.status, priority=q.priority, overdue=q.overdue)
        rows = await TaskRepository(self.session).search(
            self.workspace_id, filters, query=q.text or None, limit=limit
        )
        return [
            SearchResult(
                type=SearchType.TASK,
                id=task.id,
                title=task.title,
                snippet=_snippet(task.description),
                score=lexical_score(rank),
                updated_at=task.updated_at,
                status=task.status.value,
                priority=task.priority.value,
                due_date=task.due_date,
            )
            for task, rank in rows
        ]

    async def _notes(self, q: ParsedQuery, limit: int) -> list[SearchResult]:
        rows = await NoteRepository(self.session).search(
            self.workspace_id, query=q.text or None, tags=q.tags, limit=limit
        )
        return [
            SearchResult(
                type=SearchType.NOTE,
                id=note.id,
                title=note.title,
                snippet=_snippet(preview),
                score=lexical_score(rank),
                updated_at=note.updated_at,
                tags=note.tags,
            )
            for note, preview, rank in rows
        ]

    async def _documents(
        self, q: ParsedQuery, embedding: list[float] | None, limit: int
    ) -> list[SearchResult]:
        repo = DocumentRepository(self.session)
        if embedding is None:  # "type:document" with no words: newest processed first
            documents, _ = await repo.list(
                self.workspace_id, status=DocumentStatus.READY, limit=limit, offset=0
            )
            return [
                SearchResult(
                    type=SearchType.DOCUMENT,
                    id=d.id,
                    title=d.filename,
                    snippet="",
                    score=None,
                    updated_at=d.updated_at,
                )
                for d in documents
            ]
        # Several chunks of one document may match: keep the best one per document
        hits = await repo.search_chunks(
            self.workspace_id, embedding, limit=limit * 3, min_score=SEMANTIC_MIN_SCORE
        )
        best: dict[uuid.UUID, SearchResult] = {}
        for hit in hits:  # already best-first
            if hit.document_id not in best:
                best[hit.document_id] = SearchResult(
                    type=SearchType.DOCUMENT,
                    id=hit.document_id,
                    title=hit.filename,
                    snippet=_snippet(hit.content),
                    score=hit.score,
                    updated_at=hit.document_updated_at,
                )
        return list(best.values())

    async def _memories(
        self, q: ParsedQuery, embedding: list[float] | None, limit: int
    ) -> list[SearchResult]:
        repo = MemoryRepository(self.session)
        if embedding is None:  # filter only ("kind:person"): newest first
            memories, _ = await repo.list(self.workspace_id, kind=q.kind, limit=limit, offset=0)
            pairs = [(m, None) for m in memories]
        else:
            hits = await repo.search(
                self.workspace_id,
                embedding,
                kind=q.kind,
                limit=limit,
                min_score=SEMANTIC_MIN_SCORE,
            )
            pairs = [(h.memory, h.score) for h in hits]
        return [
            SearchResult(
                type=SearchType.MEMORY,
                id=m.id,
                title=m.subject or m.kind.value.capitalize(),
                snippet=_snippet(m.content),
                score=score,
                updated_at=m.updated_at,
                kind=m.kind.value,
            )
            for m, score in pairs
        ]

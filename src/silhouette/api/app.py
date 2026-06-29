"""FastAPI surface for the Silhouette Brain.

The app is created via :func:`create_app`, which accepts an existing
:class:`MemorySystem` (used by tests and the CLI) or builds one from settings.
Legacy route aliases from v2 are preserved for backward compatibility.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from silhouette import __version__
from silhouette.api.schemas import RememberRequest, RememberResponse
from silhouette.engines import DEFAULT_ENGINES
from silhouette.errors import MemorySkipped
from silhouette.reasoning import ContextAssembler, get_synthesizer
from silhouette.security.injection import check_injection
from silhouette.storage.memory import MemorySystem

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_app(memory: MemorySystem | None = None) -> FastAPI:
    from fastapi import FastAPI, HTTPException, Query

    memory = memory or MemorySystem()
    synthesizer = get_synthesizer(memory.settings)
    assembler = ContextAssembler(memory, synthesizer)

    app = FastAPI(
        title="Silhouette Brain",
        version=__version__,
        description="4-tier cognitive memory system for AI agents.",
    )
    app.state.memory = memory

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/status")
    @app.get("/status")
    def status() -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "embedder": memory.embedder.name,
            "synthesizer": synthesizer.name,
            "stats": memory.stats(),
        }

    @app.get("/api/stats")
    def stats() -> dict[str, object]:
        return memory.stats()

    @app.post("/api/memory", response_model=RememberResponse)
    def remember(req: RememberRequest) -> RememberResponse:
        trusted_dm = req.channel in ("telegram_dm", "whatsapp_dm")
        if memory.settings.injection_guard_enabled and not trusted_dm:
            inj = check_injection(
                req.content, sender_id=req.sender_id, channel=req.channel
            )
            if inj.should_block:
                return RememberResponse(
                    status="blocked",
                    reason="injection_detected",
                    threat=inj.threat_level.value,
                )

        try:
            rec = memory.remember(
                req.content,
                importance=req.importance,
                tags=req.tags,
                source=req.source,
            )
        except MemorySkipped as exc:
            return RememberResponse(status="blocked", reason=exc.reason)

        return RememberResponse(id=rec.id, status="ok")

    @app.get("/api/memory/recent")
    @app.get("/api/recent")
    def recent(hours: float = 24.0, limit: int = Query(20, ge=1, le=200)) -> dict[str, object]:
        records = memory.recent(hours=hours, limit=limit)
        return {"count": len(records), "records": [r.model_dump() for r in records]}

    @app.get("/api/memory/semantic")
    @app.get("/api/semantic")
    def semantic(
        query: str,
        limit: int = Query(5, ge=1, le=100),
        min_score: float = 0.0,
    ) -> dict[str, object]:
        results = memory.recall(query, limit=limit, min_score=min_score)
        return {"query": query, "count": len(results), "results": [r.model_dump() for r in results]}

    @app.get("/api/context")
    @app.get("/api/memory/context")
    @app.get("/api/reasoning/context")
    def context(
        query: str,
        sem_limit: int = 5,
        rec_limit: int = 3,
        hours: float = 2.0,
        min_score: float = 0.1,
        graph: bool = False,
        tiers: bool = False,  # legacy param, ignored in v3
        synthesize: bool = False,
        token_budget: int | None = None,
        filter_heartbeats: bool = True,
    ) -> dict[str, object]:
        del tiers
        packet = assembler.assemble(
            query,
            sem_limit=sem_limit,
            rec_limit=rec_limit,
            hours=hours,
            min_score=min_score,
            include_graph=graph,
            synthesize=synthesize,
            token_budget=token_budget,
            filter_heartbeats=filter_heartbeats,
        )
        return packet.model_dump()

    @app.get("/api/entities")
    @app.get("/api/memory/entities")
    def entities(limit: int = Query(50, ge=1, le=500), type: str | None = None) -> dict[str, object]:
        ents = memory.entities(limit=limit, etype=type)
        return {"count": len(ents), "entities": [e.model_dump() for e in ents]}

    @app.get("/api/graph")
    @app.get("/api/memory/graph")
    def graph_endpoint(entity: str | None = None, limit: int = 50) -> dict[str, object]:
        rels = memory.neighbors(entity, limit=limit) if entity else memory.graph.relationships(limit)
        return {"count": len(rels), "relationships": [r.model_dump() for r in rels]}

    @app.get("/api/heartbeat")
    def heartbeat() -> dict[str, object]:
        hb = memory.settings.db_path("heartbeat_state.json")
        if not hb.exists():
            raise HTTPException(status_code=404, detail="heartbeat_state.json not found")
        return json.loads(hb.read_text(encoding="utf-8"))

    @app.post("/api/engines/{name}/run")
    def run_engine(name: str) -> dict[str, object]:
        engine = DEFAULT_ENGINES.get(name)
        if engine is None:
            raise HTTPException(status_code=404, detail=f"Unknown engine '{name}'")
        return engine.run(memory).model_dump()

    return app

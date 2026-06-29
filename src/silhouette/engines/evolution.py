"""Evolution engine — measures system health and proposes improvements.

It computes a small set of quality metrics from the live stores and turns
threshold violations into concrete, actionable proposals. Proposals are written
to ``<data_dir>/evolution_state.json`` for review; nothing is auto-applied.
"""

from __future__ import annotations

import json
import time

from silhouette.engines.base import CognitiveEngine
from silhouette.storage.memory import MemorySystem


class EvolutionEngine(CognitiveEngine):
    name = "evolution"

    def _execute(self, memory: MemorySystem) -> tuple[str, dict[str, object]]:
        episodic = memory.episodic.count()
        semantic = memory.semantic.count()
        entities = memory.graph.entity_count()
        relationships = memory.graph.relationship_count()

        coverage = (semantic / episodic) if episodic else 1.0
        density = (relationships / entities) if entities else 0.0

        metrics = {
            "episodic": episodic,
            "semantic": semantic,
            "entities": entities,
            "relationships": relationships,
            "embedding_coverage": round(coverage, 4),
            "graph_density": round(density, 4),
        }

        proposals: list[str] = []
        if coverage < 0.95:
            proposals.append("Backfill embeddings: episodic memories lack semantic vectors.")
        if entities >= 5 and density < 0.5:
            proposals.append("Run Dreamer: graph is sparse relative to entity count.")
        if episodic > 0 and entities == 0:
            proposals.append("Entity extraction produced nothing; review extractor rules.")

        report = {"updated_at": time.time(), "metrics": metrics, "proposals": proposals}
        state_path = memory.settings.db_path("evolution_state.json")
        state_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        summary = f"coverage={coverage:.2f} density={density:.2f}; {len(proposals)} proposals"
        return summary, {"metrics": metrics, "proposals": proposals, "report_path": str(state_path)}

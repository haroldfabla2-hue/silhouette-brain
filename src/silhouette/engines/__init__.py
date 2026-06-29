"""The cognitive engines that keep memory alive and improving."""

from silhouette.engines.base import CognitiveEngine
from silhouette.engines.curiosity import CuriosityEngine
from silhouette.engines.dreamer import DreamerEngine
from silhouette.engines.evolution import EvolutionEngine
from silhouette.engines.janitor import JanitorEngine

#: Default engine instances keyed by name (used by the daemon).
DEFAULT_ENGINES: dict[str, CognitiveEngine] = {
    CuriosityEngine.name: CuriosityEngine(),
    JanitorEngine.name: JanitorEngine(),
    DreamerEngine.name: DreamerEngine(),
    EvolutionEngine.name: EvolutionEngine(),
}

__all__ = [
    "DEFAULT_ENGINES",
    "CognitiveEngine",
    "CuriosityEngine",
    "DreamerEngine",
    "EvolutionEngine",
    "JanitorEngine",
]

"""Deep memory: a graph of entities and their relationships.

Two interchangeable backends behind the same ``GraphStore`` protocol:

- :class:`SqliteGraphStore` — the dependency-free default (entities and edges
  in SQLite). Works everywhere.
- :class:`Neo4jGraphStore` — production backend, used automatically when a
  Neo4j URI/password are configured and the ``neo4j`` driver is installed.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

from silhouette.config import Settings, get_settings
from silhouette.models import Entity, Relationship
from silhouette.storage.sqlite import connect, writing

logger = logging.getLogger("silhouette.storage.graph")


@runtime_checkable
class GraphStore(Protocol):
    def upsert_entity(self, entity: Entity) -> None: ...
    def add_relationship(self, rel: Relationship) -> None: ...
    def entities(self, limit: int = 50, etype: str | None = None) -> list[Entity]: ...
    def neighbors(self, name: str, limit: int = 20) -> list[Relationship]: ...
    def relationships(self, limit: int = 50) -> list[Relationship]: ...
    def entity_count(self) -> int: ...
    def relationship_count(self) -> int: ...
    def close(self) -> None: ...


class SqliteGraphStore:
    def __init__(self, path: str | Path) -> None:
        self._conn = connect(path)
        self._init_schema()

    def _init_schema(self) -> None:
        with writing(self._conn):
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    name TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    mention_count INTEGER NOT NULL,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relationships (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    PRIMARY KEY (source, target, type)
                )
                """
            )

    def upsert_entity(self, entity: Entity) -> None:
        with writing(self._conn):
            row = self._conn.execute(
                "SELECT mention_count FROM entities WHERE name = ?", (entity.name,)
            ).fetchone()
            if row:
                self._conn.execute(
                    "UPDATE entities SET mention_count = mention_count + ?, last_seen = ? "
                    "WHERE name = ?",
                    (entity.mention_count, time.time(), entity.name),
                )
            else:
                self._conn.execute(
                    "INSERT INTO entities (name, type, mention_count, first_seen, last_seen, "
                    "metadata) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        entity.name,
                        entity.type,
                        entity.mention_count,
                        entity.first_seen,
                        entity.last_seen,
                        json.dumps(entity.metadata, default=str),
                    ),
                )

    def add_relationship(self, rel: Relationship) -> None:
        with writing(self._conn):
            self._conn.execute(
                """
                INSERT INTO relationships (source, target, type, weight)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source, target, type)
                DO UPDATE SET weight = weight + excluded.weight
                """,
                (rel.source, rel.target, rel.type, rel.weight),
            )

    def entities(self, limit: int = 50, etype: str | None = None) -> list[Entity]:
        if etype:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE type = ? ORDER BY mention_count DESC LIMIT ?",
                (etype, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM entities ORDER BY mention_count DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            Entity(
                name=r["name"],
                type=r["type"],
                mention_count=r["mention_count"],
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                metadata=json.loads(r["metadata"]),
            )
            for r in rows
        ]

    def neighbors(self, name: str, limit: int = 20) -> list[Relationship]:
        rows = self._conn.execute(
            "SELECT * FROM relationships WHERE source = ? OR target = ? "
            "ORDER BY weight DESC LIMIT ?",
            (name, name, limit),
        ).fetchall()
        return [
            Relationship(source=r["source"], target=r["target"], type=r["type"], weight=r["weight"])
            for r in rows
        ]

    def relationships(self, limit: int = 50) -> list[Relationship]:
        rows = self._conn.execute(
            "SELECT * FROM relationships ORDER BY weight DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            Relationship(source=r["source"], target=r["target"], type=r["type"], weight=r["weight"])
            for r in rows
        ]

    def entity_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])

    def relationship_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0])

    def close(self) -> None:
        self._conn.close()


class Neo4jGraphStore:  # pragma: no cover - requires a live Neo4j server
    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()

    def upsert_entity(self, entity: Entity) -> None:
        with self._driver.session() as session:
            session.run(
                "MERGE (e:Entity {name: $name}) "
                "ON CREATE SET e.type=$type, e.mention_count=$mc, e.first_seen=$fs "
                "ON MATCH SET e.mention_count = coalesce(e.mention_count,0)+$mc "
                "SET e.last_seen=$ls",
                name=entity.name,
                type=entity.type,
                mc=entity.mention_count,
                fs=entity.first_seen,
                ls=entity.last_seen,
            )

    def add_relationship(self, rel: Relationship) -> None:
        with self._driver.session() as session:
            session.run(
                "MERGE (a:Entity {name:$s}) MERGE (b:Entity {name:$t}) "
                "MERGE (a)-[r:REL {type:$ty}]->(b) "
                "SET r.weight = coalesce(r.weight,0)+$w",
                s=rel.source,
                t=rel.target,
                ty=rel.type,
                w=rel.weight,
            )

    def entities(self, limit: int = 50, etype: str | None = None) -> list[Entity]:
        cypher = "MATCH (e:Entity) "
        if etype:
            cypher += "WHERE e.type = $etype "
        cypher += "RETURN e ORDER BY e.mention_count DESC LIMIT $limit"
        with self._driver.session() as session:
            result = session.run(cypher, etype=etype, limit=limit)
            return [
                Entity(
                    name=rec["e"]["name"],
                    type=rec["e"].get("type", "concept"),
                    mention_count=rec["e"].get("mention_count", 1),
                )
                for rec in result
            ]

    def neighbors(self, name: str, limit: int = 20) -> list[Relationship]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (a:Entity {name:$name})-[r:REL]-(b:Entity) "
                "RETURN a.name AS s, b.name AS t, r.type AS ty, r.weight AS w "
                "ORDER BY w DESC LIMIT $limit",
                name=name,
                limit=limit,
            )
            return [
                Relationship(source=rec["s"], target=rec["t"], type=rec["ty"], weight=rec["w"] or 1.0)
                for rec in result
            ]

    def relationships(self, limit: int = 50) -> list[Relationship]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (a:Entity)-[r:REL]->(b:Entity) "
                "RETURN a.name AS s, b.name AS t, r.type AS ty, r.weight AS w "
                "ORDER BY w DESC LIMIT $limit",
                limit=limit,
            )
            return [
                Relationship(source=rec["s"], target=rec["t"], type=rec["ty"], weight=rec["w"] or 1.0)
                for rec in result
            ]

    def entity_count(self) -> int:
        with self._driver.session() as session:
            return int(session.run("MATCH (e:Entity) RETURN count(e) AS c").single()["c"])

    def relationship_count(self) -> int:
        with self._driver.session() as session:
            return int(session.run("MATCH ()-[r:REL]->() RETURN count(r) AS c").single()["c"])

    def close(self) -> None:
        self._driver.close()


def get_graph_store(settings: Settings | None = None) -> GraphStore:
    settings = settings or get_settings()
    if settings.neo4j_uri and settings.neo4j_password:
        try:
            store = Neo4jGraphStore(
                settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password
            )
            logger.info("Deep memory backed by Neo4j at %s", settings.neo4j_uri)
            return store
        except Exception as exc:  # pragma: no cover - optional backend
            logger.warning("Neo4j unavailable (%s); using SQLite graph fallback", exc)
    return SqliteGraphStore(settings.db_path("graph.db"))

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
    def apply_episode(self, record_id: str, entities: list[tuple[str, str]],
                      edges: list[tuple[str, str, str, float]]) -> None: ...
    def retract_episode(self, record_id: str) -> None: ...
    def has_episode(self, record_id: str) -> bool: ...
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
            # Existing graphs predate lineage. Preserve their aggregates as an
            # unattributed legacy support rather than erasing them on forget.
            had_lineage = self._conn.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='entity_support'""").fetchone() is not None
            self._conn.execute("""CREATE TABLE IF NOT EXISTS entity_support (
                episode_id TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
                observed_at REAL NOT NULL, PRIMARY KEY (episode_id, name))""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS edge_support (
                episode_id TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL,
                type TEXT NOT NULL, weight REAL NOT NULL,
                PRIMARY KEY (episode_id, source, target, type))""")
            if not had_lineage:
                self._conn.execute("""INSERT INTO entity_support
                    SELECT '__legacy__', name, type, first_seen FROM entities""")
                self._conn.execute("""INSERT INTO edge_support
                    SELECT '__legacy__', source, target, type, weight FROM relationships""")

    def apply_episode(self, record_id: str, entities: list[tuple[str, str]],
                      edges: list[tuple[str, str, str, float]]) -> None:
        """Replace an episode's support idempotently, then recompute affected aggregates."""
        with writing(self._conn):
            old_entities = {r[0] for r in self._conn.execute(
                "SELECT name FROM entity_support WHERE episode_id=?", (record_id,))}
            old_edges = {(r[0], r[1], r[2]) for r in self._conn.execute(
                "SELECT source,target,type FROM edge_support WHERE episode_id=?", (record_id,))}
            self._conn.execute("DELETE FROM entity_support WHERE episode_id=?", (record_id,))
            self._conn.execute("DELETE FROM edge_support WHERE episode_id=?", (record_id,))
            now = time.time()
            for name, etype in entities:
                self._conn.execute("INSERT INTO entity_support VALUES (?,?,?,?)",
                                   (record_id, name, etype, now))
            for source, target, kind, weight in edges:
                self._conn.execute("INSERT INTO edge_support VALUES (?,?,?,?,?)",
                                   (record_id, source, target, kind, weight))
            for name in old_entities | {n for n, _ in entities}:
                count = self._conn.execute("SELECT COUNT(*) FROM entity_support WHERE name=?", (name,)).fetchone()[0]
                if count:
                    etype = self._conn.execute("SELECT type FROM entity_support WHERE name=? LIMIT 1", (name,)).fetchone()[0]
                    self._conn.execute("""INSERT INTO entities VALUES (?,?,?,?,?,?)
                        ON CONFLICT(name) DO UPDATE SET type=excluded.type,
                        mention_count=excluded.mention_count, last_seen=excluded.last_seen""",
                        (name, etype, count, now, now, '{}'))
                else:
                    self._conn.execute("DELETE FROM entities WHERE name=?", (name,))
            for source, target, kind in old_edges | {(a,b,k) for a,b,k,_ in edges}:
                weight = self._conn.execute("""SELECT SUM(weight) FROM edge_support
                    WHERE source=? AND target=? AND type=?""", (source,target,kind)).fetchone()[0]
                if weight is None:
                    self._conn.execute("DELETE FROM relationships WHERE source=? AND target=? AND type=?", (source,target,kind))
                else:
                    self._conn.execute("""INSERT INTO relationships VALUES (?,?,?,?)
                        ON CONFLICT(source,target,type) DO UPDATE SET weight=excluded.weight""",
                        (source,target,kind,weight))

    def retract_episode(self, record_id: str) -> None:
        self.apply_episode(record_id, [], [])

    def has_episode(self, record_id: str) -> bool:
        return bool(self._conn.execute(
            "SELECT 1 FROM entity_support WHERE episode_id=? LIMIT 1", (record_id,)).fetchone()
            or self._conn.execute(
            "SELECT 1 FROM edge_support WHERE episode_id=? LIMIT 1", (record_id,)).fetchone())

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

    def apply_episode(self, record_id: str, entities: list[tuple[str, str]],
                      edges: list[tuple[str, str, str, float]]) -> None:
        """Neo4j support nodes tie projections to the canonical episode ID."""
        with self._driver.session() as session:
            session.execute_write(self._replace_support, record_id, entities, edges)

    @staticmethod
    def _replace_support(tx, record_id, entities, edges):
        old = tx.run("""MATCH (s:EpisodeSupport {id:$id})
            OPTIONAL MATCH (s)-[:SUPPORTS]->(e:Entity)
            WITH s,collect(DISTINCT e.name) AS names
            OPTIONAL MATCH (s)-[r:SUPPORTS_EDGE]->()
            RETURN names, collect(DISTINCT [r.source,r.target,r.type]) AS edge_keys""",
            id=record_id).single()
        touched = set(old["names"] if old else []) | {n for n, _ in entities}
        edge_keys = {tuple(key) for key in (old["edge_keys"] if old else []) if key[0]}
        edge_keys |= {(a,b,k) for a,b,k,_ in edges}
        # Retract and replace in one Neo4j transaction: replay is idempotent.
        tx.run("MATCH (s:EpisodeSupport {id:$id}) DETACH DELETE s", id=record_id).consume()
        if entities:
            tx.run("MERGE (s:EpisodeSupport {id:$id})", id=record_id).consume()
        for name, etype in entities:
            tx.run("""MERGE (e:Entity {name:$name}) ON CREATE SET e.type=$type
                WITH e MATCH (s:EpisodeSupport {id:$id}) MERGE (s)-[:SUPPORTS]->(e)""",
                name=name, type=etype, id=record_id).consume()
        for source, target, kind, weight in edges:
            tx.run("""MATCH (a:Entity {name:$source}), (b:Entity {name:$target}),
                (s:EpisodeSupport {id:$id})
                MERGE (s)-[r:SUPPORTS_EDGE {source:$source,target:$target,type:$kind}]->(a)
                SET r.weight=$weight""", source=source, target=target,
                kind=kind, weight=weight, id=record_id).consume()
        for source, target, kind in edge_keys:
            row = tx.run("""MATCH (s:EpisodeSupport)-[r:SUPPORTS_EDGE
                {source:$source,target:$target,type:$kind}]->()
                RETURN sum(r.weight) AS weight""",
                source=source,target=target,kind=kind).single()
            weight = row["weight"] if row else None
            if weight is None:
                tx.run("""MATCH (a:Entity {name:$source})-[r:REL {type:$kind}]->
                    (b:Entity {name:$target}) DELETE r""",
                    source=source,target=target,kind=kind).consume()
            else:
                tx.run("""MATCH (a:Entity {name:$source}), (b:Entity {name:$target})
                    MERGE (a)-[r:REL {type:$kind}]->(b) SET r.weight=$weight""",
                    source=source,target=target,kind=kind,weight=weight).consume()
        # Only nodes touched by this episode are eligible for removal. Existing
        # non-projection edges/nodes are left intact.
        for name in touched:
            row = tx.run("""MATCH (e:Entity {name:$name})
                OPTIONAL MATCH (s:EpisodeSupport)-[:SUPPORTS]->(e)
                RETURN count(DISTINCT s) AS n""", name=name).single()
            if row and row["n"]:
                tx.run("MATCH (e:Entity {name:$name}) SET e.mention_count=$n",
                       name=name, n=row["n"]).consume()
            else:
                tx.run("""MATCH (e:Entity {name:$name})
                    WHERE NOT (e)--(:EpisodeSupport) AND NOT (e)-[:REL]-()
                    DETACH DELETE e""", name=name).consume()

    def retract_episode(self, record_id: str) -> None:
        self.apply_episode(record_id, [], [])

    def has_episode(self, record_id: str) -> bool:
        with self._driver.session() as session:
            return bool(session.run("MATCH (s:EpisodeSupport {id:$id}) RETURN s LIMIT 1",
                                    id=record_id).single())

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

# Multi-Tenant Architecture — Silhouette Brain

**Status:** Implemented (PR `feat/multi-tenant-brain`)
**Date:** 2026-07-30
**Author:** Silhouette (CEO) + Alberto Farah

## Overview

The Silhouette Brain API supports multiple isolated client tenants (e.g. `alfonso`, `isabella`) plus a system tenant (`default`) for internal memories (curiosity, janitor, dreamer).

All API endpoints now require an `owner_id` parameter that:
1. Must be in the whitelist (`config/clients.json`)
2. Is used to filter all data access
3. Determines the `view_scope` (which owners' data this client can see)

## Architecture

### 3 Layers of Isolation

1. **Schema layer** — `owner_id` column in SQLite tables + `Client` nodes + `:BELONGS_TO` relations in Neo4j
2. **API layer** — validation in every handler (GET/POST) via `_validate_owner_id()`
3. **Query layer** — `WHERE owner_id IN (view_scope)` in every SQLite query, `MATCH ... Client` in every Neo4j query

### Tenant Configuration

**File:** `config/clients.json`

```json
{
  "default_owner": "default",
  "clients": {
    "default": {
      "name": "System (internal)",
      "is_system": true,
      "view_scope": ["default"]
    },
    "alfonso": {
      "name": "Alfonso Grados",
      "view_scope": ["alfonso"]
    },
    "isabella": {
      "name": "Isabella Escudero",
      "view_scope": ["isabella", "alfonso"]
    }
  }
}
```

### View Scope

Each client has a `view_scope` array that determines which owners' data they can see:

| Tenant | view_scope | Sees |
|--------|------------|------|
| `default` | `["default"]` | Only system memories |
| `alfonso` | `["alfonso"]` | Only Alfonso's data |
| `isabella` | `["isabella", "alfonso"]` | Isabella + Alfonso's data |

## Usage

### API calls

All endpoints now require `?owner_id=xxx` (GET) or `"owner_id": "xxx"` (POST):

```bash
# Alfonso queries memory
curl 'http://localhost:9876/api/memory?query=proyecto&owner_id=alfonso'

# Isabella queries memory (sees her own + Alfonso's)
curl 'http://localhost:9876/api/memory?query=proyecto&owner_id=isabella'

# Default tenant (system)
curl 'http://localhost:9876/api/memory?query=curiosity&owner_id=default'

# Missing owner_id → 403
curl 'http://localhost:9876/api/memory?query=test'
# {"error": "owner_id required for multi-tenant brain", ...}

# Unknown owner_id → 403
curl 'http://localhost:9876/api/memory?query=test&owner_id=hacker'
# {"error": "Unknown owner_id: hacker"}
```

### Public endpoints (no owner_id required)

These are system-level metadata:
- `/api/status` — service info
- `/api/heartbeat` — health check
- `/api/soul` — SOUL.md content

## Migration

### For new deployments

Run the migration script on first deploy:

```bash
cd /root/silhouette-brain
python3 scripts/migrate_owner_id.py --dry-run  # preview
python3 scripts/migrate_owner_id.py             # apply
```

This:
1. Adds `owner_id` column to `memory_nodes` (and `conversations` if it exists)
2. Backfills `NULL`/`''` to `'default'`
3. Creates `idx_{table}_owner_ts` composite index

### For Neo4j

Run once after deploy:

```bash
cd /root/silhouette-brain/src/core
python3 sync_to_graph.py migrate
```

This:
1. Creates Client nodes for `default`, `alfonso`, `isabella`
2. Attaches orphan Semantic nodes to Client `default`

## Adding a new tenant

1. Edit `config/clients.json`, add client to `clients` object:

```json
{
  "newclient": {
    "name": "New Client Name",
    "industry": "...",
    "view_scope": ["newclient"],
    "telegram_bot": "@newclient_bot"
  }
}
```

2. Reload config (no restart needed if cached invalidation is added; otherwise restart Brain API)

3. Optionally seed Client node in Neo4j:

```bash
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:17687', auth=('neo4j','silhouette2035'))
with d.session() as s:
    s.run('MERGE (c:Client {id: \"newclient\"}) SET c.name = \"New Client Name\"')
d.close()
"
```

4. Tests should still pass:

```bash
python3 tests/test_multi_tenant.py
```

## Security Considerations

- **Strict mode** is enabled by default (`reject_unknown: true`)
- All rejections are logged via `LOG.warning()`
- Cache keys include `owner_id` to prevent cache leak between tenants
- Client IDs are case-sensitive (whitelist exact match)
- The `default` tenant is for system use only; client tenants should NOT use it

## Testing

Run isolation tests:

```bash
cd /root/silhouette-brain
python3 tests/test_multi_tenant.py
```

Expected output:
```
======================================================================
MULTI-TENANT ISOLATION TESTS — Silhouette Brain
======================================================================

  ✅ PASS: valid_owners
  ✅ PASS: invalid_owners
  ✅ PASS: view_scope_default
  ✅ PASS: view_scope_alfonso
  ✅ PASS: view_scope_isabella
  ✅ PASS: list_clients
  ✅ PASS: context_requires_owner
  ✅ PASS: recent_requires_owner
  ✅ PASS: alfonso_no_isabella
  ✅ PASS: isabella_no_default
  ✅ PASS: alfonso_sees_own

RESULTS: 11 passed, 0 failed, 0 skipped
```

## Files changed

| File | Change |
|------|--------|
| `config/clients.json` | NEW — tenant whitelist |
| `src/core/clients_config.py` | NEW — whitelist helpers |
| `src/core/agent_memory_readonly.py` | MODIFIED — owner_id parameter, view_scope filter |
| `src/core/sync_to_graph.py` | MODIFIED — Client nodes + BELONGS_TO, migration helper |
| `src/api/enhanced_memory_api.py` | MODIFIED — validation in GET/POST handlers |
| `scripts/migrate_owner_id.py` | NEW — SQLite migration tool |
| `tests/test_multi_tenant.py` | NEW — 11 isolation tests |
| `docs/MULTI_TENANT.md` | NEW — this file |

## Rollback

If issues arise, revert the branch:

```bash
git checkout main
git branch -D feat/multi-tenant-brain
```

The migration is also reversible:

```sql
-- Remove owner_id assignments (keep column for now)
UPDATE memory_nodes SET owner_id = 'default' WHERE owner_id != 'default';
```

## Future work

- [ ] Auth header (`Authorization: Bearer <token>`) instead of query param
- [ ] Per-tenant rate limiting
- [ ] Per-tenant embeddings namespace
- [ ] Tenant-level config (max memory size, retention policy)
- [ ] Audit log of cross-tenant access attempts

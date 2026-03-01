#!/usr/bin/env bash
# =============================================================================
# deploy_plugin.sh — Sync silhouette-brain improvements to running services
# =============================================================================
# Syncs Python API changes from the repo to the running skills directory,
# and updates the version field in openclaw.json.
#
# The OpenClaw plugin JS lives in the existing managed path:
#   /root/.openclaw/custom-plugins/silhouette-memory-managed-20260226-234443/
# (edited in-place, not duplicated)
#
# Usage:
#   bash deploy_plugin.sh           # sync and restart API
#   bash deploy_plugin.sh --dry-run # show what would happen
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# Python scripts: repo → skills (the location the running API uses)
PYTHON_SRC="$REPO_ROOT/src"
PYTHON_DST="/root/.openclaw/skills/silhouette-memory/scripts"
OC_CONFIG="/root/.openclaw/openclaw.json"
DRY_RUN=false

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

log()  { echo "[deploy] $*"; }
ok()   { echo "[deploy] ✅ $*"; }
warn() { echo "[deploy] ⚠️  $*"; }
err()  { echo "[deploy] ❌ $*" >&2; exit 1; }

[[ -d "$PYTHON_SRC" ]] || err "Repo src not found: $PYTHON_SRC"
[[ -d "$PYTHON_DST" ]] || err "Skills scripts dir not found: $PYTHON_DST"
[[ -f "$OC_CONFIG" ]]  || err "openclaw.json not found: $OC_CONFIG"

log "Repo src  : $PYTHON_SRC"
log "Skills dst: $PYTHON_DST"

$DRY_RUN && log "DRY RUN — no files will be changed"

# ── Backup openclaw.json ───────────────────────────────────────────────────
if ! $DRY_RUN; then
  cp "$OC_CONFIG" "$OC_CONFIG.bak.deploy-$(date +%Y%m%d-%H%M%S)"
  ok "Config backed up"
fi

# ── Sync Python files ─────────────────────────────────────────────────────
PYTHON_FILES=(
  "api/enhanced_memory_api.py"
  "core/memory_noise_filter.py"
  "core/agent_memory_readonly.py"
  "core/sync_openclaw_sessions.py"
  "core/smart_session_sync.py"
  "core/zhipu_embeddings.py"
  "core/reasoning_engine.py"
  "core/embeddings_wrapper.py"
  "core/memory_core_embeddings.py"
)

for rel in "${PYTHON_FILES[@]}"; do
  src="$PYTHON_SRC/$rel"
  dst="$PYTHON_DST/$(basename "$rel")"
  if [[ -f "$src" ]]; then
    if ! $DRY_RUN; then
      cp "$src" "$dst"
      ok "Synced $(basename "$rel")"
    else
      log "(dry) Would sync $rel → $dst"
    fi
  else
    warn "Source not found, skipping: $src"
  fi
done

# ── Ensure DB symlink points to canonical database ────────────────────────
DATA_DST="/root/.openclaw/skills/silhouette-memory/data"
CANONICAL_DB="/root/silhouette-brain/data/memory_core.db"
SKILLS_DB="$DATA_DST/memory_core.db"
if ! $DRY_RUN; then
  if [[ -f "$CANONICAL_DB" ]]; then
    if [[ ! -L "$SKILLS_DB" ]] || [[ "$(readlink "$SKILLS_DB")" != "$CANONICAL_DB" ]]; then
      [[ -f "$SKILLS_DB" && ! -L "$SKILLS_DB" ]] && mv "$SKILLS_DB" "${SKILLS_DB}.bak.$(date +%Y%m%d-%H%M%S)"
      ln -sf "$CANONICAL_DB" "$SKILLS_DB"
      ok "DB symlink set → $CANONICAL_DB"
    else
      ok "DB symlink already correct"
    fi
  fi
else
  log "(dry) Would ensure DB symlink: $SKILLS_DB → $CANONICAL_DB"
fi

# ── Restart memory API ────────────────────────────────────────────────────
if ! $DRY_RUN; then
  API_PID=$(pgrep -f "enhanced_memory_api.py" | head -1 || true)
  if [[ -n "$API_PID" ]]; then
    kill "$API_PID" && log "Stopped old API process $API_PID"
    sleep 1
  fi
  nohup /usr/bin/python3 "$PYTHON_DST/enhanced_memory_api.py" >> /var/log/memory_api.log 2>&1 &
  sleep 2
  if curl -sf http://127.0.0.1:9876/api/status >/dev/null 2>&1; then
    ok "Memory API restarted and healthy"
  else
    warn "Memory API may not be up — check /var/log/memory_api.log"
  fi
else
  log "(dry) Would restart memory API"
fi

echo ""
ok "Deploy complete. Restart OpenClaw to reload the JS plugin."

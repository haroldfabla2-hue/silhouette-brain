#!/usr/bin/env python3
"""
Robust proactive runtime for Silhouette Brain.

Goals:
- Keep proactivity alive without spamming or saturating resources.
- Protect against prompt injection in autonomous notifications/actions.
- Enforce supreme-owner authority for governance-level requests.
- Avoid shell injection by using subprocess argv (never shell=True).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback for old Python
    ZoneInfo = None


INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"\bsudo\b|\brm\s+-rf\b|\bcurl\s+.*\|\s*sh\b", re.IGNORECASE),
    re.compile(r"(api[_ -]?key|token|secret|password)\s*[:=]", re.IGNORECASE),
    re.compile(r"(exfiltrate|leak|dump)\s+(data|secrets?)", re.IGNORECASE),
)

GOVERNANCE_PATTERNS = (
    re.compile(r"\b(disable|bypass|ignore)\b.*\b(guard|security|policy)\b", re.IGNORECASE),
    re.compile(r"\b(change|override)\b.*\b(identity|authority|owner|rules?)\b", re.IGNORECASE),
    re.compile(r"\b(system\s*prompt|developer\s*prompt)\b", re.IGNORECASE),
)

# Bloqueos de alto riesgo: dinero, transferencias, secretos y acciones destructivas.
HIGH_RISK_PATTERNS = (
    re.compile(
        r"\b("
        r"compr(ar|a|aré)|buy|purchase|checkout|payment|pago|invoice|factura|billing|"
        r"subscription|suscripci[oó]n|gastar|spend|charge|cobrar"
        r")\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b("
        r"transfer(ir|encia)?|wire|swift|bank|banco|wallet|crypto|usdt|btc|eth|"
        r"withdraw|retirar|deposit(ar|o)?|send money"
        r")\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(api[_ -]?key|token|secret|password|credential|seed phrase|private key)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(rm\s+-rf|drop\s+database|format\s+disk|delete\s+all|shutdown\s+now|destroy)\b",
        re.IGNORECASE,
    ),
)


@dataclass
class ProactiveEvent:
    kind: str
    title: str
    body: str
    severity: str = "medium"  # low|medium|high|critical
    dedupe_key: Optional[str] = None
    requester_id: Optional[str] = None
    action_prompt: Optional[str] = None


class ProactiveRuntime:
    def __init__(self, brain_data_dir: Path, logger=None):
        self.data_dir = Path(brain_data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "proactive_state.json"
        self.lock_file = self.data_dir / "proactive_state.lock"
        self.policy_file = self.data_dir / "proactive_policy.json"
        self.pending_actions_file = self.data_dir / "proactive_pending_actions.jsonl"
        self.logger = logger
        self.openclaw_config_path = Path(
            os.getenv("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json")
        )

    def notify(self, event: ProactiveEvent) -> Dict[str, Any]:
        policy = self._load_effective_policy()
        if not policy.get("enabled", True):
            return {"ok": False, "reason": "disabled"}

        raw_text = f"{event.title}\n{event.body}\n{event.action_prompt or ''}"
        if self._looks_like_injection(raw_text):
            self._log("warning", f"[proactive] bloqueado por posible injection ({event.kind})")
            return self._update_state_and_return(
                policy, event, allowed=False, reason="blocked_injection"
            )

        if self._is_governance_request(event) and not self._is_supreme_owner(
            event.requester_id, policy
        ):
            self._log("warning", f"[proactive] bloqueado por autoridad ({event.kind})")
            return self._update_state_and_return(
                policy, event, allowed=False, reason="blocked_unauthorized"
            )

        target = policy.get("target")
        channel = policy.get("channel", "telegram")
        if not target:
            return {"ok": False, "reason": "missing_target"}

        message = self._build_message(event)
        now_ts = time.time()
        event_hash = self._event_hash(event, message)

        with open(self.lock_file, "a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            state = self._load_state_unlocked()
            self._prune_state(state, now_ts)

            blocked_reason = self._rate_limit_reason(
                state=state,
                policy=policy,
                now_ts=now_ts,
                event_hash=event_hash,
                severity=event.severity,
                dedupe_key=event.dedupe_key,
                event_kind=event.kind,
            )
            if blocked_reason:
                self._save_state_unlocked(state)
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                return {"ok": False, "reason": blocked_reason}

            send_result = self._send_message(
                channel=channel,
                target=target,
                account=policy.get("account"),
                message=message,
            )
            if not send_result["ok"]:
                self._save_state_unlocked(state)
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                return send_result

            sent_entry = {
                "ts": now_ts,
                "kind": event.kind,
                "severity": event.severity,
                "hash": event_hash,
                "dedupe_key": event.dedupe_key or "",
            }
            state.setdefault("sent", []).append(sent_entry)

            action_result = None
            if event.action_prompt:
                action_result = self._maybe_run_safe_action(
                    state=state,
                    policy=policy,
                    prompt=event.action_prompt,
                    severity=event.severity,
                    requester_id=event.requester_id,
                    now_ts=now_ts,
                )

            self._save_state_unlocked(state)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            return {
                "ok": True,
                "sent": True,
                "action": action_result,
                "channel": channel,
                "target": str(target),
            }

    # ------------------------------------------------------------------
    # Policy and authority
    # ------------------------------------------------------------------
    def _default_policy(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "channel": "telegram",
            "target": self._discover_default_target(),
            "account": "default",
            "timezone": "America/Lima",
            "quietHours": {"startHour": 23, "endHour": 8},
            "limits": {
                "perHour": 1,
                "perDay": 6,
                "dedupeHours": 6,
            },
            "actions": {
                "enabled": True,
                "ownerOnlyForGovernance": True,
                "allowSystemAutonomy": True,
                "cooldownSeconds": 3600,
                "maxPerDay": 4,
                # event_now | next-heartbeat | agent-background
                "executionMode": "event_now",
                "agentId": "silhouette",
                "agentTimeoutSec": 120,
                "maxPromptChars": 700,
            },
            "highRisk": {
                "blockWithoutOwnerApproval": True,
                "requireApprovalToken": True,
                "approvalToken": "OWNER_APPROVED",
            },
            # "Solo yo soy el dios supremo": lock to owner IDs you trust.
            "ownerIds": self._discover_owner_ids(),
        }

    def _load_effective_policy(self) -> Dict[str, Any]:
        policy = self._default_policy()
        if self.policy_file.exists():
            try:
                user_policy = json.loads(self.policy_file.read_text(encoding="utf-8"))
                policy = self._deep_merge(policy, user_policy)
            except Exception as e:
                self._log("warning", f"[proactive] policy inválida: {e}")

        if os.getenv("PROACTIVE_CHANNEL"):
            policy["channel"] = os.getenv("PROACTIVE_CHANNEL")
        if os.getenv("PROACTIVE_TARGET"):
            policy["target"] = os.getenv("PROACTIVE_TARGET")
        if os.getenv("SUPREME_OWNER_IDS"):
            owners = [
                item.strip()
                for item in os.getenv("SUPREME_OWNER_IDS", "").split(",")
                if item.strip()
            ]
            if owners:
                policy["ownerIds"] = owners
        return policy

    def _discover_default_target(self) -> str:
        cfg = self._read_openclaw_config()
        try:
            allow = (
                cfg.get("channels", {})
                .get("telegram", {})
                .get("accounts", {})
                .get("default", {})
                .get("allowFrom", [])
            )
            if allow:
                return str(allow[0])
        except Exception:
            pass
        return os.getenv("PROACTIVE_TARGET", "7350058748")

    def _discover_owner_ids(self) -> List[str]:
        cfg = self._read_openclaw_config()
        owners: List[str] = []
        try:
            allow = (
                cfg.get("channels", {})
                .get("telegram", {})
                .get("accounts", {})
                .get("default", {})
                .get("allowFrom", [])
            )
            if allow:
                owners.append(str(allow[0]))
        except Exception:
            pass

        if not owners:
            owners.append("7350058748")

        wa = cfg.get("channels", {}).get("whatsapp", {}).get("allowFrom", [])
        if wa:
            owners.append(str(wa[0]))

        # Deduplicate preserving order.
        out: List[str] = []
        seen: Set[str] = set()
        for item in owners:
            if item not in seen:
                out.append(item)
                seen.add(item)
        return out

    def _read_openclaw_config(self) -> Dict[str, Any]:
        try:
            if self.openclaw_config_path.exists():
                return json.loads(self.openclaw_config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _is_supreme_owner(self, requester_id: Optional[str], policy: Dict[str, Any]) -> bool:
        if requester_id is None:
            return False
        normalized = str(requester_id).strip()
        return normalized in {str(x).strip() for x in policy.get("ownerIds", [])}

    def _is_governance_request(self, event: ProactiveEvent) -> bool:
        blob = f"{event.title}\n{event.body}\n{event.action_prompt or ''}"
        return any(p.search(blob) for p in GOVERNANCE_PATTERNS) or event.kind in {
            "governance",
            "policy_change",
        }

    # ------------------------------------------------------------------
    # State and limits
    # ------------------------------------------------------------------
    def _load_state_unlocked(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {"sent": [], "actions": [], "blocked": []}
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"sent": [], "actions": [], "blocked": []}

    def _save_state_unlocked(self, state: Dict[str, Any]) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.state_file)

    def _prune_state(self, state: Dict[str, Any], now_ts: float) -> None:
        state.setdefault("sent", [])
        state.setdefault("actions", [])
        state.setdefault("blocked", [])
        keep_after = now_ts - (7 * 86400)
        state["sent"] = [x for x in state["sent"] if float(x.get("ts", 0)) >= keep_after]
        state["actions"] = [x for x in state["actions"] if float(x.get("ts", 0)) >= keep_after]
        state["blocked"] = [x for x in state["blocked"] if float(x.get("ts", 0)) >= keep_after]

    def _rate_limit_reason(
        self,
        state: Dict[str, Any],
        policy: Dict[str, Any],
        now_ts: float,
        event_hash: str,
        severity: str,
        dedupe_key: Optional[str] = None,
        event_kind: Optional[str] = None,
    ) -> Optional[str]:
        limits = policy.get("limits", {})
        per_hour = int(limits.get("perHour", 1))
        per_day = int(limits.get("perDay", 6))
        dedupe_hours = int(limits.get("dedupeHours", 6))
        recent = state.get("sent", [])

        if self._is_quiet_hours(policy) and severity not in ("high", "critical"):
            return "quiet_hours"

        normalized_key = str(dedupe_key or "").strip().lower()
        normalized_kind = str(event_kind or "").strip()
        if normalized_key:
            if any(
                str(x.get("dedupe_key", "")).strip().lower() == normalized_key
                and (not normalized_kind or str(x.get("kind", "")).strip() == normalized_kind)
                and now_ts - float(x.get("ts", 0)) < dedupe_hours * 3600
                for x in recent
            ):
                return "deduplicated_key"

        if any(
            x.get("hash") == event_hash and now_ts - float(x.get("ts", 0)) < dedupe_hours * 3600
            for x in recent
        ):
            return "deduplicated"

        hour_count = sum(1 for x in recent if now_ts - float(x.get("ts", 0)) <= 3600)
        day_count = sum(1 for x in recent if now_ts - float(x.get("ts", 0)) <= 86400)
        if hour_count >= per_hour:
            return "rate_limited_hour"
        if day_count >= per_day:
            return "rate_limited_day"
        return None

    def _is_quiet_hours(self, policy: Dict[str, Any]) -> bool:
        qh = policy.get("quietHours", {})
        start_hour = int(qh.get("startHour", 23))
        end_hour = int(qh.get("endHour", 8))
        tz_name = policy.get("timezone", "America/Lima")
        now = self._now_in_tz(tz_name)
        hour = now.hour
        if start_hour == end_hour:
            return False
        if start_hour < end_hour:
            return start_hour <= hour < end_hour
        return hour >= start_hour or hour < end_hour

    def _now_in_tz(self, tz_name: str) -> datetime:
        if ZoneInfo is None:
            return datetime.utcnow()
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            return datetime.utcnow()

    # ------------------------------------------------------------------
    # Delivery and actions
    # ------------------------------------------------------------------
    def _send_message(self, channel: str, target: str, account: Optional[str], message: str) -> Dict[str, Any]:
        cmd = ["openclaw", "message", "send", "--channel", channel, "--target", str(target), "--message", message]
        if account and channel in ("telegram", "discord", "whatsapp"):
            cmd.extend(["--account", str(account)])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()
                self._log("warning", f"[proactive] fallo envío: {err[:300]}")
                return {"ok": False, "reason": "send_failed", "error": err[:500]}
            self._log("info", f"[proactive] mensaje enviado ({channel})")
            return {"ok": True}
        except Exception as e:
            self._log("warning", f"[proactive] excepción enviando mensaje: {e}")
            return {"ok": False, "reason": "send_exception", "error": str(e)}

    def _maybe_run_safe_action(
        self,
        state: Dict[str, Any],
        policy: Dict[str, Any],
        prompt: str,
        severity: str,
        requester_id: Optional[str],
        now_ts: float,
    ) -> Dict[str, Any]:
        action_cfg = policy.get("actions", {})
        if not action_cfg.get("enabled", True):
            return {"ok": False, "reason": "actions_disabled"}

        if self._looks_like_injection(prompt):
            state["blocked"].append({"ts": now_ts, "reason": "action_injection"})
            return {"ok": False, "reason": "action_injection"}

        if action_cfg.get("ownerOnlyForGovernance", True) and self._is_governance_text(prompt):
            if not self._is_supreme_owner(requester_id, policy):
                state["blocked"].append({"ts": now_ts, "reason": "governance_owner_required"})
                return {"ok": False, "reason": "governance_owner_required"}

        # Alto riesgo: bloqueado sin aprobación explícita del owner.
        if self._is_high_risk_text(prompt):
            hr = policy.get("highRisk", {})
            if hr.get("blockWithoutOwnerApproval", True):
                owner_ok = self._is_supreme_owner(requester_id, policy)
                token_ok = self._has_owner_approval_token(prompt, hr)
                if not owner_ok or not token_ok:
                    state["blocked"].append({"ts": now_ts, "reason": "high_risk_requires_owner_approval"})
                    return {"ok": False, "reason": "high_risk_requires_owner_approval"}

        if not requester_id and not action_cfg.get("allowSystemAutonomy", True):
            return {"ok": False, "reason": "system_autonomy_disabled"}

        cooldown = int(action_cfg.get("cooldownSeconds", 21600))
        max_per_day = int(action_cfg.get("maxPerDay", 1))
        actions = state.get("actions", [])
        if actions:
            last_ts = max(float(x.get("ts", 0)) for x in actions)
            if now_ts - last_ts < cooldown:
                return {"ok": False, "reason": "action_cooldown"}
        day_actions = sum(1 for x in actions if now_ts - float(x.get("ts", 0)) <= 86400)
        if day_actions >= max_per_day:
            return {"ok": False, "reason": "action_rate_limited_day"}

        if severity not in ("high", "critical"):
            return {"ok": False, "reason": "action_severity_too_low"}

        safe_prompt = self._sanitize_text(
            prompt, max_chars=int(action_cfg.get("maxPromptChars", 700))
        )
        mode = str(action_cfg.get("executionMode", "event_now")).strip().lower()

        # Autonomía fuerte, pero segura:
        # 1) event_now (rápido, inmediato), 2) next-heartbeat, 3) agent-background.
        if mode in ("event_now", "next-heartbeat"):
            wake_mode = "now" if mode == "event_now" else "next-heartbeat"
            result = self._run_system_event(safe_prompt, wake_mode)
            if result.get("ok"):
                state.setdefault("actions", []).append(
                    {"ts": now_ts, "kind": f"system_event:{wake_mode}", "severity": severity}
                )
                self._log("info", f"[proactive] acción programada ({wake_mode})")
                return {"ok": True, "mode": f"system-event:{wake_mode}"}
            fallback = self._queue_and_local_fallback(
                prompt=safe_prompt,
                wake_mode=wake_mode,
                failure=result,
            )
            if fallback.get("ok"):
                state.setdefault("actions", []).append(
                    {
                        "ts": now_ts,
                        "kind": f"fallback:{wake_mode}",
                        "severity": severity,
                    }
                )
                return fallback
            return result

        if mode == "agent-background":
            agent_id = str(action_cfg.get("agentId", "silhouette"))
            timeout_sec = int(action_cfg.get("agentTimeoutSec", 120))
            result = self._spawn_agent_background(agent_id, safe_prompt, timeout_sec)
            if result.get("ok"):
                state.setdefault("actions", []).append(
                    {
                        "ts": now_ts,
                        "kind": "agent_background",
                        "severity": severity,
                        "agent": agent_id,
                    }
                )
                self._log("info", f"[proactive] acción autónoma lanzada (agent={agent_id})")
                return {"ok": True, "mode": "agent-background", "agent": agent_id}

            # Fallback robusto: si falla el agente, encola evento inmediato.
            fallback = self._run_system_event(safe_prompt, "now")
            if fallback.get("ok"):
                state.setdefault("actions", []).append(
                    {"ts": now_ts, "kind": "system_event:now_fallback", "severity": severity}
                )
                return {"ok": True, "mode": "system-event:now-fallback"}
            queued = self._queue_and_local_fallback(
                prompt=safe_prompt,
                wake_mode="next-heartbeat",
                failure=fallback,
            )
            if queued.get("ok"):
                state.setdefault("actions", []).append(
                    {"ts": now_ts, "kind": "queued_local_fallback", "severity": severity}
                )
                return queued
            return {
                "ok": False,
                "reason": "agent_background_and_fallback_failed",
                "error": (
                    result.get("error")
                    or fallback.get("error")
                    or queued.get("error")
                    or ""
                )[:500],
            }

        return {"ok": False, "reason": f"unknown_execution_mode:{mode}"}

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------
    def _build_message(self, event: ProactiveEvent) -> str:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        title = self._sanitize_text(event.title, max_chars=140)
        body = self._sanitize_text(event.body, max_chars=700)
        return f"🧠 Proactivo/{event.severity.upper()} • {timestamp}\n{title}\n\n{body}"

    def _sanitize_text(self, text: str, max_chars: int) -> str:
        clean = (text or "").replace("\x00", " ").strip()
        clean = re.sub(r"[ \t]+", " ", clean)
        clean = re.sub(r"\n{3,}", "\n\n", clean)
        return clean[:max_chars]

    def _looks_like_injection(self, text: str) -> bool:
        sample = (text or "")[:2000]
        return any(pattern.search(sample) for pattern in INJECTION_PATTERNS)

    def _is_governance_text(self, text: str) -> bool:
        sample = (text or "")[:1200]
        return any(pattern.search(sample) for pattern in GOVERNANCE_PATTERNS)

    def _is_high_risk_text(self, text: str) -> bool:
        sample = (text or "")[:2000]
        return any(pattern.search(sample) for pattern in HIGH_RISK_PATTERNS)

    def _has_owner_approval_token(self, text: str, high_risk_cfg: Dict[str, Any]) -> bool:
        if not high_risk_cfg.get("requireApprovalToken", True):
            return True
        token = str(high_risk_cfg.get("approvalToken", "OWNER_APPROVED")).strip()
        if not token:
            return False
        return token.lower() in (text or "").lower()

    def _run_system_event(self, text: str, wake_mode: str) -> Dict[str, Any]:
        mode = "now" if str(wake_mode).strip().lower() == "now" else "next-heartbeat"
        cmd = [
            "openclaw",
            "system",
            "event",
            "--mode",
            mode,
            "--text",
            text,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()
                return {"ok": False, "reason": "system_event_failed", "error": err[:500]}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "reason": "system_event_exception", "error": str(e)}

    def _queue_and_local_fallback(self, prompt: str, wake_mode: str, failure: Dict[str, Any]) -> Dict[str, Any]:
        queue_result = self._queue_pending_action(
            prompt=prompt,
            wake_mode=wake_mode,
            failure=failure,
        )
        local_result = self._enqueue_local_cognitive_task(
            prompt=prompt,
            failure=failure,
        )
        if queue_result.get("ok") or local_result.get("ok"):
            modes = []
            if queue_result.get("ok"):
                modes.append("queued")
            if local_result.get("ok"):
                modes.append("local-memory")
            self._log(
                "warning",
                "[proactive] gateway inestable; aplicado fallback "
                f"({'+'.join(modes)})",
            )
            return {
                "ok": True,
                "mode": "fallback:" + "+".join(modes),
                "reason": "gateway_unavailable_fallback",
                "queue": queue_result,
                "local": local_result,
            }
        return {
            "ok": False,
            "reason": "fallback_failed",
            "error": (
                queue_result.get("error")
                or local_result.get("error")
                or failure.get("error")
                or failure.get("reason")
                or "unknown"
            )[:500],
        }

    def _queue_pending_action(self, prompt: str, wake_mode: str, failure: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "ts": time.time(),
            "mode": "now" if str(wake_mode).strip().lower() == "now" else "next-heartbeat",
            "text": self._sanitize_text(prompt, max_chars=900),
            "retries": 0,
            "last_error": (failure.get("error") or failure.get("reason") or "")[:300],
        }
        try:
            with open(self.lock_file, "a+", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                with open(self.pending_actions_file, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _enqueue_local_cognitive_task(self, prompt: str, failure: Dict[str, Any]) -> Dict[str, Any]:
        note = (
            "[TAREA COGNITIVA - FALLBACK GATEWAY]\n"
            "No pude despachar la acción por gateway inestable.\n"
            f"Error: {(failure.get('error') or failure.get('reason') or 'unknown')[:180]}\n"
            f"Acción pendiente:\n{self._sanitize_text(prompt, max_chars=800)}"
        )
        tags = ["cognitive_task", "autonomy_fallback", "gateway_unavailable"]
        try:
            from silhouette_memory import SilhouetteMemory

            memory = SilhouetteMemory()
            memory.add(
                note,
                importance=0.92,
                tags=tags,
                tier="WORKING",
            )
            memory.close()
            return {"ok": True}
        except Exception as e:
            # Fallback extra robusto: inserción directa en memory.db (SQLite only).
            try:
                import sqlite3

                db_path = self.data_dir / "memory.db"
                now_ts = time.time()
                node_id = hashlib.sha1(f"{now_ts}:{note}".encode("utf-8")).hexdigest()[:16]
                conn = sqlite3.connect(str(db_path), timeout=10)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_nodes (
                        id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        tier TEXT NOT NULL,
                        importance REAL NOT NULL,
                        tags TEXT,
                        owner_id TEXT,
                        access_count INTEGER DEFAULT 0,
                        last_access REAL,
                        embedding BLOB
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_nodes
                    (id, content, timestamp, tier, importance, tags, owner_id, access_count, last_access, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        note,
                        now_ts,
                        "WORKING",
                        0.92,
                        json.dumps(tags, ensure_ascii=False),
                        None,
                        0,
                        now_ts,
                        None,
                    ),
                )
                conn.commit()
                conn.close()
                return {"ok": True, "fallback": "sqlite"}
            except Exception as e2:
                return {"ok": False, "error": f"{e}; sqlite_fallback={e2}"}

    def replay_pending_actions(self, max_items: int = 3, max_age_hours: int = 48) -> Dict[str, Any]:
        if not self.pending_actions_file.exists():
            return {"ok": True, "processed": 0, "sent": 0, "remaining": 0}

        now_ts = time.time()
        max_age_sec = max(1, int(max_age_hours)) * 3600
        policy = self._load_effective_policy()
        agent_id = str(policy.get("actions", {}).get("agentId", "silhouette"))
        agent_timeout = int(policy.get("actions", {}).get("agentTimeoutSec", 120))
        processed = 0
        sent = 0
        kept: List[Dict[str, Any]] = []

        try:
            with open(self.lock_file, "a+", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

                raw_lines = self.pending_actions_file.read_text(encoding="utf-8").splitlines()
                entries: List[Dict[str, Any]] = []
                for raw in raw_lines:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                        if isinstance(item, dict):
                            entries.append(item)
                    except Exception:
                        continue

                for item in entries:
                    if processed >= max_items:
                        kept.append(item)
                        continue

                    created_ts = float(item.get("ts", 0) or 0)
                    if created_ts <= 0 or (now_ts - created_ts) > max_age_sec:
                        continue

                    retries = int(item.get("retries", 0) or 0)
                    if retries >= 8:
                        continue

                    text = self._sanitize_text(str(item.get("text", "")), max_chars=900)
                    mode = str(item.get("mode", "next-heartbeat"))
                    if not text:
                        continue

                    result = self._run_system_event(text, mode)
                    processed += 1
                    if result.get("ok"):
                        sent += 1
                        continue

                    # Compatibilidad robusta: si system.event falla (ej. gateway 1006),
                    # intentar ejecución autónoma por agente embebido.
                    agent_result = self._spawn_agent_background(
                        agent_id=agent_id,
                        prompt=text,
                        timeout_sec=agent_timeout,
                    )
                    if agent_result.get("ok"):
                        sent += 1
                        continue

                    item["retries"] = retries + 1
                    item["last_error"] = (
                        result.get("error")
                        or result.get("reason")
                        or agent_result.get("error")
                        or agent_result.get("reason")
                        or item.get("last_error")
                        or "unknown"
                    )[:300]
                    item["last_attempt_ts"] = now_ts
                    kept.append(item)

                tmp = self.pending_actions_file.with_suffix(".tmp")
                if kept:
                    tmp.write_text(
                        "\n".join(json.dumps(x, ensure_ascii=False) for x in kept) + "\n",
                        encoding="utf-8",
                    )
                    os.replace(tmp, self.pending_actions_file)
                else:
                    if tmp.exists():
                        tmp.unlink()
                    if self.pending_actions_file.exists():
                        self.pending_actions_file.unlink()

                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            return {"ok": True, "processed": processed, "sent": sent, "remaining": len(kept)}
        except Exception as e:
            return {"ok": False, "error": str(e), "processed": processed, "sent": sent}

    def _spawn_agent_background(self, agent_id: str, prompt: str, timeout_sec: int) -> Dict[str, Any]:
        ts = int(time.time())
        digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
        session_id = f"proactive-{ts}-{digest}"
        cmd = [
            "openclaw",
            "agent",
            "--agent",
            str(agent_id),
            "--session-id",
            session_id,
            "--message",
            prompt,
            "--timeout",
            str(max(20, timeout_sec)),
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            if proc.pid <= 0:
                return {"ok": False, "reason": "agent_spawn_failed"}
            return {"ok": True, "pid": proc.pid}
        except Exception as e:
            return {"ok": False, "reason": "agent_spawn_exception", "error": str(e)}

    def _event_hash(self, event: ProactiveEvent, message: str) -> str:
        base = "|".join(
            [
                event.kind or "",
                event.dedupe_key or "",
                event.severity or "",
                message,
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def _deep_merge(self, base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(base)
        for key, value in (extra or {}).items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = self._deep_merge(out[key], value)
            else:
                out[key] = value
        return out

    def _update_state_and_return(
        self,
        policy: Dict[str, Any],
        event: ProactiveEvent,
        allowed: bool,
        reason: str,
    ) -> Dict[str, Any]:
        now_ts = time.time()
        with open(self.lock_file, "a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            state = self._load_state_unlocked()
            self._prune_state(state, now_ts)
            state.setdefault("blocked", []).append(
                {"ts": now_ts, "kind": event.kind, "reason": reason}
            )
            self._save_state_unlocked(state)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return {"ok": allowed, "reason": reason}

    def _log(self, level: str, message: str) -> None:
        if not self.logger:
            return
        fn = getattr(self.logger, level, None)
        if callable(fn):
            fn(message)

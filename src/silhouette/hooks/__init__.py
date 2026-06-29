"""Event hooks for extensibility (memory, security, system events)."""

from silhouette.hooks.system import (
    HookCallback,
    HookEvent,
    HookInput,
    HookResult,
    HooksSystem,
    auto_register_hooks,
    create_counter_hook,
    create_logging_hook,
    create_metrics_hook,
    create_notification_hook,
    emit_errorOccurred,
    emit_memory_stored,
    emit_memory_stored_async,
    hooks_system,
    on_hook,
)

__all__ = [
    "HookCallback",
    "HookEvent",
    "HookInput",
    "HookResult",
    "HooksSystem",
    "auto_register_hooks",
    "create_counter_hook",
    "create_logging_hook",
    "create_metrics_hook",
    "create_notification_hook",
    "emit_errorOccurred",
    "emit_memory_stored",
    "emit_memory_stored_async",
    "hooks_system",
    "on_hook",
]

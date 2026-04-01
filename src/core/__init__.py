"""
Silhouette Brain - Core Security Systems

This module exports:
- Bash Permissions System: Controls which bash commands each agent can execute
- Anti-Distillation System: Protects against AI training data distillation
"""

from .bash_permissions import (
    PERMISSIONS,
    DANGEROUS_COMMANDS,
    PROTECTED_DIRS,
    BLACKLIST_PATTERNS,
    PermissionLevel,
    PermissionResult,
    check_bash_permission,
    get_allowed_dirs,
    get_allowed_cmds,
    is_dangerous_command,
    validate_path,
    extract_base_command,
    extract_paths_from_command,
    matches_blacklist_pattern,
    is_protected_dir,
    is_command_allowed,
    get_permission_info,
    check_permission_sync,
    load_permissions_config,
    save_permissions_config,
    test_permissions,
)

from .anti_distillation import (
    FAKE_TOOLS,
    ANTI_DISTILLATION_ENABLED,
    FAKE_TOOLS_INJECTION_RATE,
    inject_fake_tools,
    strip_fake_tools,
    generate_fake_result,
    get_injection_status,
    set_anti_distillation_enabled,
    set_injection_rate,
    add_custom_fake_tool,
    remove_custom_fake_tool,
    test_anti_distillation,
)

__all__ = [
    # Bash Permissions
    "PERMISSIONS",
    "DANGEROUS_COMMANDS", 
    "PROTECTED_DIRS",
    "BLACKLIST_PATTERNS",
    "PermissionLevel",
    "PermissionResult",
    "check_bash_permission",
    "get_allowed_dirs",
    "get_allowed_cmds",
    "is_dangerous_command",
    "validate_path",
    "extract_base_command",
    "extract_paths_from_command",
    "matches_blacklist_pattern",
    "is_protected_dir",
    "is_command_allowed",
    "get_permission_info",
    "check_permission_sync",
    "load_permissions_config",
    "save_permissions_config",
    "test_permissions",
    # Anti-Distillation
    "FAKE_TOOLS",
    "ANTI_DISTILLATION_ENABLED",
    "FAKE_TOOLS_INJECTION_RATE",
    "inject_fake_tools",
    "strip_fake_tools",
    "generate_fake_result",
    "get_injection_status",
    "set_anti_distillation_enabled",
    "set_injection_rate",
    "add_custom_fake_tool",
    "remove_custom_fake_tool",
    "test_anti_distillation",
]

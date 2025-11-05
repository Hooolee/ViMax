import os
import re
from typing import Any, Dict, List

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _expand_env_in_str(value: str) -> str:
    def repl(m):
        var = m.group(1) or m.group(2)
        return os.getenv(var, m.group(0))
    return _ENV_PATTERN.sub(repl, value)


def resolve_env_vars(obj: Any) -> Any:
    """Recursively expand $VAR / ${VAR} in a nested config structure."""
    if isinstance(obj, dict):
        return {k: resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_env_vars(v) for v in obj]
    if isinstance(obj, str):
        return _expand_env_in_str(obj)
    return obj


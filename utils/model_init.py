from __future__ import annotations

import copy
from typing import Any, Dict

from langchain.chat_models import init_chat_model as _lc_init_chat_model
from utils.chat_gemini_proxy import create_gemini_proxy_runnable


def init_chat_model_compat(**init_args: Any):
    """
    A compatibility wrapper over langchain.chat_models.init_chat_model that accepts
    custom provider aliases and normalizes arguments.

    Supported aliases:
    - model_provider="gemini" -> If base_url is provided, uses custom HTTP-based proxy;
                                 otherwise uses langchain's native google_genai provider (gRPC).
    - model_provider="openai" -> passed through as-is (supports custom base_url for OpenAI-compatible gateways).

    All other providers are passed through unchanged.
    """
    args: Dict[str, Any] = copy.deepcopy(init_args)
    provider = (args.get("model_provider") or args.get("provider") or "").strip()

    if provider.lower() in {"gemini", "google", "google_genai"}:
        base_url = args.get("base_url")
        api_key = args.get("api_key")
        model = args.get("model")
        
        # If base_url is provided, use custom HTTP-based proxy (langchain-google-genai uses gRPC which doesn't work with HTTP proxies)
        if base_url:
            if not api_key or not model:
                raise ValueError("gemini provider with base_url requires api_key and model")
            return create_gemini_proxy_runnable(api_key=api_key, base_url=base_url, model=model)
        
        # Otherwise, use langchain's native google_genai provider
        args["model_provider"] = "google_genai"
        args.pop("base_url", None)
        if not args.get("api_key"):
            raise ValueError("GEMINI provider requires api_key. Set via config or environment.")
        return _lc_init_chat_model(**args)

    # passthrough for openai-compatible and others
    return _lc_init_chat_model(**args)

from __future__ import annotations

import asyncio
from typing import Any, List, Tuple, Union

from google import genai
from google.genai import types
from langchain_core.runnables import RunnableLambda


def _flatten_messages(input_messages: Any) -> List[dict]:
    """
    Convert LangChain-style messages (list of tuples, BaseMessage objects, or
    ChatPromptValue) into a list of content parts for google.genai.
    Supports text and {'type':'image_url','image_url':{'url':...}} parts.
    """
    parts: List[dict] = []

    def add_text(t: str):
        if t is None:
            return
        parts.append({"type": "text", "text": str(t)})

    if isinstance(input_messages, str):
        add_text(input_messages)
        return parts

    # List of messages (tuples or objects)
    if isinstance(input_messages, (list, tuple)):
        for msg in input_messages:
            # tuple like (role, content)
            if isinstance(msg, tuple) and len(msg) == 2:
                _, content = msg
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "image_url":
                            parts.append({
                                "type": "image_url",
                                "image_url": {"url": item.get("image_url", {}).get("url")},
                            })
                        elif isinstance(item, dict) and item.get("type") == "text":
                            add_text(item.get("text"))
                        else:
                            add_text(str(item))
                else:
                    add_text(content)
            else:
                # try BaseMessage-like
                content = getattr(msg, "content", None)
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "image_url":
                            parts.append({
                                "type": "image_url",
                                "image_url": {"url": item.get("image_url", {}).get("url")},
                            })
                        elif isinstance(item, dict) and item.get("type") == "text":
                            add_text(item.get("text"))
                        else:
                            add_text(str(item))
                else:
                    add_text(content if content is not None else str(msg))
        return parts

    # Fallback
    add_text(str(input_messages))
    return parts


def create_gemini_proxy_runnable(*, api_key: str, base_url: str, model: str, api_version: str = "v1beta"):
    """
    Create a Runnable that calls google.genai with base_url support, suitable for
    piping into LangChain parsers (returns plain text).
    """
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(base_url=base_url, api_version=api_version),
    )

    async def _ainvoke(messages: Any) -> str:
        parts = _flatten_messages(messages)
        # google.genai expects a list of parts; pass through images & text
        resp = await client.aio.models.generate_content(
            model=model,
            contents=parts,
            config=types.GenerateContentConfig(response_modalities=["TEXT"]),
        )
        # Collect all text parts
        out = []
        try:
            for cand in resp.candidates:
                for p in cand.content.parts:
                    if p.text:
                        out.append(p.text)
        except Exception:
            pass
        return "\n".join(out).strip()

    def _invoke(messages: Any) -> str:
        return asyncio.get_event_loop().run_until_complete(_ainvoke(messages))

    return RunnableLambda(function=_invoke, afunction=_ainvoke)


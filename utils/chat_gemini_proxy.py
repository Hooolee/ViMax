from __future__ import annotations

import asyncio
import base64
import re
from typing import Any, List, Tuple, Union

from google import genai
from google.genai import types
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import AIMessage


def _flatten_messages(input_messages: Any) -> Union[str, List[Union[str, types.Part]]]:
    """
    Convert LangChain-style messages into format acceptable by google.genai.
    Returns either a string (text-only) or a list of Parts (mixed text/image).
    """
    parts: List[Union[str, types.Part]] = []
    has_images = False

    def process_content_item(item: Any):
        nonlocal has_images
        if isinstance(item, dict):
            if item.get("type") == "text":
                text = item.get("text", "")
                if text:
                    parts.append(text)
            elif item.get("type") == "image_url":
                has_images = True
                image_url = item.get("image_url", {}).get("url", "")
                if image_url:
                    # Parse data URL: data:image/jpeg;base64,/9j/4AAQ...
                    if image_url.startswith("data:"):
                        match = re.match(r'data:([^;]+);base64,(.+)', image_url)
                        if match:
                            mime_type = match.group(1)
                            b64_data = match.group(2)
                            image_bytes = base64.b64decode(b64_data)
                            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
                    elif image_url.startswith("http"):
                        # Remote image URL
                        parts.append(types.Part.from_uri(uri=image_url))
        elif isinstance(item, str):
            if item:
                parts.append(item)
        else:
            text = str(item)
            if text:
                parts.append(text)

    if isinstance(input_messages, str):
        return input_messages

    # List of messages (tuples or objects)
    if isinstance(input_messages, (list, tuple)):
        for msg in input_messages:
            # tuple like (role, content)
            if isinstance(msg, tuple) and len(msg) == 2:
                _, content = msg
                if isinstance(content, list):
                    for item in content:
                        process_content_item(item)
                elif isinstance(content, str):
                    if content:
                        parts.append(content)
                else:
                    text = str(content)
                    if text:
                        parts.append(text)
            else:
                # try BaseMessage-like
                content = getattr(msg, "content", None)
                if isinstance(content, list):
                    for item in content:
                        process_content_item(item)
                elif content is not None:
                    text = str(content)
                    if text:
                        parts.append(text)
                else:
                    text = str(msg)
                    if text:
                        parts.append(text)
        
        # If no images, return as simple string for better compatibility
        if not has_images and parts:
            return "\n".join(str(p) for p in parts)
        return parts if parts else ""

    # Fallback
    return str(input_messages)


def create_gemini_proxy_runnable(*, api_key: str, base_url: str, model: str, api_version: str = "v1beta"):
    """
    Create a Runnable that calls google.genai with base_url support, suitable for
    piping into LangChain parsers (returns plain text).
    """
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(baseUrl=base_url, apiVersion=api_version),
    )

    async def _ainvoke(messages: Any) -> AIMessage:
        text_content = _flatten_messages(messages)
        # google.genai expects a simple string or proper Content objects
        resp = await client.aio.models.generate_content(
            model=model,
            contents=text_content,
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
        return AIMessage(content="\n".join(out).strip())

    def _invoke(messages: Any) -> AIMessage:
        return asyncio.get_event_loop().run_until_complete(_ainvoke(messages))

    return RunnableLambda(func=_invoke, afunc=_ainvoke)


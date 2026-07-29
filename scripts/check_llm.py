"""Probe configured LLM chat endpoint (local openai or silicon)."""

from __future__ import annotations

import sys

import httpx

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    api_type = settings.llm_model_api_type.strip().lower()
    if api_type == "silicon":
        base = settings.silicon_base_url.rstrip("/")
        key = settings.silicon_key or ""
        source = "silicon"
    else:
        base = settings.llm_model_base_url.rstrip("/")
        key = settings.llm_model_api_key or ""
        source = "openai_compat"

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    print(f"source={source}")
    print(f"base_url={base}")
    print(f"model={settings.llm_model_name}")

    try:
        with httpx.Client(timeout=20.0) as client:
            models = client.get(f"{base}/models", headers=headers)
            print(f"GET /models -> {models.status_code}")
            chat = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={
                    "model": settings.llm_model_name,
                    "temperature": 0,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                },
            )
            print(f"POST /chat/completions -> {chat.status_code}")
            if chat.status_code >= 400:
                print(chat.text[:500])
                return 2
            payload = chat.json()
            content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
            print(f"content_preview={(content or '')[:120]!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"error={type(exc).__name__}: {exc}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Make one explicit, small Azure chat-completions connectivity check.

No provider request is made unless --send-request is supplied. Output is
deliberately limited to status and safe API error codes; credentials, endpoint,
prompts, model output, and raw provider exceptions are never printed.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import sys
import time

from mcp_ri.api.azure_openai import AzureOpenAIClient
from mcp_ri.api.errors import APIError
from mcp_ri.api.settings import APISettings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send-request",
        action="store_true",
        help="send one small chat-completions request (may incur Azure usage charges)",
    )
    args = parser.parse_args()

    settings = APISettings.from_environment()
    client = AzureOpenAIClient(replace(settings, azure_openai_max_retries=0))
    missing = client.missing_configuration()
    if missing:
        print("Azure configuration is incomplete. Missing: " + ", ".join(missing))
        return 2
    if not args.send_request:
        print("Azure settings are present. No provider request was sent.")
        print("Pass --send-request to check deployment connectivity; this may incur usage charges.")
        return 0

    try:
        started = time.monotonic()
        result = client.chat_json(
            system='Return only the JSON object {"ok":true}.',
            user='{"purpose":"connectivity_check"}',
            max_tokens=32,
        )
        latency_ms = (time.monotonic() - started) * 1000
    except APIError as exc:
        print(f"Azure connectivity check failed ({exc.code}). {exc.message}")
        return 1
    except Exception:
        print("Azure connectivity check failed (unexpected client error); raw details were withheld.")
        return 1

    print("Azure chat-completions connectivity check succeeded.")
    print(f"HTTP status: {result.status_code}")
    print(f"Configured deployment: {settings.azure_openai_deployment_name}")
    print(f"Response model: {result.model or 'not supplied'}")
    print(f"Latency: {latency_ms:.1f} ms")
    print(f"Response content: {result.content}")
    if result.usage is None:
        print("Token usage: not supplied by Azure")
    else:
        prompt = result.usage.get("prompt_tokens", "unknown")
        completion = result.usage.get("completion_tokens", "unknown")
        total = result.usage.get("total_tokens", "unknown")
        print(f"Token usage: prompt={prompt}, completion={completion}, total={total}")
    print("Credentials and endpoint were not printed. Retries were disabled; one request at most was sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

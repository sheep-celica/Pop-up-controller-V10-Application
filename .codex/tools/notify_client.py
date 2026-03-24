from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


URL = os.environ.get("CODEX_NOTIFY_URL", "http://127.0.0.1:8765/notify")
TOKEN = os.environ.get("CODEX_NOTIFY_TOKEN", "")


def main() -> int:
    """
    Usage:
      python .codex/tools/notify_client.py
      python .codex/tools/notify_client.py "Codex finished"
      python .codex/tools/notify_client.py "Codex finished" "Implemented feature X"
    """
    title = "Codex"
    message = "Task finished"

    if len(sys.argv) >= 2 and sys.argv[1].strip():
        title = sys.argv[1].strip()

    if len(sys.argv) >= 3 and sys.argv[2].strip():
        message = sys.argv[2].strip()

    payload = {
        "title": title,
        "message": message,
    }
    if TOKEN:
        payload["token"] = TOKEN

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(body)
        return 0
    except urllib.error.HTTPError as e:
        print(f"notify HTTP error: {e.code} {e.reason}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"notify failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
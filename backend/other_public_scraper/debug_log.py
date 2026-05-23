from __future__ import annotations

import json
import time
from pathlib import Path

LOG_PATH = Path("/home/ir6/my/tender_hack/.cursor/debug-6c5798.log")
SESSION_ID = "6c5798"


def agent_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
) -> None:
    #region agent log
    entry = {
        "sessionId": SESSION_ID,
        "timestamp": int(time.time() * 1000),
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    #endregion

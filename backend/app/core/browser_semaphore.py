"""Global concurrency limit for Ozon nodriver (max 1 Chromium at a time)."""

import asyncio

ozon_browser_semaphore = asyncio.Semaphore(1)

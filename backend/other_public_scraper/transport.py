from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

from curl_cffi import requests as curl_requests

from other_public_scraper.config import DESKTOP_UA, settings
from other_public_scraper.diagnostics import active_diagnostics

logger = logging.getLogger(__name__)


@dataclass
class HttpResult:
    status_code: int
    body: str
    latency_ms: int
    url: str


_fetch_semaphore = asyncio.Semaphore(settings.other_fetch_concurrency)


def _solve_citilink_challenge(html: str) -> tuple[str, str] | None:
    if "data-name=\"_pcl\"" not in html or "new Int8Array" not in html:
        return None
    try:
        before_phrase = html.split("var phrase", 1)[0]
        value = ""
        for match in re.finditer(
            r"var value2 = '([^']*)';(.*?)(?:value = value \+ value2;)",
            before_phrase,
            re.S,
        ):
            chunk = match.group(1)
            if ".reverse()" in match.group(2):
                chunk = chunk[::-1]
            value += chunk

        phrase_match = re.search(
            r"var phrase = new Int8Array\(\[([\s\S]*?)\]\);", html
        )
        target_match = re.search(r"if \(data\[i\] === (-?\d+)\)", html)
        length_match = re.search(r"new Int8Array\((\d+)\)", html)
        name_match = re.search(r'data-name="([^"]+)"', html)
        if not (phrase_match and target_match and length_match and name_match):
            return None

        phrase = [int(value) for value in re.findall(r"-?\d+", phrase_match.group(1))]
        for offset, increment in re.findall(
            r"for\(var i = (\d+); i < data\.length; i\+=1024\) \{\s*"
            r"data\[i\] = data\[i\] \+ (\d+) > 127 \? "
            r"data\[i\] -128 \+ \d+ : data\[i\] \+ \d+;",
            html,
        ):
            index = int(offset)
            delta = int(increment)
            phrase[index] = (
                phrase[index] - 128 + delta
                if phrase[index] + delta > 127
                else phrase[index] + delta
            )

        target = int(target_match.group(1))
        data_length = int(length_match.group(1))
        checksum = sum(1 for item in phrase if item == target) * (data_length // 1024)
        trim = 5
        for char in str(checksum)[::-1]:
            digit = int(char)
            if digit > 0:
                trim = digit
                break
        return name_match.group(1), value[:-trim]
    except Exception:
        return None


async def fetch_html(url: str) -> HttpResult | None:
    t0 = time.perf_counter()

    def _do() -> HttpResult:
        session = curl_requests.Session(impersonate="chrome120")
        resp = session.get(
            url,
            headers={"User-Agent": DESKTOP_UA, "Accept-Language": "ru-RU,ru;q=0.9"},
            timeout=settings.other_request_timeout,
        )
        if resp.status_code == 429 and "citilink.ru" in url:
            solved = _solve_citilink_challenge(resp.text or "")
            if solved is not None:
                name, value = solved
                session.cookies.set(name, value, domain=".citilink.ru")
                resp = session.get(
                    url,
                    headers={
                        "User-Agent": DESKTOP_UA,
                        "Accept-Language": "ru-RU,ru;q=0.9",
                    },
                    timeout=settings.other_request_timeout,
                )
        return HttpResult(
            status_code=resp.status_code,
            body=resp.text or "",
            latency_ms=int((time.perf_counter() - t0) * 1000),
            url=url,
        )

    try:
        async with _fetch_semaphore:
            result = await asyncio.to_thread(_do)
        if result.status_code >= 400:
            active_diagnostics().note_failure(f"HTTP {result.status_code} — {url[:80]}")
            logger.info(
                "other_fetch_http_error url=%s status=%d latency_ms=%d",
                url,
                result.status_code,
                result.latency_ms,
            )
            return None
        if len(result.body) < 200:
            logger.info(
                "other_fetch_empty_body url=%s status=%d body_len=%d latency_ms=%d",
                url,
                result.status_code,
                len(result.body),
                result.latency_ms,
            )
            return None
        logger.info(
            "other_fetch_ok url=%s status=%d body_len=%d latency_ms=%d",
            url,
            result.status_code,
            len(result.body),
            result.latency_ms,
        )
        return result
    except Exception as exc:
        active_diagnostics().note_failure(f"Fetch error — {url[:80]}: {exc}")
        logger.info("other_fetch_exception url=%s error=%s", url, exc)
        return None

#!/usr/bin/env python3
"""Check WB proxy: download ~100 KB and report IP + speed.

Proxy is read from (first match wins):
  1. WB_PROXY env var
  2. key_proxy.txt in the repo root
  3. backend/.env  (WB_PROXY=... line)
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent


def _load_proxy() -> str:
    if val := os.environ.get("WB_PROXY", "").strip():
        return val
    key_file = ROOT / "key_proxy.txt"
    if key_file.exists():
        if val := key_file.read_text().strip():
            return val
    env_file = ROOT / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("WB_PROXY="):
                if val := line.split("=", 1)[1].strip():
                    return val
    return ""


def _to_url(raw: str) -> str:
    if raw.startswith(("http://", "https://", "socks5://")):
        return raw
    host_port, _, user_pass = raw.partition("@")
    return f"http://{user_pass}@{host_port}"


try:
    from curl_cffi import requests as curl_requests
except ImportError:
    sys.exit("curl_cffi not found — run: backend/.venv/bin/python check_proxy.py")

raw_proxy = _load_proxy()
if not raw_proxy:
    sys.exit("WB_PROXY not set — add it to WB_PROXY env var, key_proxy.txt, or backend/.env")

PROXY_URL = _to_url(raw_proxy)
TEST_URL = "https://httpbin.org/bytes/102400"
proxies = {"http": PROXY_URL, "https": PROXY_URL}

print("=== Proxy check ===")
print(f"Proxy : {PROXY_URL}")
print(f"Target: {TEST_URL}\n")

print("Direct IP (no proxy)…", end=" ", flush=True)
try:
    r = curl_requests.get("https://httpbin.org/ip", timeout=8, impersonate="chrome131")
    direct_ip = r.json().get("origin", "?")
    print(direct_ip)
except Exception as e:
    print(f"ERROR: {e}")
    direct_ip = None

print("Proxy  IP…", end=" ", flush=True)
try:
    r = curl_requests.get("https://httpbin.org/ip", proxies=proxies, timeout=8, impersonate="chrome131")
    proxy_ip = r.json().get("origin", "?")
    print(proxy_ip)
except Exception as e:
    print(f"ERROR: {e}")
    proxy_ip = None

if direct_ip and proxy_ip and direct_ip == proxy_ip:
    print("\nWARN: proxy IP == direct IP — proxy may not be routing traffic!")
elif direct_ip and proxy_ip:
    print("\nOK: IPs differ — traffic is going through the proxy.")

print("\nDownloading 100 KB via proxy…", end=" ", flush=True)
try:
    t0 = time.perf_counter()
    r = curl_requests.get(TEST_URL, proxies=proxies, timeout=60, impersonate="chrome131")
    elapsed = time.perf_counter() - t0
    size = len(r.content)
    speed = size / elapsed / 1024
    print(f"{size // 1024} KB in {elapsed:.2f}s — {speed:.0f} KB/s")
    if r.status_code == 200 and size > 90_000:
        print("\nRESULT: PASS — proxy is working correctly.")
    else:
        print(f"\nRESULT: FAIL — unexpected status {r.status_code} or size {size} bytes.")
except Exception as e:
    print(f"ERROR: {e}")
    print("\nRESULT: FAIL — could not download through proxy.")

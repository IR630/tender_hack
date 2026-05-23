import os

from curl_cffi import requests
from dotenv import load_dotenv

load_dotenv()


def get_proxies() -> dict[str, str]:
    user = os.getenv("OZON_PROXY_USER")
    password = os.getenv("OZON_PROXY_PASS")
    host = os.getenv("OZON_PROXY_HOST")
    port = os.getenv("OZON_PROXY_PORT")
    if not all([user, password, host, port]):
        raise RuntimeError("Proxy environment variables are incomplete")
    proxy_url = f"http://{user}:{password}@{host}:{port}"
    return {"http": proxy_url, "https": proxy_url}


def main() -> None:
    proxies = get_proxies()

    ip_response = requests.get("https://api.ipify.org", proxies=proxies, timeout=15)
    print(f"IP through proxy: {ip_response.text}")
    assert "190.2.142.241" not in ip_response.text, "Got proxy server IP instead of exit IP"

    home_response = requests.get(
        "https://www.ozon.ru",
        impersonate="chrome120",
        proxies=proxies,
        timeout=30,
    )
    print(
        "Ozon home:",
        f"status={home_response.status_code}",
        f"size={len(home_response.text)}",
    )
    assert home_response.status_code == 200, f"Ozon home returned {home_response.status_code}"

    search_response = requests.get(
        "https://www.ozon.ru/search/?text=футболка",
        impersonate="chrome120",
        proxies=proxies,
        timeout=30,
    )
    print(
        "Ozon search:",
        f"status={search_response.status_code}",
        f"size={len(search_response.text)}",
        f"next_data={'__NEXT_DATA__' in search_response.text}",
    )


if __name__ == "__main__":
    main()

import os
import httpx

_SERPER_URL = "https://google.serper.dev/search"


def serper_search(query: str, gl: str = "de", hl: str = "de", num: int = 5) -> list[dict]:
    """POST to Serper and return organic results. Raises on HTTP error."""
    headers = {"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"}
    r = httpx.post(
        _SERPER_URL,
        headers=headers,
        json={"q": query, "gl": gl, "hl": hl, "num": num},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("organic", [])

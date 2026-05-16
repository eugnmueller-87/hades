import re
import json


def parse_json_response(raw: str) -> dict:
    """
    Strip markdown fences from a Claude response and parse as JSON.
    Raises ValueError with a clear message if parsing fails.
    """
    if not raw:
        raise ValueError("Empty response from Claude")

    # Strip ```json ... ``` or ``` ... ``` fences robustly
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw (first 300 chars): {raw[:300]}")

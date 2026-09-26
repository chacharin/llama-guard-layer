import re

import httpx

from .categories import CATEGORIES
from .settings import Settings

_CODE_RE = re.compile(r"S\d{1,2}", re.IGNORECASE)


class GuardError(Exception):
    """เรียก OpenRouter ไม่สำเร็จ หรืออ่านผลของ Llama Guard ไม่ได้"""


def build_messages(message: str, direction: str) -> list[dict[str, str]]:
    # input = ข้อความผู้ใช้, output = ข้อความที่บอทจะตอบ
    role = "user" if direction == "input" else "assistant"
    return [{"role": role, "content": message}]


def parse_verdict(raw: str) -> tuple[bool, list[str]]:
    """คืน (is_unsafe, [รหัสหมวด]) จากผลของ Llama Guard: 'safe' หรือ 'unsafe\\nS1,S2'"""
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if not lines:
        raise GuardError("ผลจาก Llama Guard ว่างเปล่า")
    verdict = lines[0].lower()
    if verdict == "safe":
        return False, []
    if verdict == "unsafe":
        codes = [c.upper() for c in _CODE_RE.findall(" ".join(lines[1:]))]
        return True, codes
    raise GuardError(f"อ่านผลจาก Llama Guard ไม่ได้: {raw[:100]!r}")


def pick_blocked(codes: list[str]) -> list[str]:
    """เลือกเฉพาะหมวดที่ตั้งให้บล็อก (เรียงตามลำดับที่โมเดลตอบ)"""
    return [c for c in codes if c in CATEGORIES and CATEGORIES[c].blocked]


async def classify(
    client: httpx.AsyncClient, settings: Settings, message: str, direction: str
) -> tuple[bool, list[str]]:
    """คืน (unsafe_ตามหมวดที่บล็อก, [รหัสหมวดที่บล็อก])"""
    try:
        resp = await client.post(
            f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.guard_model,
                "messages": build_messages(message, direction),
                "temperature": 0,
            },
            timeout=settings.request_timeout_seconds,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise GuardError(f"เรียก OpenRouter ไม่สำเร็จ: {exc}") from exc

    is_unsafe, codes = parse_verdict(raw or "")
    if not is_unsafe:
        return False, []
    blocked = pick_blocked(codes)
    return bool(blocked), blocked

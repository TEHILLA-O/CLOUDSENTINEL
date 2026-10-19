import time

import httpx

from analysis_api.analyser import Analysis, Keyword
from analysis_api.config import Settings


async def analyse_with_llm(text: str, language: str, settings: Settings) -> Analysis:
    """Optional backend. Callers must only use this when a key is configured."""
    started = time.perf_counter()
    prompt = (
        "Return a JSON object with keys summary (string), sentiment_label "
        "(positive|neutral|negative), and keywords (array of strings). "
        f"Language hint: {language}. Text:\n{text}"
    )
    async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
        response = await client.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": "You analyse text and reply with JSON only."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    # The model is asked for JSON. If it doesn't comply, the caller returns a safe 502.
    import json

    parsed = json.loads(content)
    keywords = [Keyword(term=str(term), score=1.0) for term in parsed.get("keywords", [])[:8]]
    words = text.split()
    elapsed_ms = (time.perf_counter() - started) * 1000
    return Analysis(
        summary=str(parsed.get("summary", ""))[:500],
        sentiment_label=parsed.get("sentiment_label"),
        sentiment_score=None,
        sentiment_note="Score is omitted because the external model did not return a calibrated value.",
        keywords=keywords,
        characters=len(text),
        words=len(words),
        sentences=text.count(".") + text.count("!") + text.count("?"),
        reading_time_seconds=round(len(words) / 200 * 60, 2),
        processing_ms=round(elapsed_ms, 3),
    )

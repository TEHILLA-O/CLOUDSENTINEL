import re
import time
from dataclasses import dataclass

# Small, explicit lexicon. This is a deterministic baseline, not a general NLP model.
POSITIVE = {
    "good", "great", "excellent", "reliable", "stable", "healthy", "improved",
    "success", "successful", "clear", "fast", "safe", "helpful", "positive",
}
NEGATIVE = {
    "bad", "poor", "failed", "failure", "unhealthy", "slow", "error", "errors",
    "outage", "degraded", "unsafe", "broken", "negative", "timeout", "unavailable",
}
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "you", "your", "our", "their", "its",
    "into", "about", "after", "before", "when", "what", "which", "while", "can",
    "will", "just", "than", "then", "them", "they", "been", "being", "over",
    "under", "also", "such", "only", "more", "most", "some", "any", "each",
}

TOKEN = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
SENTENCE = re.compile(r"[^.!?]+[.!?]?")


@dataclass(frozen=True)
class Keyword:
    term: str
    score: float


@dataclass(frozen=True)
class Analysis:
    summary: str
    sentiment_label: str | None
    sentiment_score: float | None
    sentiment_note: str | None
    keywords: list[Keyword]
    characters: int
    words: int
    sentences: int
    reading_time_seconds: float
    processing_ms: float


def analyse_text(text: str, language: str, max_keywords: int) -> Analysis:
    started = time.perf_counter()
    tokens = [match.group(0).lower() for match in TOKEN.finditer(text)]
    sentences = [part.strip() for part in SENTENCE.findall(text) if part.strip()]
    words = re.findall(r"\b[\w'-]+\b", text)
    keywords = _keywords(tokens, max_keywords)
    label, score, note = _sentiment(tokens, language)
    summary = _summary(text, sentences, keywords, label)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return Analysis(
        summary=summary,
        sentiment_label=label,
        sentiment_score=score,
        sentiment_note=note,
        keywords=keywords,
        characters=len(text),
        words=len(words),
        sentences=max(len(sentences), 1 if text.strip() else 0),
        reading_time_seconds=round(len(words) / 200 * 60, 2),
        processing_ms=round(elapsed_ms, 3),
    )


def _keywords(tokens: list[str], limit: int) -> list[Keyword]:
    counts: dict[str, int] = {}
    for token in tokens:
        if token in STOPWORDS or token in POSITIVE or token in NEGATIVE:
            continue
        counts[token] = counts.get(token, 0) + 1
    if not counts:
        return []
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    top = ranked[0][1]
    return [Keyword(term=term, score=round(count / top, 3)) for term, count in ranked]


def _sentiment(tokens: list[str], language: str) -> tuple[str | None, float | None, str | None]:
    if language.lower() not in {"en", "en-gb", "en-us"}:
        return None, None, "Sentiment lexicon is English-only; statistics and keywords are still returned."
    if not tokens:
        return "neutral", 0.0, None
    positive = sum(1 for token in tokens if token in POSITIVE)
    negative = sum(1 for token in tokens if token in NEGATIVE)
    score = max(-1.0, min(1.0, (positive - negative) / len(tokens)))
    rounded = round(score, 4)
    if rounded > 0.02:
        label = "positive"
    elif rounded < -0.02:
        label = "negative"
    else:
        label = "neutral"
    return label, rounded, None


def _summary(text: str, sentences: list[str], keywords: list[Keyword], label: str | None) -> str:
    lead = sentences[0].strip() if sentences else text.strip()
    if len(lead) > 180:
        lead = lead[:177].rstrip() + "..."
    terms = ", ".join(keyword.term for keyword in keywords[:3])
    sentiment = label or "unscored"
    if terms:
        return f"{lead} Sentiment is {sentiment}. Leading terms: {terms}."
    return f"{lead} Sentiment is {sentiment}."

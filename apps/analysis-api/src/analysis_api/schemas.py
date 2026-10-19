from pydantic import BaseModel, Field


class AnalyseOptions(BaseModel):
    include_keywords: bool = True
    max_keywords: int = Field(default=8, ge=1, le=20)


class AnalyseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=32_000)
    language: str = Field(default="en", min_length=2, max_length=16)
    options: AnalyseOptions = Field(default_factory=AnalyseOptions)


class KeywordModel(BaseModel):
    term: str
    score: float


class SentimentModel(BaseModel):
    label: str | None
    score: float | None
    note: str | None = None


class StatisticsModel(BaseModel):
    characters: int
    words: int
    sentences: int
    reading_time_seconds: float


class AnalyseResponse(BaseModel):
    request_id: str
    summary: str
    language: str
    sentiment: SentimentModel
    keywords: list[KeywordModel]
    statistics: StatisticsModel
    backend: str
    processing_ms: float
    environment: str
    provider: str


class VersionResponse(BaseModel):
    name: str
    version: str
    environment: str
    provider: str
    backend: str


class HealthResponse(BaseModel):
    status: str
    environment: str


class FaultRequest(BaseModel):
    mode: str = Field(pattern="^(none|latency|errors|unreadiness|unliveness)$")
    latency_ms: int = Field(default=0, ge=0, le=10_000)
    error_status: int = Field(default=500, ge=400, le=599)
    # Faults expire so a crashed dashboard cannot leave an environment broken.
    duration_seconds: int = Field(default=60, ge=0, le=300)


class FaultResponse(BaseModel):
    mode: str
    latency_ms: int
    error_status: int
    expires_at: str | None


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str
    details: list[dict] | None = None

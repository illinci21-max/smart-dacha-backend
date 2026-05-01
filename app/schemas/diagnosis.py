from pydantic import BaseModel, UUID4
from datetime import datetime


class DiagnosisCreateRequest(BaseModel):
    plant_id: UUID4 | None = None
    photo_taken_at: datetime | None = None


class DiagnosisResult(BaseModel):
    disease_id: str
    disease_name: str
    confidence: float
    severity: str
    recommendations: list[str]
    bounding_box: dict | None = None


class DiagnosisResponse(BaseModel):
    id: UUID4
    plant_id: UUID4 | None
    photo_url: str
    status: str
    results: list[DiagnosisResult]
    model_version: str | None
    processing_time_ms: int | None
    error_message: str | None
    user_feedback: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class DiagnosisFeedbackRequest(BaseModel):
    feedback: str   # correct|incorrect|unsure

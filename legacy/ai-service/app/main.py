from __future__ import annotations

import io
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from PIL import Image
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.copygen import GenerateCopyRequest, GenerateCopyResponse, generate_copy
from app.crest import CompositeCrestRequest, CompositeCrestResponse, composite_crest
from app.embeddings import (
    EmbedAssetRequest,
    EmbedAssetResponse,
    TrainAvatarIdentityRequest,
    TrainAvatarIdentityResponse,
    embed_asset,
    train_avatar_identity,
)
from app.extract import ExtractRequest, ExtractResponse, extract_document
from app.image_ops import ProcessImageRequest, ProcessImageResponse, fetch_image_bytes, process_image
from app.qc import QCScoreRequest, QCScoreResponse, mean_lab_from_rgb_samples, score_qc
from providers.base import GenerateImageRequest, GenerateImageResponse, resolve_provider_key
from providers.fal_provider import FalProvider
from providers.mock import MockProvider

REQUEST_COUNT = Counter(
    "kitframe_ai_requests_total",
    "AI service request count",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "kitframe_ai_request_latency_seconds",
    "AI service request latency",
    ["method", "endpoint"],
)
REQUEST_ERRORS = Counter(
    "kitframe_ai_request_errors_total",
    "AI service request errors",
    ["method", "endpoint"],
)

REQUEST_ID_HEADER = "X-Request-ID"


def build_providers() -> dict[str, Any]:
    settings = get_settings()
    providers: dict[str, Any] = {"mock": MockProvider()}
    if settings.fal_key or settings.generation_provider == "fal":
        providers["fal"] = FalProvider()
    return providers


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        endpoint = request.url.path
        method = request.method
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        except Exception:
            REQUEST_ERRORS.labels(method=method, endpoint=endpoint).inc()
            raise
        finally:
            elapsed = time.perf_counter() - started
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status_code)).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.providers = build_providers()
    yield


app = FastAPI(title="Kitframe AI Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/extract", response_model=ExtractResponse)
async def extract_endpoint(body: ExtractRequest) -> ExtractResponse:
    return await extract_document(body)


@app.post("/generate-copy", response_model=GenerateCopyResponse)
async def generate_copy_endpoint(body: GenerateCopyRequest) -> GenerateCopyResponse:
    return await generate_copy(body)


@app.post("/process-image", response_model=ProcessImageResponse)
async def process_image_endpoint(body: ProcessImageRequest) -> ProcessImageResponse:
    return await process_image(body)


async def _load_lab_means(url: str, timeout: float) -> tuple[np.ndarray, int, int]:
    raw = await fetch_image_bytes(url, timeout)
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    width, height = image.size
    arr = np.asarray(image, dtype=np.float64)
    luminance = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]
    mask = luminance < 245.0
    samples = arr[mask] if mask.any() else arr.reshape(-1, 3)
    if samples.shape[0] > 5000:
        idx = np.linspace(0, samples.shape[0] - 1, 5000).astype(np.int64)
        samples = samples[idx]
    lab_mean = mean_lab_from_rgb_samples(samples)
    return lab_mean, width, height


@app.post("/qc-score", response_model=QCScoreResponse)
async def qc_score_endpoint(body: QCScoreRequest) -> QCScoreResponse:
    settings = get_settings()
    request = body
    if body.candidate_image_lab is None or body.golden_image_lab is None:
        timeout = settings.image_ops_timeout_seconds
        try:
            candidate_lab, c_w, c_h = await _load_lab_means(body.asset_url, timeout)
            golden_lab, g_w, g_h = await _load_lab_means(body.golden_set_image_url, timeout)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"image_fetch_failed:{exc}") from exc
        request = body.model_copy(
            update={
                "candidate_image_lab": [candidate_lab.tolist()],
                "golden_image_lab": [golden_lab.tolist()],
                "candidate_width": body.candidate_width or c_w,
                "candidate_height": body.candidate_height or c_h,
                "golden_width": body.golden_width or g_w,
                "golden_height": body.golden_height or g_h,
            }
        )
    return score_qc(request, settings)


@app.post("/train-avatar-identity", response_model=TrainAvatarIdentityResponse)
async def train_avatar_identity_endpoint(
    body: TrainAvatarIdentityRequest,
) -> TrainAvatarIdentityResponse:
    return await train_avatar_identity(body)


@app.post("/generate-image", response_model=GenerateImageResponse)
async def generate_image_endpoint(body: GenerateImageRequest) -> GenerateImageResponse:
    settings = get_settings()
    providers = app.state.providers
    if settings.generation_provider == "mock":
        key = "mock"
    else:
        key = resolve_provider_key(body.provider, settings.generation_provider, providers)
    provider = providers[key]
    garment = body.prompt.garment_asset_url or (body.reference_assets[0] if body.reference_assets else "")
    prompt = body.prompt.model_copy(
        update={
            "garment_asset_url": garment,
            "avatar_identity_ref": body.avatar_identity_ref
            if body.avatar_identity_ref is not None
            else body.prompt.avatar_identity_ref,
            "pose_skeleton_url": body.pose_skeleton_url
            if body.pose_skeleton_url is not None
            else body.prompt.pose_skeleton_url,
        }
    )
    if not provider.supports(prompt.output_type):
        provider = providers["mock"]
        key = "mock"
    asset = provider.generate(prompt)
    return GenerateImageResponse(
        generated_url=asset.url,
        provider_used=asset.provider,
        cost_usd=asset.cost_usd,
        latency_ms=asset.latency_ms,
    )


@app.post("/embed-asset", response_model=EmbedAssetResponse)
async def embed_asset_endpoint(body: EmbedAssetRequest) -> EmbedAssetResponse:
    return await embed_asset(body)


@app.post("/composite-crest", response_model=CompositeCrestResponse)
async def composite_crest_endpoint(body: CompositeCrestRequest) -> CompositeCrestResponse:
    return await composite_crest(body)

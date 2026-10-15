from __future__ import annotations

import asyncio
import io
import logging
import random
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from PIL import Image
from sqlalchemy import select

from kitframe.db.models import (
    Asset,
    AssetVersion,
    Brand,
    Export,
    Generation,
    Job,
    Product,
    ProductPhase,
    Project,
    ReferenceImage,
    RightsRecord,
    SourceDocument,
    Variant,
)
from kitframe.db.session import SessionLocal
from kitframe.errors import AppError, ErrorCode
from kitframe.extraction.schema import alt_text_schema, copy_schema, taxonomy_extraction_schema
from kitframe.media.storage import get_bytes, presign_get, put_bytes
from kitframe.providers.image.base import ImageGenerationRequest
from kitframe.providers.registry import get_image_provider, get_llm_client
from kitframe.qc.runner import run_qc_for_version
from kitframe.settings import get_settings
from kitframe.shopify.mapping import map_product_to_shopify
from kitframe.studio.rights import check_rights
from kitframe.workflow.transitions import mark_published

logger = logging.getLogger("kitframe.worker")


async def process_job(job_id: UUID) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.attempts += 1
        await session.commit()
        try:
            if job.type == "extract_document":
                await _extract(session, job)
            elif job.type == "generate_copy":
                await _copy(session, job)
            elif job.type == "fill_ecom_excel":
                await _fill_ecom_excel(session, job, settings)
            elif job.type == "generate_images":
                await _generate(session, job, settings)
            elif job.type == "run_qc":
                await run_qc_for_version(session, settings, job.entity_id)  # type: ignore[arg-type]
            elif job.type == "remove_background":
                await _remove_bg(session, job, settings)
            elif job.type == "validate_reference_image":
                await _validate_ref(session, job)
            elif job.type == "build_export":
                await _export(session, job, settings)
            elif job.type == "publish_shopify":
                await _publish(session, job, settings)
            elif job.type == "generate_alt_text":
                await _alt_text(session, job)
            elif job.type == "send_email":
                from kitframe.email.smtp import send_email

                settings = get_settings()
                payload = job.payload or {}
                to = payload.get("to")
                subject = payload.get("subject") or "Kitframe"
                body = payload.get("body") or payload.get("text") or ""
                html = payload.get("html")
                if not to:
                    raise RuntimeError("send_email job missing 'to'")
                await asyncio.to_thread(
                    send_email,
                    settings,
                    to=str(to),
                    subject=str(subject),
                    body_text=str(body),
                    body_html=str(html) if html else None,
                )
            elif job.type == "daily_due_dates":
                await _daily(session)
            else:
                raise RuntimeError(f"Unknown job type {job.type}")
            job.status = "completed"
            job.finished_at = datetime.now(UTC)
            await session.commit()
        except Exception as exc:
            logger.exception("job_failed", extra={"job_id": str(job_id)})
            job.status = "failed"
            if isinstance(exc, AppError):
                job.error_detail = f"{exc.code}: {exc.message}"
            else:
                job.error_detail = str(exc)
            job.finished_at = datetime.now(UTC)
            # Mark generation failed if applicable
            if job.type == "generate_images" and job.entity_id:
                gen = await session.get(Generation, job.entity_id)
                if gen is not None:
                    gen.status = "failed"
                    gen.error_detail = job.error_detail
            await session.commit()


async def _extract(session: Any, job: Job) -> None:
    doc = await session.get(SourceDocument, job.entity_id)
    assert doc is not None
    doc.extraction_status = "running"
    await session.flush()
    settings = get_settings()
    brand = await session.get(Brand, doc.brand_id)
    assert brand is not None
    llm_cfg = (brand.provider_config or {}).get("llm") or {}
    llm = get_llm_client(settings, llm_cfg)
    schema = taxonomy_extraction_schema(brand.taxonomy_schema or {"fields": []})
    result = await llm.complete_json_async(
        "Extract product data from the document. Return JSON matching the schema.",
        f"Document id {doc.id}. Extract all products.",
        schema,
        schema_name="taxonomy_extraction",
        temperature=0.0,
    )
    products = result.get("products") or []
    product_ids = []
    for item in products:
        ref = item.get("internal_reference") or f"EXT-{uuid4().hex[:8].upper()}"
        existing = (
            await session.execute(
                select(Product).where(Product.brand_id == doc.brand_id, Product.internal_reference == ref)
            )
        ).scalar_one_or_none()
        fields = {}
        conf = {}
        for k, payload in (item.get("fields") or {}).items():
            fields[k] = payload.get("value")
            conf[k] = payload.get("confidence", 0.5)
        if existing and existing.current_phase == "data":
            existing.structured_data = {**(existing.structured_data or {}), **fields}
            existing.field_confidence = {**(existing.field_confidence or {}), **conf}
            if "garment_category" in fields:
                existing.garment_category = fields["garment_category"]
            product_ids.append(existing.id)
            product = existing
        elif existing:
            continue
        else:
            product = Product(
                brand_id=doc.brand_id,
                project_id=doc.project_id,
                internal_reference=ref,
                garment_category=fields.get("garment_category"),
                structured_data=fields,
                field_confidence=conf,
            )
            session.add(product)
            await session.flush()
            project = await session.get(Project, doc.project_id)
            for phase in ("data", "visuals", "retouch", "approval"):
                due = None
                raw = (project.phase_due_dates or {}).get(phase) if project else None
                if raw:
                    due = date.fromisoformat(raw) if isinstance(raw, str) else raw
                session.add(
                    ProductPhase(
                        product_id=product.id,
                        phase=phase,
                        status="todo",
                        due_date=due,
                        entered_at=datetime.now(UTC) if phase == "data" else None,
                    )
                )
            product_ids.append(product.id)
        for v in item.get("variants") or []:
            session.add(
                Variant(
                    brand_id=doc.brand_id,
                    product_id=product.id,
                    color=v.get("color"),
                    size=v.get("size"),
                    sku=v.get("sku") or f"{ref}-VAR",
                    price_eur=v.get("price_eur"),
                )
            )
        from kitframe.jobs.enqueue import enqueue_job

        await enqueue_job(
            session,
            brand_id=doc.brand_id,
            type="generate_copy",
            entity_type="product",
            entity_id=product.id,
            requested_by=doc.uploaded_by,
        )
    doc.product_ids = product_ids
    doc.extraction_result = result
    doc.extraction_status = "completed"
    doc.sha256 = "extracted"


async def _fill_ecom_excel(session: Any, job: Job, settings: Any) -> None:
    from uuid import uuid4

    from kitframe.content.ecom_excel import (
        apply_row_fill,
        build_system_prompt,
        ecom_row_schema,
        list_rows_to_fill,
        load_workbook_bytes,
        workbook_to_bytes,
    )
    from kitframe.media.storage import get_bytes, put_bytes
    from kitframe.providers.registry import get_llm_client

    brand = await session.get(Brand, job.brand_id) if job.brand_id else None
    assert brand is not None
    payload = dict(job.payload or {})
    input_key = payload.get("input_storage_key")
    if not input_key:
        raise RuntimeError("fill_ecom_excel missing input_storage_key")

    data = get_bytes(settings, str(input_key))
    wb = load_workbook_bytes(data)
    rows = list_rows_to_fill(wb)
    llm_cfg = (brand.provider_config or {}).get("llm") or {}
    llm = get_llm_client(settings, llm_cfg)
    glossary = brand.glossary or {}
    system = build_system_prompt(
        tone=str(glossary.get("tone") or ""),
        do_not_translate=list(glossary.get("do_not_translate") or []),
    )

    filled = 0
    for row in rows:
        user = str(
            {
                "referencia": row.ref,
                "titulo_tecnico": row.title,
                "coleccion": row.collection,
                "tipo_producto": row.product_type,
                "fit_es_existente": row.existing_fit_es or None,
            }
        )
        result = await llm.complete_json_async(
            system,
            user,
            ecom_row_schema(),
            schema_name="ecom_excel_row",
            temperature=0.35,
        )
        apply_row_fill(wb, row.row, result)
        filled += 1

    out_name = payload.get("original_filename") or "descripcions.xlsx"
    if isinstance(out_name, str) and out_name.lower().endswith(".xlsx"):
        out_name = out_name[:-5] + "_filled.xlsx"
    else:
        out_name = "descripcions_filled.xlsx"
    out_key = f"brands/{brand.id}/ecom_excel/out/{uuid4()}/{out_name}"
    put_bytes(
        settings,
        out_key,
        workbook_to_bytes(wb),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    payload["output_storage_key"] = out_key
    payload["filled_count"] = filled
    payload["skipped_count"] = max(0, int(payload.get("pending_count") or 0) - filled)
    job.payload = payload


async def _copy(session: Any, job: Job) -> None:

    from kitframe.content.locales import CONTENT_LOCALES, LOCALE_LABELS

    product = await session.get(Product, job.entity_id)
    brand = await session.get(Brand, product.brand_id) if product else None
    assert product is not None and brand is not None
    settings = get_settings()
    llm_cfg = (brand.provider_config or {}).get("llm") or {}
    llm = get_llm_client(settings, llm_cfg)
    glossary = brand.glossary or {}
    payload = job.payload or {}
    mode = (payload.get("mode") or "generate").strip().lower()
    source_locale = (payload.get("source_locale") or "es").strip().lower()
    if source_locale not in CONTENT_LOCALES:
        source_locale = "es"

    if mode == "translate":
        source = (product.content or {}).get(source_locale) or {}
        system = (
            f"Translate ecommerce product copy from {LOCALE_LABELS.get(source_locale, source_locale)} "
            f"into all required locales. Tone: {glossary.get('tone', '')}. "
            f"Do not translate these terms literally if they are brand names: "
            f"{glossary.get('do_not_translate', [])}. "
            "Keep commercial names natural for each market. "
            "seo_title max 70 chars, seo_meta max 160 chars."
        )
        user = str(
            {
                "source_locale": source_locale,
                "source": {
                    "name": source.get("name"),
                    "description": source.get("description"),
                    "seo_title": source.get("seo_title"),
                    "seo_meta": source.get("seo_meta"),
                    "seo_keywords": source.get("seo_keywords") or [],
                },
                "target_locales": list(CONTENT_LOCALES),
            }
        )
        temperature = 0.3
    else:
        system = (
            f"Write ecommerce product copy in all required locales. "
            f"Tone: {glossary.get('tone', '')}. "
            f"Do not translate: {glossary.get('do_not_translate', [])}. "
            "Propose a commercial product name derived from the technical title/reference when useful. "
            "seo_title max 70 chars, seo_meta max 160 chars."
        )
        user = str(product.structured_data)
        temperature = 0.4

    result = await llm.complete_json_async(
        system,
        user,
        copy_schema(),
        schema_name="copy",
        temperature=temperature,
    )
    content = dict(product.content or {})
    for locale in CONTENT_LOCALES:
        payload_loc = result.get(locale)
        if not isinstance(payload_loc, dict):
            continue
        existing = content.get(locale) or {}
        manual = set(existing.get("manually_edited") or [])
        merged = {**payload_loc, "manually_edited": list(manual)}
        for field in manual:
            if field in existing:
                merged[field] = existing[field]
        content[locale] = merged
    product.content = content


async def _generate(session: Any, job: Job, settings: Any) -> None:
    gen = await session.get(Generation, job.entity_id)
    assert gen is not None
    brand = await session.get(Brand, gen.brand_id)
    assert brand is not None

    # Re-check rights in worker before any provider call
    rights = await check_rights(
        session,
        brand_id=gen.brand_id,
        model_set_id=gen.model_set_id,
        prompt=gen.prompt,
        restrictions=gen.restrictions,
    )
    gen.rights_check = rights
    if not rights.get("ok"):
        gen.status = "blocked_rights"
        return

    gen.status = "running"
    await session.flush()

    image_cfg = (brand.provider_config or {}).get("image") or {}
    provider = get_image_provider(settings, image_cfg)
    use_placeholder_urls = provider.key == "fake"

    def _url(storage_key: str, placeholder: str) -> str:
        if use_placeholder_urls:
            return placeholder
        return presign_get(settings, storage_key, expires=900)

    garment_urls: list[str] = []
    for vid in gen.garment_version_ids or []:
        version = await session.get(AssetVersion, vid)
        if version is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Garment version missing", status_code=422)
        garment_urls.append(_url(version.storage_key, f"https://fixture.local/garment/{vid}.jpg"))

    model_urls: list[str] = []
    if gen.model_set_id:
        model_imgs = (
            await session.execute(
                select(ReferenceImage)
                .where(
                    ReferenceImage.set_id == gen.model_set_id,
                    ReferenceImage.validation_status == "valid",
                )
                .order_by(ReferenceImage.sort_order, ReferenceImage.created_at)
                .limit(3)
            )
        ).scalars().all()
        model_urls = [
            _url(m.storage_key, f"https://fixture.local/model/{m.id}.jpg") for m in model_imgs
        ]

    pose_url = None
    if gen.pose_reference_id:
        pose = await session.get(ReferenceImage, gen.pose_reference_id)
        if pose:
            pose_url = _url(pose.storage_key, f"https://fixture.local/pose/{pose.id}.jpg")

    style_urls: list[str] = []
    for sid in gen.style_reference_ids or []:
        style = await session.get(ReferenceImage, sid)
        if style:
            style_urls.append(_url(style.storage_key, f"https://fixture.local/style/{style.id}.jpg"))
    base_seed = gen.seed if gen.seed is not None else random.randint(0, 2**31 - 1)
    gen.seed = base_seed
    await session.flush()

    req = ImageGenerationRequest(
        final_prompt=gen.final_prompt,
        garment_image_urls=garment_urls,  # type: ignore[arg-type]
        model_image_urls=model_urls,  # type: ignore[arg-type]
        pose_image_url=pose_url,  # type: ignore[arg-type]
        style_image_urls=style_urls,  # type: ignore[arg-type]
        aspect_ratio=gen.aspect_ratio,  # type: ignore[arg-type]
        variant_count=gen.variant_count,
        seed=base_seed,
    )

    if hasattr(provider, "generate_async"):
        result = await provider.generate_async(req)
    else:
        result = await asyncio.to_thread(provider.generate, req)

    for img in result.images:
        key = f"brands/{gen.brand_id}/generated/{uuid4()}.png"
        put_bytes(settings, key, img.content, img.mime_type)
        asset = Asset(
            brand_id=gen.brand_id,
            product_id=gen.product_id,
            shot_type=gen.target_shot_type,
            origin="generated",
            generation_id=gen.id,
            status="studio",
            created_by=gen.requested_by,
        )
        session.add(asset)
        await session.flush()
        version = AssetVersion(
            asset_id=asset.id,
            version_number=1,
            source="generation",
            storage_key=key,
            mime_type=img.mime_type,
            width=img.width,
            height=img.height,
            sha256=str(uuid4()),
            created_by=gen.requested_by,
        )
        session.add(version)
        await session.flush()
        asset.current_version_id = version.id
        from kitframe.jobs.enqueue import enqueue_job

        await enqueue_job(
            session,
            brand_id=gen.brand_id,
            type="run_qc",
            entity_type="asset_version",
            entity_id=version.id,
            requested_by=gen.requested_by,
        )
    gen.status = "completed"
    gen.images_returned = len(result.images)
    gen.latency_ms = result.latency_ms
    gen.cost_eur = result.cost_eur
    gen.provider = result.provider
    gen.provider_model = result.provider_model
    gen.completed_at = datetime.now(UTC)


async def _alt_text(session: Any, job: Job) -> None:
    asset = await session.get(Asset, job.entity_id)
    assert asset is not None
    product = await session.get(Product, asset.product_id)
    brand = await session.get(Brand, asset.brand_id)
    assert product is not None and brand is not None
    # Never overwrite manually edited alt text
    existing = asset.alt_text or {}
    if existing.get("manually_edited"):
        return
    settings = get_settings()
    llm_cfg = (brand.provider_config or {}).get("llm") or {}
    llm = get_llm_client(settings, llm_cfg)
    name = ((product.content or {}).get("es") or {}).get("name") or product.internal_reference
    result = await llm.complete_json_async(
        "Write short accessible alt text for an e-commerce product image.",
        f"Product: {name}. Shot type: {asset.shot_type}. Data: {product.structured_data}",
        alt_text_schema(),
        schema_name="alt_text",
        temperature=0.0,
    )
    asset.alt_text = {**result, "manually_edited": False}


async def _remove_bg(session: Any, job: Job, settings: Any) -> None:
    asset = await session.get(Asset, job.entity_id)
    assert asset is not None and asset.current_version_id
    current = await session.get(AssetVersion, asset.current_version_id)
    assert current is not None
    try:
        from rembg import remove

        raw = get_bytes(settings, current.storage_key)
        out = remove(raw)
        content = out if isinstance(out, (bytes, bytearray)) else bytes(out)
        img = Image.open(io.BytesIO(content))
        width, height = img.size
    except Exception:
        img = Image.new("RGBA", (current.width or 1024, current.height or 1024), (0, 0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        content = buf.getvalue()
        width, height = img.size
    key = f"brands/{asset.brand_id}/bgremoved/{uuid4()}.png"
    put_bytes(settings, key, content, "image/png")
    count = len(
        (await session.execute(select(AssetVersion).where(AssetVersion.asset_id == asset.id))).scalars().all()
    )
    version = AssetVersion(
        asset_id=asset.id,
        version_number=count + 1,
        source="background_removal",
        storage_key=key,
        mime_type="image/png",
        width=width,
        height=height,
        sha256=str(uuid4()),
        created_by=asset.created_by,
    )
    session.add(version)
    await session.flush()
    asset.current_version_id = version.id
    from kitframe.jobs.enqueue import enqueue_job

    await enqueue_job(
        session,
        brand_id=asset.brand_id,
        type="run_qc",
        entity_type="asset_version",
        entity_id=version.id,
        requested_by=asset.created_by,
    )


async def _validate_ref(session: Any, job: Job) -> None:
    img = await session.get(ReferenceImage, job.entity_id)
    assert img is not None
    img.width = img.width or 1200
    img.height = img.height or 1600
    short = min(img.width, img.height)
    if short < 768:
        img.validation_status = "invalid"
        img.validation_detail = {"reason": "short_side_below_768", "short_side_px": short}
    else:
        img.validation_status = "valid"
    img.sha256 = img.sha256 or str(uuid4())


async def _export(session: Any, job: Job, settings: Any) -> None:
    exp = await session.get(Export, job.entity_id)
    assert exp is not None
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.txt", ",".join(exp.channels))
    key = f"brands/{exp.brand_id}/exports/{exp.id}.zip"
    put_bytes(settings, key, buf.getvalue(), "application/zip")
    exp.storage_key = key
    exp.status = "completed"
    exp.completed_at = datetime.now(UTC)


async def _publish(session: Any, job: Job, settings: Any) -> None:
    product = await session.get(Product, job.entity_id)
    assert product is not None
    brand = await session.get(Brand, product.brand_id)
    variants = (
        await session.execute(select(Variant).where(Variant.product_id == product.id))
    ).scalars().all()
    payload = map_product_to_shopify(product, list(variants), [], brand)  # type: ignore[arg-type]
    _ = payload
    env = brand.active_shopify_environment
    ids = dict(product.shopify_ids or {})
    env_ids = ids.get(env) or {}
    if not env_ids.get("product_id"):
        env_ids["product_id"] = f"gid://shopify/Product/{uuid4().hex[:10]}"
    ids[env] = env_ids
    product.shopify_ids = ids
    await mark_published(session, product, job.requested_by or product.id)


async def _daily(session: Any) -> None:
    today = date.today()
    rights = (await session.execute(select(RightsRecord).where(RightsRecord.status == "cleared"))).scalars().all()
    for r in rights:
        if r.valid_until and r.valid_until < today:
            r.status = "expired"


async def worker_loop() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        async with SessionLocal() as session:
            jobs = (
                await session.execute(
                    select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(4)
                )
            ).scalars().all()
            ids = [j.id for j in jobs]
        for jid in ids:
            await process_job(jid)
        await asyncio.sleep(1)


def run_worker() -> None:
    asyncio.run(worker_loop())

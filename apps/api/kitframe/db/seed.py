from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from kitframe.auth.tokens import hash_password
from kitframe.db.models import (
    Asset,
    AssetVersion,
    Brand,
    BrandMembership,
    ChannelSpec,
    GoldenSetImage,
    ModelReferenceSet,
    Product,
    ProductPhase,
    Project,
    ProjectMember,
    QCRun,
    ReferenceImage,
    RightsRecord,
    User,
    Variant,
)
from kitframe.db.session import SessionLocal
from kitframe.db.seed_media import PRODUCT_FINAL_SHOTS, PRODUCT_REFS, sha256_file, sha256_product_final, upload_seed_media

DEFAULT_QC = {
    "resolution": {"min_short_side_px": 2000, "min_short_side_px_generated": 1440},
    "color": {"clusters": 3, "pass_max_delta_e": 3.0, "review_max_delta_e": 6.0},
    "crest": {"pass_min_confidence": 0.80, "review_min_confidence": 0.55, "position_tolerance": 0.05},
    "extraction": {"confirm_below_confidence": 0.85},
}


def _default_provider_config() -> dict:
    from kitframe.settings import get_settings

    settings = get_settings()
    use_bfl = bool(settings.bfl_api_key) and settings.image_provider != "fake"
    use_mistral = bool(settings.mistral_api_key) and settings.llm_provider != "fake"
    return {
        "image": (
            {
                "provider": "bfl",
                "model": "flux-2-pro",
                "safety_tolerance": 2,
                "output_format": "png",
                "price_per_image_eur": 0.06,
            }
            if use_bfl
            else {"provider": "fake", "model": "fake-v1"}
        ),
        "llm": (
            {"provider": "mistral", "model": "mistral-large-2512"}
            if use_mistral
            else {"provider": "fake", "model": "fake-llm"}
        ),
    }

TAXONOMY = {
    "fields": [
        {"key": "composition", "label": {"es": "Composición", "ca": "Composició", "en": "Composition"}, "type": "string", "required": True},
        {"key": "care_instructions", "label": {"es": "Cuidados", "ca": "Cures", "en": "Care"}, "type": "text", "required": True},
        {"key": "origin", "label": {"es": "Origen", "ca": "Origen", "en": "Origin"}, "type": "string", "required": False},
        {
            "key": "garment_category",
            "label": {"es": "Categoría", "ca": "Categoria", "en": "Category"},
            "type": "enum",
            "values": ["jersey", "training", "leisure", "accessories"],
            "required": True,
        },
        {
            "key": "gender",
            "label": {"es": "Género", "ca": "Gènere", "en": "Gender"},
            "type": "enum",
            "values": ["kids", "adult_men", "adult_women", "unisex"],
            "required": True,
        },
        {"key": "season", "label": {"es": "Temporada", "ca": "Temporada", "en": "Season"}, "type": "string", "required": False},
    ]
}


async def _add_generated_product_images(
    session,
    *,
    brand: Brand,
    product: Product,
    ref: str,
    created_by,
) -> int:
    """Add definitive (origin=generated, status=selected) product images for demo review."""
    added = 0
    for shot_i, shot in enumerate(PRODUCT_FINAL_SHOTS):
        existing = (
            await session.execute(
                select(Asset).where(
                    Asset.product_id == product.id,
                    Asset.origin == "generated",
                    Asset.shot_type == shot,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        asset = Asset(
            brand_id=brand.id,
            product_id=product.id,
            shot_type=shot,
            origin="generated",
            status="selected",
            sort_order=10 + shot_i,
            alt_text={
                "es": f"Camiseta FC Barcelona — {shot.replace('_', ' ')}",
                "ca": f"Samarreta FC Barcelona — {shot.replace('_', ' ')}",
                "en": f"FC Barcelona jersey — {shot.replace('_', ' ')}",
                "manually_edited": False,
            },
            created_by=created_by,
        )
        session.add(asset)
        await session.flush()
        version = AssetVersion(
            asset_id=asset.id,
            version_number=1,
            source="studio",
            storage_key=f"seed/product/{ref}/{shot}.jpg",
            mime_type="image/jpeg",
            width=2000 if shot != "model_front" else 1200,
            height=2000 if shot != "model_front" else 1600,
            sha256=sha256_product_final(ref, shot),
            created_by=created_by,
        )
        session.add(version)
        await session.flush()
        asset.current_version_id = version.id
        session.add(
            QCRun(
                asset_version_id=version.id,
                status="completed",
                result="pass",
                checks={
                    "resolution": {"ok": True},
                    "color": {"ok": True, "skipped": True},
                    "crest": {"ok": True, "skipped": True},
                },
                completed_at=datetime.now(UTC),
            )
        )
        added += 1
    return added


async def ensure_demo_product_images(session, brand: Brand) -> int:
    """Ensure products past data have definitive images (for review / publish demos)."""
    owner = (
        await session.execute(select(User).where(User.email == "owner@kitframe.local"))
    ).scalar_one_or_none()
    if owner is None:
        return 0
    products = (
        await session.execute(select(Product).where(Product.brand_id == brand.id))
    ).scalars().all()
    total = 0
    for product in products:
        if product.current_phase == "data":
            continue
        ref = product.internal_reference
        if ref not in PRODUCT_REFS:
            # Allow any FCB-DEMO-* style ref
            if not (ref or "").startswith("FCB-DEMO-"):
                continue
        total += await _add_generated_product_images(
            session,
            brand=brand,
            product=product,
            ref=ref,
            created_by=owner.id,
        )
    return total


async def run_seed(*, with_passwords: bool = True) -> None:
    password = "Kitframe-dev-2026!"
    from kitframe.settings import get_settings

    settings = get_settings()
    # Always ensure fixture bytes exist in storage (works on re-seed too)
    try:
        upload_seed_media(settings)
    except Exception as exc:
        print(f"WARNING: seed media upload failed: {exc}")
        raise

    async with SessionLocal() as session:
        existing = (await session.execute(select(Brand).where(Brand.slug == "fc-barcelona"))).scalar_one_or_none()
        if existing:
            # Keep brand provider_config in sync with current .env (demo switch fake↔bfl)
            desired = _default_provider_config()
            if existing.provider_config != desired:
                existing.provider_config = desired
                print(f"Updated brand provider_config → image={desired['image']['provider']}")
            added = await ensure_demo_product_images(session, existing)
            await session.commit()
            print(
                f"Seed brand already present; media refreshed"
                + (f"; +{added} product images" if added else "")
                + "."
            )
            return

        brand = Brand(
            name="FC Barcelona",
            slug="fc-barcelona",
            taxonomy_schema=TAXONOMY,
            glossary={
                "do_not_translate": ["Barça", "Blaugrana", "Spotify", "FC Barcelona", "Camp Nou"],
                "preferred": {},
                "tone": "Tono institucional, claro y orgulloso.",
            },
            generation_rules=(
                "Preserve FC Barcelona brand integrity. Exact garment fidelity. "
                "No invented logos or crest distortions."
            ),
            required_shots={
                "jersey": ["product_front", "product_back", "model_front"],
                "accessories": ["product_front"],
                "training": ["product_front", "product_back", "model_front"],
                "leisure": ["product_front", "model_front"],
            },
            qc_config=DEFAULT_QC,
            provider_config=_default_provider_config(),
        )
        session.add(brand)
        await session.flush()

        channels = [
            ("shopify", 2000, 2000, "jpg", "white", "{reference}-{shot}-{index}-{channel}", True),
            ("instagram_feed", 1080, 1350, "jpg", "keep", "{reference}-{shot}-{index}-{channel}", False),
            ("instagram_story", 1080, 1920, "jpg", "keep", "{reference}-{shot}-{index}-{channel}", False),
            ("print_retail", 3000, 3000, "png", "transparent", "{reference}-{shot}-{index}-{channel}", False),
            ("email", 1200, 1200, "jpg", "white", "{reference}-{shot}-{index}-{channel}", False),
        ]
        for ch, w, h, fmt, bg, pattern, primary in channels:
            session.add(
                ChannelSpec(
                    brand_id=brand.id,
                    channel=ch,
                    width_px=w,
                    height_px=h,
                    format=fmt,
                    background=bg,
                    filename_pattern=pattern,
                    is_primary=primary,
                )
            )

        users_spec = [
            ("owner@kitframe.local", "Owner Demo", "owner", True),
            ("admin@kitframe.local", "Admin Demo", "admin", True),
            ("viewer@kitframe.local", "Viewer Demo", "viewer", False),
            ("datos@kitframe.local", "Editor Datos", "member", False),
            ("creativo@kitframe.local", "Editor Creativo", "editor", False),
            ("diseno@kitframe.local", "Editor Diseño", "editor", False),
            ("revisor@kitframe.local", "Revisor Demo", "member", False),
        ]
        users: dict[str, User] = {}
        for email, name, role, golden in users_spec:
            user = User(
                email=email,
                name=name,
                password_hash=hash_password(password) if with_passwords else hash_password(str(uuid4()) + "Xx1!"),
                locale="es",
            )
            session.add(user)
            await session.flush()
            session.add(
                BrandMembership(
                    user_id=user.id,
                    brand_id=brand.id,
                    role=role,
                    can_approve_golden_set=golden and role in ("owner", "admin"),
                )
            )
            users[email] = user

        rights = RightsRecord(
            brand_id=brand.id,
            subject_type="player",
            subject_name="Jugador Ejemplo",
            aliases=["Ejemplo"],
            status="not_cleared",
            notes="",
        )
        session.add(rights)
        await session.flush()

        project = Project(
            brand_id=brand.id,
            name="Demo 1ª equipación",
            description="Proyecto demo para el flujo completo Kitframe.",
            lead_user_id=users["owner@kitframe.local"].id,
            requirements=[
                {"id": str(uuid4()), "text": "El escudo debe verse nítido"},
                {"id": str(uuid4()), "text": "Fondo gris claro en las fotos de modelo"},
                {"id": str(uuid4()), "text": "Colores blaugrana fieles a la prenda real"},
            ],
            phase_due_dates={
                "data": (date.today() + timedelta(days=3)).isoformat(),
                "visuals": (date.today() + timedelta(days=7)).isoformat(),
                "retouch": (date.today() + timedelta(days=10)).isoformat(),
                "approval": (date.today() + timedelta(days=14)).isoformat(),
            },
            sample_arrival_date=date.today(),
            must_ship_date=date.today() + timedelta(days=21),
            sale_date=date.today() + timedelta(days=28),
        )
        session.add(project)
        await session.flush()

        assignments = [
            ("data", users["datos@kitframe.local"].id, "editor"),
            ("data", users["revisor@kitframe.local"].id, "reviewer"),
            ("visuals", users["creativo@kitframe.local"].id, "editor"),
            ("visuals", users["revisor@kitframe.local"].id, "reviewer"),
            ("retouch", users["diseno@kitframe.local"].id, "editor"),
            ("retouch", users["revisor@kitframe.local"].id, "reviewer"),
            ("approval", users["revisor@kitframe.local"].id, "reviewer"),
        ]
        for phase, uid, role in assignments:
            session.add(ProjectMember(project_id=project.id, phase=phase, user_id=uid, role=role))

        phases_cycle = ["data", "visuals", "retouch", "approval", "published", "data"]
        for i, phase in enumerate(phases_cycle):
            ref = f"FCB-DEMO-{i+1:03d}"
            product = Product(
                brand_id=brand.id,
                project_id=project.id,
                internal_reference=ref,
                garment_category="jersey",
                current_phase=phase if phase != "published" else "published",
                structured_data={
                    "composition": "100% polyester",
                    "care_instructions": "Lavar a 30º",
                    "garment_category": "jersey",
                    "gender": "adult_men",
                    "season": "26/27",
                },
                field_confidence={"composition": 0.92, "garment_category": 0.95, "gender": 0.9, "care_instructions": 0.88},
                confirmed_fields=["composition", "garment_category", "gender", "care_instructions"],
                content={
                    "es": {
                        "name": f"Camiseta home {i+1}",
                        "description": "Camiseta oficial Blaugrana con escudo nítido y tejido técnico para uso diario.",
                        "seo_title": f"Camiseta FC Barcelona {i+1}",
                        "seo_meta": "Camiseta oficial del FC Barcelona, edición demo Kitframe.",
                        "seo_keywords": ["Barça", "camiseta", "oficial"],
                        "manually_edited": [],
                    },
                    "ca": {
                        "name": f"Samarreta home {i+1}",
                        "description": "Samarreta oficial Blaugrana amb escut nítid i teixit tècnic.",
                        "seo_title": f"Samarreta FC Barcelona {i+1}",
                        "seo_meta": "Samarreta oficial del FC Barcelona, edició demo Kitframe.",
                        "seo_keywords": ["Barça", "samarreta"],
                        "manually_edited": [],
                    },
                    "en": {
                        "name": f"Home jersey {i+1}",
                        "description": "Official Blaugrana jersey with crisp crest and technical fabric.",
                        "seo_title": f"FC Barcelona jersey {i+1}",
                        "seo_meta": "Official FC Barcelona jersey, Kitframe demo edition.",
                        "seo_keywords": ["Barça", "jersey"],
                        "manually_edited": [],
                    },
                },
                published_at=datetime.now(UTC) if phase == "published" else None,
            )
            session.add(product)
            await session.flush()
            session.add(
                Variant(
                    brand_id=brand.id,
                    product_id=product.id,
                    color="Blaugrana",
                    size="M",
                    sku=f"{ref}-M",
                    price_eur=Decimal("89.95"),
                )
            )
            for ph in ("data", "visuals", "retouch", "approval"):
                status = "todo"
                entered = None
                if phase == "published" or ("data", "visuals", "retouch", "approval", "published").index(phase) > ("data", "visuals", "retouch", "approval").index(ph):
                    status = "done"
                    entered = datetime.now(UTC)
                elif phase == ph:
                    status = "in_progress" if ph != "approval" else "in_review"
                    entered = datetime.now(UTC)
                session.add(
                    ProductPhase(
                        product_id=product.id,
                        phase=ph,
                        status=status,
                        assignee_user_id=users["datos@kitframe.local"].id if ph == "data" else users["creativo@kitframe.local"].id,
                        due_date=date.today() + timedelta(days=7),
                        entered_at=entered,
                    )
                )
            # Real garment photos for Studio garment references
            for shot_i, shot in enumerate(("product_front", "product_back", "product_detail")):
                asset = Asset(
                    brand_id=brand.id,
                    product_id=product.id,
                    shot_type=shot,
                    origin="real_photo",
                    status="candidate",
                    sort_order=shot_i,
                    created_by=users["owner@kitframe.local"].id,
                )
                session.add(asset)
                await session.flush()
                version = AssetVersion(
                    asset_id=asset.id,
                    version_number=1,
                    source="upload",
                    storage_key=f"seed/garment/{ref}/{shot}.jpg",
                    mime_type="image/jpeg",
                    width=2000,
                    height=2000,
                    sha256=sha256_file(f"garment/{ref}/{shot}.jpg"),
                    created_by=users["owner@kitframe.local"].id,
                )
                session.add(version)
                await session.flush()
                asset.current_version_id = version.id

            # Definitive product images for phases past data (review / publish demos)
            if phase != "data":
                await _add_generated_product_images(
                    session,
                    brand=brand,
                    product=product,
                    ref=ref,
                    created_by=users["owner@kitframe.local"].id,
                )

        model_set = ModelReferenceSet(
            brand_id=brand.id,
            name="Modelo sintético demo",
            kind="synthetic",
            created_by=users["owner@kitframe.local"].id,
            notes="Set sintético para Studio",
        )
        session.add(model_set)
        await session.flush()
        for i in range(5):
            session.add(
                ReferenceImage(
                    brand_id=brand.id,
                    kind="model",
                    set_id=model_set.id,
                    name=f"foto-{i+1}",
                    storage_key=f"seed/model/{i+1}.jpg",
                    width=1200,
                    height=1600,
                    sha256=sha256_file(f"model/{i+1}.jpg"),
                    validation_status="valid",
                    sort_order=i,
                    created_by=users["owner@kitframe.local"].id,
                )
            )
        for name in ("Frontal brazos relajados", "Perfil caminando", "Tres cuartos"):
            session.add(
                ReferenceImage(
                    brand_id=brand.id,
                    kind="pose",
                    name=name,
                    storage_key=f"seed/pose/{name}.jpg",
                    width=1000,
                    height=1400,
                    sha256=sha256_file(f"pose/{name}.jpg"),
                    validation_status="valid",
                    created_by=users["owner@kitframe.local"].id,
                )
            )
        for name, tags in (("Estudio gris", ["estudio", "fondo gris"]), ("Luz suave", ["luz suave"]), ("Editorial", ["editorial"])):
            session.add(
                ReferenceImage(
                    brand_id=brand.id,
                    kind="style",
                    name=name,
                    tags=tags,
                    storage_key=f"seed/style/{name}.jpg",
                    width=1200,
                    height=1200,
                    sha256=sha256_file(f"style/{name}.jpg"),
                    validation_status="valid",
                    created_by=users["owner@kitframe.local"].id,
                )
            )

        session.add(
            GoldenSetImage(
                brand_id=brand.id,
                garment_category="jersey",
                shot_type="product_front",
                storage_key="seed/golden/jersey-front.jpg",
                reference_colors=[{"lab": [40.0, 25.0, -10.0], "weight": 0.5}, {"lab": [55.0, 5.0, -20.0], "weight": 0.5}],
                crest_bbox={"x": 0.42, "y": 0.22, "w": 0.16, "h": 0.18},
                status="approved",
                created_by=users["owner@kitframe.local"].id,
                approved_by=users["owner@kitframe.local"].id,
                approved_at=datetime.now(UTC),
            )
        )

        await session.commit()
        print("Seed complete: brand FC Barcelona + media in storage.")

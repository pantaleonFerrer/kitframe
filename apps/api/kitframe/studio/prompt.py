from __future__ import annotations

from kitframe.errors import AppError, ErrorCode

SHOT_LABELS = {
    "product_front": (
        "front view of the garment alone, laid flat or on an invisible mannequin, no person"
    ),
    "product_back": (
        "back view of the garment alone, laid flat or on an invisible mannequin, no person"
    ),
    "product_detail": "close-up detail of the garment, no person",
    "model_front": "full-body front view of the model wearing the garment",
    "model_back": "full-body back view of the model wearing the garment",
    "lifestyle": "the model wearing the garment in the described scene",
}


def format_image_refs(start: int, count: int) -> str:
    if count <= 0:
        return ""
    nums = list(range(start, start + count))
    if len(nums) == 1:
        return f"image {nums[0]}"
    if len(nums) == 2:
        return f"image {nums[0]} and image {nums[1]}"
    return f"images {nums[0]} to {nums[-1]}"


def compose_final_prompt(
    *,
    generation_rules: str,
    prompt: str,
    restrictions: str,
    aspect_ratio: str,
    shot_type: str,
    n_garment: int,
    n_model: int = 0,
    n_pose: int = 0,
    n_style: int = 0,
) -> str:
    if n_garment < 1:
        raise AppError(ErrorCode.VALIDATION_ERROR, "At least one garment reference", status_code=422)
    idx = 1
    garment_refs = format_image_refs(idx, n_garment)
    idx += n_garment
    model_refs = format_image_refs(idx, n_model) if n_model else ""
    idx += n_model
    pose_ref = format_image_refs(idx, n_pose) if n_pose else ""
    idx += n_pose
    style_refs = format_image_refs(idx, n_style) if n_style else ""

    parts: list[str] = []
    if generation_rules.strip():
        parts.append(generation_rules.strip())
        parts.append("")
    parts.append(
        f"GARMENT: {garment_refs} show the real garment. Reproduce this garment exactly:\n"
        "same colors, stripes, crest, sponsor logos, collar, cuffs, fabric texture and fit.\n"
        "Do not add, remove, move, distort or redraw any logo, crest or text."
    )
    if n_model:
        parts.append(
            f"MODEL: The person must be the same person shown in {model_refs}: "
            "same face, hair, skin tone and body type. Only take the person from these images, "
            "not their clothing."
        )
    if n_pose:
        parts.append(
            f"POSE: Match the body pose shown in {pose_ref}. "
            "Only take the pose from this image, not the person or the clothing."
        )
    if n_style:
        parts.append(
            f"STYLE: Match the lighting, background treatment, composition and mood of "
            f"{style_refs}. Do not copy people or garments from these images."
        )
    parts.append(f"SCENE: {prompt}")
    if restrictions.strip():
        parts.append(f"AVOID: {restrictions}")
    label = SHOT_LABELS.get(shot_type, shot_type)
    parts.append(
        f"OUTPUT: Photorealistic e-commerce photograph, {label}, aspect ratio {aspect_ratio}."
    )
    return "\n".join(parts)

"""Upload validation helpers.

Checks declared content type and file signature (magic bytes) so files cannot
masquerade as images by using a forged extension or MIME header.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException


ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_IMAGE_EXTENSIONS_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_JPEG_MAGIC = bytes.fromhex("ffd8ff")
_PNG_MAGIC = bytes.fromhex("89504e470d0a1a0a")


@dataclass(frozen=True)
class ValidatedImageUpload:
    content_type: str
    extension: str
    size_bytes: int


def detect_image_content_type(content: bytes) -> str | None:
    """Detect supported image type from magic bytes."""
    if content.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if content.startswith(_PNG_MAGIC):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image_upload(
    content: bytes,
    declared_content_type: str | None,
    *,
    max_size_bytes: int,
) -> ValidatedImageUpload:
    """Validate image upload size, MIME header, and magic bytes."""
    if declared_content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Only JPEG, PNG, and WebP images are supported",
        )

    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large. Maximum: {max_size_bytes // 1024 // 1024} MB",
        )

    detected_content_type = detect_image_content_type(content)
    if detected_content_type is None:
        raise HTTPException(
            status_code=415,
            detail="File content is not a supported JPEG, PNG, or WebP image",
        )

    if detected_content_type != declared_content_type:
        raise HTTPException(
            status_code=415,
            detail=(
                "Declared file type does not match file content: "
                f"declared {declared_content_type}, detected {detected_content_type}"
            ),
        )

    return ValidatedImageUpload(
        content_type=detected_content_type,
        extension=_IMAGE_EXTENSIONS_BY_CONTENT_TYPE[detected_content_type],
        size_bytes=len(content),
    )

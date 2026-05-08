"""Tests for image upload magic-byte validation."""

import pytest
from fastapi import HTTPException

from app.services.upload_validation import (
    detect_image_content_type,
    validate_image_upload,
)


JPEG_BYTES = bytes.fromhex("ffd8ffe000104a4649460001") + b"jpeg-body"
PNG_BYTES = bytes.fromhex("89504e470d0a1a0a") + b"png-body"
WEBP_BYTES = b"RIFF" + (12).to_bytes(4, "little") + b"WEBP" + b"webp-body"


class TestDetectImageContentType:
    def test_detects_jpeg(self):
        assert detect_image_content_type(JPEG_BYTES) == "image/jpeg"

    def test_detects_png(self):
        assert detect_image_content_type(PNG_BYTES) == "image/png"

    def test_detects_webp(self):
        assert detect_image_content_type(WEBP_BYTES) == "image/webp"

    def test_rejects_non_image_bytes(self):
        assert detect_image_content_type(b"<script>alert(1)</script>") is None


class TestValidateImageUpload:
    @pytest.mark.parametrize(
        ("content", "content_type", "extension"),
        [
            (JPEG_BYTES, "image/jpeg", "jpg"),
            (PNG_BYTES, "image/png", "png"),
            (WEBP_BYTES, "image/webp", "webp"),
        ],
    )
    def test_accepts_supported_images(self, content, content_type, extension):
        result = validate_image_upload(
            content,
            content_type,
            max_size_bytes=1024,
        )

        assert result.content_type == content_type
        assert result.extension == extension
        assert result.size_bytes == len(content)

    def test_rejects_unsupported_declared_content_type(self):
        with pytest.raises(HTTPException) as exc:
            validate_image_upload(
                JPEG_BYTES,
                "application/octet-stream",
                max_size_bytes=1024,
            )

        assert exc.value.status_code == 415

    def test_rejects_fake_jpeg_with_script_content(self):
        with pytest.raises(HTTPException) as exc:
            validate_image_upload(
                b"<script>alert('not an image')</script>",
                "image/jpeg",
                max_size_bytes=1024,
            )

        assert exc.value.status_code == 415
        assert "not a supported" in exc.value.detail

    def test_rejects_fake_png_with_zip_content(self):
        with pytest.raises(HTTPException) as exc:
            validate_image_upload(
                b"PKfake-zip-content",
                "image/png",
                max_size_bytes=1024,
            )

        assert exc.value.status_code == 415

    def test_rejects_mime_magic_mismatch(self):
        with pytest.raises(HTTPException) as exc:
            validate_image_upload(
                PNG_BYTES,
                "image/jpeg",
                max_size_bytes=1024,
            )

        assert exc.value.status_code == 415
        assert "declared image/jpeg, detected image/png" in exc.value.detail

    def test_rejects_oversized_file_before_magic_check(self):
        with pytest.raises(HTTPException) as exc:
            validate_image_upload(
                JPEG_BYTES,
                "image/jpeg",
                max_size_bytes=4,
            )

        assert exc.value.status_code == 413

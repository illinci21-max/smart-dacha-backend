"""
Тести авторизації — покриття S-01, S-04, S-10, IDOR.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone


# ── Unit тести create_token / decode ──────────────────────────────────────────

class TestCreateToken:
    def test_token_has_jti(self):
        """S-01: Кожен токен має унікальний jti."""
        from app.routers.auth import create_token
        with patch("app.routers.auth.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret-key-for-testing-only"
            token1, jti1 = create_token("user-1", timedelta(hours=1))
            token2, jti2 = create_token("user-1", timedelta(hours=1))
        assert jti1 != jti2, "jti повинні бути унікальними"
        assert len(jti1) == 36  # UUID format

    def test_access_token_type(self):
        """S-10: Access токен має type='access'."""
        import jwt as pyjwt
        from app.routers.auth import create_token
        with patch("app.routers.auth.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret-key-for-testing-only"
            token, jti = create_token("user-1", timedelta(hours=1), token_type="access")
        # Decode без перевірки (просто перевіряємо payload)
        payload = pyjwt.decode(token, "test-secret-key-for-testing-only", algorithms=["HS256"])
        assert payload["type"] == "access"
        assert payload["jti"] == jti

    def test_refresh_token_type(self):
        """S-10: Refresh токен має type='refresh'."""
        import jwt as pyjwt
        from app.routers.auth import create_token
        with patch("app.routers.auth.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret-key-for-testing-only"
            token, jti = create_token("user-1", timedelta(days=30), token_type="refresh")
        payload = pyjwt.decode(token, "test-secret-key-for-testing-only", algorithms=["HS256"])
        assert payload["type"] == "refresh"


class TestDecodeAndValidateToken:
    def test_wrong_token_type_raises(self):
        """S-10: access токен не приймається як refresh."""
        import jwt as pyjwt
        from fastapi import HTTPException
        from app.routers.auth import decode_and_validate_token
        
        # Створюємо access token
        payload = {"sub": "user-1", "type": "access", "jti": "test-jti-123"}
        token = pyjwt.encode(payload, "test-secret", algorithm="HS256")

        with patch("app.routers.auth.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            with patch("app.routers.auth._get_blacklist_redis") as mock_redis:
                mock_redis.return_value.get.return_value = None
                with pytest.raises(HTTPException) as exc_info:
                    decode_and_validate_token(token, expected_type="refresh")
        assert exc_info.value.status_code == 401
        assert "Невірний тип токена" in exc_info.value.detail

    def test_blacklisted_token_raises(self):
        """S-01: Відкликаний токен відхиляється."""
        import jwt as pyjwt
        from fastapi import HTTPException
        from app.routers.auth import decode_and_validate_token
        
        payload = {"sub": "user-1", "type": "access", "jti": "revoked-jti-456"}
        token = pyjwt.encode(payload, "test-secret", algorithm="HS256")

        with patch("app.routers.auth.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            with patch("app.routers.auth._get_blacklist_redis") as mock_redis:
                mock_redis.return_value.get.return_value = "1"  # В blacklist!
                with pytest.raises(HTTPException) as exc_info:
                    decode_and_validate_token(token, expected_type="access")
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail


# ── Unit тести watering service ───────────────────────────────────────────────

class TestWateringService:
    def _make_weather(self, **kwargs):
        defaults = {
            "temp_avg": 25.0, "temp_max": 30.0, "temp_min": 18.0,
            "precipitation": 0.0, "rain_probability": 0.0,
            "relative_humidity": 60.0, "wind_speed": 2.0,
            "shortwave_radiation_sum": 20.0, "et0_fao_evapotranspiration": 0.0,
        }
        return {**defaults, **kwargs}

    def test_null_weather_data_returns_decision(self):
        """T-03: Null weather дані не ламають систему."""
        from app.services.watering_service import calculate_watering_need
        decision = calculate_watering_need(
            plant_id="test-plant",
            last_watered_at=None,
            crop={"water_need_ml_per_day": 300, "drought_tolerance": 3},
            weather_today=None,
            weather_tomorrow=None,
        )
        assert decision is not None
        assert isinstance(decision.amount_ml, int)
        assert decision.amount_ml >= 0

    def test_all_zero_sensor_values_fallback(self):
        """T-03: Нульові значення сенсорів (збій) — fallback на defaults."""
        from app.services.watering_service import calculate_watering_need
        from datetime import datetime, timezone, timedelta
        
        zero_weather = {
            "temp_avg": 0, "temp_max": 0, "temp_min": 0,
            "precipitation": 0, "rain_probability": 0,
            "relative_humidity": 0, "wind_speed": 0,
            "shortwave_radiation_sum": 0, "et0_fao_evapotranspiration": 0,
        }
        last_watered = datetime.now(timezone.utc) - timedelta(days=5)
        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=last_watered,
            crop={"water_need_ml_per_day": 300, "drought_tolerance": 3},
            weather_today=zero_weather,
            weather_tomorrow=None,
        )
        assert decision.amount_ml >= 0

    def test_rain_today_skips_watering(self):
        """Дощ сьогодні → не поливаємо."""
        from app.services.watering_service import calculate_watering_need
        weather = self._make_weather(precipitation=15.0, rain_probability=90.0)
        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=None,
            crop={"water_need_ml_per_day": 300, "drought_tolerance": 3},
            weather_today=weather,
            weather_tomorrow=None,
        )
        assert not decision.should_water
        assert decision.skip_reason == "rain_expected_today"

    def test_frost_suspends_watering(self):
        """Мороз → поливання призупинено."""
        from app.services.watering_service import calculate_watering_need
        weather = self._make_weather(temp_avg=-10.0, precipitation=0.0, rain_probability=0.0)
        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=None,
            crop={"water_need_ml_per_day": 300, "drought_tolerance": 3},
            weather_today=weather,
            weather_tomorrow=None,
        )
        assert not decision.should_water
        assert decision.skip_reason == "frost_suspended"

    def test_et0_from_openmeteo_used_when_available(self):
        """I-02: et0_fao_evapotranspiration від Open-Meteo використовується напряму."""
        from app.services.watering_service import calculate_watering_need
        from datetime import datetime, timezone, timedelta
        
        weather = self._make_weather(et0_fao_evapotranspiration=5.5)  # 5.5mm ETo від API
        last_watered = datetime.now(timezone.utc) - timedelta(days=4)
        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=last_watered,
            crop={"water_need_ml_per_day": 300, "drought_tolerance": 3, "kc_stage": 1.1},
            weather_today=weather,
            weather_tomorrow=None,
        )
        assert decision.reason_factors["eto_mm"] == 5.5


# ── SSRF захист тести ─────────────────────────────────────────────────────────

class TestSSRFProtection:
    def test_http_url_rejected(self):
        """S-02: HTTP (не HTTPS) відхиляється."""
        from app.services.ai_service import validate_photo_url
        with pytest.raises(ValueError, match="HTTPS"):
            validate_photo_url("http://cdn.smartdacha.ua/photo.jpg")

    def test_private_ip_rejected(self):
        """S-02: Приватні IP блокуються."""
        from app.services.ai_service import validate_photo_url
        with pytest.raises(ValueError):
            validate_photo_url("https://192.168.1.1/photo.jpg")

    def test_aws_metadata_rejected(self):
        """S-02: AWS metadata endpoint заблоковано."""
        from app.services.ai_service import validate_photo_url
        with pytest.raises(ValueError):
            validate_photo_url("https://169.254.169.254/latest/meta-data/")

    def test_non_whitelisted_domain_rejected(self):
        """S-02: Домени поза whitelist відхиляються."""
        from app.services.ai_service import validate_photo_url
        with pytest.raises(ValueError, match="дозволеного домену"):
            validate_photo_url("https://evil.com/photo.jpg")


# ── Storage magic bytes тести ─────────────────────────────────────────────────

class TestStorageMagicBytes:
    def test_valid_jpeg_accepted(self):
        """S-11: JPEG magic bytes приймаються."""
        from app.services.storage_service import _validate_image_magic_bytes
        jpeg_content = b"\xff\xd8\xff" + b"\x00" * 100
        mime = _validate_image_magic_bytes(jpeg_content)
        assert mime == "image/jpeg"

    def test_valid_png_accepted(self):
        """S-11: PNG magic bytes приймаються."""
        from app.services.storage_service import _validate_image_magic_bytes
        png_content = b"\x89PNG" + b"\x00" * 100
        mime = _validate_image_magic_bytes(png_content)
        assert mime == "image/png"

    def test_fake_image_rejected(self):
        """S-11: Файл з неправильними magic bytes відхиляється."""
        from app.services.storage_service import _validate_image_magic_bytes
        from fastapi import HTTPException
        fake_content = b"<?php echo shell_exec($_GET['cmd']); ?>" + b"\x00" * 50
        with pytest.raises(HTTPException) as exc_info:
            _validate_image_magic_bytes(fake_content)
        assert exc_info.value.status_code == 400


# ── check_plants_limit R-03 тест ──────────────────────────────────────────────

class TestPlantsLimit:
    @pytest.mark.asyncio
    async def test_plants_limit_is_per_plot(self):
        """R-03: Ліміт рослин рахується для конкретного plot, а не для всього user."""
        # Мок: user має plants_limit=10, в plot 8 рослин → дозволено
        from unittest.mock import AsyncMock, MagicMock
        
        mock_user = MagicMock()
        mock_user.id = "user-uuid-123"
        mock_user.plants_limit = 10
        
        mock_plot = MagicMock()
        mock_plot.id = "plot-uuid-456"
        
        mock_db = AsyncMock()
        # Перший scalar → повертає plot
        # Другий scalar → повертає count=8 (в межах ліміту)
        mock_db.scalar = AsyncMock(side_effect=[mock_plot, 8])
        
        # Не повинно кидати HTTPException
        from app.dependencies import check_plants_limit
        result = await check_plants_limit(
            plot_id="plot-uuid-456",
            current_user=mock_user,
            db=mock_db,
        )
        assert result == mock_user
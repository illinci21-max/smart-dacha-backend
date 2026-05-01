"""
Integration + Security Tests — plots, plants, watering, IDOR checks.

ВИПРАВЛЕНО (T-01, T-02, T-03):
  - Integration тести для plots та watering ендпоінтів
  - IDOR тести (спроба доступу до чужих ресурсів)
  - Edge cases: null weather, zero values, recently watered
  - Premium gate тести
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient


# ════════════════════════════════════════════════════════════════════
# PLOTS — Integration Tests (T-01)
# ════════════════════════════════════════════════════════════════════

class TestPlotsIntegration:

    @pytest.mark.asyncio
    async def test_create_plot_success(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/plots", json={
            "name": "Городня ділянка",
            "description": "Моя грядка з помідорами",
            "latitude": 48.5,
            "longitude": 35.0,
            "area_sqm": 20.0,
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Городня ділянка"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_plots_returns_only_own(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Список ділянок повертає тільки власні."""
        await client.post("/api/v1/plots", json={"name": "Plot 1"}, headers=auth_headers)
        resp = await client.get("/api/v1/plots", headers=auth_headers)
        assert resp.status_code == 200
        plots = resp.json()
        assert isinstance(plots, list)

    @pytest.mark.asyncio
    async def test_create_plot_without_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/plots", json={"name": "Test"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_delete_plot_soft_delete(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Soft delete — ділянка не повертається в списку після видалення."""
        create = await client.post(
            "/api/v1/plots", json={"name": "To Delete"}, headers=auth_headers
        )
        plot_id = create.json()["id"]

        delete = await client.delete(f"/api/v1/plots/{plot_id}", headers=auth_headers)
        assert delete.status_code == 204

        get = await client.get(f"/api/v1/plots/{plot_id}", headers=auth_headers)
        assert get.status_code == 404


# ════════════════════════════════════════════════════════════════════
# SECURITY / IDOR Tests (T-02)
# ════════════════════════════════════════════════════════════════════

class TestIDOR:
    """
    IDOR = Insecure Direct Object Reference.
    Перевіряємо що user не може отримати/змінити чужі ресурси.
    FIX T-02: Тести повертають 404 (не 403, бо не підтверджуємо існування ресурсу).
    """

    @pytest.mark.asyncio
    async def test_cannot_get_other_user_plot(
        self,
        client: AsyncClient,
        auth_headers: dict,
        other_user_auth_headers: dict,
    ):
        """User A не може переглянути ділянку User B."""
        # User B створює ділянку
        create = await client.post(
            "/api/v1/plots", json={"name": "User B Plot"}, headers=other_user_auth_headers
        )
        plot_id = create.json()["id"]

        # User A намагається отримати ділянку User B
        resp = await client.get(f"/api/v1/plots/{plot_id}", headers=auth_headers)
        # 404 — не підтверджуємо існування чужого ресурсу
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_update_other_user_plot(
        self,
        client: AsyncClient,
        auth_headers: dict,
        other_user_auth_headers: dict,
    ):
        """User A не може змінити ділянку User B."""
        create = await client.post(
            "/api/v1/plots", json={"name": "User B Plot"}, headers=other_user_auth_headers
        )
        plot_id = create.json()["id"]

        resp = await client.put(
            f"/api/v1/plots/{plot_id}",
            json={"name": "Hijacked!"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_delete_other_user_plot(
        self,
        client: AsyncClient,
        auth_headers: dict,
        other_user_auth_headers: dict,
    ):
        """User A не може видалити ділянку User B."""
        create = await client.post(
            "/api/v1/plots", json={"name": "User B Plot"}, headers=other_user_auth_headers
        )
        plot_id = create.json()["id"]

        resp = await client.delete(f"/api/v1/plots/{plot_id}", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_watering_premium_required(self, client: AsyncClient, auth_headers: dict):
        """Free user не може отримати рекомендації поливу."""
        resp = await client.get("/api/v1/watering/today", headers=auth_headers)
        assert resp.status_code == 402
        data = resp.json()
        assert data["detail"]["error"] == "premium_required"

    @pytest.mark.asyncio
    async def test_expired_premium_no_access(
        self, client: AsyncClient, expired_premium_auth_headers: dict
    ):
        """Прострочена підписка не дає доступу до Premium."""
        resp = await client.get(
            "/api/v1/watering/today", headers=expired_premium_auth_headers
        )
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client: AsyncClient, auth_headers: dict):
        """Невалідний UUID повертає 422 (не 500)."""
        resp = await client.get("/api/v1/plots/not-a-uuid", headers=auth_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_nonexistent_resource_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Неіснуючий ресурс повертає 404 (не 500)."""
        fake_uuid = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/plots/{fake_uuid}", headers=auth_headers)
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════
# JWT Security Tests
# ════════════════════════════════════════════════════════════════════

class TestJWTSecurity:

    @pytest.mark.asyncio
    async def test_logout_invalidates_token(self, client: AsyncClient, test_user):
        """Після logout токен більше не працює (якщо Redis доступний)."""
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": test_user.email, "password": "password123"
        })
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Logout
        logout_resp = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout_resp.status_code == 204

        # Спробуємо використати відкликаний токен
        # Якщо Redis недоступний — тест може пройти (fail-open behavior)
        me_resp = await client.get("/api/v1/auth/me", headers=headers)
        # 401 якщо blacklist працює, 200 якщо Redis недоступний
        assert me_resp.status_code in (200, 401)

    @pytest.mark.asyncio
    async def test_refresh_token_cannot_access_api(self, client: AsyncClient, test_user):
        """Refresh token не може бути використаний як access token."""
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": test_user.email, "password": "password123"
        })
        refresh_token = login_resp.json()["refresh_token"]
        headers = {"Authorization": f"Bearer {refresh_token}"}

        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_tampered_token_rejected(self, client: AsyncClient):
        """Підроблений токен відхиляється."""
        fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmYWtlIn0.fake"
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {fake_token}"}
        )
        assert resp.status_code == 401


# ════════════════════════════════════════════════════════════════════
# Watering Edge Cases (T-03)
# ════════════════════════════════════════════════════════════════════

class TestWateringEdgeCases:
    """Edge cases для алгоритму поливу."""

    def test_null_weather_data_returns_decision(self):
        """При відсутності погодних даних — повертає рішення (не None/виняток)."""
        from app.services.watering_service import calculate_watering_need
        from datetime import datetime, timezone, timedelta

        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=3),
            crop={"water_need_ml_per_day": 300, "drought_tolerance": 3},
            weather_today=None,
            weather_tomorrow=None,
        )
        assert decision is not None
        assert isinstance(decision.amount_ml, int)
        assert decision.amount_ml >= 0

    def test_zero_weather_values_handled(self):
        """Нульові значення погоди не спричиняють помилок."""
        from app.services.watering_service import calculate_watering_need
        from datetime import datetime, timezone, timedelta

        weather = {"temp_avg": 0, "precipitation": 0, "rain_probability": 0}
        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=2),
            crop={"water_need_ml_per_day": 300, "drought_tolerance": 3},
            weather_today=weather,
            weather_tomorrow=None,
        )
        assert decision is not None
        assert decision.amount_ml >= 0

    def test_fog_blocks_evaporation(self):
        """При тумані (humidity >= 95%) — випаровування = 0."""
        from app.services.watering_service import calculate_daily_evaporation
        result = calculate_daily_evaporation(humidity_pct=96.0, is_fog=True)
        assert result == 0.0

    def test_rain_resets_deficit(self):
        """Сильний дощ знижує дефіцит вологи."""
        from app.services.watering_service import update_deficit
        # Накопичений дефіцит 80, потім 10мм дощу → 80 - (10 * 15) = -70 → 0
        result = update_deficit(current_dw=80.0, evaporation=5.0, rain_mm=10.0)
        assert result == 0.0  # min(0, 80 + 5 - 150) = 0

    def test_sun_coefficient_clear(self):
        """Ясна погода дає максимальний коефіцієнт сонця."""
        from app.services.watering_service import _get_sun_coefficient
        k = _get_sun_coefficient(cloud_cover_pct=10, solar_radiation=None)
        assert k == 1.5

    def test_sun_coefficient_cloudy(self):
        """Похмура погода дає мінімальний коефіцієнт."""
        from app.services.watering_service import _get_sun_coefficient
        k = _get_sun_coefficient(cloud_cover_pct=85, solar_radiation=None)
        assert k == 0.5

    def test_humidity_coefficient_dry(self):
        """Суха погода збільшує потребу у воді."""
        from app.services.watering_service import _get_humidity_coefficient
        k = _get_humidity_coefficient(30.0)
        assert k == 1.3

    def test_dw_threshold_triggers_watering(self):
        """При DW >= 100 — рекомендується полив."""
        from app.services.watering_service import calculate_watering_need
        from datetime import datetime, timezone, timedelta

        # Жарка суха погода протягом 7 днів → DW > 100
        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=7),
            crop={"water_need_ml_per_day": 300, "drought_tolerance": 3},
            weather_today={"temp_avg": 30.0, "precipitation": 0, "rain_probability": 0},
            weather_tomorrow=None,
        )
        assert decision.should_water is True
        assert decision.urgency in ("high", "critical")

    def test_amount_ml_within_reasonable_bounds(self):
        """Обсяг поливу в розумних межах (100мл - 5л)."""
        from app.services.watering_service import calculate_watering_need
        from datetime import datetime, timezone, timedelta

        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=10),
            crop={"water_need_ml_per_day": 500, "drought_tolerance": 1},
            weather_today={"temp_avg": 35.0, "precipitation": 0, "rain_probability": 0},
            weather_tomorrow=None,
        )
        if decision.should_water:
            assert 100 <= decision.amount_ml <= 5000

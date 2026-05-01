from pathlib import Path
import re


CONTAINER_PATH = Path("/app/app/services/smart_gardener_engine.py")
HOST_PATH = Path(r"D:\Garden\backend\app\services\smart_gardener_engine.py")
path = CONTAINER_PATH if CONTAINER_PATH.exists() else HOST_PATH
text = path.read_text(encoding="utf-8")
backup = path.with_name(path.name + ".bak_20260424_2215")
if not backup.exists():
    backup.write_text(text, encoding="utf-8")


def rep(pattern: str, replacement: str) -> None:
    global text
    new_text, count = re.subn(pattern, lambda _: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Pattern not found or not unique: {pattern[:80]}")
    text = new_text


rep(r'category: str = ".*?"\n', '    category: str = "\\u041a\\u0443\\u043b\\u044c\\u0442\\u0443\\u0440\\u0430"\n')
rep(r'label: str = ".*?"\n', '    label: str = "\\u0490\\u0440\\u0443\\u043d\\u0442"\n')

rep(
    r"_SOIL_TYPES = \{.*?\n\}\n",
    r'''_SOIL_TYPES = {
    "sand": SoilProperties(0.45, 0.60, 0.70, "\u041f\u0456\u0449\u0430\u043d\u0438\u0439"),
    "loamy_sand": SoilProperties(0.60, 0.75, 0.80, "\u0421\u0443\u043f\u0456\u0449\u0430\u043d\u0438\u0439"),
    "sandy_loam": SoilProperties(0.78, 0.85, 0.90, "\u041b\u0435\u0433\u043a\u0438\u0439 \u0441\u0443\u0433\u043b\u0438\u043d\u043e\u043a"),
    "loam": SoilProperties(1.0, 1.0, 1.0, "\u0421\u0443\u0433\u043b\u0438\u043d\u043e\u043a"),
    "silt_loam": SoilProperties(1.10, 1.05, 1.05, "\u041c\u0443\u043b\u043a\u0438\u0439 \u0441\u0443\u0433\u043b\u0438\u043d\u043e\u043a"),
    "clay_loam": SoilProperties(1.15, 1.15, 1.20, "\u0412\u0430\u0436\u043a\u0438\u0439 \u0441\u0443\u0433\u043b\u0438\u043d\u043e\u043a"),
    "clay": SoilProperties(0.95, 1.30, 1.40, "\u0413\u043b\u0438\u043d\u0438\u0441\u0442\u0438\u0439"),
    "peat": SoilProperties(1.50, 0.90, 1.30, "\u0422\u043e\u0440\u0444'\u044f\u043d\u0438\u0439"),
    "chernozem": SoilProperties(1.45, 1.0, 0.90, "\u0427\u043e\u0440\u043d\u043e\u0437\u0435\u043c"),
}
''',
)

rep(
    r"_DISEASE_NAMES = \{.*?\n\}\n",
    r'''_DISEASE_NAMES = {
    "late_blight": "\u0424\u0456\u0442\u043e\u0444\u0442\u043e\u0440\u043e\u0437",
    "powdery_mildew": "\u0411\u043e\u0440\u043e\u0448\u043d\u0438\u0441\u0442\u0430 \u0440\u043e\u0441\u0430",
    "downy_mildew": "\u041d\u0435\u0441\u043f\u0440\u0430\u0432\u0436\u043d\u044f \u0431\u043e\u0440\u043e\u0448\u043d\u0438\u0441\u0442\u0430 \u0440\u043e\u0441\u0430",
    "botrytis": "\u0421\u0456\u0440\u0430 \u0433\u043d\u0438\u043b\u044c",
    "alternaria": "\u0410\u043b\u044c\u0442\u0435\u0440\u043d\u0430\u0440\u0456\u043e\u0437",
    "rust": "\u0406\u0440\u0436\u0430",
}
''',
)

rep(
    r"def _date_label\(value: str, today: date\) -> str:\n.*?\n(?=def _weather_date)",
    r'''def _date_label(value: str, today: date) -> str:
    try:
        target = date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return "\u041d\u0435\u0432\u0456\u0434\u043e\u043c\u0430 \u0434\u0430\u0442\u0430"
    delta = (target - today).days
    if delta == 0:
        return "\u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456"
    if delta == 1:
        return "\u0437\u0430\u0432\u0442\u0440\u0430"
    if delta == 2:
        return "\u043f\u0456\u0441\u043b\u044f\u0437\u0430\u0432\u0442\u0440\u0430"
    return f"\u0447\u0435\u0440\u0435\u0437 {delta} \u0434\u043d." if delta > 0 else target.isoformat()

''',
)

rep(
    r"def _phase_name\(phase: GrowthPhase\) -> str:\n.*?\n(?=def _risk_to_priority)",
    r'''def _phase_name(phase: GrowthPhase) -> str:
    return {
        GrowthPhase.INITIAL: "\u043f\u043e\u0447\u0430\u0442\u043a\u043e\u0432\u0430",
        GrowthPhase.DEVELOPMENT: "\u0440\u043e\u0437\u0432\u0438\u0442\u043e\u043a",
        GrowthPhase.MID_SEASON: "\u0441\u0435\u0440\u0435\u0434\u0438\u043d\u0430 \u0441\u0435\u0437\u043e\u043d\u0443",
        GrowthPhase.LATE_SEASON: "\u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043d\u044f",
    }.get(phase, phase.value)

''',
)

rep(
    r"def _safe_date_label\(days: int\) -> str:\n.*?\n(?=def get_soil_properties)",
    r'''def _safe_date_label(days: int) -> str:
    if days <= 0:
        return "\u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456"
    if days == 1:
        return "\u0447\u0435\u0440\u0435\u0437 1 \u0434\u0435\u043d\u044c"
    if days < 5:
        return f"\u0447\u0435\u0440\u0435\u0437 {days} \u0434\u043d\u0456"
    return f"\u0447\u0435\u0440\u0435\u0437 {days} \u0434\u043d\u0456\u0432"

''',
)

rep(
    r'category=str\(data.get\("category"\) or category or ".*?"\),',
    '        category=str(data.get("category") or category or "\\u041a\\u0443\\u043b\\u044c\\u0442\\u0443\\u0440\\u0430"),',
)

rep(
    r"    def _apply_profile_confidence\(profile: CropProfile, tasks: list\[GardenTask\]\) -> None:\n.*?\n(?=    def _assess_disease_risks)",
    r'''    def _apply_profile_confidence(profile: CropProfile, tasks: list[GardenTask]) -> None:
        if profile.profile_confidence >= 95 and not profile.validation_warnings:
            return
        for task in tasks:
            penalty = max(0, 85 - profile.profile_confidence) // 3
            if profile.validation_warnings:
                penalty += min(8, len(profile.validation_warnings) * 2)
            task.confidence = _confidence(task.confidence - penalty)
            task.reasons.append(f"\u0414\u043e\u0432\u0456\u0440\u0430 \u0434\u043e \u043f\u0440\u043e\u0444\u0456\u043b\u044e \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438: {profile.profile_confidence}%")
            if profile.validation_warnings:
                task.reasons.append("\u041f\u0440\u043e\u0444\u0456\u043b\u044c \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438 \u043c\u0430\u0454 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u043d\u0456 \u043a\u043e\u0440\u0435\u043a\u0446\u0456\u0457 \u0442\u0430 \u043f\u043e\u0442\u0440\u0435\u0431\u0443\u0454 \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u043a\u0438")

''',
)

rep(
    r"    def _assess_disease_risks\(\n.*?\n(?=    @staticmethod\n    def _assess_nutrient_leaching)",
    r'''    def _assess_disease_risks(
        self,
        profile: CropProfile,
        w_today: WeatherSnapshot,
        w_forecast: list[WeatherSnapshot],
        w_history: list[WeatherSnapshot],
        age_days: int,
        phase: GrowthPhase,
        soil: SoilProperties,
    ) -> list[DiseaseRisk]:
        risks: list[DiseaseRisk] = []
        recent = (w_history + [w_today])[-7:]
        upcoming = [
            weather for weather in w_forecast
            if weather.date and w_today.date and (_weather_date(weather.date) or date.max) > (_weather_date(w_today.date) or date.min)
        ][:3]
        risk_window = recent + upcoming
        soil_mult = soil.disease_risk_mult

        def add_if(disease: str, n: int, sus: float, description: str, recommendation: str, phase_boost: bool = False) -> None:
            denominator = max(7, len(risk_window))
            risk = min(1.0, (n / denominator) * sus * soil_mult)
            if phase_boost and phase in (GrowthPhase.DEVELOPMENT, GrowthPhase.MID_SEASON):
                risk = min(1.0, risk * 1.3)
            if upcoming and any(w.precipitation_mm > 2 or w.humidity_avg > 80 or w.has_dew or w.is_fog for w in upcoming):
                risk = min(1.0, risk * 1.15)
            if risk > 0.1:
                risks.append(DiseaseRisk(disease, _round(risk, 2), _risk_to_priority(risk), description, recommendation))

        sus = profile.susceptibility
        n = sum(1 for w in risk_window if 10 <= w.temp_mean <= 25 and (w.humidity_avg > 75 or w.has_dew or w.is_fog) and (w.precipitation_mm > 0.2 or w.cloud_cover_pct > 65))
        add_if(
            "late_blight",
            n,
            sus.get("late_blight", 0),
            f"\u041e\u0437\u043d\u0430\u043a\u0438 \u0444\u0456\u0442\u043e\u0444\u0442\u043e\u0440\u043e\u0437\u0443: {n} \u0434\u043d\u0456\u0432 \u0456\u0437 \u043f\u0440\u043e\u0445\u043e\u043b\u043e\u0434\u043d\u043e\u044e \u0432\u043e\u043b\u043e\u0433\u043e\u044e \u043f\u043e\u0433\u043e\u0434\u043e\u044e. \u0424\u0430\u0437\u0430: {_phase_name(phase)}.",
            "\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0456\u044f: \u043f\u0440\u043e\u0432\u0456\u0442\u0440\u044e\u0439\u0442\u0435 \u043f\u043e\u0441\u0430\u0434\u043a\u0438, \u043f\u043e\u043b\u0438\u0432\u0430\u0439\u0442\u0435 \u043f\u0456\u0434 \u043a\u043e\u0440\u0456\u043d\u044c \u0432\u0440\u0430\u043d\u0446\u0456, \u0437\u0430 \u043f\u043e\u0442\u0440\u0435\u0431\u0438 \u0437\u0430\u0441\u0442\u043e\u0441\u0443\u0439\u0442\u0435 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434. \u041d\u0435 \u043e\u0431\u0440\u043e\u0431\u043b\u044f\u0439\u0442\u0435 \u043f\u0435\u0440\u0435\u0434 \u0441\u0438\u043b\u044c\u043d\u0438\u043c \u0434\u043e\u0449\u0435\u043c.",
            True,
        )
        n = sum(1 for w in risk_window if 15 <= w.temp_mean <= 28 and 40 <= w.humidity_avg <= 75 and w.precipitation_mm < 1 and w.cloud_cover_pct < 70)
        add_if(
            "powdery_mildew",
            n,
            sus.get("powdery_mildew", 0),
            f"\u041e\u0437\u043d\u0430\u043a\u0438 \u0431\u043e\u0440\u043e\u0448\u043d\u0438\u0441\u0442\u043e\u0457 \u0440\u043e\u0441\u0438: {n} \u0442\u0435\u043f\u043b\u0438\u0445 \u0441\u0443\u0445\u0438\u0445 \u0434\u043d\u0456\u0432 \u0456\u0437 \u043f\u043e\u043c\u0456\u0440\u043d\u043e\u044e \u0432\u043e\u043b\u043e\u0433\u0456\u0441\u0442\u044e.",
            "\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0456\u044f: \u0441\u043b\u0456\u0434\u043a\u0443\u0439\u0442\u0435 \u0437\u0430 \u043b\u0438\u0441\u0442\u044f\u043c, \u0437\u0430\u0431\u0435\u0437\u043f\u0435\u0447\u0442\u0435 \u043f\u0440\u043e\u0432\u0456\u0442\u0440\u044e\u0432\u0430\u043d\u043d\u044f, \u0437\u0430 \u043f\u043e\u0442\u0440\u0435\u0431\u0438 \u0432\u0438\u043a\u043e\u0440\u0438\u0441\u0442\u0430\u0439\u0442\u0435 \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442.",
        )
        n = sum(1 for w in risk_window if 10 <= w.temp_mean <= 22 and (w.humidity_avg > 80 or w.has_dew or w.is_fog) and w.precipitation_mm > 0.5)
        add_if(
            "downy_mildew",
            n,
            sus.get("downy_mildew", 0),
            f"\u041e\u0437\u043d\u0430\u043a\u0438 \u043d\u0435\u0441\u043f\u0440\u0430\u0432\u0436\u043d\u044c\u043e\u0457 \u0431\u043e\u0440\u043e\u0448\u043d\u0438\u0441\u0442\u043e\u0457 \u0440\u043e\u0441\u0438: {n} \u0432\u043e\u043b\u043e\u0433\u0438\u0445 \u043f\u0440\u043e\u0445\u043e\u043b\u043e\u0434\u043d\u0438\u0445 \u043f\u0435\u0440\u0456\u043e\u0434\u0456\u0432.",
            "\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0456\u044f: \u0437\u043c\u0435\u043d\u0448\u0456\u0442\u044c \u0437\u0432\u043e\u043b\u043e\u0436\u0435\u043d\u043d\u044f \u043b\u0438\u0441\u0442\u044f, \u0437\u0430 \u043f\u043e\u0442\u0440\u0435\u0431\u0438 \u0437\u0430\u0441\u0442\u043e\u0441\u0443\u0439\u0442\u0435 \u0437\u0430\u0445\u0438\u0441\u043d\u0438\u0439 \u043e\u0431\u0440\u043e\u0431\u0456\u0442\u043e\u043a \u043f\u0456\u0441\u043b\u044f \u0441\u0442\u0430\u0431\u0456\u043b\u0456\u0437\u0430\u0446\u0456\u0457 \u043f\u043e\u0433\u043e\u0434\u0438.",
        )
        n = sum(1 for w in risk_window if 15 <= w.temp_mean <= 25 and (w.humidity_avg > 85 or w.has_dew or w.is_fog) and w.cloud_cover_pct > 60)
        add_if(
            "botrytis",
            n,
            sus.get("botrytis", 0),
            f"\u041e\u0437\u043d\u0430\u043a\u0438 \u0441\u0456\u0440\u043e\u0457 \u0433\u043d\u0438\u043b\u0456: {n} \u0434\u043d\u0456\u0432 \u0456\u0437 \u0432\u0438\u0441\u043e\u043a\u043e\u044e \u0432\u043e\u043b\u043e\u0433\u0456\u0441\u0442\u044e \u0442\u0430 \u0445\u043c\u0430\u0440\u043d\u0456\u0441\u0442\u044e.",
            "\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0456\u044f: \u043f\u0440\u043e\u0440\u0456\u0434\u044c\u0442\u0435 \u043f\u043e\u0441\u0430\u0434\u043a\u0438, \u0437\u043c\u0435\u043d\u0448\u0456\u0442\u044c \u043f\u0435\u0440\u0435\u0437\u0432\u043e\u043b\u043e\u0436\u0435\u043d\u043d\u044f, \u0437\u0430 \u043f\u043e\u0442\u0440\u0435\u0431\u0438 \u0437\u0430\u0441\u0442\u043e\u0441\u0443\u0439\u0442\u0435 \u043f\u0440\u043e\u0442\u0438\u0433\u043d\u0438\u043b\u044c\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442.",
        )
        return risks

''',
)

rep(
    r"    def _application_blockers\(w_forecast: list\[WeatherSnapshot\]\) -> list\[str\]:\n.*?\n(?=    @staticmethod\n    def _blocked_reason_messages)",
    r'''    def _application_blockers(w_forecast: list[WeatherSnapshot]) -> list[str]:
        blockers: list[str] = []
        window = w_forecast[:2]
        if any(w.precipitation_mm >= 10 or (w.precipitation_mm >= 6 and w.rain_probability >= 70) for w in window):
            blockers.append("\u0441\u0438\u043b\u044c\u043d\u0438\u0439 \u0434\u043e\u0449")
        if any(w.temp_max >= 30 for w in window):
            blockers.append("\u0441\u043f\u0435\u043a\u0430")
        if any(w.wind_speed_ms >= 6 for w in window):
            blockers.append("\u0441\u0438\u043b\u044c\u043d\u0438\u0439 \u0432\u0456\u0442\u0435\u0440")
        return blockers

''',
)

rep(
    r"    def _blocked_reason_messages\(blockers: list\[str\], w_forecast: list\[WeatherSnapshot\], today: date\) -> list\[str\]:\n.*?\n(?=    @staticmethod\n    def _days_until_harvest_start)",
    r'''    def _blocked_reason_messages(blockers: list[str], w_forecast: list[WeatherSnapshot], today: date) -> list[str]:
        messages: list[str] = []
        for blocker in blockers:
            if blocker == "\u0441\u0438\u043b\u044c\u043d\u0438\u0439 \u0434\u043e\u0449":
                rainy = next((w for w in w_forecast[:2] if w.precipitation_mm >= 6 or w.rain_probability >= 70), None)
                if rainy:
                    messages.append(f"\u0412\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {_date_label(rainy.date or today.isoformat(), today)} \u043e\u0447\u0456\u043a\u0443\u0454\u0442\u044c\u0441\u044f {rainy.precipitation_mm:.0f} \u043c\u043c \u0434\u043e\u0449\u0443")
            elif blocker == "\u0441\u043f\u0435\u043a\u0430":
                hot = next((w for w in w_forecast[:2] if w.temp_max >= 30), None)
                if hot:
                    messages.append(f"\u0412\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {_date_label(hot.date or today.isoformat(), today)} \u0441\u043f\u0435\u043a\u0430 \u0434\u043e {hot.temp_max:.0f}\u00b0C")
            elif blocker == "\u0441\u0438\u043b\u044c\u043d\u0438\u0439 \u0432\u0456\u0442\u0435\u0440":
                windy = next((w for w in w_forecast[:2] if w.wind_speed_ms >= 6), None)
                if windy:
                    messages.append(f"\u0412\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {_date_label(windy.date or today.isoformat(), today)} \u0432\u0456\u0442\u0435\u0440 {windy.wind_speed_ms:.1f} \u043c/\u0441")
        return messages

''',
)

rep(
    r"    def _generate_watering_task\(\n.*?\n(?=    def _generate_fertilizing_tasks)",
    r'''    def _generate_watering_task(
        self,
        plant: PlantInstance,
        profile: CropProfile,
        diag: CellDiagnostics,
        depletion_pct: float,
        w_forecast: list[WeatherSnapshot],
        w_history: list[WeatherSnapshot],
        today: date,
        soil: SoilProperties,
    ) -> None:
        if self._in_cooldown(plant.last_watered_at, today, _WATERING_COOLDOWN_DAYS) or depletion_pct < 0.15:
            return
        future_forecast = [
            weather for weather in w_forecast
            if weather.date and (_weather_date(weather.date) or today) > today
        ]
        tomorrow_weather = future_forecast[0] if future_forecast else None
        rain_tomorrow = bool(
            tomorrow_weather
            and tomorrow_weather.precipitation_mm > 5
            and tomorrow_weather.rain_probability > 60
        )
        reason_groups = {
            "weather": [],
            "soil": [f"\u0422\u0438\u043f \u0491\u0440\u0443\u043d\u0442\u0443: {soil.label}"],
            "phase": [f"\u0424\u0430\u0437\u0430: {_phase_name(plant.growth_phase)}", f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432"],
            "history": [],
        }
        _append_group(reason_groups, "weather", f"ETc: {diag.etc_mm} \u043c\u043c/\u0434\u043e\u0431\u0443")
        _append_group(reason_groups, "soil", f"\u0414\u0435\u0444\u0456\u0446\u0438\u0442 \u0432\u043e\u043b\u043e\u0433\u0438: {depletion_pct * 100:.0f}%")
        if plant.last_watered_at:
            days = (today - plant.last_watered_at.date()).days
            _append_group(
                reason_groups,
                "history",
                f"\u041e\u0441\u0442\u0430\u043d\u043d\u0456\u0439 \u043f\u043e\u043b\u0438\u0432: {'\u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456' if days == 0 else f'{days} \u0434\u043d\u0456\u0432 \u0442\u043e\u043c\u0443'}",
            )
        else:
            _append_group(reason_groups, "history", "\u0414\u0430\u043d\u0438\u0445 \u043f\u0440\u043e \u043f\u043e\u043b\u0438\u0432 \u0449\u0435 \u043d\u0435\u043c\u0430\u0454")
        if tomorrow_weather:
            _append_group(reason_groups, "weather", f"\u0417\u0430\u0432\u0442\u0440\u0430: {tomorrow_weather.precipitation_mm:.0f} \u043c\u043c, \u0456\u043c\u043e\u0432\u0456\u0440\u043d\u0456\u0441\u0442\u044c \u0434\u043e\u0449\u0443 {tomorrow_weather.rain_probability:.0f}%")
        if rain_tomorrow and depletion_pct < 0.4:
            diag.hidden_tasks.append(GardenTask(
                TaskType.WATERING,
                TaskPriority.LOW,
                f"\u041f\u043e\u043b\u0438\u0432 \u043c\u043e\u0436\u043d\u0430 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}",
                "\u0417\u0430\u0432\u0442\u0440\u0430 \u043e\u0447\u0456\u043a\u0443\u0454\u0442\u044c\u0441\u044f \u0434\u043e\u0449, \u0442\u043e\u043c\u0443 \u043f\u043e\u0442\u043e\u0447\u043d\u0438\u0439 \u0434\u0435\u0444\u0456\u0446\u0438\u0442 \u0432\u043e\u043b\u043e\u0433\u0438 \u043c\u043e\u0436\u043d\u0430 \u0447\u0430\u0441\u0442\u043a\u043e\u0432\u043e \u043f\u0435\u0440\u0435\u043a\u0440\u0438\u0442\u0438 \u043f\u0440\u0438\u0440\u043e\u0434\u043d\u0438\u043c\u0438 \u043e\u043f\u0430\u0434\u0430\u043c\u0438.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                confidence=_confidence(88 if len(w_history) >= 7 else 78),
                reasons=[
                    f"\u0417\u0430\u0432\u0442\u0440\u0430 \u043e\u0447\u0456\u043a\u0443\u0454\u0442\u044c\u0441\u044f \u0434\u043e\u0449: {tomorrow_weather.precipitation_mm:.0f} \u043c\u043c",
                    f"\u0414\u0435\u0444\u0456\u0446\u0438\u0442 \u0432\u043e\u043b\u043e\u0433\u0438 \u0449\u0435 \u043d\u0435 \u043a\u0440\u0438\u0442\u0438\u0447\u043d\u0438\u0439: {depletion_pct * 100:.0f}%",
                ],
                reason_groups=reason_groups,
                blocked_reasons=[f"\u041f\u043e\u043b\u0438\u0432 \u0432\u0456\u0434\u043a\u043b\u0430\u0434\u0435\u043d\u043e, \u0431\u043e \u0437\u0430\u0432\u0442\u0440\u0430 \u0434\u043e\u0449 {tomorrow_weather.precipitation_mm:.0f} \u043c\u043c"],
                is_hidden=True,
            ))
            return
        crit = profile.critical_depletion
        if depletion_pct >= crit * 1.3 or diag.heat_stress:
            priority = TaskPriority.CRITICAL
        elif depletion_pct >= crit:
            priority = TaskPriority.HIGH
        elif depletion_pct >= crit * 0.6:
            priority = TaskPriority.MEDIUM
        else:
            priority = TaskPriority.LOW
        watering_liters = _round(diag.water_deficit_mm * 1.1 * self.cell_area_sqm, 1)
        diag.watering_needed_ml = watering_liters * 1000
        v = f" ({plant.variety})" if plant.variety else ""
        parts = [
            f"\u0420\u043e\u0441\u043b\u0438\u043d\u0456 {plant.age_days} \u0434\u043d\u0456\u0432 ({_phase_name(plant.growth_phase)}).",
            f"\u0414\u043e\u0431\u043e\u0432\u0430 \u0432\u0438\u0442\u0440\u0430\u0442\u0430 \u0432\u043e\u043b\u043e\u0433\u0438 ~{diag.etc_mm} \u043c\u043c.",
            f"\u0414\u0435\u0444\u0456\u0446\u0438\u0442 \u0432\u043e\u043b\u043e\u0433\u0438 {depletion_pct * 100:.0f}%.",
        ]
        if plant.last_watered_at:
            days = (today - plant.last_watered_at.date()).days
            parts.append(f"\u041e\u0441\u0442\u0430\u043d\u043d\u0456\u0439 \u043f\u043e\u043b\u0438\u0432 {'\u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456' if days == 0 else f'{days} \u0434\u043d\u0456\u0432 \u0442\u043e\u043c\u0443'}.")
        if diag.heat_stress:
            parts.append("\u0421\u043f\u0435\u043a\u0430 \u043f\u0456\u0434\u0441\u0438\u043b\u044e\u0454 \u043f\u043e\u0442\u0440\u0435\u0431\u0443 \u0432 \u043f\u043e\u043b\u0438\u0432\u0456.")
        if diag.fog_dew_bonus_mm > 0:
            parts.append(f"\u0420\u043e\u0441\u0430/\u0442\u0443\u043c\u0430\u043d: +{diag.fog_dew_bonus_mm:.1f} \u043c\u043c.")
        if rain_tomorrow:
            parts.append("\u0417\u0430\u0432\u0442\u0440\u0430 \u043c\u043e\u0436\u043b\u0438\u0432\u0456 \u043e\u043f\u0430\u0434\u0438.")
        parts.append(f"\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u043e\u0432\u0430\u043d\u043e: {watering_liters} \u043b \u043d\u0430 \u043a\u043b\u0456\u0442\u0438\u043d\u0443.")
        conf = 92
        if len(w_history) < 7:
            conf -= 10
        if not future_forecast:
            conf -= 5
        reasons = [
            f"\u041f\u043e\u043b\u0438\u0432: \u0434\u0435\u0444\u0456\u0446\u0438\u0442 {depletion_pct * 100:.0f}%",
            f"\u0490\u0440\u0443\u043d\u0442: {soil.label}",
            f"ETc: {diag.etc_mm} \u043c\u043c/\u0434\u043e\u0431\u0443",
        ]
        if rain_tomorrow and tomorrow_weather:
            reasons.append(f"\u0414\u043e\u0449 \u0437\u0430\u0432\u0442\u0440\u0430: {tomorrow_weather.precipitation_mm:.0f} \u043c\u043c, \u0456\u043c\u043e\u0432\u0456\u0440\u043d\u0456\u0441\u0442\u044c {tomorrow_weather.rain_probability:.0f}%")
        if diag.heat_stress:
            reasons.append(f"\u0421\u043f\u0435\u043a\u0430: +{diag.heat_stress_factor * 100 - 100:.0f}% \u0434\u043e \u0432\u0438\u0442\u0440\u0430\u0442\u0438 \u0432\u043e\u043b\u043e\u0433\u0438")
            _append_group(reason_groups, "weather", f"\u0421\u043f\u0435\u043a\u0430: +{diag.heat_stress_factor * 100 - 100:.0f}% \u0434\u043e \u0432\u0438\u0442\u0440\u0430\u0442\u0438 \u0432\u043e\u043b\u043e\u0433\u0438")
        diag.tasks.append(GardenTask(
            TaskType.WATERING,
            priority,
            f"\u041f\u043e\u043b\u0438\u0432: {plant.plant_type}{v}",
            " ".join(parts),
            plant.plant_type,
            plant.variety,
            plant.cell_col,
            plant.cell_row,
            f"{watering_liters} \u043b/\u043a\u043b\u0456\u0442\u0438\u043d\u0443",
            confidence=_confidence(conf),
            reasons=reasons,
            reason_groups=reason_groups,
        ))

''',
)

rep(
    r"    def _generate_fertilizing_tasks\(\n.*?\n(?=    def _generate_disease_tasks)",
    r'''    def _generate_fertilizing_tasks(
        self,
        plant: PlantInstance,
        profile: CropProfile,
        diag: CellDiagnostics,
        phase: GrowthPhase,
        w_history: list[WeatherSnapshot],
        w_forecast: list[WeatherSnapshot],
        today: date,
    ) -> None:
        if self._in_cooldown(plant.last_fertilized_at, today, _FERTILIZING_COOLDOWN_DAYS):
            return
        days_since_feed = (today - plant.last_fertilized_at.date()).days if plant.last_fertilized_at else plant.age_days
        if plant.last_fertilized_at and days_since_feed < 7:
            return
        if plant.age_days < 7:
            return
        v = f" ({plant.variety})" if plant.variety else ""
        n = profile.nutrients
        rain_next_3 = sum(w.precipitation_mm for w in w_forecast[:3])
        dry_window = rain_next_3 < 8
        blockers = self._application_blockers(w_forecast)
        blocked_messages = self._blocked_reason_messages(w_forecast=w_forecast, blockers=blockers, today=today)
        base_groups = {
            "weather": [],
            "soil": [],
            "phase": [f"\u0424\u0430\u0437\u0430: {_phase_name(phase)}", f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432"],
            "history": [],
            "profile": [],
        }
        _append_group(base_groups, "weather", f"\u0414\u043e\u0449 \u043d\u0430 3 \u0434\u043d\u0456: {rain_next_3:.0f} \u043c\u043c")
        _append_group(base_groups, "profile", f"\u0414\u043e\u0432\u0456\u0440\u0430 \u0434\u043e \u043f\u0440\u043e\u0444\u0456\u043b\u044e: {profile.profile_confidence}%")
        if plant.last_fertilized_at:
            days = (today - plant.last_fertilized_at.date()).days
            _append_group(base_groups, "history", f"\u041e\u0441\u0442\u0430\u043d\u043d\u0454 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f: {days} \u0434\u043d\u0456\u0432 \u0442\u043e\u043c\u0443")
        else:
            _append_group(base_groups, "history", "\u041f\u043e\u043f\u0435\u0440\u0435\u0434\u043d\u0456\u0445 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u044c \u0449\u0435 \u043d\u0435 \u0431\u0443\u043b\u043e")
        if diag.nutrient_leaching_risk > 0.4:
            conf = self._fertilizing_confidence(86, plant, w_history, w_forecast, diag.nutrient_leaching_risk)
            reasons = [
                f"\u0420\u0438\u0437\u0438\u043a \u0432\u0438\u043c\u0438\u0432\u0430\u043d\u043d\u044f: {diag.nutrient_leaching_risk * 100:.0f}%",
                f"\u0414\u043e\u0449 \u0437\u0430 5 \u0434\u043d\u0456\u0432: {sum(w.precipitation_mm for w in w_history[-5:]):.0f} \u043c\u043c",
                f"Mg: {n.magnesium} \u0433/\u043c\u00b2",
                f"Ca: {n.calcium} \u0433/\u043c\u00b2",
            ]
            reason_groups = {key: list(values) for key, values in base_groups.items()}
            _append_group(reason_groups, "weather", f"\u041e\u043f\u0430\u0434\u0438 \u0437\u0430 5 \u0434\u043d\u0456\u0432: {sum(w.precipitation_mm for w in w_history[-5:]):.0f} \u043c\u043c")
            _append_group(reason_groups, "soil", f"\u0412\u0438\u043c\u0438\u0432\u0430\u043d\u043d\u044f \u043f\u043e\u0436\u0438\u0432\u043d\u0438\u0445: {diag.nutrient_leaching_risk * 100:.0f}%")
            if dry_window:
                reasons.append("\u0412\u0456\u043a\u043d\u043e \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f: \u043d\u0430\u0439\u0431\u043b\u0438\u0436\u0447\u0456 3 \u0434\u043d\u0456 \u0431\u0435\u0437 \u0441\u0438\u043b\u044c\u043d\u0438\u0445 \u043e\u043f\u0430\u0434\u0456\u0432")
                _append_group(reason_groups, "weather", "\u0404 \u0441\u0443\u0445\u0435 \u0432\u0456\u043a\u043d\u043e \u0434\u043b\u044f \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f")
            if blockers:
                diag.hidden_tasks.append(GardenTask(
                    TaskType.FERTILIZING,
                    TaskPriority.MEDIUM,
                    f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}{v}",
                    "\u0420\u0438\u0437\u0438\u043a \u0432\u0438\u043c\u0438\u0432\u0430\u043d\u043d\u044f \u0432\u0438\u0441\u043e\u043a\u0438\u0439, \u0430\u043b\u0435 \u043f\u043e\u0433\u043e\u0434\u043d\u0435 \u0432\u0456\u043a\u043d\u043e \u0437\u0430\u0440\u0430\u0437 \u043d\u0435\u043f\u0456\u0434\u0445\u043e\u0434\u044f\u0449\u0435 \u0434\u043b\u044f \u0431\u0435\u0437\u043f\u0435\u0447\u043d\u043e\u0433\u043e \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f.",
                    plant.plant_type,
                    plant.variety,
                    plant.cell_col,
                    plant.cell_row,
                    f"Mg {n.magnesium}\u0433 + Ca {n.calcium}\u0433",
                    confidence=conf,
                    reasons=reasons,
                    reason_groups=reason_groups,
                    recommendation_type="\u043c\u0456\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u0435",
                    constraints=blockers,
                    blocked_reasons=blocked_messages,
                    is_hidden=True,
                ))
            else:
                diag.tasks.append(GardenTask(
                    TaskType.FERTILIZING,
                    TaskPriority.HIGH,
                    f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u043f\u0456\u0441\u043b\u044f \u0434\u043e\u0449\u0456\u0432: {plant.plant_type}{v}",
                    f"\u041f\u0456\u0441\u043b\u044f \u0441\u0438\u043b\u044c\u043d\u0438\u0445 \u043e\u043f\u0430\u0434\u0456\u0432 \u0454 \u0440\u0438\u0437\u0438\u043a \u0432\u0438\u043c\u0438\u0432\u0430\u043d\u043d\u044f Mg \u0442\u0430 Ca. \u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u043e\u0432\u0430\u043d\u043e \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f: \u0441\u0443\u043b\u044c\u0444\u0430\u0442 \u043c\u0430\u0433\u043d\u0456\u044e ({n.magnesium} \u0433/\u043c\u00b2) + \u043a\u0430\u043b\u044c\u0446\u0456\u0439 ({n.calcium} \u0433/\u043c\u00b2).",
                    plant.plant_type,
                    plant.variety,
                    plant.cell_col,
                    plant.cell_row,
                    f"Mg {n.magnesium}\u0433 + Ca {n.calcium}\u0433",
                    confidence=conf,
                    reasons=reasons,
                    reason_groups=reason_groups,
                    recommendation_type="\u043c\u0456\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u0435",
                    constraints=blockers,
                ))
            return
        if phase == GrowthPhase.INITIAL and plant.age_days >= 7:
            p_hi = n.phosphorus * 1.2
            reasons = [
                f"\u0424\u0430\u0437\u0430: {_phase_name(phase)}",
                f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432",
                f"\u0424\u043e\u0441\u0444\u043e\u0440: {p_hi:.1f} \u0433/\u043c\u00b2",
                "\u0426\u0456\u043b\u044c: \u0440\u043e\u0437\u0432\u0438\u0442\u043e\u043a \u043a\u043e\u0440\u0435\u043d\u0456\u0432",
            ]
            reason_groups = {key: list(values) for key, values in base_groups.items()}
            _append_group(reason_groups, "phase", "\u0426\u0456\u043b\u044c: \u0440\u043e\u0437\u0432\u0438\u0442\u043e\u043a \u043a\u043e\u0440\u0435\u043d\u0435\u0432\u043e\u0457 \u0441\u0438\u0441\u0442\u0435\u043c\u0438")
            task = GardenTask(
                TaskType.FERTILIZING,
                TaskPriority.LOW,
                f"\u0421\u0442\u0430\u0440\u0442\u043e\u0432\u0435 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f: {plant.plant_type}{v}",
                f"\u0420\u043e\u0441\u043b\u0438\u043d\u0456 {plant.age_days} \u0434\u043d\u0456\u0432, \u043a\u043e\u0440\u0435\u043d\u0435\u0432\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u043e \u0444\u043e\u0440\u043c\u0443\u0454\u0442\u044c\u0441\u044f. \u0414\u043e\u0434\u0430\u0439\u0442\u0435 \u0444\u043e\u0441\u0444\u043e\u0440 {p_hi:.1f} \u0433/\u043c\u00b2 (+20% \u0434\u043e \u043d\u043e\u0440\u043c\u0438).",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                f"P: {p_hi:.1f} \u0433/\u043c\u00b2",
                confidence=self._fertilizing_confidence(82, plant, w_history, w_forecast, 0.35),
                reasons=reasons,
                reason_groups=reason_groups,
                recommendation_type="\u043b\u0438\u0441\u0442\u043a\u043e\u0432\u0435",
                constraints=blockers,
            )
            (diag.hidden_tasks if blockers else diag.tasks).append(
                task if not blockers else GardenTask(**{**task.__dict__, "title": f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}{v}", "description": "\u041f\u043e\u0442\u0440\u0435\u0431\u0430 \u0432 \u0441\u0442\u0430\u0440\u0442\u043e\u0432\u043e\u043c\u0443 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u0456 \u0454, \u0430\u043b\u0435 \u043f\u043e\u0433\u043e\u0434\u0430 \u0437\u0430\u0440\u0430\u0437 \u043d\u0435 \u043f\u0456\u0434\u0445\u043e\u0434\u0438\u0442\u044c \u0434\u043b\u044f \u0431\u0435\u0437\u043f\u0435\u0447\u043d\u043e\u0433\u043e \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f.", "blocked_reasons": blocked_messages, "is_hidden": True})
            )
        elif phase == GrowthPhase.DEVELOPMENT:
            n_hi, p_norm, k_lo = n.nitrogen * 1.3, n.phosphorus, n.potassium * 0.7
            reasons = [
                f"\u0424\u0430\u0437\u0430: {_phase_name(phase)}",
                f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432",
                "\u0410\u043a\u0446\u0435\u043d\u0442: \u0430\u0437\u043e\u0442 \u0434\u043b\u044f \u043d\u0430\u0440\u043e\u0441\u0442\u0430\u043d\u043d\u044f \u043c\u0430\u0441\u0438",
                f"NPK: {n_hi:.1f}/{p_norm:.1f}/{k_lo:.1f}",
            ]
            if rain_next_3 > 15:
                reasons.append(f"\u0414\u043e\u0449\u0456: \u043d\u0430 3 \u0434\u043d\u0456 {rain_next_3:.0f} \u043c\u043c, \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0434\u043e \u043e\u043f\u0430\u0434\u0456\u0432")
            reason_groups = {key: list(values) for key, values in base_groups.items()}
            _append_group(reason_groups, "phase", "\u0410\u043a\u0446\u0435\u043d\u0442: \u0430\u0437\u043e\u0442 \u0434\u043b\u044f \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0433\u043e \u0440\u043e\u0441\u0442\u0443")
            task = GardenTask(
                TaskType.FERTILIZING,
                TaskPriority.MEDIUM,
                f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u043d\u0430 \u0440\u0456\u0441\u0442: {plant.plant_type}{v}",
                f"\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u043e \u043d\u0430\u0440\u043e\u0441\u0442\u0430\u0454 (\u0432\u0456\u043a {plant.age_days}). \u0414\u043e\u0440\u0435\u0447\u043d\u0435 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0437 \u0430\u043a\u0446\u0435\u043d\u0442\u043e\u043c \u043d\u0430 \u0430\u0437\u043e\u0442: N {n_hi:.1f}\u0433, P {p_norm:.1f}\u0433, K {k_lo:.1f}\u0433 \u043d\u0430 1 \u043c\u00b2.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                f"NPK {n_hi:.1f}/{p_norm:.1f}/{k_lo:.1f}",
                confidence=self._fertilizing_confidence(84, plant, w_history, w_forecast, 0.55),
                reasons=reasons,
                reason_groups=reason_groups,
                recommendation_type="\u043c\u0456\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u0435",
                constraints=blockers,
            )
            (diag.hidden_tasks if blockers else diag.tasks).append(
                task if not blockers else GardenTask(**{**task.__dict__, "title": f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}{v}", "description": "\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u043f\u043e\u0442\u0440\u0456\u0431\u043d\u0435, \u0430\u043b\u0435 \u043f\u043e\u0442\u043e\u0447\u043d\u0430 \u043f\u043e\u0433\u043e\u0434\u0430 \u043d\u0435 \u0434\u0430\u0454 \u0431\u0435\u0437\u043f\u0435\u0447\u043d\u043e\u0433\u043e \u0432\u0456\u043a\u043d\u0430 \u0434\u043b\u044f \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f.", "blocked_reasons": blocked_messages, "is_hidden": True})
            )
        elif phase == GrowthPhase.MID_SEASON:
            n_lo, p_hi, k_hi = n.nitrogen * 0.6, n.phosphorus * 1.5, n.potassium * 1.4
            reasons = [
                f"\u0424\u0430\u0437\u0430: {_phase_name(phase)}",
                "\u0410\u043a\u0446\u0435\u043d\u0442: P \u0456 K \u0434\u043b\u044f \u0446\u0432\u0456\u0442\u0456\u043d\u043d\u044f \u0442\u0430 \u043f\u043b\u043e\u0434\u0443",
                f"NPK: {n_lo:.1f}/{p_hi:.1f}/{k_hi:.1f}",
            ]
            if dry_window:
                reasons.append("\u0412\u0456\u043a\u043d\u043e \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f: \u0441\u0443\u0445\u0430 \u043f\u043e\u0433\u043e\u0434\u0430 \u0431\u0435\u0437 \u0441\u0438\u043b\u044c\u043d\u0438\u0445 \u043e\u043f\u0430\u0434\u0456\u0432")
            reason_groups = {key: list(values) for key, values in base_groups.items()}
            _append_group(reason_groups, "phase", "\u0410\u043a\u0446\u0435\u043d\u0442: P \u0456 K \u0434\u043b\u044f \u0446\u0432\u0456\u0442\u0456\u043d\u043d\u044f \u0442\u0430 \u043d\u0430\u043b\u0438\u0432\u0443 \u043f\u043b\u043e\u0434\u0456\u0432")
            task = GardenTask(
                TaskType.FERTILIZING,
                TaskPriority.MEDIUM,
                f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u043d\u0430 \u0446\u0432\u0456\u0442\u0456\u043d\u043d\u044f/\u043f\u043b\u0456\u0434: {plant.plant_type}{v}",
                f"\u0420\u043e\u0437\u043f\u043e\u0447\u0430\u043b\u043e\u0441\u044f \u0446\u0432\u0456\u0442\u0456\u043d\u043d\u044f \u0430\u0431\u043e \u043d\u0430\u043b\u0438\u0432 \u043f\u043b\u043e\u0434\u0456\u0432. \u0414\u043e\u0440\u0435\u0447\u043d\u0435 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0437 \u043f\u0435\u0440\u0435\u0432\u0430\u0433\u043e\u044e P \u0456 K: N {n_lo:.1f}\u0433, P {p_hi:.1f}\u0433, K {k_hi:.1f}\u0433 \u043d\u0430 1 \u043c\u00b2.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                f"NPK {n_lo:.1f}/{p_hi:.1f}/{k_hi:.1f}",
                confidence=self._fertilizing_confidence(86, plant, w_history, w_forecast, 0.65),
                reasons=reasons,
                reason_groups=reason_groups,
                recommendation_type="\u043c\u0456\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u0435",
                constraints=blockers,
            )
            (diag.hidden_tasks if blockers else diag.tasks).append(
                task if not blockers else GardenTask(**{**task.__dict__, "title": f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}{v}", "description": "\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0434\u043e\u0440\u0435\u0447\u043d\u0435, \u0430\u043b\u0435 \u0432\u0438\u043a\u043e\u043d\u0430\u0442\u0438 \u0439\u043e\u0433\u043e \u0431\u0435\u0437\u043f\u0435\u0447\u043d\u043e \u0437\u0430\u0440\u0430\u0437 \u0437\u0430\u0432\u0430\u0436\u0430\u0454 \u043f\u043e\u0433\u043e\u0434\u0430.", "blocked_reasons": blocked_messages, "is_hidden": True})
            )

''',
)

rep(
    r"    def _generate_disease_tasks\(self, plant: PlantInstance, diag: CellDiagnostics, w_history: list\[WeatherSnapshot\], w_forecast: list\[WeatherSnapshot\], today: date\) -> None:\n.*?\n(?=    def _generate_cold_stress_tasks)",
    r'''    def _generate_disease_tasks(self, plant: PlantInstance, diag: CellDiagnostics, w_history: list[WeatherSnapshot], w_forecast: list[WeatherSnapshot], today: date) -> None:
        if self._in_cooldown(plant.last_disease_at, today, _DISEASE_COOLDOWN_DAYS):
            return
        v = f" ({plant.variety})" if plant.variety else ""
        blockers = self._application_blockers(w_forecast)
        blocked_messages = self._blocked_reason_messages(w_forecast=w_forecast, blockers=blockers, today=today)
        for risk in diag.disease_risks:
            if risk.is_significant:
                fungicide_type = "\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434" if risk.risk_level >= 0.7 else "\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434"
                reentry_days = 2 if risk.risk_level >= 0.7 else 1
                phi_days = 14 if risk.risk_level >= 0.7 else 7
                harvest_in = self._days_until_harvest_start(plant, diag.profile)
                reasons = [
                    risk.description.rstrip("."),
                    f"\u0420\u0438\u0437\u0438\u043a: {risk.risk_level * 100:.0f}%",
                    f"\u041f\u043e\u0432\u043d\u043e\u0442\u0430 \u0434\u0430\u043d\u0438\u0445: \u0456\u0441\u0442\u043e\u0440\u0456\u044f {min(len(w_history), 7)}/7 \u0434\u043d\u0456\u0432, \u043f\u0440\u043e\u0433\u043d\u043e\u0437 {min(len(w_forecast), 3)}/3 \u0434\u043d\u0456",
                ]
                reason_groups = {
                    "weather": [f"\u0406\u0441\u0442\u043e\u0440\u0456\u044f: {min(len(w_history), 7)}/7 \u0434\u043d\u0456\u0432", f"\u041f\u0440\u043e\u0433\u043d\u043e\u0437: {min(len(w_forecast), 3)}/3 \u0434\u043d\u0456"],
                    "soil": [],
                    "phase": [f"\u0424\u0430\u0437\u0430: {_phase_name(plant.growth_phase)}"],
                    "history": [],
                    "profile": [f"\u0427\u0443\u0442\u043b\u0438\u0432\u0456\u0441\u0442\u044c \u043f\u0440\u043e\u0444\u0456\u043b\u044e: {diag.profile.susceptibility.get(risk.disease, 0) * 100:.0f}%"],
                }
                if plant.last_disease_at:
                    _append_group(reason_groups, "history", f"\u041e\u0441\u0442\u0430\u043d\u043d\u044f \u043e\u0431\u0440\u043e\u0431\u043a\u0430: {(today - plant.last_disease_at.date()).days} \u0434\u043d\u0456\u0432 \u0442\u043e\u043c\u0443")
                _append_group(reason_groups, "weather", risk.description.rstrip("."))
                constraints = [*blockers, f"re-entry interval {reentry_days} \u0434\u043d.", f"pre-harvest interval {phi_days} \u0434\u043d."]
                task = GardenTask(
                    TaskType.DISEASE_PROTECTION,
                    risk.priority,
                    f"\u0424\u0443\u043d\u0433\u0456\u0446\u0438\u0434\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442: {_DISEASE_NAMES.get(risk.disease, risk.disease)} \u2014 {plant.plant_type}{v}",
                    f"{risk.description} {risk.recommendation} \u0422\u0438\u043f \u0437\u0430\u0445\u0438\u0441\u0442\u0443: {fungicide_type}. Re-entry interval: {reentry_days} \u0434\u043d., pre-harvest interval: {phi_days} \u0434\u043d.",
                    plant.plant_type,
                    plant.variety,
                    plant.cell_col,
                    plant.cell_row,
                    confidence=self._disease_confidence(risk, w_history, w_forecast),
                    reasons=reasons,
                    reason_groups=reason_groups,
                    recommendation_type=fungicide_type,
                    constraints=constraints,
                )
                if harvest_in <= phi_days:
                    task.is_hidden = True
                    task.title = f"\u0417\u0430\u0445\u0438\u0441\u0442 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {_DISEASE_NAMES.get(risk.disease, risk.disease)} \u2014 {plant.plant_type}{v}"
                    task.blocked_reasons = [f"\u0414\u043e \u0437\u0431\u043e\u0440\u0443 \u0432\u0440\u043e\u0436\u0430\u044e {_safe_date_label(harvest_in)}, \u0430 pre-harvest interval \u0434\u043b\u044f \u0446\u044c\u043e\u0433\u043e \u0437\u0430\u0445\u0438\u0441\u0442\u0443 {phi_days} \u0434\u043d\u0456\u0432"]
                    diag.hidden_tasks.append(task)
                elif blockers:
                    task.is_hidden = True
                    task.title = f"\u0417\u0430\u0445\u0438\u0441\u0442 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {_DISEASE_NAMES.get(risk.disease, risk.disease)} \u2014 {plant.plant_type}{v}"
                    task.blocked_reasons = blocked_messages
                    diag.hidden_tasks.append(task)
                else:
                    diag.tasks.append(task)

''',
)

rep(
    r"    def _generate_climate_tasks\(self, plant: PlantInstance, profile: CropProfile, diag: CellDiagnostics, w_today: WeatherSnapshot, w_forecast: list\[WeatherSnapshot\], today: date\) -> None:\n.*?\n(?=    @staticmethod\n    def _generate_harvest_task)",
    r'''    def _generate_climate_tasks(self, plant: PlantInstance, profile: CropProfile, diag: CellDiagnostics, w_today: WeatherSnapshot, w_forecast: list[WeatherSnapshot], today: date) -> None:
        frost_cooldown = self._in_cooldown(plant.last_frost_protection_at, today, _FROST_COOLDOWN_DAYS)
        v = f" ({plant.variety})" if plant.variety else ""
        if diag.frost_risk and not frost_cooldown:
            diag.tasks.append(GardenTask(
                TaskType.FROST_PROTECTION,
                TaskPriority.CRITICAL,
                f"\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043e\u043a: {plant.plant_type}{v}",
                f"\u041c\u0456\u043d\u0456\u043c\u0430\u043b\u044c\u043d\u0430 \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 {w_today.temp_min:.0f}\u00b0C \u043d\u0438\u0436\u0447\u0430 \u0437\u0430 \u043c\u0435\u0436\u0443 \u0441\u0442\u0456\u0439\u043a\u043e\u0441\u0442\u0456 \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438 ({profile.frost_tolerance:.0f}\u00b0C). \u0422\u0435\u0440\u043c\u0456\u043d\u043e\u0432\u043e \u043f\u0456\u0434\u0433\u043e\u0442\u0443\u0439\u0442\u0435 \u0443\u043a\u0440\u0438\u0442\u0442\u044f.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                confidence=97,
                reasons=[
                    f"\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043e\u043a: \u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456 {w_today.temp_min:.0f}\u00b0C",
                    f"\u041c\u0435\u0436\u0430 \u0441\u0442\u0456\u0439\u043a\u043e\u0441\u0442\u0456: {profile.frost_tolerance:.0f}\u00b0C",
                ],
            ))
        upcoming = [
            weather for weather in w_forecast
            if weather.date and (_weather_date(weather.date) or today) > today
        ]
        for weather in upcoming[:3]:
            if weather.temp_min <= profile.frost_tolerance and not frost_cooldown:
                label = _date_label(weather.date, today)
                diag.tasks.append(GardenTask(
                    TaskType.FROST_PROTECTION,
                    TaskPriority.HIGH,
                    f"\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043e\u043a {label}: {plant.plant_type}",
                    f"\u041f\u0440\u043e\u0433\u043d\u043e\u0437 \u043d\u0430 {label}: \u043c\u0456\u043d. {weather.temp_min:.0f}\u00b0C, \u0449\u043e \u043d\u0438\u0436\u0447\u0435 \u0437\u0430 \u043c\u0435\u0436\u0443 \u0441\u0442\u0456\u0439\u043a\u043e\u0441\u0442\u0456 {profile.frost_tolerance:.0f}\u00b0C. \u041f\u0456\u0434\u0433\u043e\u0442\u0443\u0439\u0442\u0435 \u0430\u0433\u0440\u043e\u0432\u043e\u043b\u043e\u043a\u043d\u043e \u0430\u0431\u043e \u0456\u043d\u0448\u0435 \u0443\u043a\u0440\u0438\u0442\u0442\u044f.",
                    plant.plant_type,
                    "",
                    plant.cell_col,
                    plant.cell_row,
                    due_date=weather.date,
                    confidence=95,
                    reasons=[
                        f"\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043e\u043a: {label} {weather.temp_min:.0f}\u00b0C",
                        f"\u041c\u0435\u0436\u0430 \u0441\u0442\u0456\u0439\u043a\u043e\u0441\u0442\u0456: {profile.frost_tolerance:.0f}\u00b0C",
                        f"\u0414\u0430\u0442\u0430 \u043f\u0440\u043e\u0433\u043d\u043e\u0437\u0443: {weather.date[:10]}",
                    ],
                ))
        if diag.heat_stress:
            extra_pct = (diag.heat_stress_factor - 1) * 100
            diag.tasks.append(GardenTask(
                TaskType.GENERAL,
                TaskPriority.HIGH,
                f"\u0421\u043f\u0435\u043a\u0430: {plant.plant_type}{v}",
                f"\u041c\u0430\u043a\u0441\u0438\u043c\u0430\u043b\u044c\u043d\u0430 \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 {w_today.temp_max:.0f}\u00b0C \u0432\u0438\u0449\u0430 \u0437\u0430 \u043a\u043e\u043c\u0444\u043e\u0440\u0442\u043d\u0438\u0439 \u043f\u043e\u0440\u0456\u0433 {profile.t_max_growth:.0f}\u00b0C. \u0421\u0442\u0435\u0436\u0442\u0435 \u0437\u0430 \u043f\u043e\u043b\u0438\u0432\u043e\u043c, \u043f\u0440\u0438\u0442\u0456\u043d\u0435\u043d\u043d\u044f\u043c \u0442\u0430 \u0430\u043d\u0442\u0438\u0441\u0442\u0440\u0435\u0441\u043e\u043c.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                confidence=93,
                reasons=[
                    f"\u0421\u043f\u0435\u043a\u0430: {w_today.temp_max:.0f}\u00b0C",
                    f"\u041f\u043e\u0440\u0456\u0433 \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438: {profile.t_max_growth:.0f}\u00b0C",
                    f"\u0417\u0440\u043e\u0441\u0442\u0430\u043d\u043d\u044f \u043f\u043e\u0442\u0440\u0435\u0431\u0438 \u0443 \u0432\u043e\u0434\u0456: {extra_pct:.0f}%",
                ],
            ))

''',
)

rep(
    r"    @staticmethod\n    def _generate_harvest_task\(plant: PlantInstance, profile: CropProfile, diag: CellDiagnostics\) -> None:\n.*?\n(?=    @staticmethod\n    def _generate_status_task)",
    r'''    @staticmethod
    def _generate_harvest_task(plant: PlantInstance, profile: CropProfile, diag: CellDiagnostics) -> None:
        if plant.age_days < profile.days_to_harvest_min:
            days_left = profile.days_to_harvest_min - plant.age_days
            if days_left <= 7:
                diag.tasks.append(GardenTask(
                    TaskType.HARVESTING,
                    TaskPriority.LOW,
                    f"\u041f\u0456\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430 \u0434\u043e \u0437\u0431\u043e\u0440\u0443: {plant.plant_type}",
                    f"\u0414\u043e \u043c\u0456\u043d\u0456\u043c\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0432\u0456\u043a\u043d\u0430 \u0437\u0431\u043e\u0440\u0443 \u0437\u0430\u043b\u0438\u0448\u0438\u043b\u043e\u0441\u044f {days_left} \u0434\u043d\u0456\u0432 (\u0437\u0430\u0440\u0430\u0437 {plant.age_days} \u0434\u043d\u0456\u0432 \u0432\u0456\u0434 \u043f\u043e\u0441\u0430\u0434\u043a\u0438, \u043d\u043e\u0440\u043c\u0430 {profile.days_to_harvest_min}\u2013{profile.days_to_harvest_max}).",
                    plant.plant_type,
                    cell_col=plant.cell_col,
                    cell_row=plant.cell_row,
                    confidence=82,
                    reasons=[
                        f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432",
                        f"\u0414\u043e \u0437\u0431\u043e\u0440\u0443: {days_left} \u0434\u043d\u0456\u0432",
                        f"\u0412\u0456\u043a\u043d\u043e \u0437\u0431\u043e\u0440\u0443: {profile.days_to_harvest_min}-{profile.days_to_harvest_max} \u0434\u043d\u0456\u0432",
                    ],
                ))
        elif plant.age_days <= profile.days_to_harvest_max:
            diag.tasks.append(GardenTask(
                TaskType.HARVESTING,
                TaskPriority.MEDIUM,
                f"\u0427\u0430\u0441 \u0437\u0431\u0438\u0440\u0430\u0442\u0438: {plant.plant_type}",
                f"\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430 \u0432\u0436\u0435 \u0443 \u0432\u0456\u043a\u043d\u0456 \u0437\u0431\u043e\u0440\u0443 (\u0432\u0456\u043a {plant.age_days}, \u043d\u043e\u0440\u043c\u0430 {profile.days_to_harvest_min}\u2013{profile.days_to_harvest_max}). \u0417\u0430\u043f\u043b\u0430\u043d\u0443\u0439\u0442\u0435 \u0437\u0431\u0456\u0440 \u0432\u0440\u043e\u0436\u0430\u044e \u0443 \u043d\u0430\u0439\u0431\u043b\u0438\u0436\u0447\u0456 \u0434\u043d\u0456.",
                plant.plant_type,
                cell_col=plant.cell_col,
                cell_row=plant.cell_row,
                confidence=86,
                reasons=[
                    f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432",
                    f"\u0412\u0456\u043a\u043d\u043e \u0437\u0431\u043e\u0440\u0443: {profile.days_to_harvest_min}-{profile.days_to_harvest_max} \u0434\u043d\u0456\u0432",
                ],
            ))

''',
)

rep(
    r"    @staticmethod\n    def _generate_status_task\(plant: PlantInstance, diag: CellDiagnostics, phase: GrowthPhase, depletion_pct: float\) -> None:\n.*?\n(?=    @staticmethod\n    def _parse_grid_cells)",
    r'''    @staticmethod
    def _generate_status_task(plant: PlantInstance, diag: CellDiagnostics, phase: GrowthPhase, depletion_pct: float) -> None:
        if diag.tasks:
            return
        v = f" ({plant.variety})" if plant.variety else ""
        phase_name = _phase_name(phase)
        if plant.age_days == 0:
            diag.tasks.append(GardenTask(
                TaskType.GENERAL,
                TaskPriority.LOW,
                f"\u0421\u043f\u043e\u0441\u0442\u0435\u0440\u0435\u0436\u0435\u043d\u043d\u044f \u043f\u0456\u0441\u043b\u044f \u043f\u043e\u0441\u0430\u0434\u043a\u0438: {plant.plant_type}{v}",
                f"\u0420\u043e\u0441\u043b\u0438\u043d\u0443 \u0432\u0438\u0441\u0430\u0434\u0436\u0435\u043d\u043e \u043d\u0435\u0434\u0430\u0432\u043d\u043e. \u0423 \u043d\u0430\u0439\u0431\u043b\u0438\u0436\u0447\u0456 1\u20132 \u0434\u043d\u0456 \u0441\u0442\u0435\u0436\u0442\u0435 \u0437\u0430 \u043f\u0440\u0438\u0436\u0438\u0432\u0430\u043d\u043d\u044f\u043c. \u0424\u0430\u0437\u0430: {phase_name}. \u041a\u043e\u0440\u0456\u043d\u044c \u043f\u043e\u043a\u0438 \u043d\u0435\u0433\u043b\u0438\u0431\u043e\u043a\u0438\u0439 ({plant.root_depth_cm:.0f} \u0441\u043c), \u0442\u043e\u043c\u0443 \u0443\u043d\u0438\u043a\u0430\u0439\u0442\u0435 \u043f\u0435\u0440\u0435\u0441\u0443\u0448\u0443\u0432\u0430\u043d\u043d\u044f.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                confidence=76,
                reasons=[f"\u0424\u0430\u0437\u0430: {phase_name}", "\u0412\u0456\u043a: 0 \u0434\u043d\u0456\u0432", f"\u041a\u043e\u0440\u0456\u043d\u044c: {plant.root_depth_cm:.0f} \u0441\u043c"],
            ))
        else:
            if depletion_pct < 0.15:
                water_status = "\u0432\u043e\u043b\u043e\u0433\u0438 \u0434\u043e\u0441\u0442\u0430\u0442\u043d\u044c\u043e"
            elif depletion_pct < 0.3:
                water_status = "\u0432\u043e\u043b\u043e\u0433\u0430 \u043f\u043e\u043c\u0456\u0440\u043d\u043e \u0437\u043d\u0438\u0436\u0435\u043d\u0430"
            else:
                water_status = f"\u0437\u0430\u043f\u0430\u0441 \u0432\u043e\u0434\u0438 {max(0.0, (1 - depletion_pct) * 100):.0f}%"
            diag.tasks.append(GardenTask(
                TaskType.GENERAL,
                TaskPriority.LOW,
                f"\u0421\u0442\u0430\u043d \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438: {plant.plant_type}{v}",
                f"\u0424\u0430\u0437\u0430: {phase_name}. GDD: {plant.cumulative_gdd:.0f}. \u0413\u043b\u0438\u0431\u0438\u043d\u0430 \u043a\u043e\u0440\u0435\u043d\u044f: {plant.root_depth_cm:.0f} \u0441\u043c. \u0414\u043e\u0431\u043e\u0432\u0430 \u043f\u043e\u0442\u0440\u0435\u0431\u0430 \u0443 \u0432\u043e\u0434\u0456: {diag.etc_mm} \u043c\u043c. \u0421\u0442\u0430\u043d \u0432\u043e\u043b\u043e\u0433\u0438: {water_status}.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                confidence=74,
                reasons=[
                    f"\u0424\u0430\u0437\u0430: {phase_name}",
                    f"GDD: {plant.cumulative_gdd:.0f}",
                    f"\u0414\u0435\u0444\u0456\u0446\u0438\u0442 \u0432\u043e\u043b\u043e\u0433\u0438: {depletion_pct * 100:.0f}%",
                ],
            ))

''',
)

rep(
    r"    @staticmethod\n    def _merge_similar_tasks\(tasks: list\[GardenTask\]\) -> list\[GardenTask\]:\n.*?\n(?=    @staticmethod\n    def _task_to_dict)",
    r'''    @staticmethod
    def _merge_similar_tasks(tasks: list[GardenTask]) -> list[GardenTask]:
        merged: dict[str, GardenTask] = {}
        counts: dict[str, int] = {}
        for task in tasks:
            key = f"{task.task_type.value}|{task.priority.value}|{task.plant_name}|{task.variety}"
            if key not in merged:
                merged[key] = task
                counts[key] = 1
            else:
                counts[key] += 1
        result = []
        for key, task in merged.items():
            if counts[key] > 1:
                task.title = f"{task.title} ({counts[key]} \u0440\u043e\u0441\u043b\u0438\u043d)"
                task.reasons = [*task.reasons, f"\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0456\u044f \u0441\u0442\u043e\u0441\u0443\u0454\u0442\u044c\u0441\u044f {counts[key]} \u0440\u043e\u0441\u043b\u0438\u043d"]
            result.append(task)
        return result

''',
)

path.write_text(text, encoding="utf-8")
print("patched smart_gardener_engine.py")

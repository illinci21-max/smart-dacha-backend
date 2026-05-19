"""Smart gardener engine ported from Flutter.

This module is the backend source of truth for agro analysis. It mirrors the
Flutter SmartGardenerEngine inputs and returns a rich task shape plus the legacy
fields expected by the existing /garden/plots/{id}/tasks schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
import math
from typing import Any

from app.services.agro_math import calculate_gdd_delta, cumulative_gdd_calendar_year
from app.services.fertilizer_profile_service import recommend_fertilizer
from app.services.lifecycle_types import LifecycleType, PerennialSeason
from app.services.perennial_phenology import (
    determine_perennial_season,
    get_perennial_disease_pressure,
    get_perennial_fertilizer_need,
    get_perennial_frost_sensitivity,
    is_plant_productive,
)
from app.services.protection_profile_service import recommend_protection
from app.services.soil_profile import SoilProfile
from app.services.soil_profile_service import PlotOverrides, get_soil_profile, plot_calibration_score


class GrowthPhase(str, Enum):
    INITIAL = "initial"
    DEVELOPMENT = "development"
    MID_SEASON = "mid_season"
    LATE_SEASON = "late_season"


def _perennial_season_to_growth_phase(season: PerennialSeason) -> GrowthPhase:
    """Map coarse perennial season to the nearest existing annual phase."""
    return {
        PerennialSeason.DORMANT_WINTER: GrowthPhase.LATE_SEASON,
        PerennialSeason.BUD_BREAK: GrowthPhase.INITIAL,
        PerennialSeason.FLOWERING_FRUIT_SET: GrowthPhase.DEVELOPMENT,
        PerennialSeason.FRUIT_DEVELOPMENT: GrowthPhase.MID_SEASON,
        PerennialSeason.HARVEST_RIPENING: GrowthPhase.LATE_SEASON,
        PerennialSeason.LEAF_FALL: GrowthPhase.LATE_SEASON,
        PerennialSeason.DORMANT_ENTRY: GrowthPhase.LATE_SEASON,
    }[season]


class TaskType(str, Enum):
    WATERING = "watering"
    FERTILIZING = "fertilizing"
    DISEASE_PROTECTION = "disease_protection"
    PEST_CONTROL = "pest_control"
    PRUNING = "pruning"
    HARVESTING = "harvesting"
    FROST_PROTECTION = "frost_protection"
    COLD_STRESS = "cold_stress"
    GENERAL = "general"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class KcStages:
    initial_days: int = 20
    development_days: int = 30
    mid_season_days: int = 40
    late_season_days: int = 20
    kc_initial: float = 0.35
    kc_mid: float = 1.05
    kc_end: float = 0.70

    @property
    def total_season_days(self) -> int:
        return self.initial_days + self.development_days + self.mid_season_days + self.late_season_days


@dataclass
class NutrientNeeds:
    nitrogen: float = 2.0
    phosphorus: float = 0.8
    potassium: float = 1.5
    magnesium: float = 0.3
    calcium: float = 0.5


@dataclass
class CropProfile:
    name: str
    category: str = "\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430"
    emoji: str = "??"
    kc: KcStages = field(default_factory=KcStages)
    root_depth_initial_cm: float = 10
    root_depth_max_cm: float = 50
    wilting_point_mm: float = 60
    field_capacity_mm: float = 180
    critical_depletion: float = 0.55
    nutrients: NutrientNeeds = field(default_factory=NutrientNeeds)
    t_min_growth: float = 8
    t_optimal_min: float = 18
    t_optimal_max: float = 28
    t_max_growth: float = 38
    frost_tolerance: float = 0
    t_base: float = 10
    susceptibility: dict[str, float] = field(default_factory=lambda: {
        "late_blight": 0.5,
        "powdery_mildew": 0.3,
        "downy_mildew": 0.3,
        "botrytis": 0.2,
    })
    days_to_harvest_min: int = 60
    days_to_harvest_max: int = 90
    disease_protection_adaptation_days: int = 5
    disease_protection_early_symptom_days: int = 2
    biofungicide_allowed_from_day: int = 0
    chemical_fungicide_allowed_from_day: int = 5
    copper_fungicide_allowed_from_day: int = 7
    max_spray_temp_c: float = 28
    avoid_spray_before_rain_hours: int = 6
    cold_stress_threshold_c: float | None = None
    frost_critical_threshold_c: float | None = None
    common_diseases: list[dict] = field(default_factory=list)
    common_pests: list[dict] = field(default_factory=list)
    treatment_guide: dict = field(default_factory=dict)
    profile_confidence: int = 80
    validation_warnings: list[str] = field(default_factory=list)


@dataclass
class WeatherSnapshot:
    date: str = ""
    temp_max: float = 25
    temp_min: float = 15
    temp_avg: float = 20
    humidity_avg: float = 60
    humidity_max: float = 80
    wind_speed_ms: float = 2
    solar_radiation_mj: float = 15
    precipitation_mm: float = 0
    rain_probability: float = 0
    cloud_cover_pct: float = 50
    is_fog: bool = False
    has_dew: bool = False

    @property
    def temp_mean(self) -> float:
        return self.temp_avg if self.temp_avg != 0 else (self.temp_max + self.temp_min) / 2

    @property
    def is_humid(self) -> bool:
        return self.humidity_avg > 90 or self.is_fog

    @property
    def effective_rain_mm(self) -> float:
        if self.precipitation_mm <= 0:
            return 0.0
        if self.precipitation_mm <= 25:
            return self.precipitation_mm * 0.8
        return min(self.precipitation_mm * 0.6, 50.0)

    @property
    def day_of_year(self) -> int:
        try:
            return date.fromisoformat(self.date[:10]).timetuple().tm_yday
        except (TypeError, ValueError):
            return date.today().timetuple().tm_yday


@dataclass
class GardenAction:
    action_type: str
    plant_type: str | None = None
    variety: str | None = None
    cell_col: int | None = None
    cell_row: int | None = None
    task_title: str | None = None
    scope: str = "single"
    created_at: datetime = field(default_factory=datetime.now)
    n_applied_g_m2: float = 0.0
    p_applied_g_m2: float = 0.0
    k_applied_g_m2: float = 0.0
    mg_applied_g_m2: float = 0.0
    ca_applied_g_m2: float = 0.0
    treatment_kind: str | None = None
    target_problem: str | None = None
    product_profile_id: str | None = None
    product_type: str | None = None
    frac_group: str | None = None
    reentry_days: int | None = None
    pre_harvest_interval_days: int | None = None
    rainfast_hours: int | None = None

    def applies_to(self, plant: "PlantInstance") -> bool:
        if self.plant_type is not None and self.plant_type != plant.plant_type:
            return False
        if self.scope == "single":
            if self.cell_col is not None and self.cell_col != plant.cell_col:
                return False
            if self.cell_row is not None and self.cell_row != plant.cell_row:
                return False
        return True


@dataclass
class ManualObservation:
    scope: str = "plot"
    plant_type: str | None = None
    variety: str | None = None
    species_filter: list[str] | None = None
    cell_col: int | None = None
    cell_row: int | None = None
    soil_moisture_pct: int | None = None
    soil_moisture_status: str | None = None
    leaf_condition: str | None = None
    symptoms: list[str] = field(default_factory=list)
    growth_phase: str | None = None
    observed_perennial_season: str | None = None
    notes: str | None = None
    observed_at: datetime = field(default_factory=datetime.now)

    def specificity(self) -> int:
        score = 0
        if self.scope == "single" or self.cell_col is not None or self.cell_row is not None:
            score += 4
        if self.plant_type:
            score += 2
        if self.species_filter:
            score += 2
        if self.variety:
            score += 1
        return score

    def applies_to(self, plant: "PlantInstance") -> bool:
        if self.species_filter and plant.plant_type not in self.species_filter:
            return False
        if self.plant_type and self.plant_type != plant.plant_type:
            return False
        if self.variety and self.variety != plant.variety:
            return False
        if self.cell_col is not None and self.cell_col != plant.cell_col:
            return False
        if self.cell_row is not None and self.cell_row != plant.cell_row:
            return False
        return True

@dataclass
class PlantInstance:
    cell_col: int
    cell_row: int
    plant_type: str
    variety: str = ""
    planted_date: str = ""
    plant_icon: str = ""
    plant_emoji: str = ""
    category: str = ""
    age_days: int = 0
    lifecycle_type: LifecycleType = LifecycleType.ANNUAL
    age_years: int | None = None
    perennial_season: PerennialSeason | None = None
    perennial_season_source: str = "auto-calendar"
    cumulative_gdd: float = 0
    gdd_anchor: str = "planting_date"
    growth_phase: GrowthPhase = GrowthPhase.INITIAL
    current_kc: float = 0.35
    root_depth_cm: float = 10
    soil_water_mm: float = 120
    soil_water_deficit_mm: float = 0
    last_watered_at: datetime | None = None
    last_fertilized_at: datetime | None = None
    last_disease_at: datetime | None = None
    last_frost_protection_at: datetime | None = None
    last_harvested_at: datetime | None = None
    last_pruned_at: datetime | None = None
    observed_soil_moisture_pct: int | None = None
    observed_soil_moisture_status: str | None = None
    observed_leaf_condition: str | None = None
    observed_symptoms: list[str] = field(default_factory=list)
    observed_growth_phase: str | None = None
    observed_at: datetime | None = None
    last_disease_observed_at: datetime | None = None
    n_applied_30d_g_m2: float = 0.0
    p_applied_30d_g_m2: float = 0.0
    k_applied_30d_g_m2: float = 0.0
    mg_applied_30d_g_m2: float = 0.0
    ca_applied_30d_g_m2: float = 0.0
    n_applied_season_g_m2: float = 0.0
    p_applied_season_g_m2: float = 0.0
    k_applied_season_g_m2: float = 0.0
    mg_applied_season_g_m2: float = 0.0
    ca_applied_season_g_m2: float = 0.0
    n_lost_season_g_m2: float = 0.0
    p_lost_season_g_m2: float = 0.0
    k_lost_season_g_m2: float = 0.0
    mg_lost_season_g_m2: float = 0.0
    ca_lost_season_g_m2: float = 0.0
    protection_counts_90d: dict[str, int] = field(default_factory=dict)
    frac_counts_90d: dict[str, int] = field(default_factory=dict)
    last_protection_by_problem: dict[str, datetime] = field(default_factory=dict)
    last_frac_group: str | None = None

    def calculate_age(self, today: date) -> None:
        if not self.planted_date:
            self.age_days = 0
            return
        try:
            self.age_days = max(0, (today - date.fromisoformat(self.planted_date[:10])).days)
        except ValueError:
            self.age_days = 0


@dataclass
class DiseaseRisk:
    disease: str
    risk_level: float
    priority: TaskPriority
    description: str
    recommendation: str
    factors: list[str] = field(default_factory=list)
    matched_days: int = 0
    window_days: int = 0
    model_confidence: int = 80

    @property
    def is_significant(self) -> bool:
        return self.risk_level >= 0.3


@dataclass
class PestRisk:
    pest: dict
    risk_level: float
    priority: TaskPriority
    description: str
    recommendation: str
    factors: list[str] = field(default_factory=list)
    observed: bool = False

    @property
    def name(self) -> str:
        return str(self.pest.get("name") or "шкідник")

    @property
    def key(self) -> str:
        return self.name.strip().lower()

    @property
    def requires_intervention(self) -> bool:
        return self.observed or self.risk_level >= 0.62


@dataclass(frozen=True)
class DiseaseRiskModel:
    disease: str
    temp_min: float
    temp_max: float
    humidity_min: float | None = None
    humidity_max: float | None = None
    rain_min_mm: float | None = None
    rain_max_mm: float | None = None
    cloud_min_pct: float | None = None
    cloud_max_pct: float | None = None
    leaf_wetness_required: bool = False
    prefers_dry_leaf: bool = False
    min_leaf_wetness_hours: float | None = None
    incubation_period_days: int = 0
    infection_pressure_carryover: float = 0.0
    model_name: str = "threshold"
    phase_boost: tuple[GrowthPhase, ...] = ()
    default_susceptibility: float = 0.25
    recommendation: str = ""
    weather_label: str = ""


@dataclass
class GardenTask:
    task_type: TaskType
    priority: TaskPriority
    title: str
    description: str
    plant_name: str = ""
    variety: str = ""
    cell_col: int = -1
    cell_row: int = -1
    amount: str = ""
    due_date: str = ""
    confidence: int = 80
    reasons: list[str] = field(default_factory=list)
    reason_groups: dict[str, list[str]] = field(default_factory=dict)
    recommendation_type: str = ""
    constraints: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    is_hidden: bool = False

    @property
    def priority_order(self) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(self.priority.value, 4)





@dataclass
class CellDiagnostics:
    plant: PlantInstance
    profile: CropProfile
    et0_mm: float = 0
    etc_mm: float = 0
    effective_rain_mm: float = 0
    water_deficit_mm: float = 0
    watering_needed_ml: float = 0
    fog_dew_bonus_mm: float = 0
    heat_stress_factor: float = 1.0
    nutrient_leaching_risk: float = 0
    disease_risks: list[DiseaseRisk] = field(default_factory=list)
    pest_risks: list[PestRisk] = field(default_factory=list)
    frost_risk: bool = False
    heat_stress: bool = False
    tasks: list[GardenTask] = field(default_factory=list)
    hidden_tasks: list[GardenTask] = field(default_factory=list)


_WATERING_COOLDOWN_DAYS = 1
_FERTILIZING_COOLDOWN_DAYS = 5
_DISEASE_COOLDOWN_DAYS = 7
_FROST_COOLDOWN_DAYS = 1


_TASK_TYPE_ORDER = {
    TaskType.WATERING: 0,
    TaskType.FERTILIZING: 1,
    TaskType.DISEASE_PROTECTION: 2,
    TaskType.PEST_CONTROL: 3,
    TaskType.PRUNING: 4,
    TaskType.HARVESTING: 5,
    TaskType.FROST_PROTECTION: 6,
    TaskType.COLD_STRESS: 7,
    TaskType.GENERAL: 8,
}

_CATEGORY_BY_TASK_TYPE = {
    TaskType.WATERING: "watering",
    TaskType.FERTILIZING: "fertilizing",
    TaskType.DISEASE_PROTECTION: "protection",
    TaskType.PEST_CONTROL: "protection",
    TaskType.PRUNING: "general",
    TaskType.HARVESTING: "harvest",
    TaskType.FROST_PROTECTION: "protection",
    TaskType.COLD_STRESS: "protection",
    TaskType.GENERAL: "general",
}

_NO_SPRAY_WIND_U2_MS = 4.5
_COLD_WET_WINDY_U2_MS = 3.5

_DISEASE_NAMES = {
    "late_blight": "Фітофтороз",
    "powdery_mildew": "Борошниста роса",
    "downy_mildew": "Несправжня борошниста роса",
    "botrytis": "Сіра гниль",
    "alternaria": "Альтернаріоз",
    "rust": "Іржа",
    "fusarium": "Фузаріоз",
}

_DISEASE_RISK_MODELS = (
    DiseaseRiskModel(
        disease="late_blight",
        temp_min=10,
        temp_max=25,
        humidity_min=75,
        rain_min_mm=0.2,
        cloud_min_pct=65,
        leaf_wetness_required=True,
        min_leaf_wetness_hours=11,
        incubation_period_days=5,
        infection_pressure_carryover=0.12,
        model_name="NegFry + Smith Periods",
        phase_boost=(GrowthPhase.DEVELOPMENT, GrowthPhase.MID_SEASON),
        default_susceptibility=0.5,
        weather_label="прохолодна волога погода з росою/туманом або опадами",
        recommendation="Рекомендація: провітрюйте посадки, поливайте під корінь вранці, за потреби застосуйте фунгіцид. Не обробляйте перед сильним дощем.",
    ),
    DiseaseRiskModel(
        disease="powdery_mildew",
        temp_min=15,
        temp_max=28,
        humidity_min=40,
        humidity_max=75,
        rain_max_mm=1,
        cloud_max_pct=70,
        prefers_dry_leaf=True,
        infection_pressure_carryover=0.10,
        default_susceptibility=0.3,
        weather_label="теплі сухі дні з помірною вологістю",
        recommendation="Рекомендація: слідкуйте за листям, забезпечте провітрювання, за потреби використайте контактний захист.",
    ),
    DiseaseRiskModel(
        disease="downy_mildew",
        temp_min=10,
        temp_max=22,
        humidity_min=80,
        rain_min_mm=0.5,
        leaf_wetness_required=True,
        min_leaf_wetness_hours=6,
        incubation_period_days=4,
        infection_pressure_carryover=0.08,
        default_susceptibility=0.3,
        weather_label="вологі прохолодні періоди із змочуванням листя",
        recommendation="Рекомендація: зменшіть зволоження листя, за потреби застосуйте захисний обробіток після стабілізації погоди.",
    ),
    DiseaseRiskModel(
        disease="botrytis",
        temp_min=15,
        temp_max=25,
        humidity_min=85,
        cloud_min_pct=60,
        leaf_wetness_required=True,
        min_leaf_wetness_hours=8,
        incubation_period_days=3,
        infection_pressure_carryover=0.06,
        default_susceptibility=0.2,
        weather_label="висока вологість, хмарність і слабке просихання рослин",
        recommendation="Рекомендація: прорідьте посадки, зменшіть перезволоження, за потреби застосуйте протигнильний захист.",
    ),
    DiseaseRiskModel(
        disease="alternaria",
        temp_min=20,
        temp_max=32,
        humidity_min=70,
        rain_min_mm=0.1,
        cloud_min_pct=45,
        min_leaf_wetness_hours=5,
        incubation_period_days=4,
        infection_pressure_carryover=0.15,
        phase_boost=(GrowthPhase.MID_SEASON, GrowthPhase.LATE_SEASON),
        default_susceptibility=0.22,
        weather_label="теплі вологі періоди після стресу рослин",
        recommendation="Рекомендація: видаліть уражене листя, уникайте стресу від пересушування, чергуйте групи захисту.",
    ),
    DiseaseRiskModel(
        disease="rust",
        temp_min=12,
        temp_max=24,
        humidity_min=75,
        rain_max_mm=4,
        leaf_wetness_required=True,
        min_leaf_wetness_hours=6,
        incubation_period_days=7,
        infection_pressure_carryover=0.08,
        default_susceptibility=0.18,
        weather_label="помірно прохолодні вологі ночі з росою",
        recommendation="Рекомендація: огляньте нижній бік листя, покращіть провітрювання і не повторюйте одну FRAC-групу поспіль.",
    ),
    DiseaseRiskModel(
        disease="fusarium",
        temp_min=20,
        temp_max=32,
        humidity_min=65,
        rain_min_mm=0.1,
        incubation_period_days=7,
        infection_pressure_carryover=0.18,
        phase_boost=(GrowthPhase.DEVELOPMENT, GrowthPhase.MID_SEASON),
        default_susceptibility=0.24,
        weather_label="тепла волога погода, перезволожений ґрунт і стрес коренів",
        recommendation="Рекомендація: перевірте дренаж, не перезволожуйте, видаляйте сильно уражені рослини, не компостуйте хворі рештки. Для профілактики використовуйте сівозміну та біопрепарати для ґрунту.",
    ),
)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round(value: float, digits: int = 2) -> float:
    return round(value + 0.0, digits)


def _date_label(value: str, today: date) -> str:
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

def _weather_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now()


def _wind_speed_to_2m(speed_ms: float, measurement_height_m: float = 10.0) -> float:
    height = max(2.0, float(measurement_height_m or 10.0))
    if abs(height - 2.0) < 0.01:
        return max(0.0, speed_ms)
    factor = 4.87 / math.log((67.8 * height) - 5.42)
    return max(0.0, speed_ms * factor)


def _atmospheric_pressure_kpa(elevation_m: float) -> float:
    elevation = max(-400.0, min(9000.0, float(elevation_m or 0.0)))
    return 101.3 * (((293.0 - 0.0065 * elevation) / 293.0) ** 5.26)


def _psychrometric_constant(elevation_m: float) -> float:
    return 0.000665 * _atmospheric_pressure_kpa(elevation_m)


def _extraterrestrial_radiation(latitude_deg: float, day_of_year: int) -> float:
    latitude = math.radians(max(-67.0, min(67.0, float(latitude_deg or 50.45))))
    day = max(1, min(366, int(day_of_year or 1)))
    dr = 1.0 + 0.033 * math.cos((2.0 * math.pi / 365.0) * day)
    solar_declination = 0.409 * math.sin((2.0 * math.pi / 365.0) * day - 1.39)
    sunset_arg = -math.tan(latitude) * math.tan(solar_declination)
    sunset_arg = max(-1.0, min(1.0, sunset_arg))
    sunset_hour_angle = math.acos(sunset_arg)
    return (
        (24.0 * 60.0 / math.pi)
        * 0.0820
        * dr
        * (
            sunset_hour_angle * math.sin(latitude) * math.sin(solar_declination)
            + math.cos(latitude) * math.cos(solar_declination) * math.sin(sunset_hour_angle)
        )
    )


def _clear_sky_radiation(latitude_deg: float, elevation_m: float, day_of_year: int) -> float:
    ra = _extraterrestrial_radiation(latitude_deg, day_of_year)
    return max(0.1, (0.75 + 2e-5 * max(-400.0, float(elevation_m or 0.0))) * ra)


def _phase_name(phase: GrowthPhase) -> str:
    return {
        GrowthPhase.INITIAL: "\u043f\u043e\u0447\u0430\u0442\u043a\u043e\u0432\u0430",
        GrowthPhase.DEVELOPMENT: "\u0440\u043e\u0437\u0432\u0438\u0442\u043e\u043a",
        GrowthPhase.MID_SEASON: "\u0441\u0435\u0440\u0435\u0434\u0438\u043d\u0430 \u0441\u0435\u0437\u043e\u043d\u0443",
        GrowthPhase.LATE_SEASON: "\u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043d\u044f",
    }.get(phase, phase.value)

def _risk_to_priority(risk: float) -> TaskPriority:
    if risk >= 0.7:
        return TaskPriority.CRITICAL
    if risk >= 0.5:
        return TaskPriority.HIGH
    if risk >= 0.3:
        return TaskPriority.MEDIUM
    return TaskPriority.LOW


def _confidence(value: int) -> int:
    return max(45, min(99, value))


def _append_group(reason_groups: dict[str, list[str]], group: str, message: str) -> None:
    if not message:
        return
    reason_groups.setdefault(group, []).append(message)


def _safe_date_label(days: int) -> str:
    if days <= 0:
        return "\u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456"
    if days == 1:
        return "\u0447\u0435\u0440\u0435\u0437 1 \u0434\u0435\u043d\u044c"
    if days < 5:
        return f"\u0447\u0435\u0440\u0435\u0437 {days} \u0434\u043d\u0456"
    return f"\u0447\u0435\u0440\u0435\u0437 {days} \u0434\u043d\u0456\u0432"

def get_soil_properties(soil_type: str | None, plot_overrides: PlotOverrides | None = None) -> SoilProfile:
    return get_soil_profile(soil_type, plot_overrides=plot_overrides)


def crop_profile_from_backend(name: str, category: str | None, data: dict | None) -> CropProfile:
    data = data or {}
    crop_name = str(name or "")
    crop_category = str(data.get("category") or category or "\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430")
    cold_stress_threshold = data.get("cold_stress_threshold_c")
    if cold_stress_threshold is None and crop_name.strip().lower() in {"\u043c\u0430\u043b\u0438\u043d\u0430", "raspberry"}:
        cold_stress_threshold = 0
    return CropProfile(
        name=name,
        emoji=str(data.get("emoji") or "??"),
        category=crop_category,
        kc=KcStages(
            initial_days=_to_int(data.get("initial_days"), 20),
            development_days=_to_int(data.get("development_days"), 30),
            mid_season_days=_to_int(data.get("mid_season_days"), 35),
            late_season_days=_to_int(data.get("late_season_days"), 20),
            kc_initial=_to_float(data.get("kc_initial"), 0.40),
            kc_mid=_to_float(data.get("kc_mid"), 1.05),
            kc_end=_to_float(data.get("kc_end"), 0.70),
        ),
        root_depth_initial_cm=_to_float(data.get("root_depth_initial_cm"), 10),
        root_depth_max_cm=_to_float(data.get("root_depth_max_cm"), 50),
        field_capacity_mm=_to_float(data.get("field_capacity_mm"), 180),
        wilting_point_mm=_to_float(data.get("wilting_point_mm"), 55),
        critical_depletion=_to_float(data.get("critical_depletion"), 0.50),
        nutrients=NutrientNeeds(
            nitrogen=_to_float(data.get("nitrogen"), 2.0),
            phosphorus=_to_float(data.get("phosphorus"), 1.0),
            potassium=_to_float(data.get("potassium"), 2.0),
            magnesium=_to_float(data.get("magnesium"), 0.3),
            calcium=_to_float(data.get("calcium"), 0.5),
        ),
        t_min_growth=_to_float(data.get("t_min_growth"), 8),
        t_optimal_min=_to_float(data.get("t_optimal_min"), 18),
        t_optimal_max=_to_float(data.get("t_optimal_max"), 28),
        t_max_growth=_to_float(data.get("t_max_growth"), 38),
        frost_tolerance=_to_float(data.get("frost_tolerance"), 0),
        t_base=_to_float(data.get("t_base"), 10),
        susceptibility={
            "late_blight": _to_float(data.get("sus_late_blight"), 0.3),
            "powdery_mildew": _to_float(data.get("sus_powdery_mildew"), 0.3),
            "downy_mildew": _to_float(data.get("sus_downy_mildew"), 0.3),
            "botrytis": _to_float(data.get("sus_botrytis"), 0.2),
            "alternaria": _to_float(data.get("sus_alternaria"), 0.0),
            "rust": _to_float(data.get("sus_rust"), 0.0),
            "fusarium": _to_float(data.get("sus_fusarium"), 0.24),
        },
        days_to_harvest_min=_to_int(data.get("days_to_harvest_min"), 60),
        days_to_harvest_max=_to_int(data.get("days_to_harvest_max"), 90),
        disease_protection_adaptation_days=_to_int(data.get("disease_protection_adaptation_days"), 5),
        disease_protection_early_symptom_days=_to_int(data.get("disease_protection_early_symptom_days"), 2),
        biofungicide_allowed_from_day=_to_int(data.get("biofungicide_allowed_from_day"), 0),
        chemical_fungicide_allowed_from_day=_to_int(data.get("chemical_fungicide_allowed_from_day"), 5),
        copper_fungicide_allowed_from_day=_to_int(data.get("copper_fungicide_allowed_from_day"), 7),
        max_spray_temp_c=_to_float(data.get("max_spray_temp_c"), 28),
        avoid_spray_before_rain_hours=_to_int(data.get("avoid_spray_before_rain_hours"), 6),
        cold_stress_threshold_c=(
            None
            if cold_stress_threshold is None
            else _to_float(cold_stress_threshold, 0)
        ),
        frost_critical_threshold_c=(
            None
            if data.get("frost_critical_threshold_c") is None
            else _to_float(data.get("frost_critical_threshold_c"), _to_float(data.get("frost_tolerance"), 0))
        ),
        common_diseases=(data.get("common_diseases") if isinstance(data.get("common_diseases"), list) else []),
        common_pests=(data.get("common_pests") if isinstance(data.get("common_pests"), list) else []),
        treatment_guide=(data.get("treatment_guide") if isinstance(data.get("treatment_guide"), dict) else {}),
        profile_confidence=_to_int(data.get("profile_confidence") or data.get("confidence"), 80),
        validation_warnings=list(data.get("validation_warnings") or []),
    )


def parse_weather(data: dict[str, Any] | None) -> WeatherSnapshot:
    data = data or {}
    solar = _to_float(data.get("solar_radiation") or data.get("solar_radiation_mj"), 15)
    if solar <= 0:
        solar = 15
    elif solar >= 50:
        solar *= 0.0864
    wind_speed = _to_float(
        data.get("wind_speed_2m")
        if data.get("wind_speed_2m") is not None
        else data.get("wind_speed")
        if data.get("wind_speed") is not None
        else data.get("wind_speed_ms"),
        2,
    )
    wind_height_m = _to_float(data.get("wind_height_m"), 10)
    if data.get("wind_speed_2m") is None:
        wind_speed = _wind_speed_to_2m(wind_speed, wind_height_m)
    return WeatherSnapshot(
        date=str(data.get("date") or ""),
        temp_max=_to_float(data.get("temp_max"), 25),
        temp_min=_to_float(data.get("temp_min"), 15),
        temp_avg=_to_float(data.get("temp_avg"), 20),
        humidity_avg=_to_float(data.get("humidity_avg") if data.get("humidity_avg") is not None else data.get("humidity"), 60),
        humidity_max=_to_float(data.get("humidity_max"), 80),
        wind_speed_ms=wind_speed,
        solar_radiation_mj=solar,
        precipitation_mm=_to_float(data.get("precipitation"), 0),
        rain_probability=_to_float(data.get("rain_probability"), 0),
        cloud_cover_pct=_to_float(data.get("cloud_cover") if data.get("cloud_cover") is not None else data.get("cloud_cover_pct"), 50),
        is_fog=data.get("is_fog") is True,
        has_dew=data.get("has_dew") is True,
    )


def default_weather(today: date) -> WeatherSnapshot:
    return WeatherSnapshot(date=today.isoformat())


class SmartGardenerEngine:
    def __init__(self, cell_area_sqm: float = 1.0):
        self.cell_area_sqm = cell_area_sqm

    def calculate_grid_needs(
        self,
        grid_cells: list[dict],
        profiles_map: dict[str, dict] | None = None,
        weather_today: dict | None = None,
        weather_forecast: list[dict] | None = None,
        weather_history: list[dict] | None = None,
        user_actions: list[dict] | None = None,
        manual_observations: list[dict] | None = None,
        soil_type: str | None = None,
        plot_overrides: PlotOverrides | dict | None = None,
        latitude: float | None = None,
        elevation_m: float | None = None,
        sat_overrides: dict[tuple[int, int], float] | None = None,
        today: date | None = None,
    ) -> dict[str, list[dict]]:
        now = today or date.today()
        profiles_map = profiles_map or {}
        w_today = parse_weather(weather_today) if weather_today else default_weather(now)
        w_forecast = [parse_weather(x) for x in (weather_forecast or [])]
        w_history = [parse_weather(x) for x in (weather_history or [])]
        actions = [self._parse_action(x) for x in (user_actions or [])]
        observations = [self._parse_observation(x) for x in (manual_observations or [])]
        plot_overrides_obj = self._parse_plot_overrides(plot_overrides)
        soil = get_soil_properties(soil_type, plot_overrides=plot_overrides_obj)
        lat = latitude if latitude is not None else 50.45
        elevation = elevation_m if elevation_m is not None else 0.0
        et0_today = self.calculate_et0(w_today, latitude_deg=lat, elevation_m=elevation)
        plants = self._parse_grid_cells(grid_cells, now)
        if not plants:
            return []

        self._apply_actions_to_plants(plants, actions, now)
        self._apply_observations_to_plants(plants, observations)
        tasks: list[GardenTask] = []
        hidden_tasks: list[GardenTask] = []
        sat_overrides = sat_overrides or {}
        for plant in plants:
            profile = crop_profile_from_backend(plant.plant_type, plant.category, profiles_map.get(plant.plant_type))
            diag = self._calculate_cell(
                plant,
                profile,
                et0_today,
                w_today,
                w_forecast,
                w_history,
                now,
                soil,
                lat,
                elevation,
                cumulative_gdd_override=sat_overrides.get((plant.cell_col, plant.cell_row)),
                observations=observations,
            )
            tasks.extend(diag.tasks)
            hidden_tasks.extend(diag.hidden_tasks)

        tasks = self._merge_similar_tasks(tasks)
        hidden_tasks = self._merge_similar_tasks(hidden_tasks)
        tasks = [task for task in tasks if not self._is_task_completed(task, actions, now)]
        hidden_tasks = [task for task in hidden_tasks if not self._is_task_completed(task, actions, now)]
        self._apply_plot_calibration_confidence(plot_overrides_obj, tasks)
        self._apply_plot_calibration_confidence(plot_overrides_obj, hidden_tasks)
        tasks.sort(key=lambda t: (t.priority_order, _TASK_TYPE_ORDER.get(t.task_type, 99)))
        hidden_tasks.sort(key=lambda t: (t.priority_order, _TASK_TYPE_ORDER.get(t.task_type, 99)))
        return {
            "tasks": [self._task_to_dict(t) for t in tasks],
            "hidden_tasks": [self._task_to_dict(t) for t in hidden_tasks],
        }

    def _parse_action(self, data: dict) -> GardenAction:
        return GardenAction(
            action_type=str(data.get("action_type") or "general"),
            plant_type=data.get("plant_type"),
            variety=data.get("variety"),
            cell_col=data.get("cell_col"),
            cell_row=data.get("cell_row"),
            task_title=data.get("task_title"),
            scope=str(data.get("scope") or "single"),
            created_at=_parse_dt(data.get("created_at")),
            n_applied_g_m2=_to_float(data.get("n_applied_g_m2"), 0.0),
            p_applied_g_m2=_to_float(data.get("p_applied_g_m2"), 0.0),
            k_applied_g_m2=_to_float(data.get("k_applied_g_m2"), 0.0),
            mg_applied_g_m2=_to_float(data.get("mg_applied_g_m2"), 0.0),
            ca_applied_g_m2=_to_float(data.get("ca_applied_g_m2"), 0.0),
            treatment_kind=data.get("treatment_kind"),
            target_problem=data.get("target_problem"),
            product_profile_id=data.get("product_profile_id"),
            product_type=data.get("product_type"),
            frac_group=data.get("frac_group"),
            reentry_days=_to_int_or_none(data.get("reentry_days")),
            pre_harvest_interval_days=_to_int_or_none(data.get("pre_harvest_interval_days")),
            rainfast_hours=_to_int_or_none(data.get("rainfast_hours")),
        )

    @staticmethod
    def _parse_plot_overrides(data: PlotOverrides | dict | None) -> PlotOverrides | None:
        if data is None or isinstance(data, PlotOverrides):
            return data
        return PlotOverrides(
            ph_class=data.get("ph_class") or data.get("plot_ph_class"),
            drainage_class=data.get("drainage_class") or data.get("plot_drainage_class"),
            organic_input=data.get("organic_input") or data.get("plot_organic_input"),
            last_season_quality=data.get("last_season_quality") or data.get("plot_last_season_quality"),
        )

    @staticmethod
    def _apply_plot_calibration_confidence(plot_overrides: PlotOverrides | None, tasks: list[GardenTask]) -> None:
        score = plot_calibration_score(plot_overrides)
        if score == 50:
            return
        for task in tasks:
            if score < 60:
                task.confidence = _confidence(task.confidence - 5)
            elif score >= 95:
                task.confidence = _confidence(task.confidence + 3)
            task.reasons.append(f"Калібрування ділянки: {score}%")

    def _parse_observation(self, data: dict) -> ManualObservation:
        symptoms = data.get("symptoms") or []
        if not isinstance(symptoms, list):
            symptoms = [str(symptoms)]
        pct = _to_int_or_none(data.get("soil_moisture_pct"))
        if pct is not None:
            pct = max(0, min(100, pct))
        return ManualObservation(
            scope=str(data.get("scope") or "plot"),
            plant_type=data.get("plant_type"),
            variety=data.get("variety"),
            species_filter=(
                [str(item).strip() for item in data.get("species_filter", []) if str(item).strip()]
                if isinstance(data.get("species_filter"), list)
                else None
            ),
            cell_col=data.get("cell_col"),
            cell_row=data.get("cell_row"),
            soil_moisture_pct=pct,
            soil_moisture_status=data.get("soil_moisture_status"),
            leaf_condition=data.get("leaf_condition"),
            symptoms=[str(item).strip() for item in symptoms if str(item).strip()],
            growth_phase=data.get("growth_phase"),
            observed_perennial_season=data.get("observed_perennial_season"),
            notes=data.get("notes"),
            observed_at=_parse_dt(data.get("observed_at")),
        )

    def _apply_observations_to_plants(self, plants: list[PlantInstance], observations: list[ManualObservation]) -> None:
        ordered = sorted(observations, key=lambda item: (item.observed_at, item.specificity()))
        for plant in plants:
            for observation in ordered:
                if not observation.applies_to(plant):
                    continue
                if observation.soil_moisture_pct is not None:
                    plant.observed_soil_moisture_pct = observation.soil_moisture_pct
                if observation.soil_moisture_status:
                    plant.observed_soil_moisture_status = observation.soil_moisture_status
                if observation.leaf_condition:
                    plant.observed_leaf_condition = observation.leaf_condition
                if observation.symptoms:
                    plant.observed_symptoms = observation.symptoms
                    if self._contains_disease_symptom(observation.symptoms, observation.leaf_condition):
                        plant.last_disease_observed_at = observation.observed_at
                if observation.growth_phase:
                    plant.observed_growth_phase = observation.growth_phase
                plant.observed_at = observation.observed_at
    def _is_task_completed(self, task: GardenTask, actions: list[GardenAction], today: date) -> bool:
        expected_action = {
            TaskType.WATERING: "watering",
            TaskType.FERTILIZING: "fertilizing",
            TaskType.DISEASE_PROTECTION: "disease",
            TaskType.PEST_CONTROL: "pest",
            TaskType.PRUNING: "pruning",
            TaskType.HARVESTING: "harvesting",
            TaskType.FROST_PROTECTION: "frost",
            TaskType.COLD_STRESS: "frost",
            TaskType.GENERAL: "general",
        }.get(task.task_type, "general")
        cooldown_days = {
            TaskType.WATERING: _WATERING_COOLDOWN_DAYS,
            TaskType.FERTILIZING: _FERTILIZING_COOLDOWN_DAYS,
            TaskType.DISEASE_PROTECTION: _DISEASE_COOLDOWN_DAYS,
            TaskType.PEST_CONTROL: _DISEASE_COOLDOWN_DAYS,
            TaskType.PRUNING: 14,
            TaskType.HARVESTING: 14,
            TaskType.FROST_PROTECTION: _FROST_COOLDOWN_DAYS,
            TaskType.COLD_STRESS: _FROST_COOLDOWN_DAYS,
            TaskType.GENERAL: 1,
        }.get(task.task_type, 1)

        for action in actions:
            if (today - action.created_at.date()).days >= cooldown_days:
                continue
            if action.task_title and action.task_title == task.title:
                return True
            if action.action_type != expected_action:
                continue
            if action.plant_type and task.plant_name and action.plant_type != task.plant_name:
                continue
            if action.variety and task.variety and action.variety != task.variety:
                continue
            if action.scope == "single":
                if action.cell_col is not None and task.cell_col >= 0 and action.cell_col != task.cell_col:
                    continue
                if action.cell_row is not None and task.cell_row >= 0 and action.cell_row != task.cell_row:
                    continue
            return True
        return False

    def _apply_actions_to_plants(self, plants: list[PlantInstance], actions: list[GardenAction], today: date) -> None:
        for plant in plants:
            for action in actions:
                if not action.applies_to(plant):
                    continue
                if action.action_type == "watering":
                    plant.last_watered_at = max(filter(None, [plant.last_watered_at, action.created_at]))
                elif action.action_type == "fertilizing":
                    plant.last_fertilized_at = max(filter(None, [plant.last_fertilized_at, action.created_at]))
                    if (today - action.created_at.date()).days <= 30:
                        plant.n_applied_30d_g_m2 += action.n_applied_g_m2
                        plant.p_applied_30d_g_m2 += action.p_applied_g_m2
                        plant.k_applied_30d_g_m2 += action.k_applied_g_m2
                        plant.mg_applied_30d_g_m2 += action.mg_applied_g_m2
                        plant.ca_applied_30d_g_m2 += action.ca_applied_g_m2
                    season_start = None
                    if plant.planted_date:
                        try:
                            season_start = date.fromisoformat(plant.planted_date[:10])
                        except ValueError:
                            season_start = None
                    if season_start is None or action.created_at.date() >= season_start:
                        plant.n_applied_season_g_m2 += action.n_applied_g_m2
                        plant.p_applied_season_g_m2 += action.p_applied_g_m2
                        plant.k_applied_season_g_m2 += action.k_applied_g_m2
                        plant.mg_applied_season_g_m2 += action.mg_applied_g_m2
                        plant.ca_applied_season_g_m2 += action.ca_applied_g_m2
                elif action.action_type == "disease":
                    plant.last_disease_at = max(filter(None, [plant.last_disease_at, action.created_at]))
                    if (today - action.created_at.date()).days <= 90:
                        if action.target_problem:
                            plant.protection_counts_90d[action.target_problem] = plant.protection_counts_90d.get(action.target_problem, 0) + 1
                            previous = plant.last_protection_by_problem.get(action.target_problem)
                            if previous is None or action.created_at > previous:
                                plant.last_protection_by_problem[action.target_problem] = action.created_at
                        if action.frac_group:
                            plant.frac_counts_90d[action.frac_group] = plant.frac_counts_90d.get(action.frac_group, 0) + 1
                            if plant.last_frac_group is None or action.created_at >= plant.last_disease_at:
                                plant.last_frac_group = action.frac_group
                elif action.action_type == "pest":
                    if (today - action.created_at.date()).days <= 90 and action.target_problem:
                        plant.protection_counts_90d[action.target_problem] = plant.protection_counts_90d.get(action.target_problem, 0) + 1
                        previous = plant.last_protection_by_problem.get(action.target_problem)
                        if previous is None or action.created_at > previous:
                            plant.last_protection_by_problem[action.target_problem] = action.created_at
                elif action.action_type == "frost":
                    plant.last_frost_protection_at = max(filter(None, [plant.last_frost_protection_at, action.created_at]))
                elif action.action_type == "harvesting":
                    plant.last_harvested_at = max(filter(None, [plant.last_harvested_at, action.created_at]))
                elif action.action_type == "pruning":
                    plant.last_pruned_at = max(filter(None, [plant.last_pruned_at, action.created_at]))

    @staticmethod
    def _in_cooldown(last_at: datetime | None, today: date, cooldown_days: int) -> bool:
        return bool(last_at and (today - last_at.date()).days < cooldown_days)

    def calculate_et0(
        self,
        weather: WeatherSnapshot,
        latitude_deg: float = 50.45,
        elevation_m: float = 0.0,
    ) -> float:
        t = weather.temp_mean
        u2 = max(0.5, weather.wind_speed_ms)
        rh = weather.humidity_avg
        rs = weather.solar_radiation_mj
        es = 0.6108 * math.exp((17.27 * t) / (t + 237.3))
        ea = es * (rh / 100.0)
        delta = (4098.0 * es) / ((t + 237.3) ** 2)
        gamma = _psychrometric_constant(elevation_m)
        rns = 0.77 * rs
        tmax_k = weather.temp_max + 273.16
        tmin_k = weather.temp_min + 273.16
        rso = _clear_sky_radiation(latitude_deg, elevation_m, weather.day_of_year)
        cloud_factor = 1.35 * min(rs / rso, 1.0) - 0.35
        cloud_factor = max(0.05, min(1.0, cloud_factor))
        rnl = (
            4.903e-9
            * (((tmax_k ** 4) + (tmin_k ** 4)) / 2)
            * (0.34 - 0.14 * math.sqrt(max(0.0, ea)))
            * cloud_factor
        )
        rn = max(0.0, rns - rnl)
        numerator = 0.408 * delta * rn + gamma * (900.0 / (t + 273.0)) * u2 * max(0.0, es - ea)
        denom = delta + gamma * (1.0 + 0.34 * u2)
        et0 = max(0.1, numerator / denom)
        return _round(et0, 2)

    @staticmethod
    def calculate_daily_gdd(weather: WeatherSnapshot, t_base: float, t_upper: float | None = None) -> float:
        return calculate_gdd_delta(weather.temp_min, weather.temp_max, t_base, t_upper)

    def accumulate_gdd(
        self,
        history: list[WeatherSnapshot],
        today_weather: WeatherSnapshot,
        t_base: float,
        age_days: int,
        t_upper: float | None = None,
    ) -> float:
        if age_days <= 0:
            return 0.0
        gdd = 0.0
        history_days_needed = max(0, age_days - 1)
        history_window = history[-history_days_needed:] if history_days_needed > 0 else []
        for weather in history_window:
            gdd += self.calculate_daily_gdd(weather, t_base, t_upper)
        history_gdd = gdd
        gdd += self.calculate_daily_gdd(today_weather, t_base, t_upper)
        missing = max(0, history_days_needed - len(history_window))
        if missing > 0:
            if history_window:
                fallback_daily_gdd = history_gdd / len(history_window)
            else:
                fallback_daily_gdd = 15.0
            gdd += fallback_daily_gdd * missing
        return _round(gdd, 1)

    @staticmethod
    def determine_growth_phase(
        age_days: int,
        kc: KcStages,
        cumulative_gdd: float | None = None,
        t_base: float | None = None,
        plant: PlantInstance | None = None,
        today: date | None = None,
    ) -> tuple[GrowthPhase, float]:
        if plant is not None and today is not None and plant.lifecycle_type.is_perennial:
            is_productive = is_plant_productive(plant.age_years, plant.lifecycle_type)
            season = determine_perennial_season(
                today,
                plant.lifecycle_type,
                is_productive=is_productive,
            )
            plant.perennial_season = season
            phase = _perennial_season_to_growth_phase(season)
            return phase, SmartGardenerEngine._kc_for_observed_phase(phase, kc)

        if cumulative_gdd is not None and t_base is not None:
            avg_daily_gdd = 15.0
            gdd_initial = kc.initial_days * avg_daily_gdd
            gdd_dev = gdd_initial + kc.development_days * avg_daily_gdd
            gdd_mid = gdd_dev + kc.mid_season_days * avg_daily_gdd
            gdd_late = gdd_mid + kc.late_season_days * avg_daily_gdd
            if cumulative_gdd <= gdd_initial:
                return GrowthPhase.INITIAL, kc.kc_initial
            if cumulative_gdd <= gdd_dev:
                p = (cumulative_gdd - gdd_initial) / max(1, gdd_dev - gdd_initial)
                return GrowthPhase.DEVELOPMENT, _round(kc.kc_initial + p * (kc.kc_mid - kc.kc_initial), 3)
            if cumulative_gdd <= gdd_mid:
                return GrowthPhase.MID_SEASON, kc.kc_mid
            if cumulative_gdd <= gdd_late:
                p = (cumulative_gdd - gdd_mid) / max(1, gdd_late - gdd_mid)
                return GrowthPhase.LATE_SEASON, _round(kc.kc_mid - p * (kc.kc_mid - kc.kc_end), 3)
            return GrowthPhase.LATE_SEASON, kc.kc_end

        d1 = kc.initial_days
        d2 = d1 + kc.development_days
        d3 = d2 + kc.mid_season_days
        d4 = d3 + kc.late_season_days
        if age_days <= d1:
            return GrowthPhase.INITIAL, kc.kc_initial
        if age_days <= d2:
            p = (age_days - d1) / max(1, kc.development_days)
            return GrowthPhase.DEVELOPMENT, _round(kc.kc_initial + p * (kc.kc_mid - kc.kc_initial), 3)
        if age_days <= d3:
            return GrowthPhase.MID_SEASON, kc.kc_mid
        if age_days <= d4:
            p = (age_days - d3) / max(1, kc.late_season_days)
            return GrowthPhase.LATE_SEASON, _round(kc.kc_mid - p * (kc.kc_mid - kc.kc_end), 3)
        return GrowthPhase.LATE_SEASON, kc.kc_end

    @staticmethod
    def _kc_for_observed_phase(phase: GrowthPhase, kc: KcStages) -> float:
        if phase == GrowthPhase.INITIAL:
            return kc.kc_initial
        if phase == GrowthPhase.DEVELOPMENT:
            return _round((kc.kc_initial + kc.kc_mid) / 2, 3)
        if phase == GrowthPhase.MID_SEASON:
            return kc.kc_mid
        return kc.kc_end
    @staticmethod
    def calculate_root_depth(age_days: int, profile: CropProfile) -> float:
        total = profile.kc.total_season_days
        if total <= 0 or age_days <= 0:
            return profile.root_depth_initial_cm
        progress = min(1.0, age_days / total)
        return _round(profile.root_depth_initial_cm + progress * (profile.root_depth_max_cm - profile.root_depth_initial_cm), 1)

    def _calculate_cell(
        self,
        plant: PlantInstance,
        profile: CropProfile,
        et0_today: float,
        w_today: WeatherSnapshot,
        w_forecast: list[WeatherSnapshot],
        w_history: list[WeatherSnapshot],
        today: date,
        soil: SoilProfile,
        latitude_deg: float,
        elevation_m: float,
        cumulative_gdd_override: float | None = None,
        observations: list[ManualObservation] | None = None,
    ) -> CellDiagnostics:
        diag = CellDiagnostics(plant=plant, profile=profile)
        if cumulative_gdd_override is not None:
            plant.cumulative_gdd = cumulative_gdd_override
            plant.gdd_anchor = "calendar_jan1" if plant.lifecycle_type.is_perennial else "planting_date"
        elif plant.lifecycle_type.is_perennial:
            plant.cumulative_gdd = cumulative_gdd_calendar_year(
                [*w_history, w_today],
                today,
                profile.t_base,
                profile.t_max_growth,
            )
            plant.gdd_anchor = "calendar_jan1"
        else:
            plant.cumulative_gdd = self.accumulate_gdd(
                w_history,
                w_today,
                profile.t_base,
                plant.age_days,
                profile.t_max_growth,
            )
            plant.gdd_anchor = "planting_date"
        phase, kc_val = self.determine_growth_phase(
            plant.age_days,
            profile.kc,
            plant.cumulative_gdd,
            profile.t_base,
            plant=plant,
            today=today,
        )
        plant.growth_phase = phase
        plant.current_kc = kc_val
        if plant.observed_growth_phase:
            try:
                observed_phase = GrowthPhase(str(plant.observed_growth_phase))
                phase = observed_phase
                kc_val = self._kc_for_observed_phase(observed_phase, profile.kc)
                plant.growth_phase = phase
                plant.current_kc = kc_val
            except ValueError:
                pass
        if plant.lifecycle_type.is_perennial:
            season, season_source = self._resolve_perennial_season(plant, today, observations)
            plant.perennial_season = season
            plant.perennial_season_source = season_source
            phase = _perennial_season_to_growth_phase(season)
            kc_val = self._kc_for_observed_phase(phase, profile.kc)
            plant.growth_phase = phase
            plant.current_kc = kc_val
        plant.root_depth_cm = self.calculate_root_depth(plant.age_days, profile)

        diag.et0_mm = et0_today
        diag.etc_mm = _round(et0_today * kc_val, 2)
        diag.effective_rain_mm = _round(w_today.precipitation_mm * soil.effective_rain_multiplier, 2)
        if w_today.is_humid or w_today.has_dew:
            diag.fog_dew_bonus_mm = min(1.5, max(0.0, 0.5 + (w_today.humidity_avg - 90) * 0.02))

        root_depth_m = max(0.05, plant.root_depth_cm / 100.0)
        field_capacity = soil.field_capacity_mm_per_m * root_depth_m
        wilting_point = soil.wilting_point_mm_per_m * root_depth_m
        effective_capacity = max(5.0, field_capacity - wilting_point)

        reset_date = plant.last_watered_at.date() if plant.last_watered_at else None
        if reset_date is None and plant.planted_date:
            try:
                reset_date = date.fromisoformat(plant.planted_date[:10])
            except ValueError:
                reset_date = None
        days_since_reset = (today - reset_date).days if reset_date else plant.age_days
        days_to_simulate = min(days_since_reset, 30)
        plant.soil_water_mm = effective_capacity
        history_window = w_history[-days_to_simulate:] if len(w_history) >= days_to_simulate and days_to_simulate > 0 else w_history
        for i in range(days_to_simulate):
            w_day = history_window[i] if i < len(history_window) else w_today
            day_et0 = self.calculate_et0(w_day, latitude_deg=latitude_deg, elevation_m=elevation_m)
            day_etc = day_et0 * kc_val
            day_rain = w_day.precipitation_mm * soil.effective_rain_multiplier
            day_fog = 0.3 if w_day.is_humid else 0.0
            plant.soil_water_mm = max(0.0, min(plant.soil_water_mm - day_etc + day_rain + day_fog, effective_capacity))

        observed_pct = plant.observed_soil_moisture_pct
        if observed_pct is None and plant.observed_soil_moisture_status:
            observed_pct = {
                "dry": 25,
                "normal": 55,
                "wet": 85,
                "waterlogged": 95,
            }.get(str(plant.observed_soil_moisture_status), None)
        if observed_pct is not None:
            plant.soil_water_mm = max(0.0, min(effective_capacity, effective_capacity * observed_pct / 100.0))

        plant.soil_water_deficit_mm = max(0.0, effective_capacity - plant.soil_water_mm)
        diag.water_deficit_mm = plant.soil_water_deficit_mm
        depletion_pct = plant.soil_water_deficit_mm / max(1, effective_capacity)

        if w_today.temp_max > profile.t_max_growth:
            diag.heat_stress = True
            diag.heat_stress_factor = 1.0 + (w_today.temp_max - profile.t_max_growth) * 0.05
        frost_threshold = profile.frost_critical_threshold_c if profile.frost_critical_threshold_c is not None else profile.frost_tolerance
        if w_today.temp_min <= frost_threshold:
            diag.frost_risk = True

        diag.disease_risks = self._assess_disease_risks(profile, w_today, w_forecast, w_history, plant.age_days, phase, soil, plant)
        self._apply_observation_disease_signals(plant, diag)
        diag.pest_risks = self._assess_pest_risks(profile, w_today, w_forecast, w_history, phase, plant)
        diag.nutrient_leaching_risk = self._assess_nutrient_leaching(w_history, soil)
        self._update_seasonal_nutrient_losses(plant, w_history, soil)
        self._generate_watering_task(plant, profile, diag, depletion_pct, w_forecast, w_history, today, soil)
        if plant.lifecycle_type.is_perennial:
            season = plant.perennial_season or self._resolve_perennial_season(plant, today, observations)[0]
            self._generate_perennial_fertilizer_tasks(plant, season, diag, w_forecast, today, soil)
            self._generate_perennial_protection_tasks(plant, season, diag, w_forecast, today)
            self._generate_perennial_frost_tasks(plant, season, diag, w_forecast, today)
        else:
            self._generate_fertilizing_tasks(plant, profile, diag, phase, w_history, w_forecast, today, soil)
        self._generate_disease_tasks(plant, diag, w_history, w_forecast, today)
        self._generate_pest_tasks(plant, diag, w_forecast, today)
        self._generate_cold_stress_tasks(plant, profile, diag, w_today, w_forecast, today)
        self._generate_climate_tasks(plant, profile, diag, w_today, w_forecast, today)
        self._generate_harvest_task(plant, profile, diag)
        self._generate_status_task(plant, diag, phase, depletion_pct)
        self._apply_profile_confidence(profile, diag.tasks)
        self._apply_profile_confidence(profile, diag.hidden_tasks)
        return diag

    @staticmethod
    def _apply_profile_confidence(profile: CropProfile, tasks: list[GardenTask]) -> None:
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

    @staticmethod
    def _is_tree_phytophthora_context(profile: CropProfile) -> bool:
        haystack = f"{profile.name} {profile.category}".lower()
        tree_terms = (
            "ябл", "apple", "pear", "груш", "айв", "quince", "слив", "plum",
            "виш", "череш", "cherry", "перс", "peach", "абрик", "apricot",
            "плодов", "зернят", "кісточк", "fruit", "tree", "сад",
        )
        disease_terms = " ".join(
            str(item.get("name", "")) if isinstance(item, dict) else str(item)
            for item in profile.common_diseases
        ).lower()
        return any(term in haystack for term in tree_terms) or (
            "phytophthora" in disease_terms
            and any(term in disease_terms for term in ("корен", "шийк", "crown", "root", "collar"))
        )

    @staticmethod
    def _disease_display_name(disease: str, profile: CropProfile) -> str:
        if disease == "late_blight" and SmartGardenerEngine._is_tree_phytophthora_context(profile):
            return "Фітофторозна гниль кореневої шийки/коренів"
        return _DISEASE_NAMES.get(disease, disease)

    def _assess_disease_risks(
        self,
        profile: CropProfile,
        w_today: WeatherSnapshot,
        w_forecast: list[WeatherSnapshot],
        w_history: list[WeatherSnapshot],
        age_days: int,
        phase: GrowthPhase,
        soil: SoilProfile,
        plant: PlantInstance,
    ) -> list[DiseaseRisk]:
        recent = (w_history + [w_today])[-7:]
        upcoming = [
            weather for weather in w_forecast
            if weather.date and w_today.date and (_weather_date(weather.date) or date.max) > (_weather_date(w_today.date) or date.min)
        ][:3]
        risk_window = recent + upcoming
        if not risk_window:
            return []

        risks: list[DiseaseRisk] = []
        inoculum_pressure = self._inoculum_pressure(plant, _weather_date(w_today.date) or date.today())
        for model in _DISEASE_RISK_MODELS:
            risk = self._evaluate_disease_model(model, profile, risk_window, upcoming, phase, soil, inoculum_pressure)
            if risk is not None:
                risks.append(risk)
        risks.sort(key=lambda item: item.risk_level, reverse=True)
        return risks

    def _evaluate_disease_model(
        self,
        model: DiseaseRiskModel,
        profile: CropProfile,
        risk_window: list[WeatherSnapshot],
        upcoming: list[WeatherSnapshot],
        phase: GrowthPhase,
        soil: SoilProfile,
        inoculum_pressure: float = 0.0,
    ) -> DiseaseRisk | None:
        if model.disease == "late_blight":
            return self._evaluate_late_blight_model(model, profile, risk_window, upcoming, phase, soil, inoculum_pressure)

        matched_days = 0
        factor_hits = {
            "temperature": 0,
            "humidity": 0,
            "leaf_wetness": 0,
            "rain": 0,
            "cloud": 0,
            "dry_leaf": 0,
        }

        for weather in risk_window:
            temp_ok = model.temp_min <= weather.temp_mean <= model.temp_max
            humidity_ok = True
            if model.humidity_min is not None:
                humidity_ok = humidity_ok and weather.humidity_avg >= model.humidity_min
            if model.humidity_max is not None:
                humidity_ok = humidity_ok and weather.humidity_avg <= model.humidity_max

            rain_ok = True
            if model.rain_min_mm is not None:
                rain_ok = rain_ok and weather.precipitation_mm >= model.rain_min_mm
            if model.rain_max_mm is not None:
                rain_ok = rain_ok and weather.precipitation_mm <= model.rain_max_mm

            cloud_ok = True
            if model.cloud_min_pct is not None:
                cloud_ok = cloud_ok and weather.cloud_cover_pct >= model.cloud_min_pct
            if model.cloud_max_pct is not None:
                cloud_ok = cloud_ok and weather.cloud_cover_pct <= model.cloud_max_pct

            wetness_hours = self._estimated_leaf_wetness_hours(weather)
            wet_leaf = wetness_hours > 0
            if model.min_leaf_wetness_hours is not None:
                leaf_ok = wetness_hours >= model.min_leaf_wetness_hours
            else:
                leaf_ok = wet_leaf if model.leaf_wetness_required else True
            dry_leaf_ok = (weather.precipitation_mm < 1 and not weather.is_fog) if model.prefers_dry_leaf else True

            if temp_ok:
                factor_hits["temperature"] += 1
            if humidity_ok:
                factor_hits["humidity"] += 1
            if wet_leaf:
                factor_hits["leaf_wetness"] += 1
            if rain_ok:
                factor_hits["rain"] += 1
            if cloud_ok:
                factor_hits["cloud"] += 1
            if dry_leaf_ok and model.prefers_dry_leaf:
                factor_hits["dry_leaf"] += 1

            if temp_ok and humidity_ok and rain_ok and cloud_ok and leaf_ok and dry_leaf_ok:
                matched_days += 1

        if matched_days == 0:
            return None

        susceptibility = profile.susceptibility.get(model.disease, model.default_susceptibility)
        denominator = max(7, len(risk_window))
        risk = (matched_days / denominator) * susceptibility * soil.disease_risk_multiplier
        if inoculum_pressure > 0:
            risk += model.infection_pressure_carryover * inoculum_pressure
        if phase in model.phase_boost:
            risk *= 1.25
        if upcoming and any(self._weather_matches_disease_model(model, weather) for weather in upcoming):
            risk *= 1.12
        risk = min(1.0, risk)
        if risk <= 0.1:
            return None

        factors = self._disease_factor_lines(model, factor_hits, matched_days, len(risk_window), susceptibility, soil, phase, inoculum_pressure)
        name = _DISEASE_NAMES.get(model.disease, model.disease)
        description = (
            f"Ризик хвороби '{name}': {matched_days}/{len(risk_window)} днів у вікні мають умови: "
            f"{model.weather_label}. Модель: {model.model_name}. Фаза: {_phase_name(phase)}."
        )
        confidence = 74 + min(12, matched_days * 2)
        if len(risk_window) >= 10:
            confidence += 4
        if susceptibility >= 0.4:
            confidence += 3
        if profile.profile_confidence < 70:
            confidence -= 6
        return DiseaseRisk(
            model.disease,
            _round(risk, 2),
            _risk_to_priority(risk),
            description,
            model.recommendation,
            factors=factors,
            matched_days=matched_days,
            window_days=len(risk_window),
            model_confidence=_confidence(confidence),
        )

    def _evaluate_late_blight_model(
        self,
        model: DiseaseRiskModel,
        profile: CropProfile,
        risk_window: list[WeatherSnapshot],
        upcoming: list[WeatherSnapshot],
        phase: GrowthPhase,
        soil: SoilProfile,
        inoculum_pressure: float,
    ) -> DiseaseRisk | None:
        if self._is_tree_phytophthora_context(profile):
            return self._evaluate_tree_phytophthora_model(model, profile, risk_window, upcoming, phase, soil, inoculum_pressure)

        susceptibility = profile.susceptibility.get(model.disease, model.default_susceptibility)
        wetness_required = model.min_leaf_wetness_hours or 11
        infection_days = 0
        negfry_score = 0.0
        smith_periods = 0
        wetness_hits = 0
        temperature_hits = 0
        humidity_hits = 0
        previous_smith_day = False

        for weather in risk_window:
            wetness_hours = self._estimated_leaf_wetness_hours(weather)
            temp_ok = model.temp_min <= weather.temp_mean <= model.temp_max
            humidity_ok = weather.humidity_avg >= 75 or weather.humidity_max >= 90
            wetness_ok = wetness_hours >= wetness_required
            smith_day = 10 <= weather.temp_mean <= 25 and wetness_ok and weather.humidity_max >= 90

            if temp_ok:
                temperature_hits += 1
            if humidity_ok:
                humidity_hits += 1
            if wetness_ok:
                wetness_hits += 1
            if temp_ok and humidity_ok and wetness_ok:
                infection_days += 1

            if smith_day and previous_smith_day:
                smith_periods += 1
            previous_smith_day = smith_day

            if temp_ok and wetness_hours >= 6:
                wetness_component = min(1.0, max(0.0, (wetness_hours - 6.0) / 12.0))
                temp_component = max(0.0, 1.0 - abs(weather.temp_mean - 17.0) / 10.0)
                humidity_component = min(1.0, max(0.0, (weather.humidity_max - 75.0) / 25.0))
                rain_component = 0.12 if weather.precipitation_mm >= 0.2 else 0.0
                negfry_score += max(0.0, wetness_component * 0.55 + temp_component * 0.30 + humidity_component * 0.15 + rain_component)

        if infection_days == 0 and smith_periods == 0 and inoculum_pressure <= 0:
            return None

        normalized_negfry = min(1.0, negfry_score / max(3.0, len(risk_window) * 0.55))
        smith_score = min(1.0, smith_periods / 2.0)
        risk = (normalized_negfry * 0.55 + smith_score * 0.25 + susceptibility * 0.20)
        risk *= soil.disease_risk_multiplier
        if phase in model.phase_boost:
            risk *= 1.18
        if upcoming and any(self._weather_matches_disease_model(model, weather) for weather in upcoming):
            risk *= 1.10
        if inoculum_pressure > 0:
            risk += model.infection_pressure_carryover * inoculum_pressure
        risk = min(1.0, risk)
        if risk <= 0.1:
            return None

        name = _DISEASE_NAMES.get(model.disease, model.disease)
        factors = [
            f"Модель: NegFry + Smith Periods",
            f"NegFry score: {normalized_negfry * 100:.0f}%",
            f"Smith Periods: {smith_periods}",
            f"Змочування листя >= {wetness_required:.0f} год: {wetness_hits}/{len(risk_window)} днів",
            f"Температура 10-25°C: {temperature_hits}/{len(risk_window)} днів",
            f"Висока вологість/роса: {humidity_hits}/{len(risk_window)} днів",
            f"Інкубаційний період моделі: {model.incubation_period_days} днів",
            f"Чутливість культури до хвороби: {susceptibility * 100:.0f}%",
            f"Коефіцієнт ґрунту для хвороб: {soil.disease_risk_multiplier:.2f}",
        ]
        if inoculum_pressure > 0:
            factors.append(f"Інокулюм після спостережених симптомів: +{model.infection_pressure_carryover * inoculum_pressure * 100:.0f}% до ризику")
        if phase in model.phase_boost:
            factors.append(f"Фаза підвищує ризик: {_phase_name(phase)}")

        description = (
            f"Ризик хвороби '{name}': NegFry {normalized_negfry * 100:.0f}%, "
            f"Smith Periods {smith_periods}, інфекційних днів {infection_days}/{len(risk_window)}. "
            f"Фаза: {_phase_name(phase)}."
        )
        confidence = 78 + min(10, infection_days * 2) + min(6, smith_periods * 3)
        if len(risk_window) >= 10:
            confidence += 4
        if inoculum_pressure > 0:
            confidence += 5
        if profile.profile_confidence < 70:
            confidence -= 6
        return DiseaseRisk(
            model.disease,
            _round(risk, 2),
            _risk_to_priority(risk),
            description,
            model.recommendation,
            factors=factors,
            matched_days=infection_days,
            window_days=len(risk_window),
            model_confidence=_confidence(confidence),
        )

    def _evaluate_tree_phytophthora_model(
        self,
        model: DiseaseRiskModel,
        profile: CropProfile,
        risk_window: list[WeatherSnapshot],
        upcoming: list[WeatherSnapshot],
        phase: GrowthPhase,
        soil: SoilProfile,
        inoculum_pressure: float,
    ) -> DiseaseRisk | None:
        susceptibility = profile.susceptibility.get(model.disease, max(model.default_susceptibility, 0.45))
        wet_days = sum(1 for weather in risk_window if weather.precipitation_mm >= 2 or weather.humidity_avg >= 85)
        heavy_rain_days = sum(1 for weather in risk_window if weather.precipitation_mm >= 10)
        saturated_days = sum(1 for weather in risk_window if weather.precipitation_mm >= 5 or weather.humidity_avg >= 90)
        mild_root_temp_days = sum(1 for weather in risk_window if 8 <= weather.temp_mean <= 24)
        upcoming_wet = sum(1 for weather in upcoming if weather.precipitation_mm >= 3 or weather.humidity_avg >= 85)
        waterlogging = max(0.0, min(1.0, soil.waterlogging_risk))
        drainage_factor = max(0.0, min(1.0, (soil.disease_risk_multiplier - 0.7) / 0.8))

        wet_score = min(1.0, wet_days / max(4, len(risk_window) * 0.55))
        saturated_score = min(1.0, saturated_days / max(3, len(risk_window) * 0.40))
        temp_score = min(1.0, mild_root_temp_days / max(4, len(risk_window) * 0.55))
        rain_score = min(1.0, heavy_rain_days / 2.0)
        forecast_score = min(1.0, upcoming_wet / 2.0)
        risk = (
            wet_score * 0.22
            + saturated_score * 0.20
            + temp_score * 0.12
            + rain_score * 0.12
            + waterlogging * 0.18
            + drainage_factor * 0.10
            + forecast_score * 0.06
        ) * max(0.45, susceptibility)
        if inoculum_pressure > 0:
            risk += model.infection_pressure_carryover * inoculum_pressure
        risk = min(1.0, risk)
        if risk <= 0.16:
            return None

        factors = [
            "Модель: Phytophthora crown/root rot для плодових дерев",
            f"Вологі/росисті дні: {wet_days}/{len(risk_window)}",
            f"Дні з ризиком перезволоження кореневої зони: {saturated_days}/{len(risk_window)}",
            f"Сильні опади: {heavy_rain_days}/{len(risk_window)}",
            f"Температура кореневої зони в активному діапазоні 8-24°C: {mild_root_temp_days}/{len(risk_window)}",
            f"Ризик застою води за типом ґрунту: {waterlogging * 100:.0f}%",
            f"Коефіцієнт ґрунту для хвороб: {soil.disease_risk_multiplier:.2f}",
            "Ключова перевірка: коренева шийка, підщепа і кора біля землі, а не тільки листя",
            "Ключовий контроль: відвести воду, відкрити кореневу шийку і не мульчувати впритул до кори",
        ]
        if upcoming_wet:
            factors.append(f"У прогнозі ще {upcoming_wet} вологі дні, ризик не знято")
        if inoculum_pressure > 0:
            factors.append(f"Інокулюм після спостережених симптомів: +{model.infection_pressure_carryover * inoculum_pressure * 100:.0f}% до ризику")

        description = (
            "Ризик фітофторозної гнилі кореневої шийки/коренів яблуні: "
            f"волога коренева зона {saturated_days}/{len(risk_window)} дн., "
            f"ризик застою води {waterlogging * 100:.0f}%. "
            "Це не листкова фітофтора томата; потрібна перевірка кореневої шийки, дренаж і тільки дозволені препарати проти ооміцетів."
        )
        recommendation = (
            "Рекомендація: відгребіть ґрунт від кореневої шийки на 10-15 см, перевірте кору біля землі, відведіть воду. "
            "За підтвердження Phytophthora використовуйте лише дозволені для плодових/зерняткових препарати проти ооміцетів: фосетил-Al, фосфіти/фосфонати або мефеноксам/металаксил-М за етикеткою. "
            "Мідь, бордоська суміш, Хорус, Скор і Топаз не є базовим рішенням для кореневої Phytophthora."
        )
        confidence = 76 + min(10, wet_days) + min(5, heavy_rain_days * 2)
        if soil.waterlogging_risk >= 0.45:
            confidence += 5
        if len(risk_window) >= 10:
            confidence += 4
        if profile.profile_confidence < 70:
            confidence -= 6
        return DiseaseRisk(
            model.disease,
            _round(risk, 2),
            _risk_to_priority(risk),
            description,
            recommendation,
            factors=factors,
            matched_days=saturated_days,
            window_days=len(risk_window),
            model_confidence=_confidence(confidence),
        )

    @staticmethod
    def _weather_matches_disease_model(model: DiseaseRiskModel, weather: WeatherSnapshot) -> bool:
        if not (model.temp_min <= weather.temp_mean <= model.temp_max):
            return False
        if model.humidity_min is not None and weather.humidity_avg < model.humidity_min:
            return False
        if model.humidity_max is not None and weather.humidity_avg > model.humidity_max:
            return False
        if model.rain_min_mm is not None and weather.precipitation_mm < model.rain_min_mm:
            return False
        if model.rain_max_mm is not None and weather.precipitation_mm > model.rain_max_mm:
            return False
        if model.cloud_min_pct is not None and weather.cloud_cover_pct < model.cloud_min_pct:
            return False
        if model.cloud_max_pct is not None and weather.cloud_cover_pct > model.cloud_max_pct:
            return False
        wetness_hours = SmartGardenerEngine._estimated_leaf_wetness_hours(weather)
        if model.min_leaf_wetness_hours is not None and wetness_hours < model.min_leaf_wetness_hours:
            return False
        if model.leaf_wetness_required and wetness_hours <= 0:
            return False
        if model.prefers_dry_leaf and (weather.precipitation_mm >= 1 or weather.is_fog):
            return False
        return True

    @staticmethod
    def _estimated_leaf_wetness_hours(weather: WeatherSnapshot) -> float:
        hours = 0.0
        if weather.is_fog:
            hours += 8.0
        if weather.has_dew:
            hours += 7.0
        if weather.humidity_max >= 95:
            hours += 6.0
        elif weather.humidity_max >= 90:
            hours += 4.0
        if weather.humidity_avg >= 90:
            hours += 3.0
        elif weather.humidity_avg >= 80 and weather.cloud_cover_pct >= 70:
            hours += 2.0
        if weather.precipitation_mm > 0.2:
            hours += min(8.0, 2.0 + weather.precipitation_mm * 0.8)
        if weather.wind_speed_ms >= 5.0:
            hours -= 2.0
        return max(0.0, min(24.0, hours))

    @staticmethod
    def _disease_factor_lines(
        model: DiseaseRiskModel,
        factor_hits: dict[str, int],
        matched_days: int,
        window_days: int,
        susceptibility: float,
        soil: SoilProfile,
        phase: GrowthPhase,
        inoculum_pressure: float = 0.0,
    ) -> list[str]:
        lines = [
            f"Інфекційне вікно: {matched_days}/{window_days} днів",
            f"Температура в межах моделі: {factor_hits['temperature']}/{window_days} днів ({model.temp_min:.0f}-{model.temp_max:.0f}°C)",
            f"Чутливість культури до хвороби: {susceptibility * 100:.0f}%",
            f"Коефіцієнт ґрунту для хвороб: {soil.disease_risk_multiplier:.2f}",
        ]
        if model.humidity_min is not None or model.humidity_max is not None:
            lines.append(f"Вологість у межах моделі: {factor_hits['humidity']}/{window_days} днів")
        if model.leaf_wetness_required:
            lines.append(f"Роса/туман/змочування листя: {factor_hits['leaf_wetness']}/{window_days} днів")
        if model.rain_min_mm is not None or model.rain_max_mm is not None:
            lines.append(f"Опади у межах моделі: {factor_hits['rain']}/{window_days} днів")
        if model.cloud_min_pct is not None or model.cloud_max_pct is not None:
            lines.append(f"Хмарність у межах моделі: {factor_hits['cloud']}/{window_days} днів")
        if model.prefers_dry_leaf:
            lines.append(f"Сухе листя/без дощу: {factor_hits['dry_leaf']}/{window_days} днів")
        if phase in model.phase_boost:
            lines.append(f"Фаза підвищує ризик: {_phase_name(phase)}")
        return lines

    @staticmethod
    def _contains_disease_symptom(symptoms: list[str], leaf_condition: str | None = None) -> bool:
        haystack = " ".join([*(symptoms or []), leaf_condition or ""]).lower()
        disease_terms = (
            "spots", "spot", "mold", "rot", "powder", "mildew", "blight", "rust",
            "\u043f\u043b\u044f\u043c", "\u043d\u0430\u043b\u0456\u0442", "\u0433\u043d\u0438\u043b", "\u0431\u043e\u0440\u043e\u0448\u043d\u0438\u0441\u0442", "\u0456\u0440\u0436", "\u0444\u0456\u0442\u043e\u0444\u0442\u043e\u0440", "\u043f\u043b\u0456\u0441\u043d\u044f",
        )
        return any(term in haystack for term in disease_terms)

    @staticmethod
    def _contains_pest_symptom(symptoms: list[str], leaf_condition: str | None = None) -> bool:
        haystack = " ".join([*(symptoms or []), leaf_condition or ""]).lower()
        pest_terms = (
            "aphid", "mite", "spider", "webbing", "beetle", "weevil", "larva",
            "caterpillar", "worm", "holes", "chewed", "sticky", "honeydew",
            "eggs", "thrips", "fly", "midge",
            "попел", "кліщ", "павутин", "жук", "довгонос", "личин",
            "гусен", "черв", "дір", "об'їд", "обїд", "скручен", "липк",
            "медв", "трипс", "яйц", "муха", "галиц", "дрозоф",
        )
        return any(term in haystack for term in pest_terms)

    @staticmethod
    def _inoculum_pressure(plant: PlantInstance, today: date) -> float:
        if plant.last_disease_observed_at is None:
            return 0.0
        days = max(0, (today - plant.last_disease_observed_at.date()).days)
        if days <= 14:
            return 1.0
        if days <= 30:
            return 0.65
        if days <= 45:
            return 0.35
        return 0.0

    def _apply_observation_disease_signals(self, plant: PlantInstance, diag: CellDiagnostics) -> None:
        symptoms = {item.lower() for item in plant.observed_symptoms}
        leaf = (plant.observed_leaf_condition or "").lower()
        if not symptoms and not leaf:
            return
        symptom_text = ", ".join(plant.observed_symptoms) if plant.observed_symptoms else plant.observed_leaf_condition or ""
        if any(key in symptoms or key in leaf for key in ["spots", "mold", "rot", "powder", "плями", "наліт", "гниль"]):
            diag.disease_risks.append(DiseaseRisk(
                "observed_symptoms",
                0.55,
                TaskPriority.HIGH,
                f"Користувач зафіксував симптоми на листі: {symptom_text}.",
                "Рекомендація: огляньте рослину зблизька, видаліть сильно уражені листки та оцініть потребу в захисті.",
            ))
        elif any(key in symptoms or key in leaf for key in ["yellowing", "wilting", "хлороз", "в'янення", "вянення", "жовтіє"]):
            diag.disease_risks.append(DiseaseRisk(
                "observed_stress",
                0.35,
                TaskPriority.MEDIUM,
                f"Користувач зафіксував стрес рослини: {symptom_text}.",
                "Рекомендація: перевірте вологість ґрунту, корені та нижній бік листя перед обробкою.",
            ))
    def _assess_pest_risks(
        self,
        profile: CropProfile,
        w_today: WeatherSnapshot,
        w_forecast: list[WeatherSnapshot],
        w_history: list[WeatherSnapshot],
        phase: GrowthPhase,
        plant: PlantInstance,
    ) -> list[PestRisk]:
        pests = [
            item if isinstance(item, dict) else {"name": str(item), "likelihood": "medium"}
            for item in profile.common_pests
            if (isinstance(item, dict) or str(item).strip())
        ]
        if not pests:
            return []
        weather_window = [*w_history[-3:], w_today, *w_forecast[:3]]
        risks: list[PestRisk] = []
        for pest in pests[:12]:
            name = str(pest.get("name") or "").strip()
            if not name:
                continue
            observed = self._pest_observed(pest, plant)
            likelihood = self._pest_likelihood_value(pest)
            weather_score, weather_factors = self._pest_weather_score(pest, weather_window, phase)
            phase_score = 0.10 if phase in {GrowthPhase.DEVELOPMENT, GrowthPhase.MID_SEASON, GrowthPhase.LATE_SEASON} else 0.04
            score = min(1.0, likelihood + weather_score + phase_score + (0.35 if observed else 0.0))
            if score < 0.32 and not observed:
                continue
            factors = [
                f"Базова ймовірність у профілі культури: {likelihood * 100:.0f}%",
                f"Фаза рослини: {_phase_name(phase)}",
                *weather_factors,
            ]
            if observed:
                factors.insert(0, "Є ручне спостереження або симптоми, схожі на шкідника")
            risks.append(PestRisk(
                pest=pest,
                risk_level=_round(score, 2),
                priority=_risk_to_priority(score),
                description=f"Ймовірність шкідника «{name}» оцінена за профілем культури, погодою, фазою росту та спостереженнями.",
                recommendation=str(pest.get("treatment") or pest.get("control") or "Оглянути рослину й обрати IPM-захід за підтвердженим шкідником."),
                factors=factors,
                observed=observed,
            ))
        risks.sort(key=lambda item: (item.observed, item.risk_level), reverse=True)
        return risks[:3]

    @staticmethod
    def _pest_likelihood_value(pest: dict) -> float:
        value = str(pest.get("likelihood") or pest.get("frequency") or pest.get("risk") or "medium").lower()
        if any(term in value for term in ("high", "вис", "част")):
            return 0.38
        if any(term in value for term in ("low", "низ", "рід")):
            return 0.16
        return 0.26

    @staticmethod
    def _pest_observed(pest: dict, plant: PlantInstance) -> bool:
        haystack = " ".join([
            *(plant.observed_symptoms or []),
            plant.observed_leaf_condition or "",
        ]).lower()
        pest_name = str(pest.get("name") or "").lower()
        name_tokens = [token for token in pest_name.replace("/", " ").replace("-", " ").split() if len(token) >= 4]
        if any(token in haystack for token in name_tokens):
            return True
        return SmartGardenerEngine._contains_pest_symptom(plant.observed_symptoms, plant.observed_leaf_condition)

    @staticmethod
    def _pest_weather_score(
        pest: dict,
        weather_window: list[WeatherSnapshot],
        phase: GrowthPhase,
    ) -> tuple[float, list[str]]:
        if not weather_window:
            return 0.0, []
        name = str(pest.get("name") or "").lower()
        factors: list[str] = []
        score = 0.0
        warm_days = sum(1 for weather in weather_window if 16 <= weather.temp_mean <= 30)
        hot_dry_days = sum(1 for weather in weather_window if weather.temp_max >= 27 and weather.humidity_avg <= 60 and weather.precipitation_mm < 1)
        wet_days = sum(1 for weather in weather_window if weather.precipitation_mm >= 2 or weather.humidity_avg >= 85)
        calm_days = sum(1 for weather in weather_window if weather.wind_speed_ms <= 3.5)

        if any(term in name for term in ("mite", "кліщ", "павутин")):
            score += min(0.34, hot_dry_days * 0.09)
            if hot_dry_days:
                factors.append(f"Спекотно й сухо для кліщів: {hot_dry_days}/{len(weather_window)} дн.")
        elif any(term in name for term in ("aphid", "попел")):
            score += min(0.30, warm_days * 0.05 + calm_days * 0.03)
            if warm_days:
                factors.append(f"Тепле вікно для попелиці: {warm_days}/{len(weather_window)} дн.")
        elif any(term in name for term in ("slug", "слимак")):
            score += min(0.30, wet_days * 0.08)
            if wet_days:
                factors.append(f"Вологі дні для слимаків: {wet_days}/{len(weather_window)}")
        elif any(term in name for term in ("beetle", "weevil", "larva", "caterpillar", "worm", "fly", "жук", "довгонос", "личин", "гусен", "черв", "муха", "галиц", "дрозоф")):
            score += min(0.28, warm_days * 0.06)
            if phase in {GrowthPhase.DEVELOPMENT, GrowthPhase.MID_SEASON}:
                score += 0.06
            if warm_days:
                factors.append(f"Активне тепле вікно для комах: {warm_days}/{len(weather_window)} дн.")
        else:
            score += min(0.22, warm_days * 0.04)
            if warm_days:
                factors.append(f"Погодні умови дозволяють активність шкідників: {warm_days}/{len(weather_window)} дн.")

        if any(term in name for term in ("root", "wireworm", "хрущ", "дротяник", "корен")) and phase in {GrowthPhase.INITIAL, GrowthPhase.DEVELOPMENT}:
            score += 0.08
            factors.append("Молода коренева система вразливіша до ґрунтових шкідників")
        return min(0.45, score), factors

    @staticmethod
    def _pest_guide_lines(profile: CropProfile, pest_name: str) -> list[str]:
        guide = profile.treatment_guide if isinstance(profile.treatment_guide, dict) else {}
        catalog_lines = SmartGardenerEngine._problem_catalog_lines(
            profile.common_pests,
            pest_name,
            problem_label="Шкідник",
        )
        pest_lines = SmartGardenerEngine._treatment_guide_lines(
            guide,
            ("pest_controls",),
            pest_name=pest_name,
            profile=profile,
            recommendation_kind="insecticide",
        )
        general_lines = SmartGardenerEngine._treatment_guide_lines(
            guide,
            ("biological_controls", "chemical_controls", "organic_options", "safety_notes"),
            profile=profile,
            recommendation_kind="insecticide",
        )
        return SmartGardenerEngine._dedupe_lines([*catalog_lines, *pest_lines, *general_lines])[:8]

    @staticmethod
    def _protection_guide_lines(profile: CropProfile, disease_name: str) -> list[str]:
        guide = profile.treatment_guide if isinstance(profile.treatment_guide, dict) else {}
        catalog_lines = SmartGardenerEngine._problem_catalog_lines(
            profile.common_diseases,
            disease_name,
            problem_label="Хвороба",
        )
        general_lines = SmartGardenerEngine._treatment_guide_lines(
            guide,
            ("biological_controls", "chemical_controls", "copper_controls", "safety_notes"),
            pest_name=disease_name,
            profile=profile,
            recommendation_kind="fungicide",
        )
        return SmartGardenerEngine._dedupe_lines([*catalog_lines, *general_lines])[:8]

    @staticmethod
    def _dedupe_lines(lines: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for line in lines:
            clean = " ".join(str(line).split())
            key = clean.lower()
            if clean and key not in seen:
                result.append(clean)
                seen.add(key)
        return result

    @staticmethod
    def _problem_catalog_lines(items: list[dict], problem_name: str, problem_label: str) -> list[str]:
        matched = SmartGardenerEngine._match_problem_item(items, problem_name)
        if not matched:
            return []

        lines: list[str] = []
        name = str(matched.get("name") or problem_name).strip()
        treatment = SmartGardenerEngine._string_list(matched.get("treatment"))
        prevention = SmartGardenerEngine._string_list(matched.get("prevention"))
        notes = str(matched.get("notes") or "").strip()
        for item in treatment[:3]:
            lines.append(f"{problem_label} {name}: {item}")
        for item in prevention[:2]:
            lines.append(f"Профілактика для {name}: {item}")
        if notes:
            lines.append(f"Уточнення для {name}: {notes}")
        return lines

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @staticmethod
    def _match_problem_item(items: list[dict], problem_name: str) -> dict | None:
        needle_tokens = SmartGardenerEngine._meaningful_tokens(problem_name)
        best: tuple[int, dict] | None = None
        for item in items or []:
            if not isinstance(item, dict):
                continue
            haystack = " ".join(
                [
                    str(item.get("name") or ""),
                    " ".join(SmartGardenerEngine._string_list(item.get("symptoms"))),
                    " ".join(SmartGardenerEngine._string_list(item.get("treatment"))),
                ]
            )
            hay_tokens = set(SmartGardenerEngine._meaningful_tokens(haystack))
            score = len(set(needle_tokens) & hay_tokens)
            item_name = str(item.get("name") or "").lower()
            if problem_name and problem_name.lower() in item_name:
                score += 3
            if score and (best is None or score > best[0]):
                best = (score, item)
        return best[1] if best else None

    @staticmethod
    def _meaningful_tokens(text: str) -> list[str]:
        normalized = (
            str(text or "")
            .lower()
            .replace("/", " ")
            .replace("-", " ")
            .replace("—", " ")
            .replace(",", " ")
            .replace(".", " ")
            .replace("(", " ")
            .replace(")", " ")
        )
        stop = {
            "для", "при", "або", "від", "проти", "та", "і", "на", "у", "в", "з",
            "the", "and", "or", "rot", "root", "leaf",
        }
        return [token for token in normalized.split() if len(token) >= 4 and token not in stop]

    @staticmethod
    def _is_tree_crop(profile: CropProfile) -> bool:
        text = f"{profile.name} {profile.category}".lower()
        return any(
            term in text
            for term in (
                "ябл", "груш", "айв", "слив", "виш", "череш", "перс", "абрик",
                "плодов", "зернят", "кісточк", "fruit", "tree", "apple", "pear",
                "cherry", "peach", "apricot", "plum",
            )
        )

    @staticmethod
    def _line_safe_for_profile(line: str, profile: CropProfile | None) -> bool:
        if not profile:
            return True
        lower = line.lower()
        if SmartGardenerEngine._is_tree_crop(profile) and any(
            term in lower for term in ("квадріс", "quadris", "азоксистробін", "azoxystrobin")
        ):
            return False
        return True

    @staticmethod
    def _line_matches_recommendation_kind(line: str, recommendation_kind: str | None) -> bool:
        if not recommendation_kind:
            return True
        lower = line.lower()
        fungicide_terms = (
            "фунгіцид", "хвороб", "фітофтор", "мілдью", "борошнист", "гниль",
            "плямист", "іржа", "парш", "мід", "манкоцеб", "фосетил", "фосфіт",
            "металаксил", "мефеноксам", "дифеноконазол", "пропіконазол",
            "азоксистробін", "trichoderma", "bacillus subtilis",
            "fungicide", "disease", "blight", "mildew", "rot", "rust",
            "mancozeb", "metalaxyl", "mefenoxam", "difenoconazole",
            "propiconazole", "azoxystrobin",
        )
        insecticide_terms = (
            "інсектицид", "акарицид", "шкідник", "попелиц", "кліщ", "жук",
            "довгонос", "личин", "гусен", "муха", "галиц", "дрозофіл",
            "дротян", "хрущ", "слимак", "нематод", "спіносад", "піретроїд",
            "ацетаміприд", "імідаклоприд", "тіаметоксам", "абамектин",
            "авермектин", "bacillus thuringiensis", "bt ",
            "insecticide", "acaricide", "pest", "aphid", "mite", "beetle",
            "weevil", "larva", "caterpillar", "fly", "wireworm", "grub",
            "spinosad", "pyrethroid", "acetamiprid", "imidacloprid",
            "thiamethoxam", "abamectin", "avermectin",
        )
        if recommendation_kind == "insecticide":
            if any(term in lower for term in fungicide_terms) and not any(term in lower for term in insecticide_terms):
                return False
            return True
        if recommendation_kind == "fungicide":
            if any(term in lower for term in insecticide_terms) and not any(term in lower for term in fungicide_terms):
                return False
            return True
        return True

    @staticmethod
    def _treatment_guide_lines(
        guide: dict,
        keys: tuple[str, ...],
        pest_name: str | None = None,
        profile: CropProfile | None = None,
        recommendation_kind: str | None = None,
    ) -> list[str]:
        labels = {
            "pest_controls": "IPM",
            "biological_controls": "Біологічні",
            "chemical_controls": "Хімічні",
            "copper_controls": "Мідьвмісні",
            "organic_options": "Органічні",
            "safety_notes": "Безпека",
        }
        exact: list[str] = []
        general: list[str] = []
        needle = (pest_name or "").lower()
        for key in keys:
            value = guide.get(key)
            raw_items: list[str] = []
            if isinstance(value, list):
                raw_items.extend(str(item) for item in value[:4] if str(item).strip())
            elif isinstance(value, str) and value.strip():
                raw_items.append(value.strip())
            label = labels.get(key, key)
            for item in raw_items:
                line = f"{label}: {item}"
                if not SmartGardenerEngine._line_safe_for_profile(line, profile):
                    continue
                if not SmartGardenerEngine._line_matches_recommendation_kind(line, recommendation_kind):
                    continue
                if needle and needle in item.lower():
                    exact.append(line)
                else:
                    general.append(line)
        return [*exact, *general]

    @staticmethod
    def _is_soil_dwelling_pest(risk: PestRisk) -> bool:
        text = " ".join(
            [
                risk.key,
                risk.description,
                risk.recommendation,
                *risk.factors,
            ]
        ).lower()
        return any(
            term in text
            for term in (
                "дротяник",
                "wireworm",
                "хрущ",
                "grub",
                "капустян",
                "mole cricket",
                "нематод",
                "nematode",
                "корен",
                "root",
                "ґрунтов",
                "грунтов",
                "soil",
            )
        )

    @staticmethod
    def _pest_confirmation_constraint(risk: PestRisk) -> str:
        if SmartGardenerEngine._is_soil_dwelling_pest(risk):
            return (
                "IPM: спочатку підтвердити ґрунтового шкідника оглядом кореневої зони, "
                "верхніх 10-15 см ґрунту, пошкоджених коренів/бульб або приманкових пасток"
            )
        return "IPM: спочатку підтвердити шкідника оглядом нижнього боку листків, бутонів, пагонів і плодів"

    @staticmethod
    def _pest_confirmation_text(risk: PestRisk) -> str:
        if SmartGardenerEngine._is_soil_dwelling_pest(risk):
            return (
                "Перед внесенням препарату підтвердіть ґрунтового шкідника: перевірте кореневу зону, "
                "верхні 10-15 см ґрунту біля рослини, пошкоджені корені/бульби або приманкові пастки. "
            )
        return (
            "Перед внесенням препарату підтвердіть шкідника: огляд 10-20 листків/бутонів, "
            "нижній бік листка, молоді пагони й плоди. "
        )

    @staticmethod
    def _pest_monitoring_text(risk: PestRisk) -> str:
        if SmartGardenerEngine._is_soil_dwelling_pest(risk):
            return (
                "Поки достатньо огляду й профілактики: перевірте кореневу зону, ґрунтові грудки, "
                "приманкові пастки та пошкодження коренів/бульб; втручайтесь лише після підтвердження."
            )
        return "Поки достатньо огляду й профілактики: перевірте рослини, пастки або нижній бік листків, і втручайтесь лише після підтвердження."

    @staticmethod
    def _assess_nutrient_leaching(w_history: list[WeatherSnapshot], soil: SoilProfile) -> float:
        if len(w_history) < 3:
            return 0.0
        rain = sum(w.precipitation_mm for w in w_history[-5:])
        if rain <= 30:
            return 0.0
        soil_factor = soil.nitrogen_leaching_multiplier * (1.0 + max(0.0, 0.55 - soil.nutrient_retention))
        return min(1.0, (rain / 80.0) * soil_factor)

    @staticmethod
    def _fertilizing_confidence(base: int, plant: PlantInstance, w_history: list[WeatherSnapshot], w_forecast: list[WeatherSnapshot], trigger_strength: float) -> int:
        conf = base + int(trigger_strength * 8)
        if plant.planted_date:
            conf += 4
        if len(w_history) >= 14:
            conf += 4
        elif len(w_history) < 7:
            conf -= 7
        if len(w_forecast) >= 3:
            conf += 2
        return _confidence(conf)

    @staticmethod
    def _disease_confidence(risk: DiseaseRisk, w_history: list[WeatherSnapshot], w_forecast: list[WeatherSnapshot]) -> int:
        conf = 76 + int(risk.risk_level * 18)
        if len(w_history) >= 7:
            conf += 4
        else:
            conf -= 8
        if len(w_forecast) >= 3:
            conf += 3
        return _confidence(conf)

    @staticmethod
    def _phase_nutrient_progress(phase: GrowthPhase, age_days: int, profile: CropProfile) -> float:
        initial_end = max(1, profile.kc.initial_days)
        development_end = initial_end + max(1, profile.kc.development_days)
        mid_end = development_end + max(1, profile.kc.mid_season_days)
        total = max(mid_end + max(1, profile.kc.late_season_days), profile.kc.total_season_days, 1)
        age = max(0, age_days)

        def lerp(start: float, end: float, position: float) -> float:
            return start + (end - start) * min(1.0, max(0.0, position))

        if age <= initial_end:
            progress = lerp(0.05, 0.18, age / initial_end)
        elif age <= development_end:
            progress = lerp(0.18, 0.58, (age - initial_end) / max(1, development_end - initial_end))
        elif age <= mid_end:
            progress = lerp(0.58, 0.92, (age - development_end) / max(1, mid_end - development_end))
        else:
            progress = lerp(0.92, 0.98, (age - mid_end) / max(1, total - mid_end))

        phase_floor = {
            GrowthPhase.INITIAL: 0.08,
            GrowthPhase.DEVELOPMENT: 0.25,
            GrowthPhase.MID_SEASON: 0.62,
            GrowthPhase.LATE_SEASON: 0.88,
        }.get(phase, progress)
        return min(0.98, max(progress, phase_floor))

    @staticmethod
    def _seasonal_nutrient_targets(profile: CropProfile) -> dict[str, float]:
        n = profile.nutrients
        return {
            "N": n.nitrogen * 4.0,
            "P": n.phosphorus * 3.2,
            "K": n.potassium * 4.2,
            "Mg": n.magnesium * 2.8,
            "Ca": n.calcium * 3.0,
        }

    @staticmethod
    def _seasonal_nutrient_loss_factor(w_history: list[WeatherSnapshot], soil: SoilProfile) -> float:
        if not w_history:
            return 0.0
        rain = sum(w.precipitation_mm for w in w_history[-30:])
        if rain <= 30:
            return 0.0
        soil_factor = soil.nitrogen_leaching_multiplier * (1.0 + max(0.0, 0.55 - soil.nutrient_retention))
        return min(0.45, ((rain - 30.0) / 180.0) * soil_factor)

    def _update_seasonal_nutrient_losses(self, plant: PlantInstance, w_history: list[WeatherSnapshot], soil: SoilProfile) -> None:
        factor = self._seasonal_nutrient_loss_factor(w_history, soil)
        plant.n_lost_season_g_m2 = plant.n_applied_season_g_m2 * factor
        plant.p_lost_season_g_m2 = plant.p_applied_season_g_m2 * factor * 0.35
        plant.k_lost_season_g_m2 = plant.k_applied_season_g_m2 * factor * 0.75
        plant.mg_lost_season_g_m2 = plant.mg_applied_season_g_m2 * factor * 0.80
        plant.ca_lost_season_g_m2 = plant.ca_applied_season_g_m2 * factor * 0.55

    @staticmethod
    def _net_seasonal_nutrients(plant: PlantInstance) -> dict[str, float]:
        return {
            "N": max(0.0, plant.n_applied_season_g_m2 - plant.n_lost_season_g_m2),
            "P": max(0.0, plant.p_applied_season_g_m2 - plant.p_lost_season_g_m2),
            "K": max(0.0, plant.k_applied_season_g_m2 - plant.k_lost_season_g_m2),
            "Mg": max(0.0, plant.mg_applied_season_g_m2 - plant.mg_lost_season_g_m2),
            "Ca": max(0.0, plant.ca_applied_season_g_m2 - plant.ca_lost_season_g_m2),
        }

    @staticmethod
    def _phosphorus_availability_factor(soil: SoilProfile) -> float:
        ph_mid = (soil.ph_min + soil.ph_max) / 2
        if 6.2 <= ph_mid <= 7.2:
            ph_factor = 1.0
        elif ph_mid < 5.5 or ph_mid > 8.0:
            ph_factor = 0.55
        else:
            ph_factor = 0.78
        fixation_factor = 1.0 - min(0.45, soil.phosphorus_fixation_risk * 0.55)
        return max(0.35, ph_factor * fixation_factor)

    @staticmethod
    def _soil_initial_nutrient_pool(soil: SoilProfile) -> dict[str, float]:
        p_factor = SmartGardenerEngine._phosphorus_availability_factor(soil)
        return {
            "N": soil.initial_n_g_m2 * (0.75 + soil.organic_matter_pct / 12.0),
            "P": soil.initial_p_g_m2 * p_factor,
            "K": soil.initial_k_g_m2 * (0.70 + soil.potassium_retention * 0.30),
            "Mg": soil.initial_mg_g_m2,
            "Ca": soil.initial_ca_g_m2,
        }

    @staticmethod
    def _apply_nutrient_antagonism(pool: dict[str, float]) -> tuple[dict[str, float], list[str]]:
        adjusted = dict(pool)
        lines: list[str] = []
        k_mg_ratio = adjusted["K"] / max(0.1, adjusted["Mg"])
        if k_mg_ratio > 4.0:
            factor = max(0.55, 1.0 - (k_mg_ratio - 4.0) * 0.08)
            adjusted["Mg"] *= factor
            lines.append(f"\u0410\u043d\u0442\u0430\u0433\u043e\u043d\u0456\u0437\u043c K-Mg: K/Mg {k_mg_ratio:.1f}, \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0456\u0441\u0442\u044c Mg \u0437\u043d\u0438\u0436\u0435\u043d\u0430 \u0434\u043e {factor * 100:.0f}%")

        ca_k_mg_ratio = adjusted["Ca"] / max(0.1, adjusted["K"] + adjusted["Mg"])
        if ca_k_mg_ratio > 3.5:
            factor = max(0.65, 1.0 - (ca_k_mg_ratio - 3.5) * 0.06)
            adjusted["K"] *= factor
            adjusted["Mg"] *= factor
            lines.append(f"\u0410\u043d\u0442\u0430\u0433\u043e\u043d\u0456\u0437\u043c Ca-K/Mg: Ca/(K+Mg) {ca_k_mg_ratio:.1f}, K \u0456 Mg \u0441\u043a\u043e\u0440\u0438\u0433\u043e\u0432\u0430\u043d\u0456 \u0434\u043e {factor * 100:.0f}%")
        return adjusted, lines

    def _available_seasonal_nutrients(self, plant: PlantInstance, soil: SoilProfile) -> tuple[dict[str, float], list[str]]:
        pool = self._soil_initial_nutrient_pool(soil)
        net = self._net_seasonal_nutrients(plant)
        combined = {name: pool[name] + net[name] for name in pool}
        return self._apply_nutrient_antagonism(combined)

    def _available_nutrients_for_recommendation(self, plant: PlantInstance, soil: SoilProfile) -> tuple[dict[str, float], list[str]]:
        pool = self._soil_initial_nutrient_pool(soil)
        # Catalog soil fertility is not the same as a lab-confirmed available pool.
        # Use it as a conservative credit so default soil types reduce overfeeding
        # without silencing phase-specific recommendations.
        soil_credit = {
            "N": pool["N"] * 0.30,
            "P": pool["P"] * 0.20,
            "K": pool["K"] * 0.35,
            "Mg": pool["Mg"] * 0.40,
            "Ca": pool["Ca"] * 0.40,
        }
        net = self._net_seasonal_nutrients(plant)
        combined = {name: soil_credit[name] + net[name] for name in soil_credit}
        return self._apply_nutrient_antagonism(combined)

    def _nutrient_ledger_lines(self, plant: PlantInstance, soil: SoilProfile, profile: CropProfile | None = None) -> list[str]:
        values_30d = [
            ("N", plant.n_applied_30d_g_m2),
            ("P", plant.p_applied_30d_g_m2),
            ("K", plant.k_applied_30d_g_m2),
            ("Mg", plant.mg_applied_30d_g_m2),
            ("Ca", plant.ca_applied_30d_g_m2),
        ]
        lines: list[str] = []
        if any(value > 0 for _, value in values_30d):
            label_30d = " / ".join(f"{name} {value:.1f} г/м²" for name, value in values_30d if value > 0)
            lines.append(f"NPK-журнал за 30 днів: {label_30d}")
        else:
            lines.append("NPK-журнал за 30 днів: внесень не зафіксовано")

        seasonal_net = self._net_seasonal_nutrients(plant)
        available_seasonal, antagonism_lines = self._available_seasonal_nutrients(plant, soil)
        soil_pool = self._soil_initial_nutrient_pool(soil)
        seasonal_applied = {
            "N": plant.n_applied_season_g_m2,
            "P": plant.p_applied_season_g_m2,
            "K": plant.k_applied_season_g_m2,
            "Mg": plant.mg_applied_season_g_m2,
            "Ca": plant.ca_applied_season_g_m2,
        }
        seasonal_lost = {
            "N": plant.n_lost_season_g_m2,
            "P": plant.p_lost_season_g_m2,
            "K": plant.k_lost_season_g_m2,
            "Mg": plant.mg_lost_season_g_m2,
            "Ca": plant.ca_lost_season_g_m2,
        }
        if any(value > 0 for value in seasonal_applied.values()):
            applied_label = " / ".join(f"{name} {value:.1f}" for name, value in seasonal_applied.items() if value > 0)
            net_label = " / ".join(f"{name} {seasonal_net[name]:.1f}" for name in seasonal_net if seasonal_net[name] > 0)
            lost_total = sum(seasonal_lost.values())
            lines.append(f"Сезонний NPK: внесено {applied_label} г/м²; доступно після втрат {net_label or '0'} г/м²")
            if lost_total > 0:
                lines.append(f"Оцінені сезонні втрати поживних: {lost_total:.1f} г/м² через опади й тип ґрунту")
        else:
            lines.append("Сезонний NPK: внесень за поточний цикл культури не зафіксовано")

        soil_pool_label = " / ".join(f"{name} {soil_pool[name]:.1f}" for name in ["N", "P", "K", "Mg", "Ca"])
        available_label = " / ".join(f"{name} {available_seasonal[name]:.1f}" for name in ["N", "P", "K", "Mg", "Ca"])
        lines.append(f"\u0421\u0442\u0430\u0440\u0442\u043e\u0432\u0438\u0439 \u043f\u0443\u043b \u0491\u0440\u0443\u043d\u0442\u0443: {soil_pool_label} \u0433/\u043c\u00b2")
        lines.append(f"\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u0437 \u0443\u0440\u0430\u0445\u0443\u0432\u0430\u043d\u043d\u044f\u043c \u0491\u0440\u0443\u043d\u0442\u0443, pH \u0456 \u0432\u0438\u043c\u0438\u0432\u0430\u043d\u043d\u044f: {available_label} \u0433/\u043c\u00b2")
        if soil.phosphorus_fixation_risk >= 0.35 or self._phosphorus_availability_factor(soil) < 0.75:
            lines.append(f"\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u0456\u0441\u0442\u044c P \u0441\u043a\u043e\u0440\u0438\u0433\u043e\u0432\u0430\u043d\u0430 \u0437\u0430 pH/\u0444\u0456\u043a\u0441\u0430\u0446\u0456\u0454\u044e: {self._phosphorus_availability_factor(soil) * 100:.0f}%")
        lines.extend(antagonism_lines)

        if profile is not None:
            targets = self._seasonal_nutrient_targets(profile)
            progress = self._phase_nutrient_progress(plant.growth_phase, plant.age_days, profile)
            target_label = " / ".join(f"{name} {targets[name] * progress:.1f}" for name in ["N", "P", "K"])
            coverage_parts = []
            for name in ["N", "P", "K"]:
                expected = max(0.1, targets[name] * progress)
                coverage_parts.append(f"{name} {min(999, available_seasonal[name] / expected * 100):.0f}%")
            lines.append(f"Потреба до цієї фази: {target_label} г/м²; покриття {' / '.join(coverage_parts)}")
        return lines

    def _nutrient_coverage_sufficient(
        self,
        plant: PlantInstance,
        *,
        nitrogen_g_m2: float = 0.0,
        phosphorus_g_m2: float = 0.0,
        potassium_g_m2: float = 0.0,
        magnesium_g_m2: float = 0.0,
        calcium_g_m2: float = 0.0,
        soil: SoilProfile | None = None,
        threshold: float = 0.70,
    ) -> bool:
        seasonal = self._available_nutrients_for_recommendation(plant, soil)[0] if soil is not None else self._net_seasonal_nutrients(plant)
        targets = [
            (nitrogen_g_m2, max(plant.n_applied_30d_g_m2, seasonal["N"])),
            (phosphorus_g_m2, max(plant.p_applied_30d_g_m2, seasonal["P"])),
            (potassium_g_m2, max(plant.k_applied_30d_g_m2, seasonal["K"])),
            (magnesium_g_m2, max(plant.mg_applied_30d_g_m2, seasonal["Mg"])),
            (calcium_g_m2, max(plant.ca_applied_30d_g_m2, seasonal["Ca"])),
        ]
        active_targets = [(target, supplied) for target, supplied in targets if target > 0]
        if not active_targets:
            return False
        return all(supplied >= target * threshold for target, supplied in active_targets)
    @staticmethod
    def _protection_history_lines(plant: PlantInstance, disease: str, today: date) -> list[str]:
        lines: list[str] = []
        last_at = plant.last_protection_by_problem.get(disease)
        if last_at:
            lines.append(f"Останній захист від цієї хвороби: {(today - last_at.date()).days} дн. тому")
        count = plant.protection_counts_90d.get(disease, 0)
        if count:
            lines.append(f"Обробок від цієї хвороби за 90 днів: {count}")
        if plant.last_frac_group:
            lines.append(f"Остання FRAC-група: {plant.last_frac_group}")
        return lines

    @staticmethod
    def _cold_application_weather(
        profile: CropProfile,
        w_forecast: list[WeatherSnapshot],
        today: date,
    ) -> WeatherSnapshot | None:
        for weather in w_forecast[:3]:
            weather_day = _weather_date(weather.date or "")
            if weather_day and weather_day < today:
                continue
            if SmartGardenerEngine._is_cold_stress_weather(weather, profile):
                return weather
        return None

    @staticmethod
    def _is_cold_stress_weather(weather: WeatherSnapshot, profile: CropProfile) -> bool:
        if profile.cold_stress_threshold_c is not None:
            return weather.temp_min < profile.cold_stress_threshold_c
        return weather.temp_min < profile.t_min_growth or weather.temp_avg < profile.t_optimal_min

    @staticmethod
    def _is_biological_protection(product: Any) -> bool:
        frac_group = str(getattr(product, "frac_group", "") or "").upper()
        protection_type = str(getattr(product, "protection_type", "") or "").lower()
        return frac_group.startswith("BM") or "\u0431\u0456\u043e" in protection_type or "\u0431io" in protection_type

    @staticmethod
    def _has_recent_disease_symptoms(plant: PlantInstance, today: date, window_days: int = 7) -> bool:
        if plant.last_disease_observed_at is None:
            return False
        return 0 <= (today - plant.last_disease_observed_at.date()).days <= window_days

    @staticmethod
    def _disease_timing_blockers(
        plant: PlantInstance,
        product: Any,
        profile: CropProfile,
        today: date,
    ) -> list[str]:
        adaptation_days = max(0, profile.disease_protection_adaptation_days)
        early_symptom_days = max(0, profile.disease_protection_early_symptom_days)
        if SmartGardenerEngine._is_biological_protection(product):
            return [] if plant.age_days >= profile.biofungicide_allowed_from_day else [
                f"\u0411\u0456\u043e\u0437\u0430\u0445\u0438\u0441\u0442 \u0434\u043b\u044f \u0446\u0456\u0454\u0457 \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438 \u043a\u0440\u0430\u0449\u0435 \u0437 {profile.biofungicide_allowed_from_day} \u0434\u043d\u044f \u043f\u0456\u0441\u043b\u044f \u0432\u0438\u0441\u0430\u0434\u043a\u0438"
            ]

        product_id = str(getattr(product, "id", "") or "").lower()
        frac_group = str(getattr(product, "frac_group", "") or "").upper()
        is_copper = "copper" in product_id or frac_group == "M01"
        allowed_from = profile.copper_fungicide_allowed_from_day if is_copper else profile.chemical_fungicide_allowed_from_day
        wait_days = max(adaptation_days, allowed_from)
        if plant.age_days >= wait_days:
            return []

        has_symptoms = SmartGardenerEngine._has_recent_disease_symptoms(plant, today)
        if has_symptoms and plant.age_days >= early_symptom_days:
            return [
                "\u0420\u043e\u0441\u043b\u0438\u043d\u0430 \u0449\u0435 \u043f\u0456\u0441\u043b\u044f \u0432\u0438\u0441\u0430\u0434\u043a\u0438: \u0434\u043b\u044f \u0441\u0438\u043c\u043f\u0442\u043e\u043c\u0456\u0432 \u043d\u0430 2-5 \u0434\u0435\u043d\u044c \u043e\u0431\u0438\u0440\u0430\u0439\u0442\u0435 \u043c'\u044f\u043a\u0438\u0439 \u0431\u0456\u043e\u0437\u0430\u0445\u0438\u0441\u0442; \u043c\u0456\u0434\u043d\u0456 \u0442\u0430 \u0441\u0438\u043b\u044c\u043d\u0456 \u0445\u0456\u043c\u0456\u0447\u043d\u0456 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434\u0438 \u043a\u0440\u0430\u0449\u0435 \u043f\u0456\u0441\u043b\u044f 5-7 \u0434\u043d\u0456\u0432 \u0430\u0434\u0430\u043f\u0442\u0430\u0446\u0456\u0457"
            ]

        return [
            f"\u041f\u0456\u0441\u043b\u044f \u0432\u0438\u0441\u0430\u0434\u043a\u0438 \u043c\u0438\u043d\u0443\u043b\u043e {plant.age_days} \u0434\u043d.; \u043f\u0440\u043e\u0444\u0456\u043b\u0430\u043a\u0442\u0438\u0447\u043d\u0443 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434\u043d\u0443 \u043e\u0431\u0440\u043e\u0431\u043a\u0443 \u0434\u043b\u044f \u0446\u0456\u0454\u0457 \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438 \u043a\u0440\u0430\u0449\u0435 \u043f\u043b\u0430\u043d\u0443\u0432\u0430\u0442\u0438 \u043f\u0456\u0441\u043b\u044f {wait_days} \u0434\u043d. \u0430\u0434\u0430\u043f\u0442\u0430\u0446\u0456\u0457"
        ]

    @staticmethod
    def _application_blockers(
        w_forecast: list[WeatherSnapshot],
        profile: CropProfile | None = None,
        today: date | None = None,
        max_temp_c: float | None = None,
    ) -> list[str]:
        blockers: list[str] = []
        window = w_forecast[:2]
        if any(w.precipitation_mm >= 10 or (w.precipitation_mm >= 6 and w.rain_probability >= 70) for w in window):
            blockers.append("\u0441\u0438\u043b\u044c\u043d\u0438\u0439 \u0434\u043e\u0449")
        heat_limit = max_temp_c if max_temp_c is not None else 30
        if any(w.temp_max >= heat_limit for w in window):
            blockers.append("\u0441\u043f\u0435\u043a\u0430")
        if any(w.wind_speed_ms >= _NO_SPRAY_WIND_U2_MS for w in window):
            blockers.append("\u0441\u0438\u043b\u044c\u043d\u0438\u0439 \u0432\u0456\u0442\u0435\u0440")
        if profile is not None and today is not None and SmartGardenerEngine._cold_application_weather(profile, w_forecast, today):
            blockers.append("\u043f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f")
        return blockers

    @staticmethod
    def _blocked_reason_messages(
        blockers: list[str],
        w_forecast: list[WeatherSnapshot],
        today: date,
        profile: CropProfile | None = None,
        max_temp_c: float | None = None,
    ) -> list[str]:
        messages: list[str] = []
        heat_limit = max_temp_c if max_temp_c is not None else 30
        for blocker in blockers:
            if blocker == "\u0441\u0438\u043b\u044c\u043d\u0438\u0439 \u0434\u043e\u0449":
                rainy = next((w for w in w_forecast[:2] if w.precipitation_mm >= 6 or w.rain_probability >= 70), None)
                if rainy:
                    messages.append(f"\u0412\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {_date_label(rainy.date or today.isoformat(), today)} \u043e\u0447\u0456\u043a\u0443\u0454\u0442\u044c\u0441\u044f {rainy.precipitation_mm:.0f} \u043c\u043c \u0434\u043e\u0449\u0443")
            elif blocker == "\u0441\u043f\u0435\u043a\u0430":
                hot = next((w for w in w_forecast[:2] if w.temp_max >= heat_limit), None)
                if hot:
                    messages.append(f"\u0412\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {_date_label(hot.date or today.isoformat(), today)} \u0441\u043f\u0435\u043a\u0430 \u0434\u043e {hot.temp_max:.0f}\u00b0C")
            elif blocker == "\u0441\u0438\u043b\u044c\u043d\u0438\u0439 \u0432\u0456\u0442\u0435\u0440":
                windy = next((w for w in w_forecast[:2] if w.wind_speed_ms >= _NO_SPRAY_WIND_U2_MS), None)
                if windy:
                    messages.append(f"\u0412\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {_date_label(windy.date or today.isoformat(), today)} \u0432\u0456\u0442\u0435\u0440 {windy.wind_speed_ms:.1f} \u043c/\u0441")
            elif blocker == "\u043f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f" and profile is not None:
                cold = SmartGardenerEngine._cold_application_weather(profile, w_forecast, today)
                if cold:
                    messages.append(
                        f"\u0412\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: "
                        f"{_date_label(cold.date or today.isoformat(), today)} \u043f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f "
                        f"{cold.temp_min:.0f}\u00b0C, \u043f\u043e\u0440\u0456\u0433 \u0440\u043e\u0441\u0442\u0443 \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438 {profile.t_min_growth:.0f}\u00b0C"
                    )
        return messages

    @staticmethod
    def _days_until_harvest_start(plant: PlantInstance, profile: CropProfile) -> int:
        return max(0, profile.days_to_harvest_min - plant.age_days)

    def _generate_watering_task(
        self,
        plant: PlantInstance,
        profile: CropProfile,
        diag: CellDiagnostics,
        depletion_pct: float,
        w_forecast: list[WeatherSnapshot],
        w_history: list[WeatherSnapshot],
        today: date,
        soil: SoilProfile,
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
            "soil": [f"\u0422\u0438\u043f \u0491\u0440\u0443\u043d\u0442\u0443: {soil.label}; \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0432\u043e\u0434\u0430 {soil.available_water_mm_per_m:.0f} \u043c\u043c/\u043c"],
            "phase": [f"\u0424\u0430\u0437\u0430: {_phase_name(plant.growth_phase)}", f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432"],
            "history": [],
        }
        _append_group(reason_groups, "weather", f"ETc: {diag.etc_mm} \u043c\u043c/\u0434\u043e\u0431\u0443")
        _append_group(reason_groups, "soil", f"\u0414\u0435\u0444\u0456\u0446\u0438\u0442 \u0432\u043e\u043b\u043e\u0433\u0438: {depletion_pct * 100:.0f}%")
        if plant.observed_soil_moisture_pct is not None:
            _append_group(reason_groups, "observation", f"Ручне спостереження вологості: {plant.observed_soil_moisture_pct}%")
        elif plant.observed_soil_moisture_status:
            _append_group(reason_groups, "observation", f"Ручна оцінка вологості: {plant.observed_soil_moisture_status}")
        if plant.observed_growth_phase:
            _append_group(reason_groups, "observation", f"Фактична фаза: {_phase_name(plant.growth_phase)}")
        if plant.observed_leaf_condition:
            _append_group(reason_groups, "observation", f"Стан листя: {plant.observed_leaf_condition}")
        if plant.observed_symptoms:
            _append_group(reason_groups, "observation", f"Симптоми: {', '.join(plant.observed_symptoms[:3])}")
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
        cold_weather = self._cold_application_weather(profile, w_forecast, today)
        if cold_weather:
            label = _date_label(cold_weather.date or today.isoformat(), today)
            _append_group(
                reason_groups,
                "weather",
                f"\u041f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f: {label} {cold_weather.temp_min:.0f}\u00b0C",
            )
            diag.hidden_tasks.append(GardenTask(
                TaskType.WATERING,
                TaskPriority.LOW,
                f"\u041f\u043e\u043b\u0438\u0432 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}",
                "\u0412 \u043d\u0430\u0439\u0431\u043b\u0438\u0436\u0447\u0456 \u0434\u043d\u0456 \u043e\u0447\u0456\u043a\u0443\u0454\u0442\u044c\u0441\u044f \u043f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f. "
                "\u0417\u0430\u0439\u0432\u0438\u0439 \u043f\u043e\u043b\u0438\u0432 \u043f\u0435\u0440\u0435\u0434 \u0445\u043e\u043b\u043e\u0434\u043d\u043e\u044e \u043d\u0456\u0447\u0447\u044e \u043f\u0456\u0434\u0441\u0438\u043b\u044e\u0454 \u0441\u0442\u0440\u0435\u0441 \u0442\u0430 \u0440\u0438\u0437\u0438\u043a \u043f\u0435\u0440\u0435\u043e\u0445\u043e\u043b\u043e\u0434\u0436\u0435\u043d\u043d\u044f \u043a\u043e\u0440\u0435\u043d\u0456\u0432.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                confidence=_confidence(88 if len(w_forecast) >= 3 else 78),
                reasons=[
                    f"\u041f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f: {label} {cold_weather.temp_min:.0f}\u00b0C",
                    f"\u041f\u043e\u0440\u0456\u0433 \u0440\u043e\u0441\u0442\u0443 \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438: {profile.t_min_growth:.0f}\u00b0C",
                    f"\u0414\u0435\u0444\u0456\u0446\u0438\u0442 \u0432\u043e\u043b\u043e\u0433\u0438: {depletion_pct * 100:.0f}%",
                ],
                reason_groups=reason_groups,
                blocked_reasons=[
                    f"\u041f\u043e\u043b\u0438\u0432 \u0432\u0456\u0434\u043a\u043b\u0430\u0434\u0435\u043d\u043e: {label} \u043e\u0447\u0456\u043a\u0443\u0454\u0442\u044c\u0441\u044f {cold_weather.temp_min:.0f}\u00b0C"
                ],
                is_hidden=True,
            ))
            return
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
            f"\u0490\u0440\u0443\u043d\u0442: {soil.label} ({soil.available_water_mm_per_m:.0f} \u043c\u043c/\u043c)",
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

    @staticmethod
    def _observation_value(observation: ManualObservation | dict, key: str, default: Any = None) -> Any:
        if isinstance(observation, dict):
            return observation.get(key, default)
        return getattr(observation, key, default)

    def _resolve_perennial_season(
        self,
        plant: PlantInstance,
        today: date,
        observations: list[ManualObservation | dict] | None = None,
    ) -> tuple[PerennialSeason, str]:
        productive = is_plant_productive(plant.age_years, plant.lifecycle_type)
        auto_season = determine_perennial_season(today, plant.lifecycle_type, is_productive=productive)
        if not observations:
            return auto_season, "auto-calendar"

        relevant: list[ManualObservation | dict] = []
        for observation in observations:
            observed_season = self._observation_value(observation, "observed_perennial_season")
            if not observed_season:
                continue

            species_filter = self._observation_value(observation, "species_filter")
            if species_filter and plant.plant_type not in species_filter:
                continue

            plant_type = self._observation_value(observation, "plant_type")
            if plant_type and plant_type != plant.plant_type:
                continue

            variety = self._observation_value(observation, "variety")
            if variety and variety != plant.variety:
                continue

            scope = self._observation_value(observation, "scope", "plot")
            cell_col = self._observation_value(observation, "cell_col")
            cell_row = self._observation_value(observation, "cell_row")
            if scope == "single" or cell_col is not None or cell_row is not None:
                if cell_col is not None and cell_col != plant.cell_col:
                    continue
                if cell_row is not None and cell_row != plant.cell_row:
                    continue

            relevant.append(observation)

        if not relevant:
            return auto_season, "auto-calendar"

        def observed_at_dt(item: ManualObservation | dict) -> datetime:
            value = self._observation_value(item, "observed_at", datetime.min)
            if isinstance(value, datetime):
                return value
            return _parse_dt(value)

        latest = max(relevant, key=observed_at_dt)
        observed_at = observed_at_dt(latest)
        age_days = (today - observed_at.date()).days
        if age_days > 21:
            return auto_season, f"auto-calendar-stale-obs-{age_days}d"

        try:
            observed = PerennialSeason(str(self._observation_value(latest, "observed_perennial_season")))
        except ValueError:
            return auto_season, "auto-calendar-invalid-obs"

        if age_days <= 7:
            return observed, "user-observation"
        if auto_season != observed:
            return auto_season, f"user-observation-aged-{age_days}d-superseded"
        return observed, f"user-observation-aged-{age_days}d"

    @staticmethod
    def _humanize_season(season: PerennialSeason) -> str:
        return {
            PerennialSeason.DORMANT_WINTER: "зимовий спокій",
            PerennialSeason.BUD_BREAK: "розпускання бруньок",
            PerennialSeason.FLOWERING_FRUIT_SET: "цвітіння і зав'язування плодів",
            PerennialSeason.FRUIT_DEVELOPMENT: "розвиток плодів",
            PerennialSeason.HARVEST_RIPENING: "достигання",
            PerennialSeason.LEAF_FALL: "листопад",
            PerennialSeason.DORMANT_ENTRY: "входження в спокій",
        }[season]

    @staticmethod
    def _humanize_nutrient(nutrient: str) -> str:
        return {
            "nitrogen": "азот",
            "phosphorus": "фосфор",
            "potassium": "калій",
            "boron": "бор",
            "zinc": "цинк",
            "calcium": "кальцій",
            "magnesium": "магній",
        }.get(nutrient, nutrient)

    def _format_amount_g_m2(self, needs: dict[str, float]) -> str:
        return ", ".join(
            f"{self._humanize_nutrient(key)} {value:.1f} г/м²"
            for key, value in needs.items()
            if value > 0
        )

    def _format_amount_micros(self, needs: dict[str, float]) -> str:
        return ", ".join(
            f"{self._humanize_nutrient(key)} {value * 1000:.0f} мг/м²"
            for key, value in needs.items()
            if value > 0
        )

    def _generate_perennial_fertilizer_tasks(
        self,
        plant: PlantInstance,
        season: PerennialSeason,
        diag: CellDiagnostics,
        w_forecast: list[WeatherSnapshot],
        today: date,
        soil: SoilProfile,
    ) -> None:
        if self._in_cooldown(plant.last_fertilized_at, today, _FERTILIZING_COOLDOWN_DAYS):
            return

        needs = get_perennial_fertilizer_need(season)
        if not needs:
            return

        productive = is_plant_productive(plant.age_years, plant.lifecycle_type)
        season_label = self._humanize_season(season)
        v = f" ({plant.variety})" if plant.variety else ""
        blockers = self._application_blockers(w_forecast, today=today)
        blocked_messages = self._blocked_reason_messages(blockers, w_forecast, today)

        macros = {key: value for key, value in needs.items() if key in ("nitrogen", "phosphorus", "potassium") and value > 0}
        micros = {key: value for key, value in needs.items() if key in ("boron", "zinc", "calcium", "magnesium") and value > 0}

        if macros and not self._nutrient_coverage_sufficient(
            plant,
            nitrogen_g_m2=macros.get("nitrogen", 0.0),
            phosphorus_g_m2=macros.get("phosphorus", 0.0),
            potassium_g_m2=macros.get("potassium", 0.0),
            soil=soil,
        ):
            reason_groups = {
                "phase": [f"Сезон: {season_label}"],
                "fertilizer": [f"Потреби г/м² крони: {macros}"],
                "soil": [f"Тип ґрунту: {soil.label}", f"pH: {soil.ph_label}"],
                "history": self._nutrient_ledger_lines(plant, soil),
            }
            task = GardenTask(
                TaskType.FERTILIZING,
                TaskPriority.MEDIUM if productive else TaskPriority.LOW,
                f"Підживлення дерева: {plant.plant_type}{v}",
                f"Для фази '{season_label}' потрібна сезонна NPK-підтримка крони.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                self._format_amount_g_m2(macros),
                confidence=70,
                reasons=[
                    f"Стадія: {season_label}",
                    f"Вік: {plant.age_years if plant.age_years is not None else 'невідомий'} років",
                    "Сезонна потреба у NPK для багаторічної культури",
                ],
                reason_groups=reason_groups,
                recommendation_type="perennial_balanced_npk",
                constraints=blockers,
            )
            if blockers:
                task.is_hidden = True
                task.title = f"Підживлення відкласти: {plant.plant_type}{v}"
                task.description = "Потреба у підживленні є, але погода зараз не підходить для безпечного внесення."
                task.blocked_reasons = blocked_messages
                diag.hidden_tasks.append(task)
            else:
                diag.tasks.append(task)

        if micros and productive:
            reason_groups = {
                "phase": [f"Сезон: {season_label}"],
                "micronutrient": [f"{key}: {value} г/м²" for key, value in micros.items()],
                "weather": [],
            }
            task = GardenTask(
                TaskType.FERTILIZING,
                TaskPriority.HIGH if season in (
                    PerennialSeason.BUD_BREAK,
                    PerennialSeason.FLOWERING_FRUIT_SET,
                ) else TaskPriority.MEDIUM,
                f"Мікродобрива: {plant.plant_type}{v}",
                f"Фаза '{season_label}' критична для бору, цинку, кальцію або магнію.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                self._format_amount_micros(micros),
                confidence=72,
                reasons=[
                    f"Стадія: {season_label}",
                    "Рекомендоване позакореневе підживлення",
                    "Особливо важливо під час бутонізації, цвітіння та наливу плодів",
                ],
                reason_groups=reason_groups,
                recommendation_type="perennial_micronutrient_foliar",
                constraints=blockers,
            )
            if blockers:
                task.is_hidden = True
                task.title = f"Мікродобрива відкласти: {plant.plant_type}{v}"
                task.description = "Листкове підживлення доречне, але погода зараз небезпечна для обробки."
                task.blocked_reasons = blocked_messages
                diag.hidden_tasks.append(task)
            else:
                diag.tasks.append(task)

    def _generate_perennial_protection_tasks(
        self,
        plant: PlantInstance,
        season: PerennialSeason,
        diag: CellDiagnostics,
        w_forecast: list[WeatherSnapshot],
        today: date,
    ) -> None:
        if self._in_cooldown(plant.last_disease_at, today, _DISEASE_COOLDOWN_DAYS):
            return
        pressures = {
            disease: pressure
            for disease, pressure in get_perennial_disease_pressure(season).items()
            if pressure >= 0.6
        }
        if not pressures:
            return

        disease, pressure = max(pressures.items(), key=lambda item: item[1])
        names = {
            "apple_scab": "парші",
            "fire_blight": "бактеріального опіку",
            "monilinia": "моніліозу",
            "powdery_mildew": "борошнистої роси",
            "alternaria": "альтернаріозу",
        }
        season_label = self._humanize_season(season)
        v = f" ({plant.variety})" if plant.variety else ""
        blockers = self._application_blockers(w_forecast, today=today)
        blocked_messages = self._blocked_reason_messages(blockers, w_forecast, today)
        task = GardenTask(
            TaskType.DISEASE_PROTECTION,
            TaskPriority.HIGH if pressure >= 0.8 else TaskPriority.MEDIUM,
            f"Захист від {names.get(disease, disease)}: {plant.plant_type}{v}",
            f"У фазі '{season_label}' для багаторічних культур підвищений сезонний ризик {names.get(disease, disease)}.",
            plant.plant_type,
            plant.variety,
            plant.cell_col,
            plant.cell_row,
            confidence=70,
            reasons=[
                f"Сезон: {season_label}",
                f"Сезонний ризик: {pressure * 100:.0f}%",
                "Модель coarse: уточнюється погодою та журналом обробок",
            ],
            reason_groups={
                "phase": [f"Сезон: {season_label}"],
                "protection": [f"Проблема: {names.get(disease, disease)}", f"Ризик: {pressure * 100:.0f}%"],
                "weather": [],
            },
            recommendation_type=f"perennial_{disease}_prevention",
            constraints=blockers,
        )
        if blockers:
            task.is_hidden = True
            task.title = f"Захист відкласти: {names.get(disease, disease)} — {plant.plant_type}{v}"
            task.description = "Профілактична обробка доречна, але погода зараз не підходить для безпечного внесення."
            task.blocked_reasons = blocked_messages
            diag.hidden_tasks.append(task)
        else:
            diag.tasks.append(task)

    def _generate_perennial_frost_tasks(
        self,
        plant: PlantInstance,
        season: PerennialSeason,
        diag: CellDiagnostics,
        w_forecast: list[WeatherSnapshot],
        today: date,
    ) -> None:
        if self._in_cooldown(plant.last_frost_protection_at, today, _FROST_COOLDOWN_DAYS):
            return
        sensitivity = get_perennial_frost_sensitivity(season)
        if sensitivity < 0.5:
            return
        forecast_3d = w_forecast[:3]
        if not forecast_3d:
            return
        coldest_idx = min(range(len(forecast_3d)), key=lambda index: forecast_3d[index].temp_min)
        coldest = forecast_3d[coldest_idx]
        if coldest.temp_min > 2:
            return
        if not (coldest.temp_min <= -2 or (coldest.temp_min <= 0 and sensitivity >= 0.8)):
            return

        days_until = max(1, coldest_idx + 1)
        season_label = self._humanize_season(season)
        v = f" ({plant.variety})" if plant.variety else ""
        diag.tasks.append(GardenTask(
            TaskType.FROST_PROTECTION,
            TaskPriority.HIGH,
            f"Заморозок {coldest.temp_min:.0f}°C: захист {plant.plant_type}{v}",
            f"Прогнозується заморозок у фазі '{season_label}'. Для квітів і зав'язі це критичне вікно.",
            plant.plant_type,
            plant.variety,
            plant.cell_col,
            plant.cell_row,
            due_date=coldest.date,
            confidence=88,
            reasons=[
                f"Чутливість фази: {int(sensitivity * 100)}%",
                f"Прогноз: {coldest.temp_min:.0f}°C через {days_until} дн.",
                "При -2°C у фазі цвітіння можлива втрата значної частини зав'язі",
            ],
            reason_groups={
                "weather": [f"Прогноз заморозку: {coldest.temp_min:.0f}°C"],
                "phase": [f"Чутлива стадія: {season_label}"],
            },
            recommendation_type="perennial_frost_protection",
            constraints=[
                "Дощування крони перед сходом сонця",
                "Димлення у безвітряну ніч",
                "Агроволокно для малих дерев або кущів",
            ],
        ))

    def _generate_fertilizing_tasks(
        self,
        plant: PlantInstance,
        profile: CropProfile,
        diag: CellDiagnostics,
        phase: GrowthPhase,
        w_history: list[WeatherSnapshot],
        w_forecast: list[WeatherSnapshot],
        today: date,
        soil: SoilProfile,
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
        blockers = self._application_blockers(w_forecast, profile=profile, today=today)
        blocked_messages = self._blocked_reason_messages(w_forecast=w_forecast, blockers=blockers, today=today, profile=profile)
        base_groups = {
            "weather": [],
            "soil": [
                f"\u0422\u0438\u043f \u0491\u0440\u0443\u043d\u0442\u0443: {soil.label}",
                f"\u0423\u0442\u0440\u0438\u043c\u0430\u043d\u043d\u044f \u043f\u043e\u0436\u0438\u0432\u043d\u0438\u0445: {soil.nutrient_retention * 100:.0f}%",
                f"pH: {soil.ph_label}",
            ],
            "phase": [f"\u0424\u0430\u0437\u0430: {_phase_name(phase)}", f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432"],
            "history": [],
            "profile": [],
            "fertilizer": [],
        }
        _append_group(base_groups, "weather", f"\u0414\u043e\u0449 \u043d\u0430 3 \u0434\u043d\u0456: {rain_next_3:.0f} \u043c\u043c")
        _append_group(base_groups, "profile", f"\u0414\u043e\u0432\u0456\u0440\u0430 \u0434\u043e \u043f\u0440\u043e\u0444\u0456\u043b\u044e: {profile.profile_confidence}%")
        if plant.last_fertilized_at:
            days = (today - plant.last_fertilized_at.date()).days
            _append_group(base_groups, "history", f"\u041e\u0441\u0442\u0430\u043d\u043d\u0454 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f: {days} \u0434\u043d\u0456\u0432 \u0442\u043e\u043c\u0443")
        else:
            _append_group(base_groups, "history", "\u041f\u043e\u043f\u0435\u0440\u0435\u0434\u043d\u0456\u0445 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u044c \u0449\u0435 \u043d\u0435 \u0431\u0443\u043b\u043e")
        for line in self._nutrient_ledger_lines(plant, soil, profile):
            _append_group(base_groups, "history", line)
        if diag.nutrient_leaching_risk > 0.4:
            if self._nutrient_coverage_sufficient(
                plant,
                magnesium_g_m2=n.magnesium,
                calcium_g_m2=n.calcium,
                threshold=0.75,
            ):
                return
            conf = self._fertilizing_confidence(86, plant, w_history, w_forecast, diag.nutrient_leaching_risk)
            fert = recommend_fertilizer(
                "leaching_recovery",
                soil,
                magnesium_g_m2=n.magnesium,
                calcium_g_m2=n.calcium,
            )
            reasons = [
                f"\u0420\u0438\u0437\u0438\u043a \u0432\u0438\u043c\u0438\u0432\u0430\u043d\u043d\u044f: {diag.nutrient_leaching_risk * 100:.0f}%",
                f"\u0414\u043e\u0449 \u0437\u0430 5 \u0434\u043d\u0456\u0432: {sum(w.precipitation_mm for w in w_history[-5:]):.0f} \u043c\u043c",
                f"Mg: {n.magnesium} \u0433/\u043c\u00b2",
                f"Ca: {n.calcium} \u0433/\u043c\u00b2",
                *fert.reasons,
            ]
            reason_groups = {key: list(values) for key, values in base_groups.items()}
            _append_group(reason_groups, "weather", f"\u041e\u043f\u0430\u0434\u0438 \u0437\u0430 5 \u0434\u043d\u0456\u0432: {sum(w.precipitation_mm for w in w_history[-5:]):.0f} \u043c\u043c")
            _append_group(reason_groups, "soil", f"\u0412\u0438\u043c\u0438\u0432\u0430\u043d\u043d\u044f \u043f\u043e\u0436\u0438\u0432\u043d\u0438\u0445: {diag.nutrient_leaching_risk * 100:.0f}%")
            _append_group(reason_groups, "fertilizer", fert.explanation)
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
                    fert.amount,
                    confidence=conf,
                    reasons=reasons,
                    reason_groups=reason_groups,
                    recommendation_type=fert.recommendation_type,
                    constraints=blockers,
                    blocked_reasons=blocked_messages,
                    is_hidden=True,
                ))
            else:
                diag.tasks.append(GardenTask(
                    TaskType.FERTILIZING,
                    TaskPriority.HIGH,
                    f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u043f\u0456\u0441\u043b\u044f \u0434\u043e\u0449\u0456\u0432: {plant.plant_type}{v}",
                    f"\u041f\u0456\u0441\u043b\u044f \u0441\u0438\u043b\u044c\u043d\u0438\u0445 \u043e\u043f\u0430\u0434\u0456\u0432 \u0454 \u0440\u0438\u0437\u0438\u043a \u0432\u0438\u043c\u0438\u0432\u0430\u043d\u043d\u044f Mg \u0442\u0430 Ca. {fert.explanation}",
                    plant.plant_type,
                    plant.variety,
                    plant.cell_col,
                    plant.cell_row,
                    fert.amount,
                    confidence=conf,
                    reasons=reasons,
                    reason_groups=reason_groups,
                    recommendation_type=fert.recommendation_type,
                    constraints=blockers,
                ))
            return
        if phase == GrowthPhase.INITIAL and plant.age_days >= 7:
            p_hi = n.phosphorus * 1.2
            if self._nutrient_coverage_sufficient(plant, phosphorus_g_m2=p_hi, soil=soil):
                return
            fert = recommend_fertilizer("root_start", soil, phosphorus_g_m2=p_hi)
            reasons = [
                f"\u0424\u0430\u0437\u0430: {_phase_name(phase)}",
                f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432",
                f"\u0424\u043e\u0441\u0444\u043e\u0440: {p_hi:.1f} \u0433/\u043c\u00b2",
                "\u0426\u0456\u043b\u044c: \u0440\u043e\u0437\u0432\u0438\u0442\u043e\u043a \u043a\u043e\u0440\u0435\u043d\u0456\u0432",
                *fert.reasons,
            ]
            reason_groups = {key: list(values) for key, values in base_groups.items()}
            _append_group(reason_groups, "phase", "\u0426\u0456\u043b\u044c: \u0440\u043e\u0437\u0432\u0438\u0442\u043e\u043a \u043a\u043e\u0440\u0435\u043d\u0435\u0432\u043e\u0457 \u0441\u0438\u0441\u0442\u0435\u043c\u0438")
            _append_group(reason_groups, "fertilizer", fert.explanation)
            task = GardenTask(
                TaskType.FERTILIZING,
                TaskPriority.LOW,
                f"\u0421\u0442\u0430\u0440\u0442\u043e\u0432\u0435 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f: {plant.plant_type}{v}",
                f"\u0420\u043e\u0441\u043b\u0438\u043d\u0456 {plant.age_days} \u0434\u043d\u0456\u0432, \u043a\u043e\u0440\u0435\u043d\u0435\u0432\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u043e \u0444\u043e\u0440\u043c\u0443\u0454\u0442\u044c\u0441\u044f. {fert.explanation}",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                fert.amount,
                confidence=self._fertilizing_confidence(82, plant, w_history, w_forecast, 0.35),
                reasons=reasons,
                reason_groups=reason_groups,
                recommendation_type=fert.recommendation_type,
                constraints=blockers,
            )
            (diag.hidden_tasks if blockers else diag.tasks).append(
                task if not blockers else GardenTask(**{**task.__dict__, "title": f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}{v}", "description": "\u041f\u043e\u0442\u0440\u0435\u0431\u0430 \u0432 \u0441\u0442\u0430\u0440\u0442\u043e\u0432\u043e\u043c\u0443 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u0456 \u0454, \u0430\u043b\u0435 \u043f\u043e\u0433\u043e\u0434\u0430 \u0437\u0430\u0440\u0430\u0437 \u043d\u0435 \u043f\u0456\u0434\u0445\u043e\u0434\u0438\u0442\u044c \u0434\u043b\u044f \u0431\u0435\u0437\u043f\u0435\u0447\u043d\u043e\u0433\u043e \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f.", "blocked_reasons": blocked_messages, "is_hidden": True})
            )
        elif phase == GrowthPhase.DEVELOPMENT:
            n_hi, p_norm, k_lo = n.nitrogen * 1.3, n.phosphorus, n.potassium * 0.7
            if self._nutrient_coverage_sufficient(
                plant,
                nitrogen_g_m2=n_hi,
                phosphorus_g_m2=p_norm,
                potassium_g_m2=k_lo,
                soil=soil,
            ):
                return
            fert = recommend_fertilizer(
                "vegetative_growth",
                soil,
                nitrogen_g_m2=n_hi,
                phosphorus_g_m2=p_norm,
                potassium_g_m2=k_lo,
            )
            reasons = [
                f"\u0424\u0430\u0437\u0430: {_phase_name(phase)}",
                f"\u0412\u0456\u043a: {plant.age_days} \u0434\u043d\u0456\u0432",
                "\u0410\u043a\u0446\u0435\u043d\u0442: \u0430\u0437\u043e\u0442 \u0434\u043b\u044f \u043d\u0430\u0440\u043e\u0441\u0442\u0430\u043d\u043d\u044f \u043c\u0430\u0441\u0438",
                f"NPK: {n_hi:.1f}/{p_norm:.1f}/{k_lo:.1f}",
                *fert.reasons,
            ]
            if rain_next_3 > 15:
                reasons.append(f"\u0414\u043e\u0449\u0456: \u043d\u0430 3 \u0434\u043d\u0456 {rain_next_3:.0f} \u043c\u043c, \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f \u043a\u0440\u0430\u0449\u0435 \u0434\u043e \u043e\u043f\u0430\u0434\u0456\u0432")
            reason_groups = {key: list(values) for key, values in base_groups.items()}
            _append_group(reason_groups, "phase", "\u0410\u043a\u0446\u0435\u043d\u0442: \u0430\u0437\u043e\u0442 \u0434\u043b\u044f \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0433\u043e \u0440\u043e\u0441\u0442\u0443")
            _append_group(reason_groups, "fertilizer", fert.explanation)
            task = GardenTask(
                TaskType.FERTILIZING,
                TaskPriority.MEDIUM,
                f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u043d\u0430 \u0440\u0456\u0441\u0442: {plant.plant_type}{v}",
                f"\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u043e \u043d\u0430\u0440\u043e\u0441\u0442\u0430\u0454 (\u0432\u0456\u043a {plant.age_days}). {fert.explanation}",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                fert.amount,
                confidence=self._fertilizing_confidence(84, plant, w_history, w_forecast, 0.55),
                reasons=reasons,
                reason_groups=reason_groups,
                recommendation_type=fert.recommendation_type,
                constraints=blockers,
            )
            (diag.hidden_tasks if blockers else diag.tasks).append(
                task if not blockers else GardenTask(**{**task.__dict__, "title": f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}{v}", "description": "\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u043f\u043e\u0442\u0440\u0456\u0431\u043d\u0435, \u0430\u043b\u0435 \u043f\u043e\u0442\u043e\u0447\u043d\u0430 \u043f\u043e\u0433\u043e\u0434\u0430 \u043d\u0435 \u0434\u0430\u0454 \u0431\u0435\u0437\u043f\u0435\u0447\u043d\u043e\u0433\u043e \u0432\u0456\u043a\u043d\u0430 \u0434\u043b\u044f \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f.", "blocked_reasons": blocked_messages, "is_hidden": True})
            )
        elif phase == GrowthPhase.MID_SEASON:
            n_lo, p_hi, k_hi = n.nitrogen * 0.6, n.phosphorus * 1.5, n.potassium * 1.4
            if self._nutrient_coverage_sufficient(
                plant,
                nitrogen_g_m2=n_lo,
                phosphorus_g_m2=p_hi,
                potassium_g_m2=k_hi,
                soil=soil,
            ):
                return
            fert = recommend_fertilizer(
                "flowering_fruiting",
                soil,
                nitrogen_g_m2=n_lo,
                phosphorus_g_m2=p_hi,
                potassium_g_m2=k_hi,
            )
            reasons = [
                f"\u0424\u0430\u0437\u0430: {_phase_name(phase)}",
                "\u0410\u043a\u0446\u0435\u043d\u0442: P \u0456 K \u0434\u043b\u044f \u0446\u0432\u0456\u0442\u0456\u043d\u043d\u044f \u0442\u0430 \u043f\u043b\u043e\u0434\u0443",
                f"NPK: {n_lo:.1f}/{p_hi:.1f}/{k_hi:.1f}",
                *fert.reasons,
            ]
            if dry_window:
                reasons.append("\u0412\u0456\u043a\u043d\u043e \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f: \u0441\u0443\u0445\u0430 \u043f\u043e\u0433\u043e\u0434\u0430 \u0431\u0435\u0437 \u0441\u0438\u043b\u044c\u043d\u0438\u0445 \u043e\u043f\u0430\u0434\u0456\u0432")
            reason_groups = {key: list(values) for key, values in base_groups.items()}
            _append_group(reason_groups, "phase", "\u0410\u043a\u0446\u0435\u043d\u0442: P \u0456 K \u0434\u043b\u044f \u0446\u0432\u0456\u0442\u0456\u043d\u043d\u044f \u0442\u0430 \u043d\u0430\u043b\u0438\u0432\u0443 \u043f\u043b\u043e\u0434\u0456\u0432")
            _append_group(reason_groups, "fertilizer", fert.explanation)
            task = GardenTask(
                TaskType.FERTILIZING,
                TaskPriority.MEDIUM,
                f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u043d\u0430 \u0446\u0432\u0456\u0442\u0456\u043d\u043d\u044f/\u043f\u043b\u0456\u0434: {plant.plant_type}{v}",
                f"\u0420\u043e\u0437\u043f\u043e\u0447\u0430\u043b\u043e\u0441\u044f \u0446\u0432\u0456\u0442\u0456\u043d\u043d\u044f \u0430\u0431\u043e \u043d\u0430\u043b\u0438\u0432 \u043f\u043b\u043e\u0434\u0456\u0432. {fert.explanation}",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                fert.amount,
                confidence=self._fertilizing_confidence(86, plant, w_history, w_forecast, 0.65),
                reasons=reasons,
                reason_groups=reason_groups,
                recommendation_type=fert.recommendation_type,
                constraints=blockers,
            )
            (diag.hidden_tasks if blockers else diag.tasks).append(
                task if not blockers else GardenTask(**{**task.__dict__, "title": f"\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {plant.plant_type}{v}", "description": "\u041f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0434\u043e\u0440\u0435\u0447\u043d\u0435, \u0430\u043b\u0435 \u0432\u0438\u043a\u043e\u043d\u0430\u0442\u0438 \u0439\u043e\u0433\u043e \u0431\u0435\u0437\u043f\u0435\u0447\u043d\u043e \u0437\u0430\u0440\u0430\u0437 \u0437\u0430\u0432\u0430\u0436\u0430\u0454 \u043f\u043e\u0433\u043e\u0434\u0430.", "blocked_reasons": blocked_messages, "is_hidden": True})
            )

    def _generate_disease_tasks(self, plant: PlantInstance, diag: CellDiagnostics, w_history: list[WeatherSnapshot], w_forecast: list[WeatherSnapshot], today: date) -> None:
        if self._in_cooldown(plant.last_disease_at, today, _DISEASE_COOLDOWN_DAYS):
            return
        v = f" ({plant.variety})" if plant.variety else ""
        for risk in diag.disease_risks:
            if risk.is_significant:
                disease_name = self._disease_display_name(risk.disease, diag.profile)
                protection = recommend_protection(
                    risk.disease,
                    risk.risk_level,
                    crop_name=diag.profile.name,
                    crop_category=diag.profile.category,
                )
                product = protection.profile
                guide_lines = self._protection_guide_lines(diag.profile, disease_name)
                max_spray_temp = min(
                    float(getattr(product, "max_temp_c", diag.profile.max_spray_temp_c) or diag.profile.max_spray_temp_c),
                    diag.profile.max_spray_temp_c,
                )
                blockers = self._application_blockers(w_forecast, max_temp_c=max_spray_temp)
                blocked_messages = self._blocked_reason_messages(
                    w_forecast=w_forecast,
                    blockers=blockers,
                    today=today,
                    max_temp_c=max_spray_temp,
                )
                timing_blockers = self._disease_timing_blockers(plant, product, diag.profile, today)
                reentry_days = product.reentry_days
                phi_days = product.pre_harvest_interval_days
                harvest_in = self._days_until_harvest_start(plant, diag.profile)
                last_same_problem_at = plant.last_protection_by_problem.get(risk.disease)
                if last_same_problem_at and (today - last_same_problem_at.date()).days < product.min_interval_days:
                    continue
                frac_count = plant.frac_counts_90d.get(product.frac_group, 0)
                disease_count = plant.protection_counts_90d.get(risk.disease, 0)
                reasons = [
                    risk.description.rstrip("."),
                    f"\u0420\u0438\u0437\u0438\u043a: {risk.risk_level * 100:.0f}%",
                    f"\u041c\u043e\u0434\u0435\u043b\u044c \u0445\u0432\u043e\u0440\u043e\u0431\u0438: {disease_name}, \u0456\u043d\u0444\u0435\u043a\u0446\u0456\u0439\u043d\u0435 \u0432\u0456\u043a\u043d\u043e {risk.matched_days}/{risk.window_days} \u0434\u043d\u0456\u0432",
                    f"\u041f\u043e\u0432\u043d\u043e\u0442\u0430 \u0434\u0430\u043d\u0438\u0445: \u0456\u0441\u0442\u043e\u0440\u0456\u044f {min(len(w_history), 7)}/7 \u0434\u043d\u0456\u0432, \u043f\u0440\u043e\u0433\u043d\u043e\u0437 {min(len(w_forecast), 3)}/3 \u0434\u043d\u0456",
                    *risk.factors,
                    *protection.reasons,
                    *guide_lines,
                ]
                if self._is_biological_protection(product) and plant.age_days < diag.profile.disease_protection_adaptation_days:
                    reasons.append("\u0411\u0456\u043e\u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434\u0438 \u043c\u043e\u0436\u043d\u0430 \u0437\u0430\u0441\u0442\u043e\u0441\u043e\u0432\u0443\u0432\u0430\u0442\u0438 \u043c\u0430\u0439\u0436\u0435 \u043e\u0434\u0440\u0430\u0437\u0443 \u043f\u0456\u0441\u043b\u044f \u0432\u0438\u0441\u0430\u0434\u043a\u0438")
                elif plant.age_days >= diag.profile.disease_protection_adaptation_days:
                    reasons.append(f"\u041f\u0456\u0441\u043b\u044f \u0432\u0438\u0441\u0430\u0434\u043a\u0438 \u043c\u0438\u043d\u0443\u043b\u043e {plant.age_days} \u0434\u043d.; \u0432\u0456\u043a\u043d\u043e \u0430\u0434\u0430\u043f\u0442\u0430\u0446\u0456\u0457 5-7 \u0434\u043d\u0456\u0432 \u043f\u0440\u043e\u0439\u0434\u0435\u043d\u043e")
                reason_groups = {
                    "weather": [f"\u0406\u0441\u0442\u043e\u0440\u0456\u044f: {min(len(w_history), 7)}/7 \u0434\u043d\u0456\u0432", f"\u041f\u0440\u043e\u0433\u043d\u043e\u0437: {min(len(w_forecast), 3)}/3 \u0434\u043d\u0456"],
                    "soil": [],
                    "phase": [f"\u0424\u0430\u0437\u0430: {_phase_name(plant.growth_phase)}"],
                    "history": [],
                    "profile": [f"\u0427\u0443\u0442\u043b\u0438\u0432\u0456\u0441\u0442\u044c \u043f\u0440\u043e\u0444\u0456\u043b\u044e: {diag.profile.susceptibility.get(risk.disease, 0) * 100:.0f}%"],
                    "protection": [],
                }
                if plant.last_disease_at:
                    _append_group(reason_groups, "history", f"\u041e\u0441\u0442\u0430\u043d\u043d\u044f \u043e\u0431\u0440\u043e\u0431\u043a\u0430: {(today - plant.last_disease_at.date()).days} \u0434\u043d\u0456\u0432 \u0442\u043e\u043c\u0443")
                for line in self._protection_history_lines(plant, risk.disease, today):
                    _append_group(reason_groups, "history", line)
                _append_group(reason_groups, "weather", risk.description.rstrip("."))
                for factor in risk.factors:
                    _append_group(reason_groups, "weather", factor)
                _append_group(reason_groups, "protection", f"Обраний варіант: {product.label} ({product.protection_type}, FRAC {product.frac_group})")
                _append_group(reason_groups, "protection", protection.explanation)
                for line in guide_lines:
                    _append_group(reason_groups, "protection", line)
                constraints = [
                    *blockers,
                    *timing_blockers,
                    f"FRAC {product.frac_group}",
                    f"re-entry interval {reentry_days} \u0434\u043d.",
                    f"pre-harvest interval {phi_days} \u0434\u043d.",
                    f"rainfastness {product.rainfast_hours} \u0433\u043e\u0434.",
                    f"\u043c\u0430\u043a\u0441. {product.max_applications_per_season} \u043e\u0431\u0440\u043e\u0431\u043e\u043a/\u0441\u0435\u0437\u043e\u043d",
                    f"\u0456\u043d\u0442\u0435\u0440\u0432\u0430\u043b {product.min_interval_days} \u0434\u043d.",
                ]
                resistance_blockers: list[str] = []
                if disease_count >= product.max_applications_per_season:
                    resistance_blockers.append(
                        f"Ліміт обробок від цієї хвороби вичерпано: {disease_count}/{product.max_applications_per_season}"
                    )
                if (
                    product.frac_group
                    and plant.last_frac_group == product.frac_group
                    and not product.frac_group.startswith("M")
                ):
                    resistance_blockers.append(
                        f"Потрібна ротація FRAC: попередня обробка вже була групою {product.frac_group}"
                    )
                if frac_count >= product.max_applications_per_season:
                    resistance_blockers.append(
                        f"Ліміт FRAC {product.frac_group} за сезон: {frac_count}/{product.max_applications_per_season}"
                    )
                task = GardenTask(
                    TaskType.DISEASE_PROTECTION,
                    risk.priority,
                    f"\u0424\u0443\u043d\u0433\u0456\u0446\u0438\u0434\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442: {disease_name} \u2014 {plant.plant_type}{v}",
                    f"{risk.description} {risk.recommendation} {protection.explanation}",
                    plant.plant_type,
                    plant.variety,
                    plant.cell_col,
                    plant.cell_row,
                    confidence=min(self._disease_confidence(risk, w_history, w_forecast), risk.model_confidence),
                    reasons=reasons,
                    reason_groups=reason_groups,
                    recommendation_type=protection.recommendation_type,
                    constraints=constraints,
                )
                if harvest_in <= phi_days:
                    task.is_hidden = True
                    task.title = f"\u0417\u0430\u0445\u0438\u0441\u0442 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {disease_name} \u2014 {plant.plant_type}{v}"
                    task.blocked_reasons = [f"\u0414\u043e \u0437\u0431\u043e\u0440\u0443 \u0432\u0440\u043e\u0436\u0430\u044e {_safe_date_label(harvest_in)}, \u0430 pre-harvest interval \u0434\u043b\u044f \u0446\u044c\u043e\u0433\u043e \u0437\u0430\u0445\u0438\u0441\u0442\u0443 {phi_days} \u0434\u043d\u0456\u0432"]
                    diag.hidden_tasks.append(task)
                elif resistance_blockers:
                    task.is_hidden = True
                    task.title = f"\u0417\u0430\u0445\u0438\u0441\u0442 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {disease_name} \u2014 {plant.plant_type}{v}"
                    task.blocked_reasons = resistance_blockers
                    task.constraints = [*constraints, *resistance_blockers]
                    diag.hidden_tasks.append(task)
                elif timing_blockers:
                    task.is_hidden = True
                    task.title = f"\u0417\u0430\u0445\u0438\u0441\u0442 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {disease_name} \u2014 {plant.plant_type}{v}"
                    task.blocked_reasons = timing_blockers
                    diag.hidden_tasks.append(task)
                elif blockers:
                    task.is_hidden = True
                    task.title = f"\u0417\u0430\u0445\u0438\u0441\u0442 \u0432\u0456\u0434\u043a\u043b\u0430\u0441\u0442\u0438: {disease_name} \u2014 {plant.plant_type}{v}"
                    task.blocked_reasons = blocked_messages
                    diag.hidden_tasks.append(task)
                else:
                    diag.tasks.append(task)

    def _generate_pest_tasks(self, plant: PlantInstance, diag: CellDiagnostics, w_forecast: list[WeatherSnapshot], today: date) -> None:
        if not diag.pest_risks:
            return
        v = f" ({plant.variety})" if plant.variety else ""
        for risk in diag.pest_risks:
            last_same_problem_at = plant.last_protection_by_problem.get(risk.key) or plant.last_protection_by_problem.get(risk.name)
            if last_same_problem_at and (today - last_same_problem_at.date()).days < _DISEASE_COOLDOWN_DAYS:
                continue

            guide_lines = self._pest_guide_lines(diag.profile, risk.name)
            count_90d = plant.protection_counts_90d.get(risk.key, 0) + plant.protection_counts_90d.get(risk.name, 0)
            confirmation_constraint = self._pest_confirmation_constraint(risk)
            confirmation_text = self._pest_confirmation_text(risk)
            monitoring_text = self._pest_monitoring_text(risk)
            base_constraints = [
                confirmation_constraint,
                "Починати з механічних/біологічних заходів; хімічний інсектицид тільки після підтвердження шкідника і за етикеткою",
                "Не обробляти під час активного льоту бджіл; безпечніше ввечері або рано-вранці",
                "Дотримуватись норми внесення, строку очікування, ЗІЗ та обмежень для конкретного препарату",
                "Ротація IRAC/MoA: не повторювати одну діючу речовину або групу поспіль",
            ]
            reason_groups = {
                "weather": [],
                "phase": [f"Фаза: {_phase_name(plant.growth_phase)}", f"Вік рослини: {plant.age_days} дн."],
                "observation": [],
                "profile": [f"Шкідник з профілю культури: {risk.name}"],
                "protection": [],
                "history": [],
            }
            reasons = [
                risk.description,
                f"Ризик: {risk.risk_level * 100:.0f}%",
                *risk.factors,
                risk.recommendation,
                *guide_lines,
            ]
            for factor in risk.factors:
                if any(word in factor.lower() for word in ("погод", "тепл", "спек", "волог", "сух")):
                    _append_group(reason_groups, "weather", factor)
                elif "фаза" in factor.lower():
                    _append_group(reason_groups, "phase", factor)
                elif "спостереж" in factor.lower():
                    _append_group(reason_groups, "observation", factor)
                else:
                    _append_group(reason_groups, "profile", factor)
            if plant.observed_symptoms:
                _append_group(reason_groups, "observation", f"Симптоми: {', '.join(plant.observed_symptoms[:3])}")
            if plant.observed_leaf_condition:
                _append_group(reason_groups, "observation", f"Стан листя: {plant.observed_leaf_condition}")
            for line in guide_lines:
                _append_group(reason_groups, "protection", line)
            if last_same_problem_at:
                _append_group(reason_groups, "history", f"Останній захист від цього шкідника: {(today - last_same_problem_at.date()).days} дн. тому")
            if count_90d:
                _append_group(reason_groups, "history", f"Обробок від цього шкідника за 90 днів: {count_90d}")

            confidence = _confidence(68 + int(risk.risk_level * 22) + (8 if risk.observed else 0))
            if risk.requires_intervention:
                blockers = self._application_blockers(
                    w_forecast,
                    profile=diag.profile,
                    today=today,
                    max_temp_c=min(28, diag.profile.max_spray_temp_c),
                )
                blocked_messages = self._blocked_reason_messages(
                    blockers=blockers,
                    w_forecast=w_forecast,
                    today=today,
                    profile=diag.profile,
                    max_temp_c=min(28, diag.profile.max_spray_temp_c),
                )
                title = f"Інсектицидний/IPM-захист: {risk.name} — {plant.plant_type}{v}"
                description = (
                    f"{risk.description} {risk.recommendation} "
                    f"{confirmation_text}"
                    "Якщо заселення слабке — почніть з ручного видалення, біопрепаратів або м'яких засобів."
                )
                task = GardenTask(
                    TaskType.PEST_CONTROL,
                    risk.priority,
                    title,
                    description,
                    plant.plant_type,
                    plant.variety,
                    plant.cell_col,
                    plant.cell_row,
                    confidence=confidence,
                    reasons=reasons,
                    reason_groups=reason_groups,
                    recommendation_type="ipm_insecticide_intervention",
                    constraints=[*base_constraints, *blockers],
                )
                if blockers:
                    task.is_hidden = True
                    task.title = f"Інсектицидний захист відкласти: {risk.name} — {plant.plant_type}{v}"
                    task.blocked_reasons = blocked_messages
                    diag.hidden_tasks.append(task)
                else:
                    diag.tasks.append(task)
            else:
                task = GardenTask(
                    TaskType.PEST_CONTROL,
                    TaskPriority.MEDIUM,
                    f"Моніторинг шкідників: {risk.name} — {plant.plant_type}{v}",
                    f"{risk.description} {monitoring_text}",
                    plant.plant_type,
                    plant.variety,
                    plant.cell_col,
                    plant.cell_row,
                    confidence=confidence,
                    reasons=reasons,
                    reason_groups=reason_groups,
                    recommendation_type="ipm_pest_monitoring",
                    constraints=base_constraints[:3],
                )
                diag.tasks.append(task)

    def _generate_cold_stress_tasks(self, plant: PlantInstance, profile: CropProfile, diag: CellDiagnostics, w_today: WeatherSnapshot, w_forecast: list[WeatherSnapshot], today: date) -> None:
        frost_cooldown = self._in_cooldown(plant.last_frost_protection_at, today, _FROST_COOLDOWN_DAYS)
        if frost_cooldown:
            return

        v = f" ({plant.variety})" if plant.variety else ""
        upcoming = [
            weather for weather in w_forecast
            if weather.date and (_weather_date(weather.date) or today) > today
        ][:3]
        cold_nights_next_3 = sum(1 for weather in upcoming if self._is_cold_stress_weather(weather, profile))
        cool_days_next_3 = 0 if profile.cold_stress_threshold_c is not None else sum(1 for weather in upcoming if weather.temp_avg < profile.t_optimal_min)
        cold_sensitive = profile.t_min_growth >= 10 and profile.cold_stress_threshold_c is None
        young_plant = plant.growth_phase == GrowthPhase.INITIAL or plant.age_days < 21

        candidates: list[tuple[WeatherSnapshot, str]] = []
        frost_threshold = profile.frost_critical_threshold_c if profile.frost_critical_threshold_c is not None else profile.frost_tolerance
        today_cold_stress = (
            self._is_cold_stress_weather(w_today, profile)
            if profile.cold_stress_threshold_c is not None
            else w_today.temp_min < profile.t_min_growth
        )
        if w_today.temp_min > frost_threshold and today_cold_stress:
            candidates.append((w_today, "\u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456"))
        for weather in upcoming:
            if weather.temp_min <= frost_threshold:
                continue
            if self._is_cold_stress_weather(weather, profile):
                candidates.append((weather, _date_label(weather.date, today)))

        seen_dates: set[str] = set()
        for weather, label in candidates:
            weather_key = weather.date or label
            if weather_key in seen_dates:
                continue
            seen_dates.add(weather_key)

            cold_wet_windy = (
                weather.precipitation_mm >= 2
                or weather.humidity_avg >= 85
                or weather.has_dew
                or weather.is_fog
            ) and weather.wind_speed_ms >= _COLD_WET_WINDY_U2_MS
            near_frost = (
                weather.temp_min < profile.cold_stress_threshold_c
                if profile.cold_stress_threshold_c is not None
                else weather.temp_min <= frost_threshold + 1.0
            )
            severity = 0
            if self._is_cold_stress_weather(weather, profile):
                severity += 1
            if profile.cold_stress_threshold_c is None and weather.temp_avg < profile.t_optimal_min:
                severity += 1
            if cold_nights_next_3 >= 2:
                severity += 1
            if cool_days_next_3 >= 2:
                severity += 1
            if young_plant:
                severity += 1
            if cold_sensitive:
                severity += 1
            if cold_wet_windy:
                severity += 1
            if near_frost:
                severity += 1

            if severity >= 6 or near_frost or (cold_wet_windy and cold_nights_next_3 >= 2 and cold_sensitive):
                priority = TaskPriority.CRITICAL
                base_confidence = 95
            elif severity >= 4:
                priority = TaskPriority.HIGH
                base_confidence = 90
            else:
                priority = TaskPriority.MEDIUM
                base_confidence = 84

            reasons = [
                f"\u041f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f: {label} {weather.temp_min:.0f}\u00b0C",
                f"\u041f\u043e\u0440\u0456\u0433 \u0440\u043e\u0441\u0442\u0443 \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438: {profile.t_min_growth:.0f}\u00b0C",
                f"\u041e\u043f\u0442\u0438\u043c\u0443\u043c \u0440\u043e\u0441\u0442\u0443 \u0432\u0456\u0434: {profile.t_optimal_min:.0f}\u00b0C",
            ]
            reason_groups = {
                "weather": [
                    f"\u041c\u0456\u043d\u0456\u043c\u0430\u043b\u044c\u043d\u0430 \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430: {weather.temp_min:.0f}\u00b0C",
                    f"\u0421\u0435\u0440\u0435\u0434\u043d\u044f \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430: {weather.temp_avg:.0f}\u00b0C",
                    f"\u0425\u043e\u043b\u043e\u0434\u043d\u0438\u0445 \u043d\u043e\u0447\u0435\u0439 \u0443 \u043f\u0440\u043e\u0433\u043d\u043e\u0437\u0456: {cold_nights_next_3}",
                ],
                "soil": [],
                "phase": [f"\u0424\u0430\u0437\u0430: {_phase_name(plant.growth_phase)}"],
                "history": [],
                "profile": [f"\u0427\u0443\u0442\u043b\u0438\u0432\u0456\u0441\u0442\u044c \u0434\u043e \u0445\u043e\u043b\u043e\u0434\u0443: {'\u0432\u0438\u0441\u043e\u043a\u0430' if cold_sensitive else '\u043f\u043e\u043c\u0456\u0440\u043d\u0430'}"],
            }
            if young_plant:
                reasons.append(f"\u041c\u043e\u043b\u043e\u0434\u0430 \u0440\u043e\u0441\u043b\u0438\u043d\u0430: {plant.age_days} \u0434\u043d\u0456\u0432")
                _append_group(reason_groups, "phase", f"\u041c\u043e\u043b\u043e\u0434\u0430 \u0440\u043e\u0441\u043b\u0438\u043d\u0430: {plant.age_days} \u0434\u043d\u0456\u0432")
            if cool_days_next_3 >= 2:
                reasons.append(f"\u041f\u0440\u043e\u0445\u043e\u043b\u043e\u0434\u043d\u0438\u0445 \u0434\u043d\u0456\u0432 \u043f\u043e\u0441\u043f\u0456\u043b\u044c: {cool_days_next_3}")
                _append_group(reason_groups, "weather", f"\u041f\u0440\u043e\u0445\u043e\u043b\u043e\u0434\u043d\u0438\u0445 \u0434\u043d\u0456\u0432 \u043f\u043e\u0441\u043f\u0456\u043b\u044c: {cool_days_next_3}")
            if cold_wet_windy:
                reasons.append(f"\u0425\u043e\u043b\u043e\u0434 + \u0432\u043e\u043b\u043e\u0433\u0430 + \u0432\u0456\u0442\u0435\u0440: {weather.wind_speed_ms:.1f} \u043c/\u0441")
                _append_group(reason_groups, "weather", f"\u041e\u043f\u0430\u0434\u0438/\u0432\u043e\u043b\u043e\u0433\u0430 + \u0432\u0456\u0442\u0435\u0440: {weather.wind_speed_ms:.1f} \u043c/\u0441")
            if weather.precipitation_mm > 0:
                _append_group(reason_groups, "weather", f"\u041e\u043f\u0430\u0434\u0438: {weather.precipitation_mm:.0f} \u043c\u043c")
            if weather.humidity_avg >= 85 or weather.has_dew or weather.is_fog:
                _append_group(reason_groups, "weather", f"\u0412\u0438\u0441\u043e\u043a\u0430 \u0432\u043e\u043b\u043e\u0433\u0456\u0441\u0442\u044c: {weather.humidity_avg:.0f}%")

            description = (
                "\u041e\u0447\u0456\u043a\u0443\u0454\u0442\u044c\u0441\u044f \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u043d\u0438\u0436\u0447\u0435 \u043a\u043e\u043c\u0444\u043e\u0440\u0442\u043d\u043e\u0433\u043e \u043f\u043e\u0440\u043e\u0433\u0443 \u0434\u043b\u044f \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438. "
                "\u041f\u0456\u0434\u0433\u043e\u0442\u0443\u0439\u0442\u0435 \u0430\u0433\u0440\u043e\u0432\u043e\u043b\u043e\u043a\u043d\u043e \u0430\u0431\u043e \u0456\u043d\u0448\u0435 \u0443\u043a\u0440\u0438\u0442\u0442\u044f, \u043d\u0435 \u043f\u043e\u043b\u0438\u0432\u0430\u0439\u0442\u0435 \u0432\u0432\u0435\u0447\u0435\u0440\u0456 "
                "\u0442\u0430 \u0432\u0456\u0434\u043a\u043b\u0430\u0434\u0456\u0442\u044c \u043b\u0438\u0441\u0442\u043a\u043e\u0432\u0456 \u043e\u0431\u0440\u043e\u0431\u043a\u0438 \u0434\u043e \u043f\u043e\u0442\u0435\u043f\u043b\u0456\u043d\u043d\u044f."
            )
            diag.tasks.append(GardenTask(
                TaskType.COLD_STRESS,
                priority,
                f"\u041f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f: {plant.plant_type}{v}",
                description,
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                due_date=weather.date,
                confidence=base_confidence,
                reasons=reasons,
                reason_groups=reason_groups,
                recommendation_type="\u0443\u043a\u0440\u0438\u0442\u0442\u044f / \u0430\u0433\u0440\u043e\u0432\u043e\u043b\u043e\u043a\u043d\u043e",
                constraints=[
                    "\u041d\u0435 \u043f\u043e\u043b\u0438\u0432\u0430\u0439\u0442\u0435 \u0432\u0432\u0435\u0447\u0435\u0440\u0456 \u043f\u0435\u0440\u0435\u0434 \u043f\u043e\u0445\u043e\u043b\u043e\u0434\u0430\u043d\u043d\u044f\u043c",
                    "\u0412\u0456\u0434\u043a\u043b\u0430\u0434\u0456\u0442\u044c \u043b\u0438\u0441\u0442\u043a\u043e\u0432\u0456 \u043f\u0456\u0434\u0436\u0438\u0432\u043b\u0435\u043d\u043d\u044f \u0442\u0430 \u043e\u0431\u0440\u043e\u0431\u043a\u0438 \u0434\u043e \u043f\u043e\u0442\u0435\u043f\u043b\u0456\u043d\u043d\u044f",
                ],
            ))

    def _generate_climate_tasks(self, plant: PlantInstance, profile: CropProfile, diag: CellDiagnostics, w_today: WeatherSnapshot, w_forecast: list[WeatherSnapshot], today: date) -> None:
        frost_cooldown = self._in_cooldown(plant.last_frost_protection_at, today, _FROST_COOLDOWN_DAYS)
        v = f" ({plant.variety})" if plant.variety else ""
        frost_threshold = profile.frost_critical_threshold_c if profile.frost_critical_threshold_c is not None else profile.frost_tolerance
        if diag.frost_risk and not frost_cooldown:
            diag.tasks.append(GardenTask(
                TaskType.FROST_PROTECTION,
                TaskPriority.CRITICAL,
                f"\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043e\u043a: {plant.plant_type}{v}",
                f"\u041c\u0456\u043d\u0456\u043c\u0430\u043b\u044c\u043d\u0430 \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 {w_today.temp_min:.0f}\u00b0C \u043d\u0438\u0436\u0447\u0430 \u0437\u0430 \u043a\u0440\u0438\u0442\u0438\u0447\u043d\u0443 \u043c\u0435\u0436\u0443 \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438 ({frost_threshold:.0f}\u00b0C). \u0422\u0435\u0440\u043c\u0456\u043d\u043e\u0432\u043e \u043f\u0456\u0434\u0433\u043e\u0442\u0443\u0439\u0442\u0435 \u0443\u043a\u0440\u0438\u0442\u0442\u044f.",
                plant.plant_type,
                plant.variety,
                plant.cell_col,
                plant.cell_row,
                confidence=97,
                reasons=[
                    f"\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043e\u043a: \u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456 {w_today.temp_min:.0f}\u00b0C",
                    f"\u041a\u0440\u0438\u0442\u0438\u0447\u043d\u0430 \u043c\u0435\u0436\u0430: {frost_threshold:.0f}\u00b0C",
                ],
            ))
        upcoming = [
            weather for weather in w_forecast
            if weather.date and (_weather_date(weather.date) or today) > today
        ]
        for weather in upcoming[:3]:
            if weather.temp_min <= frost_threshold and not frost_cooldown:
                label = _date_label(weather.date, today)
                diag.tasks.append(GardenTask(
                    TaskType.FROST_PROTECTION,
                    TaskPriority.HIGH,
                    f"\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043e\u043a {label}: {plant.plant_type}",
                    f"\u041f\u0440\u043e\u0433\u043d\u043e\u0437 \u043d\u0430 {label}: \u043c\u0456\u043d. {weather.temp_min:.0f}\u00b0C, \u0449\u043e \u043d\u0438\u0436\u0447\u0435 \u0437\u0430 \u043a\u0440\u0438\u0442\u0438\u0447\u043d\u0443 \u043c\u0435\u0436\u0443 {frost_threshold:.0f}\u00b0C. \u041f\u0456\u0434\u0433\u043e\u0442\u0443\u0439\u0442\u0435 \u0430\u0433\u0440\u043e\u0432\u043e\u043b\u043e\u043a\u043d\u043e \u0430\u0431\u043e \u0456\u043d\u0448\u0435 \u0443\u043a\u0440\u0438\u0442\u0442\u044f.",
                    plant.plant_type,
                    "",
                    plant.cell_col,
                    plant.cell_row,
                    due_date=weather.date,
                    confidence=95,
                    reasons=[
                        f"\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043e\u043a: {label} {weather.temp_min:.0f}\u00b0C",
                        f"\u041a\u0440\u0438\u0442\u0438\u0447\u043d\u0430 \u043c\u0435\u0436\u0430: {frost_threshold:.0f}\u00b0C",
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def _parse_grid_cells(cells: list[dict], today: date) -> list[PlantInstance]:
        plants: list[PlantInstance] = []
        for data in cells:
            if not data.get("plant_type"):
                continue
            try:
                lifecycle = LifecycleType(str(data.get("lifecycle_type") or "annual"))
            except ValueError:
                lifecycle = LifecycleType.ANNUAL
            planting_year = _to_int(data.get("planting_year"), 0)
            plant = PlantInstance(
                cell_col=_to_int(data.get("col"), 0),
                cell_row=_to_int(data.get("row"), 0),
                plant_type=str(data.get("plant_type")),
                variety=str(data.get("variety") or ""),
                planted_date=str(data.get("planted_date") or ""),
                plant_icon=str(data.get("plant_icon") or ""),
                plant_emoji=str(data.get("plant_emoji") or ""),
                category=str(data.get("category") or ""),
                lifecycle_type=lifecycle,
                age_years=(today.year - planting_year) if planting_year else None,
            )
            plant.calculate_age(today)
            plants.append(plant)
        return plants

    @staticmethod
    def _merge_similar_tasks(tasks: list[GardenTask]) -> list[GardenTask]:
        tasks = SmartGardenerEngine._dedupe_climate_risk_tasks(tasks)
        merged: dict[str, GardenTask] = {}
        for task in tasks:
            key = f"{task.task_type.value}|{task.priority.value}|{task.plant_name}|{task.variety}"
            if key not in merged:
                merged[key] = task
        return list(merged.values())

    @staticmethod
    def _climate_risk_key(task: GardenTask) -> tuple[str, int, int]:
        return (
            task.plant_name.casefold(),
            task.cell_col,
            task.cell_row,
        )

    @staticmethod
    def _dedupe_climate_risk_tasks(tasks: list[GardenTask]) -> list[GardenTask]:
        frost_keys = {
            SmartGardenerEngine._climate_risk_key(task)
            for task in tasks
            if task.task_type == TaskType.FROST_PROTECTION
        }
        if not frost_keys:
            return tasks
        return [
            task
            for task in tasks
            if not (
                task.task_type == TaskType.COLD_STRESS
                and SmartGardenerEngine._climate_risk_key(task) in frost_keys
            )
        ]

    @staticmethod
    def _task_to_dict(task: GardenTask) -> dict:
        return {
            "task_type": task.task_type.value,
            "priority": task.priority.value,
            "title": task.title,
            "description": task.description,
            "plant_name": task.plant_name,
            "plant_type": task.plant_name,
            "variety": task.variety,
            "cell_col": task.cell_col,
            "cell_row": task.cell_row,
            "amount": task.amount,
            "due_date": task.due_date,
            "confidence": task.confidence,
            "reasons": task.reasons,
            "reason_groups": task.reason_groups,
            "recommendation_type": task.recommendation_type,
            "constraints": task.constraints,
            "blocked_reasons": task.blocked_reasons,
            "is_hidden": task.is_hidden,
            "task_date": task.due_date or date.today().isoformat(),
            "action": task.title,
            "category": _CATEGORY_BY_TASK_TYPE.get(task.task_type, "general"),
        }


def generate_analysis(
    cells: list[dict],
    profiles_map: dict[str, dict],
    today: date | None = None,
    weather_today: dict | None = None,
    weather_forecast: list[dict] | None = None,
    weather_history: list[dict] | None = None,
    user_actions: list[dict] | None = None,
    manual_observations: list[dict] | None = None,
    soil_type: str | None = None,
    plot_overrides: PlotOverrides | dict | None = None,
    latitude: float | None = None,
    elevation_m: float | None = None,
    sat_overrides: dict[tuple[int, int], float] | None = None,
) -> dict[str, list[dict]]:
    return SmartGardenerEngine().calculate_grid_needs(
        grid_cells=cells,
        profiles_map=profiles_map,
        weather_today=weather_today,
        weather_forecast=weather_forecast,
        weather_history=weather_history,
        user_actions=user_actions,
        manual_observations=manual_observations,
        soil_type=soil_type,
        plot_overrides=plot_overrides,
        latitude=latitude,
        elevation_m=elevation_m,
        sat_overrides=sat_overrides,
        today=today,
    )


def generate_tasks(
    cells: list[dict],
    profiles_map: dict[str, dict],
    today: date | None = None,
    weather_today: dict | None = None,
    weather_forecast: list[dict] | None = None,
    weather_history: list[dict] | None = None,
    user_actions: list[dict] | None = None,
    manual_observations: list[dict] | None = None,
    soil_type: str | None = None,
    plot_overrides: PlotOverrides | dict | None = None,
    latitude: float | None = None,
    elevation_m: float | None = None,
    sat_overrides: dict[tuple[int, int], float] | None = None,
) -> list[dict]:
    return generate_analysis(
        cells,
        profiles_map,
        today=today,
        weather_today=weather_today,
        weather_forecast=weather_forecast,
        weather_history=weather_history,
        user_actions=user_actions,
        manual_observations=manual_observations,
        soil_type=soil_type,
        plot_overrides=plot_overrides,
        latitude=latitude,
        elevation_m=elevation_m,
        sat_overrides=sat_overrides,
    )["tasks"]





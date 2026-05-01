"""SQLAlchemy models — import all to register with Base.metadata."""
from app.models.user import User
from app.models.plot import Plot
from app.models.plant import Plant
from app.models.crop import CropCatalog
from app.models.care_journal import CareJournal
from app.models.finance import FinanceTransaction
from app.models.subscription import Subscription
from app.models.watering import WateringRecommendation
from app.models.weather_cache import WeatherDailyCache
from app.models.weather_zone import WeatherZone
from app.models.ai_diagnosis import AIDiagnosis
from app.models.forum import ForumTopic, ForumReply
from app.models.plant_profile import PlantProfile
from app.models.garden_action import GardenAction
from app.models.work_plan_item import WorkPlanItem
from app.models.treatment_application import TreatmentApplication
from app.models.garden_observation import GardenObservation

__all__ = [
    "User", "Plot", "Plant", "CropCatalog",
    "CareJournal", "FinanceTransaction", "Subscription",
    "WateringRecommendation", "WeatherDailyCache", "WeatherZone",
    "AIDiagnosis", "ForumTopic", "ForumReply", "PlantProfile", "GardenAction",
    "WorkPlanItem", "TreatmentApplication", "GardenObservation",
]



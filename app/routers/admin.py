"""Internal admin panel for Smart Dacha operations."""
from __future__ import annotations

import html
import uuid
from datetime import date, datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.forum import ForumReply, ForumTopic
from app.models.plant_profile import PlantProfile
from app.models.plot import Plot
from app.models.user import User
from app.models.weather_zone import WeatherZone
from app.services.fertilizer_profile_service import list_fertilizer_profiles
from app.services.gemini_usage import get_gemini_usage_by_user, get_gemini_usage_total
from app.services.plant_profile_service import lookup_profile
from app.services.protection_profile_service import list_protection_profiles
from app.services.redis_service import get_cache_redis


router = APIRouter(prefix="/admin", tags=["admin"])

_FLOAT_FIELDS = [
    "kc_initial", "kc_mid", "kc_end",
    "root_depth_initial_cm", "root_depth_max_cm",
    "field_capacity_mm", "wilting_point_mm", "critical_depletion",
    "t_min_growth", "t_optimal_min", "t_optimal_max", "t_max_growth", "frost_tolerance",
    "nitrogen", "phosphorus", "potassium", "magnesium", "calcium",
    "sus_late_blight", "sus_powdery_mildew", "sus_downy_mildew", "sus_botrytis",
]
_INT_FIELDS = [
    "initial_days", "development_days", "mid_season_days", "late_season_days",
    "days_to_harvest_min", "days_to_harvest_max", "confidence",
]


def _is_admin(user: User) -> bool:
    return bool(user.is_admin or user.email.lower() in settings.admin_email_set)


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _badge(text: str, tone: str = "slate") -> str:
    colors = {
        "green": "#14532d",
        "red": "#7f1d1d",
        "blue": "#1e3a8a",
        "amber": "#78350f",
        "slate": "#334155",
    }
    return (
        f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
        f"background:{colors.get(tone, colors['slate'])};color:#fff;font-size:12px'>{_esc(text)}</span>"
    )


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _join_short(value: object, limit: int = 4) -> str:
    items = [str(item) for item in _as_list(value) if item]
    if not items:
        return "—"
    shown = items[:limit]
    suffix = f" +{len(items) - limit}" if len(items) > limit else ""
    return "; ".join(shown) + suffix


def _render_problem_catalog(title: str, items: object) -> str:
    rows = []
    for item in _as_list(items):
        if not isinstance(item, dict):
            continue
        likelihood = str(item.get("likelihood") or "unknown")
        tone = "red" if likelihood == "high" else "amber" if likelihood == "medium" else "slate"
        rows.append(
            "<div class='problem-card'>"
            f"<h4>{_esc(item.get('name') or 'Без назви')} {_badge(likelihood, tone)}</h4>"
            f"<div class='small'>{_esc(item.get('type') or '')}</div>"
            f"<p><b>Симптоми:</b> {_esc(_join_short(item.get('symptoms')))}</p>"
            f"<p><b>Умови ризику:</b> {_esc(_join_short(item.get('risk_conditions')))}</p>"
            f"<p><b>Профілактика:</b> {_esc(_join_short(item.get('prevention')))}</p>"
            f"<p><b>Лікування/контроль:</b> {_esc(_join_short(item.get('treatment')))}</p>"
            f"<p class='small'>{_esc(item.get('notes') or '')}</p>"
            "</div>"
        )
    return (
        f"<div class='section'><h3>{_esc(title)} ({len(rows)})</h3>"
        f"<div class='problem-grid'>{''.join(rows) or '<p class=\"muted\">Даних ще немає.</p>'}</div></div>"
    )


def _render_treatment_guide(guide: object) -> str:
    labels = {
        "general_prevention": "Загальна профілактика",
        "biological_controls": "Біологічний контроль",
        "chemical_controls": "Хімічний контроль",
        "copper_controls": "Мідьвмісні препарати",
        "pest_controls": "Контроль шкідників",
        "organic_options": "Органічні методи",
        "when_to_call_expert": "Коли потрібен фахівець",
        "safety_notes": "Безпека",
    }
    data = guide if isinstance(guide, dict) else {}
    rows = []
    for key, label in labels.items():
        rows.append(
            "<tr>"
            f"<th>{_esc(label)}</th>"
            f"<td>{_esc(_join_short(data.get(key), limit=8))}</td>"
            "</tr>"
        )
    return (
        "<div class='section'><h3>Практичний довідник лікування</h3>"
        f"<table><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _layout(title: str, body: str, user: User | None = None, flash: str | None = None) -> HTMLResponse:
    nav = ""
    if user:
        nav = (
            "<nav style='display:flex;gap:16px;align-items:center;margin-bottom:24px'>"
            "<a href='/admin'>Dashboard</a>"
            "<a href='/admin/plant-profiles'>Plant Profiles</a>"
            "<a href='/admin/profile-validation'>Validation</a>"
            "<a href='/admin/forum'>Forum</a>"
            "<a href='/admin/users'>Users</a>"
            f"<span style='margin-left:auto;color:#64748b'>{_esc(user.email)}</span>"
            "<form method='post' action='/admin/logout' style='margin:0'>"
            "<button type='submit'>Logout</button>"
            "</form>"
            "</nav>"
        )
    flash_html = (
        f"<div style='margin:0 0 16px;padding:10px 12px;background:#ecfeff;border:1px solid #a5f3fc;border-radius:8px'>{_esc(flash)}</div>"
        if flash else ""
    )
    page = f"""<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }}
    .wrap {{ max-width: 1240px; margin: 0 auto; padding: 24px; }}
    a {{ color: #166534; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    h1, h2, h3 {{ margin: 0 0 16px; }}
    .cards {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:24px; }}
    .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:16px; }}
    .muted {{ color:#64748b; }}
    table {{ width:100%; border-collapse: collapse; background:#fff; border:1px solid #e2e8f0; border-radius:8px; overflow:hidden; }}
    th, td {{ padding:10px 12px; border-bottom:1px solid #e2e8f0; vertical-align:top; text-align:left; }}
    th {{ background:#f1f5f9; font-size:13px; }}
    input, select, textarea {{ width:100%; box-sizing:border-box; padding:8px 10px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; }}
    textarea {{ min-height:100px; resize:vertical; }}
    .grid {{ display:grid; gap:12px; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); }}
    .section {{ background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:16px; margin-bottom:16px; }}
    .problem-grid {{ display:grid; gap:12px; grid-template-columns: repeat(auto-fit,minmax(280px,1fr)); }}
    .problem-card {{ border:1px solid #e2e8f0; border-radius:8px; padding:12px; background:#f8fafc; }}
    .problem-card h4 {{ margin:0 0 8px; }}
    .problem-card p {{ margin:8px 0 0; }}
    .actions {{ display:flex; gap:8px; flex-wrap:wrap; }}
    button {{ padding:8px 12px; border:none; border-radius:6px; background:#166534; color:#fff; cursor:pointer; }}
    button.secondary {{ background:#475569; }}
    button.warn {{ background:#b45309; }}
    button.danger {{ background:#b91c1c; }}
    .inline {{ display:inline; }}
    .small {{ font-size:12px; color:#64748b; }}
    .filters {{ display:grid; gap:12px; grid-template-columns: 2fr 1fr auto; margin-bottom:16px; }}
  </style>
</head>
<body>
  <div class="wrap">
    {nav}
    {flash_html}
    {body}
  </div>
</body>
</html>"""
    return HTMLResponse(page)


async def _get_admin_user(request: Request, db: AsyncSession) -> User:
    user_id = request.session.get("admin_user_id")
    if not user_id:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    try:
        user_uuid = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"}) from exc
    user = await db.scalar(select(User).where(User.id == user_uuid))
    if not user or not user.is_active or not _is_admin(user):
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return user


async def _admin_dep(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    return await _get_admin_user(request, db)


def _coerce_float(value: str | None, default: float) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


def _coerce_int(value: str | None, default: int) -> int:
    try:
        return int(float(value)) if value not in (None, "") else default
    except ValueError:
        return default


def _validation_tone(issues: list[str]) -> str:
    return "green" if not issues else "red" if any("critical:" in item for item in issues) else "amber"


def _validate_plant_profile(profile: PlantProfile) -> list[str]:
    issues: list[str] = []
    if profile.confidence < 70:
        issues.append(f"critical: низька довіра профілю {profile.confidence}%")
    elif profile.confidence < 85:
        issues.append(f"warning: профіль бажано перевірити, довіра {profile.confidence}%")
    if profile.validation_warnings:
        issues.extend(f"warning: {warning}" for warning in profile.validation_warnings)
    if not (0.1 <= profile.kc_initial <= profile.kc_mid <= 1.6):
        issues.append("critical: Kc initial/mid поза очікуваним порядком або межами")
    if not (0.1 <= profile.kc_end <= 1.4):
        issues.append("warning: Kc end поза типовими межами")
    if profile.root_depth_initial_cm <= 0 or profile.root_depth_max_cm <= profile.root_depth_initial_cm:
        issues.append("critical: некоректна глибина коренів")
    if profile.critical_depletion <= 0 or profile.critical_depletion >= 0.9:
        issues.append("critical: critical_depletion має бути між 0 і 0.9")
    if profile.t_min_growth > profile.t_optimal_min or profile.t_optimal_min > profile.t_optimal_max:
        issues.append("critical: температурні пороги росту мають неправильний порядок")
    if profile.t_max_growth < profile.t_optimal_max:
        issues.append("critical: t_max_growth нижче оптимального максимуму")
    if profile.days_to_harvest_min > profile.days_to_harvest_max:
        issues.append("critical: мінімальний збір пізніше максимального")
    for field in ("nitrogen", "phosphorus", "potassium"):
        if getattr(profile, field) <= 0:
            issues.append(f"warning: {field} не заданий або нульовий")
    for field in ("sus_late_blight", "sus_powdery_mildew", "sus_downy_mildew", "sus_botrytis"):
        value = getattr(profile, field)
        if value < 0 or value > 1:
            issues.append(f"critical: {field} має бути в межах 0..1")
    if not profile.description:
        issues.append("warning: немає опису джерела/агрономічної примітки")
    return issues


def _validate_fertilizer_profile(profile) -> list[str]:
    issues: list[str] = []
    nutrients = profile.n_pct + profile.p_pct + profile.k_pct + profile.mg_pct + profile.ca_pct
    if nutrients <= 0 and profile.organic_matter_pct <= 0:
        issues.append("critical: немає NPK/Mg/Ca або органічної речовини")
    if nutrients > 100:
        issues.append("critical: сумарний склад поживних перевищує 100%")
    if not profile.suitable_goals:
        issues.append("warning: не задані suitable_goals")
    if profile.avoid_before_rain_mm < 0:
        issues.append("critical: avoid_before_rain_mm не може бути від'ємним")
    if profile.max_temp_c < 20:
        issues.append("warning: max_temp_c виглядає надто низьким")
    if profile.max_wind_ms <= 0:
        issues.append("critical: max_wind_ms має бути > 0")
    if profile.release_speed not in {"slow", "medium", "fast"}:
        issues.append("warning: release_speed має бути slow/medium/fast")
    return issues


def _validate_protection_profile(profile) -> list[str]:
    issues: list[str] = []
    if not profile.target_diseases:
        issues.append("critical: не задані target_diseases")
    if not profile.frac_group:
        issues.append("critical: не задана FRAC-група")
    if profile.pre_harvest_interval_days < 0 or profile.reentry_days < 0:
        issues.append("critical: PHI/REI не можуть бути від'ємними")
    if profile.min_interval_days <= 0:
        issues.append("critical: min_interval_days має бути > 0")
    if profile.max_applications_per_season <= 0:
        issues.append("critical: max_applications_per_season має бути > 0")
    if profile.rainfast_hours <= 0:
        issues.append("warning: rainfast_hours має бути > 0")
    if profile.max_wind_ms <= 0:
        issues.append("critical: max_wind_ms має бути > 0")
    if not profile.preventive and not profile.curative:
        issues.append("warning: профіль не preventive і не curative")
    return issues


def _issue_list(issues: list[str]) -> str:
    if not issues:
        return "<span class='small'>OK</span>"
    return "<ul style='margin:0;padding-left:18px'>" + "".join(f"<li>{_esc(issue)}</li>" for issue in issues) + "</ul>"


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get("admin_user_id")
    if user_id:
        user = await db.scalar(select(User).where(User.id == uuid.UUID(str(user_id))))
        if user and _is_admin(user):
            return _redirect("/admin")
    body = """
    <div class='section' style='max-width:420px;margin:80px auto'>
      <h1>Smart Dacha Admin</h1>
      <p class='muted'>Вхід для внутрішньої адмінки бекенду.</p>
      <form method='post' action='/admin/login'>
        <div class='grid' style='grid-template-columns:1fr'>
          <label>Email<input type='email' name='email' required></label>
          <label>Пароль<input type='password' name='password' required></label>
          <button type='submit'>Увійти</button>
        </div>
      </form>
    </div>
    """
    flash = request.query_params.get("error")
    return _layout("Admin Login", body, flash=flash)


@router.post("/login")
async def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(User.email == email.strip()))
    if not user or not user.is_active or not _is_admin(user):
        return _redirect("/admin/login?error=Немає+доступу")
    if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return _redirect("/admin/login?error=Невірний+пароль")
    request.session["admin_user_id"] = str(user.id)
    return _redirect("/admin")


@router.post("/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return _redirect("/admin/login")


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    user_count = await db.scalar(select(func.count()).select_from(User)) or 0
    plot_count = await db.scalar(select(func.count()).select_from(Plot)) or 0
    profile_count = await db.scalar(select(func.count()).select_from(PlantProfile)) or 0
    topic_count = await db.scalar(select(func.count()).select_from(ForumTopic).where(ForumTopic.is_deleted.is_(False))) or 0
    reply_count = await db.scalar(select(func.count()).select_from(ForumReply).where(ForumReply.is_deleted.is_(False))) or 0
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=8)
    stale_weather = await db.scalar(
        select(func.count()).select_from(WeatherZone).where(
            or_(WeatherZone.last_fetched_at.is_(None), WeatherZone.last_fetched_at < stale_cutoff)
        )
    ) or 0
    gemini_profile_used = "n/a"
    try:
        gemini_profile_used = await (await get_cache_redis()).get(f"gemini:profile_lookup:{date.today().isoformat()}") or "0"
    except Exception:
        pass
    gemini_today = await get_gemini_usage_total(days=1)
    gemini_week = await get_gemini_usage_total(days=7)
    gemini_user_stats = await get_gemini_usage_by_user(days=7, limit=10)
    gemini_user_ids = []
    for item in gemini_user_stats:
        try:
            gemini_user_ids.append(uuid.UUID(str(item["user_id"])))
        except ValueError:
            continue
    gemini_users = {}
    if gemini_user_ids:
        users = (await db.execute(select(User).where(User.id.in_(gemini_user_ids)))).scalars().all()
        gemini_users = {str(user.id): user for user in users}
    gemini_rows = []
    for item in gemini_user_stats:
        user = gemini_users.get(str(item["user_id"]))
        label = user.email if user else item["user_id"]
        gemini_rows.append(
            "<tr>"
            f"<td>{_esc(label)}</td>"
            f"<td>{_esc(item['count'])}</td>"
            "</tr>"
        )
    gemini_table = (
        "<table><thead><tr><th>User</th><th>Gemini calls, 7d</th></tr></thead><tbody>"
        + "".join(gemini_rows)
        + "</tbody></table>"
        if gemini_rows
        else "<p class='muted'>No per-user Gemini usage recorded yet.</p>"
    )

    body = f"""
    <h1>Admin Dashboard</h1>
    <div class='cards'>
      <div class='card'><div class='muted'>Users</div><h2>{user_count}</h2></div>
      <div class='card'><div class='muted'>Plots</div><h2>{plot_count}</h2></div>
      <div class='card'><div class='muted'>Plant Profiles</div><h2>{profile_count}</h2></div>
      <div class='card'><div class='muted'>Forum Topics</div><h2>{topic_count}</h2></div>
      <div class='card'><div class='muted'>Forum Replies</div><h2>{reply_count}</h2></div>
      <div class='card'><div class='muted'>Stale Weather Zones</div><h2>{stale_weather}</h2></div>
      <div class='card'><div class='muted'>Gemini Today</div><h2>{gemini_today}</h2><div class='small'>profile budget: {_esc(gemini_profile_used)} / {settings.GEMINI_DAILY_BUDGET}</div></div>
      <div class='card'><div class='muted'>Gemini 7 Days</div><h2>{gemini_week}</h2></div>
    </div>
    <div class='grid'>
      <div class='section'>
        <h3>Gemini Usage</h3>
        {gemini_table}
      </div>
      <div class='section'>
        <h3>Що вже є в MVP</h3>
        <ul>
          <li>admin login через backend user</li>
          <li>dashboard зі станом даних</li>
          <li>редагування plant profiles</li><li>validation center для PlantProfile, fertilizer і protection profiles</li>
          <li>forum moderation</li>
          <li>керування admin/active для користувачів</li>
        </ul>
      </div>
      <div class='section'>
        <h3>Наступний крок</h3>
        <p class='muted'>Після MVP логічно додати audit log, verified/deprecated status для профілів і debug view агроаналізу по ділянці.</p>
      </div>
    </div>
    """
    return _layout("Admin Dashboard", body, user=admin_user, flash=request.query_params.get("flash"))


@router.get("/profile-validation", response_class=HTMLResponse)
async def admin_profile_validation(
    request: Request,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    profiles = (await db.execute(select(PlantProfile).order_by(PlantProfile.confidence.asc(), PlantProfile.created_at.desc()).limit(300))).scalars().all()
    plant_rows = []
    plant_problem_count = 0
    for profile in profiles:
        issues = _validate_plant_profile(profile)
        if issues:
            plant_problem_count += 1
        plant_rows.append(
            "<tr>"
            f"<td><a href='/admin/plant-profiles/{profile.id}'>{_esc(profile.name)}</a><div class='small'>{_esc(profile.category)}</div></td>"
            f"<td>{_badge(str(profile.confidence), _validation_tone(issues))}</td>"
            f"<td>{_badge(profile.source or 'db', 'slate')}</td>"
            f"<td>{_issue_list(issues)}</td>"
            "</tr>"
        )

    fertilizer_rows = []
    fertilizer_problem_count = 0
    for profile in list_fertilizer_profiles():
        issues = _validate_fertilizer_profile(profile)
        if issues:
            fertilizer_problem_count += 1
        fertilizer_rows.append(
            "<tr>"
            f"<td><strong>{_esc(profile.label)}</strong><div class='small'>{_esc(profile.id)}</div></td>"
            f"<td>{_esc(profile.fertilizer_type)} / {_esc(profile.application_method)}</td>"
            f"<td>{_esc(profile.nutrient_label)}</td>"
            f"<td>{_issue_list(issues)}</td>"
            "</tr>"
        )

    protection_rows = []
    protection_problem_count = 0
    for profile in list_protection_profiles():
        issues = _validate_protection_profile(profile)
        if issues:
            protection_problem_count += 1
        protection_rows.append(
            "<tr>"
            f"<td><strong>{_esc(profile.label)}</strong><div class='small'>{_esc(profile.id)}</div></td>"
            f"<td>{_esc(profile.protection_type)}<div class='small'>FRAC {_esc(profile.frac_group)}</div></td>"
            f"<td>REI {profile.reentry_days} дн. / PHI {profile.pre_harvest_interval_days} дн.<div class='small'>max {profile.max_applications_per_season}, interval {profile.min_interval_days} дн.</div></td>"
            f"<td>{_issue_list(issues)}</td>"
            "</tr>"
        )

    body = f"""
    <h1>Profile Validation Center</h1>
    <div class='cards'>
      <div class='card'><div class='muted'>Plant profiles checked</div><h2>{len(profiles)}</h2><div>{_badge(str(plant_problem_count) + ' with issues', 'amber' if plant_problem_count else 'green')}</div></div>
      <div class='card'><div class='muted'>Fertilizer profiles</div><h2>{len(fertilizer_rows)}</h2><div>{_badge(str(fertilizer_problem_count) + ' with issues', 'amber' if fertilizer_problem_count else 'green')}</div></div>
      <div class='card'><div class='muted'>Protection profiles</div><h2>{len(protection_rows)}</h2><div>{_badge(str(protection_problem_count) + ' with issues', 'amber' if protection_problem_count else 'green')}</div></div>
    </div>
    <div class='section'>
      <h2>PlantProfile checks</h2>
      <p class='muted'>Перевіряє Kc, корені, температурні пороги, NPK, disease susceptibility, confidence і warnings. Редагування відкривається через назву профілю.</p>
      <table><thead><tr><th>Профіль</th><th>Confidence</th><th>Source</th><th>Issues</th></tr></thead><tbody>{''.join(plant_rows) or "<tr><td colspan='4'>Профілів немає</td></tr>"}</tbody></table>
    </div>
    <div class='section'>
      <h2>Fertilizer catalog checks</h2>
      <p class='muted'>Read-only перевірка статичних профілів добрив: склад, цілі, обмеження за дощем, температурою і вітром.</p>
      <table><thead><tr><th>Профіль</th><th>Тип / метод</th><th>Nutrients</th><th>Issues</th></tr></thead><tbody>{''.join(fertilizer_rows)}</tbody></table>
    </div>
    <div class='section'>
      <h2>Protection catalog checks</h2>
      <p class='muted'>Read-only перевірка профілів захисту: target diseases, FRAC, REI, PHI, інтервали і ліміти сезону.</p>
      <table><thead><tr><th>Профіль</th><th>Тип</th><th>Safety</th><th>Issues</th></tr></thead><tbody>{''.join(protection_rows)}</tbody></table>
    </div>
    """
    return _layout("Profile Validation", body, user=admin_user, flash=request.query_params.get("flash"))


@router.get("/plant-profiles", response_class=HTMLResponse)
async def admin_plant_profiles(
    request: Request,
    q: str | None = None,
    source: str | None = None,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    query = select(PlantProfile).order_by(PlantProfile.created_at.desc()).limit(200)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(PlantProfile.name.ilike(like), PlantProfile.category.ilike(like)))
    if source:
        query = query.where(PlantProfile.source == source)
    profiles = (await db.execute(query)).scalars().all()
    rows = []
    for profile in profiles:
        tone = "green" if profile.confidence >= 90 else "blue" if profile.confidence >= 75 else "amber"
        rows.append(
            "<tr>"
            f"<td><a href='/admin/plant-profiles/{profile.id}'>{_esc(profile.name)}</a><div class='small'>{_esc(profile.category)}</div></td>"
            f"<td>{_badge(profile.source or 'db', 'slate')}</td>"
            f"<td>{_badge(str(profile.confidence), tone)}</td>"
            f"<td>{len(profile.common_diseases or [])}</td>"
            f"<td>{len(profile.common_pests or [])}</td>"
            f"<td>{_esc(', '.join(profile.validation_warnings or []) or '—')}</td>"
            f"<td>{_esc(profile.created_at)}</td>"
            f"<td><form class='inline' method='post' action='/admin/plant-profiles/{profile.id}/delete' "
            "onsubmit=\"return confirm('Видалити цей профіль рослини?')\">"
            "<button class='danger' type='submit'>Видалити</button></form></td>"
            "</tr>"
        )
    body = f"""
    <h1>Plant Profiles</h1>
    <div class='section'>
      <h3>Додати профіль рослини через Gemini</h3>
      <form method='post' action='/admin/plant-profiles/create' class='filters'>
        <input type='text' name='plant_name' placeholder='Назва рослини, наприклад: Абрикос' required>
        <input type='text' name='category' value='Овочі' placeholder='Категорія'>
        <button type='submit'>Створити</button>
      </form>
      <div class='small'>Якщо профіль уже існує, адмінка відкриє наявний запис. Якщо ні — підтягне дані з Gemini та збере повний агрономічний профіль.</div>
    </div>
    <form method='get' class='filters'>
      <input type='text' name='q' value='{_esc(q)}' placeholder='Пошук по назві або категорії'>
      <select name='source'>
        <option value=''>Усі джерела</option>
        <option value='curated' {'selected' if source == 'curated' else ''}>curated</option>
        <option value='catalog' {'selected' if source == 'catalog' else ''}>catalog</option>
        <option value='gemini' {'selected' if source == 'gemini' else ''}>gemini</option>
        <option value='default' {'selected' if source == 'default' else ''}>default</option>
      </select>
      <button type='submit'>Фільтр</button>
    </form>
    <table>
      <thead><tr><th>Рослина</th><th>Source</th><th>Confidence</th><th>Хвороби</th><th>Шкідники</th><th>Warnings</th><th>Створено</th><th>Дії</th></tr></thead>
      <tbody>{''.join(rows) or "<tr><td colspan='8'>Нічого не знайдено</td></tr>"}</tbody>
    </table>
    """
    return _layout("Plant Profiles", body, user=admin_user, flash=request.query_params.get("flash"))


@router.post("/plant-profiles/create")
async def admin_plant_profile_create(
    plant_name: str = Form(...),
    category: str = Form("Овочі"),
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    name = plant_name.strip()
    category_value = (category or "Овочі").strip() or "Овочі"
    if not name:
        return _redirect("/admin/plant-profiles?flash=Назва+рослини+обов'язкова")

    data = await lookup_profile(name, category_value, db, allow_gemini=True, user_id=admin_user.id)
    profile_name = str(data.get("name") or name).strip()
    profile = await db.scalar(select(PlantProfile).where(PlantProfile.name == profile_name))
    if not profile:
        profile = await db.scalar(select(PlantProfile).where(PlantProfile.name == name))
    if not profile:
        return _redirect("/admin/plant-profiles?flash=Gemini+не+створив+профіль")
    return _redirect(f"/admin/plant-profiles/{profile.id}?flash=Профіль+готовий")


@router.get("/plant-profiles/{profile_id}", response_class=HTMLResponse)
async def admin_plant_profile_detail(
    profile_id: uuid.UUID,
    request: Request,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.scalar(select(PlantProfile).where(PlantProfile.id == profile_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Plant profile not found")
    warnings_value = "\n".join(profile.validation_warnings or [])
    field_groups = [
        ("Основне", ["name", "name_normalized", "category", "emoji", "source", "confidence"]),
        ("Сезон і Kc", ["kc_initial", "kc_mid", "kc_end", "initial_days", "development_days", "mid_season_days", "late_season_days"]),
        ("Корені та вода", ["root_depth_initial_cm", "root_depth_max_cm", "field_capacity_mm", "wilting_point_mm", "critical_depletion"]),
        ("Температури", ["t_min_growth", "t_optimal_min", "t_optimal_max", "t_max_growth", "frost_tolerance"]),
        ("Живлення і захист", ["nitrogen", "phosphorus", "potassium", "magnesium", "calcium", "sus_late_blight", "sus_powdery_mildew", "sus_downy_mildew", "sus_botrytis"]),
        ("Збір", ["days_to_harvest_min", "days_to_harvest_max"]),
    ]
    sections = []
    for title, fields in field_groups:
        inputs = []
        for field in fields:
            value = getattr(profile, field)
            input_type = "number" if field in _FLOAT_FIELDS + _INT_FIELDS else "text"
            step = "0.01" if field in _FLOAT_FIELDS else "1"
            extra = f" step='{step}'" if input_type == "number" else ""
            inputs.append(
                f"<label>{_esc(field)}<input name='{_esc(field)}' type='{input_type}' value='{_esc(value)}'{extra}></label>"
            )
        sections.append(f"<div class='section'><h3>{_esc(title)}</h3><div class='grid'>{''.join(inputs)}</div></div>")
    body = f"""
    <h1>Plant Profile: {_esc(profile.name)}</h1>
    <form method='post'>
      {''.join(sections)}
      <div class='section'>
        <h3>Опис</h3>
        <textarea name='description'>{_esc(profile.description)}</textarea>
      </div>
      <div class='section'>
        <h3>Validation Warnings</h3>
        <textarea name='validation_warnings'>{_esc(warnings_value)}</textarea>
        <div class='small'>Один warning на рядок.</div>
      </div>
      {_render_problem_catalog("Найчастіші хвороби", profile.common_diseases)}
      {_render_problem_catalog("Найчастіші шкідники", profile.common_pests)}
      {_render_treatment_guide(profile.treatment_guide)}
      <div class='actions'>
        <button type='submit'>Зберегти</button>
        <a href='/admin/plant-profiles'>Назад до списку</a>
      </div>
    </form>
    <div class='section'>
      <h3>Небезпечна зона</h3>
      <p class='muted'>Видалення прибирає тільки агрономічний профіль з каталогу Plant Profiles. Ділянки, рослини, спостереження і плани робіт користувачів не видаляються.</p>
      <form method='post' action='/admin/plant-profiles/{profile.id}/delete' onsubmit="return confirm('Остаточно видалити цей профіль рослини?')">
        <button class='danger' type='submit'>Видалити профіль рослини</button>
      </form>
    </div>
    """
    return _layout(f"Plant Profile {profile.name}", body, user=admin_user, flash=request.query_params.get("flash"))


@router.post("/plant-profiles/{profile_id}")
async def admin_plant_profile_update(
    profile_id: uuid.UUID,
    request: Request,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.scalar(select(PlantProfile).where(PlantProfile.id == profile_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Plant profile not found")
    form = await request.form()
    for field in ["name", "name_normalized", "category", "emoji", "source", "description"]:
        if field in form:
            setattr(profile, field, (form.get(field) or "").strip() or None)
    for field in _FLOAT_FIELDS:
        setattr(profile, field, _coerce_float(form.get(field), getattr(profile, field)))
    for field in _INT_FIELDS:
        setattr(profile, field, _coerce_int(form.get(field), getattr(profile, field)))
    profile.validation_warnings = [
        line.strip() for line in str(form.get("validation_warnings") or "").splitlines() if line.strip()
    ]
    await db.flush()
    return _redirect(f"/admin/plant-profiles/{profile.id}?flash=Профіль+збережено")


@router.post("/plant-profiles/{profile_id}/delete")
async def admin_plant_profile_delete(
    profile_id: uuid.UUID,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.scalar(select(PlantProfile).where(PlantProfile.id == profile_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Plant profile not found")
    await db.delete(profile)
    await db.flush()
    return _redirect("/admin/plant-profiles?flash=Профіль+видалено")


@router.get("/forum", response_class=HTMLResponse)
async def admin_forum(
    request: Request,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    topics = (
        await db.execute(
            select(ForumTopic)
            .options(selectinload(ForumTopic.author), selectinload(ForumTopic.replies))
            .order_by(ForumTopic.is_deleted.asc(), ForumTopic.is_pinned.desc(), ForumTopic.created_at.desc())
            .limit(200)
        )
    ).scalars().all()
    rows = []
    for topic in topics:
        rows.append(
            "<tr>"
            f"<td>{_badge('pinned', 'blue') if topic.is_pinned else ''} {_badge('hidden', 'red') if topic.is_deleted else ''}<div><strong>{_esc(topic.title)}</strong></div><div class='small'>{_esc(topic.body[:160])}</div></td>"
            f"<td>{_esc(topic.tag)}</td>"
            f"<td>{_esc(topic.author.email if topic.author else '—')}</td>"
            f"<td>{topic.replies_count}</td>"
            "<td class='actions'>"
            f"<form class='inline' method='post' action='/admin/forum/topics/{topic.id}/toggle-pin'><button class='secondary' type='submit'>{'Unpin' if topic.is_pinned else 'Pin'}</button></form>"
            f"<form class='inline' method='post' action='/admin/forum/topics/{topic.id}/toggle-delete'><button class='{'warn' if not topic.is_deleted else 'secondary'}' type='submit'>{'Hide' if not topic.is_deleted else 'Restore'}</button></form>"
            "</td>"
            "</tr>"
        )
    body = f"""
    <h1>Forum Moderation</h1>
    <table>
      <thead><tr><th>Тема</th><th>Tag</th><th>Автор</th><th>Replies</th><th>Дії</th></tr></thead>
      <tbody>{''.join(rows) or "<tr><td colspan='5'>Немає тем</td></tr>"}</tbody>
    </table>
    """
    return _layout("Forum Moderation", body, user=admin_user, flash=request.query_params.get("flash"))


@router.post("/forum/topics/{topic_id}/toggle-pin")
async def admin_forum_toggle_pin(
    topic_id: uuid.UUID,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    topic = await db.scalar(select(ForumTopic).where(ForumTopic.id == topic_id))
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.is_pinned = not topic.is_pinned
    await db.flush()
    return _redirect("/admin/forum?flash=Стан+pin+оновлено")


@router.post("/forum/topics/{topic_id}/toggle-delete")
async def admin_forum_toggle_delete(
    topic_id: uuid.UUID,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    topic = await db.scalar(select(ForumTopic).where(ForumTopic.id == topic_id))
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.is_deleted = not topic.is_deleted
    await db.flush()
    return _redirect("/admin/forum?flash=Статус+теми+оновлено")


@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    users = (await db.execute(select(User).order_by(User.created_at.desc()).limit(200))).scalars().all()
    rows = []
    for user in users:
        admin_badge = _badge("admin", "green") if _is_admin(user) else ""
        active_badge = _badge("active", "green") if user.is_active else _badge("inactive", "red")
        rows.append(
            "<tr>"
            f"<td>{_esc(user.email)}<div class='small'>{_esc(user.full_name)}</div></td>"
            f"<td>{admin_badge} {active_badge}</td>"
            f"<td>{_esc(user.subscription_tier)}</td>"
            f"<td>{user.plots_limit}/{user.plants_limit}</td>"
            f"<td>{_esc(user.created_at)}</td>"
            "<td class='actions'>"
            f"<form class='inline' method='post' action='/admin/users/{user.id}/toggle-admin'><button class='secondary' type='submit'>{'Зняти admin' if user.is_admin else 'Зробити admin'}</button></form>"
            f"<form class='inline' method='post' action='/admin/users/{user.id}/toggle-active'><button class='{'danger' if user.is_active else 'secondary'}' type='submit'>{'Деактивувати' if user.is_active else 'Активувати'}</button></form>"
            "</td>"
            "</tr>"
        )
    body = f"""
    <h1>Users</h1>
    <div class='section'><p class='muted'>Користувачі з `ADMIN_EMAILS` у .env теж матимуть доступ, навіть якщо `is_admin=false`.</p></div>
    <table>
      <thead><tr><th>Користувач</th><th>Статус</th><th>Tier</th><th>Ліміти</th><th>Створено</th><th>Дії</th></tr></thead>
      <tbody>{''.join(rows) or "<tr><td colspan='6'>Немає користувачів</td></tr>"}</tbody>
    </table>
    """
    return _layout("Users", body, user=admin_user, flash=request.query_params.get("flash"))


@router.post("/users/{user_id}/toggle-admin")
async def admin_toggle_user_admin(
    user_id: uuid.UUID,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_admin = not user.is_admin
    await db.flush()
    return _redirect("/admin/users?flash=Admin+status+оновлено")


@router.post("/users/{user_id}/toggle-active")
async def admin_toggle_user_active(
    user_id: uuid.UUID,
    admin_user: User = Depends(_admin_dep),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin_user.id and user.is_active:
        return _redirect("/admin/users?flash=Не+можна+деактивувати+себе")
    user.is_active = not user.is_active
    await db.flush()
    return _redirect("/admin/users?flash=Active+status+оновлено")

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


CITY_PARAMS: Dict[str, Dict[str, object]] = {
    "beijing": {
        "horizon_years": 10,
        "discount_rate": 0.12,
        "gross_margin": 0.189,
        "variable_cost_rate": 0.045,
        "tax_rate": 0.025,
        "store_residual_rate": 0.15,
        "growth": [0.9, 1.0, 1.06, 1.10, 1.10, 1.08, 1.06, 1.04, 1.03, 1.02],
        "delivery_freq": 104,
        "delivery_fixed_cost": 120.0,
        "delivery_var_cost_km": 3.5,
        "standard_store_sales_10k": 800.0,
        "standard_store_area_sqm": 650.0,
        "delivery_area_cost_base": 18.0,
        # 10-year NPV baseline for chain supermarkets (unit: 10k CNY)
        "npv_threshold_10k": 100.0,
        "dpp_threshold_years": 5.0,
        # annual revenue per sqm threshold (10k CNY / sqm / year)
        "revenue_per_sqm_threshold_10k": 1.15,
        "rent_cap_per_sqm_day": 1.8,
        "wacc": 0.12,
    },
    "hangzhou": {
        "horizon_years": 10,
        "discount_rate": 0.11,
        "gross_margin": 0.189,
        "variable_cost_rate": 0.042,
        "tax_rate": 0.025,
        "store_residual_rate": 0.15,
        "growth": [0.9, 1.0, 1.06, 1.10, 1.10, 1.08, 1.06, 1.04, 1.03, 1.02],
        "delivery_freq": 104,
        "delivery_fixed_cost": 110.0,
        "delivery_var_cost_km": 3.2,
        "standard_store_sales_10k": 800.0,
        "standard_store_area_sqm": 650.0,
        "delivery_area_cost_base": 16.5,
        "npv_threshold_10k": 105.0,
        "dpp_threshold_years": 5.0,
        "revenue_per_sqm_threshold_10k": 1.15,
        "rent_cap_per_sqm_day": 1.5,
        "wacc": 0.11,
    },
}

DEFAULT_CITY_PARAMS = {
    "horizon_years": 10,
    "discount_rate": 0.115,
    "gross_margin": 0.189,
    "variable_cost_rate": 0.043,
    "tax_rate": 0.025,
    "store_residual_rate": 0.15,
    "growth": [0.9, 1.0, 1.06, 1.10, 1.10, 1.08, 1.06, 1.04, 1.03, 1.02],
    "delivery_freq": 104,
    "delivery_fixed_cost": 115.0,
    "delivery_var_cost_km": 3.35,
    "standard_store_sales_10k": 800.0,
    "standard_store_area_sqm": 650.0,
    "delivery_area_cost_base": 17.2,
    "npv_threshold_10k": 102.0,
    "dpp_threshold_years": 5.0,
    "revenue_per_sqm_threshold_10k": 1.15,
    "rent_cap_per_sqm_day": 1.7,
    "wacc": 0.115,
}

CITY_GIS_META: Dict[str, Dict[str, object]] = {
    "beijing": {
        "label": "北京",
        "center": [39.9042, 116.4074],
        "zoom": 10.6,
        "inner_ring_radius_km": 15.5,
        "inner_ring_name": "五环内近似圈",
        "inner_ring_warning": "违反VV通行蓝区硬指标，该区域禁止蓝牌VV白天通行。",
        "logistics_belts": [
            {"name": "马驹桥物流带", "lat": 39.78, "lon": 116.57, "radius_km": 6.0},
            {"name": "大兴京南物流带", "lat": 39.73, "lon": 116.35, "radius_km": 6.2},
            {"name": "顺义空港物流带", "lat": 40.12, "lon": 116.63, "radius_km": 5.4},
        ],
    },
    "hangzhou": {
        "label": "杭州",
        "center": [30.2741, 120.1551],
        "zoom": 10.8,
        "inner_ring_radius_km": 12.0,
        "inner_ring_name": "绕城内近似圈",
        "inner_ring_warning": "违反VV通行蓝区硬指标，该区域禁止蓝牌VV白天通行。",
        "logistics_belts": [
            {"name": "余杭仁和物流带", "lat": 30.44, "lon": 120.04, "radius_km": 5.5},
            {"name": "萧山传化物流带", "lat": 30.16, "lon": 120.32, "radius_km": 5.2},
            {"name": "下沙综合物流带", "lat": 30.31, "lon": 120.37, "radius_km": 4.8},
        ],
    },
}


def normalize_city(city: str) -> str:
    city = (city or "").strip().lower()
    aliases = {
        "bj": "beijing",
        "beijing": "beijing",
        "北京": "beijing",
        "hz": "hangzhou",
        "hangzhou": "hangzhou",
        "杭州": "hangzhou",
    }
    return aliases.get(city, city)


def city_params(city: str) -> Dict[str, object]:
    key = normalize_city(city)
    base = dict(DEFAULT_CITY_PARAMS)
    base.update(CITY_PARAMS.get(key, {}))
    return base


def get_city_configs() -> Dict[str, object]:
    payload: Dict[str, object] = {}
    for key, meta in CITY_GIS_META.items():
        cp = city_params(key)
        payload[key] = {
            "city": key,
            "label": meta["label"],
            "center": list(meta["center"]),
            "zoom": meta["zoom"],
            "inner_ring_radius_km": meta["inner_ring_radius_km"],
            "inner_ring_name": meta["inner_ring_name"],
            "inner_ring_warning": meta["inner_ring_warning"],
            "logistics_belts": list(meta["logistics_belts"]),
            "params": {
                "wacc": cp["wacc"],
                "npv_threshold_10k": cp["npv_threshold_10k"],
                "dpp_threshold_years": cp["dpp_threshold_years"],
                "revenue_per_sqm_threshold_10k": cp["revenue_per_sqm_threshold_10k"],
            },
        }
    return payload


def parse_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "t", "ok", "pass", "qualified", "合格", "是"}:
        return True
    if text in {"0", "false", "no", "n", "f", "fail", "unqualified", "不合格", "否"}:
        return False
    return default


def to_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def is_valid_coord(lat: float, lon: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0 and not (lat == 0 and lon == 0)


@dataclass
class Store:
    store_id: str
    name: str
    city: str
    lat: float
    lon: float
    rf_sales_10k: float
    area_sqm: float
    initial_investment_10k: float
    annual_fixed_cost_10k: float
    is_existing: bool = False


@dataclass
class RDC:
    rdc_id: str
    name: str
    city: str
    lat: float
    lon: float
    area_sqm: float
    initial_investment_10k: float
    annual_rent_10k: float
    annual_property_10k: float
    annual_operating_10k: float
    annual_labor_10k: float
    annual_utility_10k: float
    residual_rate: float
    rent_per_sqm_day: float
    lease_years: float
    blue_access: bool
    core_travel_min: float
    clear_height_m: float
    loading_dock: bool
    can_three_temp: bool
    fire_pass: bool
    disturbance_risk: bool


@dataclass
class Stage1Result:
    store: Store
    yearly_cashflow_10k: List[float]
    npv_10k: float
    dpp_years: Optional[float]
    revenue_per_sqm_10k: float
    passed: bool
    reasons: List[str]


@dataclass
class Stage2StoreResult:
    store: Store
    base_npv_10k: float
    base_sales_10k: float
    attenuation_ratio: float
    adjusted_sales_10k: float
    adjusted_npv_10k: float
    adjusted_dpp_years: Optional[float]


@dataclass
class Assignment:
    store_id: str
    store_name: str
    store_city: str
    store_is_existing: bool
    demand_sales_10k: float
    rdc_id: str
    rdc_name: str
    rdc_city: str
    store_lat: float
    store_lon: float
    rdc_lat: float
    rdc_lon: float
    distance_km: float
    delivery_cost_pv_10k: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2.0) ** 2
    return radius * (2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))


def point_inner_ring_violation(city: str, lat: float, lon: float) -> Dict[str, object]:
    city_key = normalize_city(city)
    meta = CITY_GIS_META.get(city_key)
    if not meta or not is_valid_coord(lat, lon):
        return {"city": city_key, "violation": False, "distance_to_center_km": None}

    center_lat, center_lon = float(meta["center"][0]), float(meta["center"][1])
    radius = float(meta["inner_ring_radius_km"])
    distance = haversine_km(lat, lon, center_lat, center_lon)
    violation = distance <= radius
    return {
        "city": city_key,
        "violation": violation,
        "distance_to_center_km": round(distance, 4),
        "inner_ring_radius_km": radius,
        "message": meta["inner_ring_warning"] if violation else "ok",
    }


def parse_stores(records: Iterable[Dict[str, object]]) -> List[Store]:
    out: List[Store] = []
    for row in records:
        store_id = str(row.get("store_id") or row.get("id") or "").strip()
        if not store_id:
            continue

        city = normalize_city(str(row.get("city") or "beijing"))
        lat = to_float(row.get("lat"))
        lon = to_float(row.get("lon"))
        out.append(
            Store(
                store_id=store_id,
                name=str(row.get("name") or store_id),
                city=city,
                lat=lat,
                lon=lon,
                rf_sales_10k=to_float(row.get("rf_sales_10k"), to_float(row.get("annual_sales_10k"), 0.0)),
                area_sqm=to_float(row.get("area_sqm"), 100.0),
                initial_investment_10k=to_float(row.get("initial_investment_10k"), 0.0),
                annual_fixed_cost_10k=to_float(row.get("annual_fixed_cost_10k"), 0.0),
                is_existing=parse_bool(row.get("is_existing"), False),
            )
        )
    return out


def parse_rdcs(records: Iterable[Dict[str, object]]) -> List[RDC]:
    out: List[RDC] = []
    for row in records:
        rdc_id = str(row.get("rdc_id") or row.get("id") or "").strip()
        if not rdc_id:
            continue

        city = normalize_city(str(row.get("city") or "beijing"))
        out.append(
            RDC(
                rdc_id=rdc_id,
                name=str(row.get("name") or rdc_id),
                city=city,
                lat=to_float(row.get("lat")),
                lon=to_float(row.get("lon")),
                area_sqm=to_float(row.get("area_sqm"), 10000.0),
                initial_investment_10k=to_float(row.get("initial_investment_10k"), 0.0),
                annual_rent_10k=to_float(row.get("annual_rent_10k"), 0.0),
                annual_property_10k=to_float(row.get("annual_property_10k"), 0.0),
                annual_operating_10k=to_float(row.get("annual_operating_10k"), 0.0),
                annual_labor_10k=to_float(row.get("annual_labor_10k"), 0.0),
                annual_utility_10k=to_float(row.get("annual_utility_10k"), 0.0),
                residual_rate=to_float(row.get("residual_rate"), 0.25),
                rent_per_sqm_day=to_float(row.get("rent_per_sqm_day"), 0.0),
                lease_years=to_float(row.get("lease_years"), 0.0),
                blue_access=parse_bool(row.get("blue_access"), False),
                core_travel_min=to_float(row.get("core_travel_min"), 999.0),
                clear_height_m=to_float(row.get("clear_height_m"), 0.0),
                loading_dock=parse_bool(row.get("loading_dock"), False),
                can_three_temp=parse_bool(row.get("can_three_temp"), False),
                fire_pass=parse_bool(row.get("fire_pass"), False),
                disturbance_risk=parse_bool(row.get("disturbance_risk"), False),
            )
        )
    return out


def parse_distance_matrix(records: Iterable[Dict[str, object]]) -> Dict[Tuple[str, str], float]:
    matrix: Dict[Tuple[str, str], float] = {}
    for row in records:
        rdc_id = str(row.get("rdc_id") or "").strip()
        store_id = str(row.get("store_id") or "").strip()
        if not rdc_id or not store_id:
            continue
        matrix[(rdc_id, store_id)] = to_float(row.get("distance_km"), math.inf)
    return matrix


def compute_dpp(discounted_cashflows: Sequence[float], initial_investment_10k: float) -> Optional[float]:
    cumulative = -initial_investment_10k
    for year, cashflow in enumerate(discounted_cashflows, start=1):
        prev = cumulative
        cumulative += cashflow
        if cumulative >= 0:
            if cashflow <= 0:
                return float(year)
            ratio = (0.0 - prev) / cashflow
            return float(year - 1 + max(0.0, min(1.0, ratio)))
    return None


def resolve_city_thresholds(
    city: str,
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> Tuple[float, float, float]:
    cp = city_params(city)
    npv_threshold = float(cp["npv_threshold_10k"])
    dpp_threshold = float(cp["dpp_threshold_years"])
    rev_threshold = float(cp["revenue_per_sqm_threshold_10k"])

    if threshold_overrides:
        ov = threshold_overrides.get(normalize_city(city))
        if ov:
            npv_threshold = float(ov.get("npv_threshold_10k", npv_threshold))
            dpp_threshold = float(ov.get("dpp_threshold_years", dpp_threshold))
            rev_threshold = float(ov.get("revenue_per_sqm_threshold_10k", rev_threshold))

    return npv_threshold, dpp_threshold, rev_threshold


def evaluate_stage1(
    stores: Sequence[Store],
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> List[Stage1Result]:
    results: List[Stage1Result] = []
    for store in stores:
        if store.is_existing:
            continue

        cp = city_params(store.city)
        years = int(cp["horizon_years"])
        growth: List[float] = list(cp["growth"])[:years]
        discount_rate = float(cp["discount_rate"])
        gross_margin = float(cp["gross_margin"])
        variable_rate = float(cp["variable_cost_rate"])
        tax_rate = float(cp["tax_rate"])
        residual_rate = float(cp["store_residual_rate"])

        npv_threshold, dpp_threshold, rev_threshold = resolve_city_thresholds(
            store.city,
            threshold_overrides=threshold_overrides,
        )

        yearly_cashflows: List[float] = []
        discounted: List[float] = []
        for idx, g in enumerate(growth, start=1):
            revenue_10k = store.rf_sales_10k * g
            gross_profit_10k = revenue_10k * gross_margin
            variable_cost_10k = revenue_10k * variable_rate
            operating_profit_10k = gross_profit_10k - variable_cost_10k - store.annual_fixed_cost_10k
            tax_10k = max(0.0, operating_profit_10k) * tax_rate
            cashflow_10k = operating_profit_10k - tax_10k
            if idx == years:
                cashflow_10k += store.initial_investment_10k * residual_rate
            yearly_cashflows.append(cashflow_10k)
            discounted.append(cashflow_10k / ((1.0 + discount_rate) ** idx))

        npv_10k = -store.initial_investment_10k + sum(discounted)
        dpp = compute_dpp(discounted, store.initial_investment_10k)

        revenue_per_sqm = 0.0
        if store.area_sqm > 0:
            revenue_per_sqm = store.rf_sales_10k / store.area_sqm

        reasons: List[str] = []
        passed = True
        if npv_10k < npv_threshold:
            passed = False
            reasons.append(f"NPV below threshold ({npv_10k:.2f} < {npv_threshold:.2f})")
        if dpp is None or dpp > dpp_threshold:
            passed = False
            reasons.append(f"DPP exceeds threshold ({dpp_threshold:.2f} years)")
        if revenue_per_sqm < rev_threshold:
            passed = False
            reasons.append(f"Revenue per sqm below threshold ({revenue_per_sqm:.2f} < {rev_threshold:.2f})")

        results.append(
            Stage1Result(
                store=store,
                yearly_cashflow_10k=yearly_cashflows,
                npv_10k=npv_10k,
                dpp_years=dpp,
                revenue_per_sqm_10k=revenue_per_sqm,
                passed=passed,
                reasons=reasons,
            )
        )
    return results


def pairwise_distance_km(stores: Sequence[Stage1Result]) -> Dict[Tuple[str, str], float]:
    dist: Dict[Tuple[str, str], float] = {}
    for i, a in enumerate(stores):
        for b in stores[i + 1 :]:
            key1 = (a.store.store_id, b.store.store_id)
            key2 = (b.store.store_id, a.store.store_id)
            if normalize_city(a.store.city) != normalize_city(b.store.city):
                dist[key1] = math.inf
                dist[key2] = math.inf
                continue
            d = haversine_km(a.store.lat, a.store.lon, b.store.lat, b.store.lon)
            dist[key1] = d
            dist[key2] = d
    return dist


def attenuation_for_pair(distance_km: float) -> float:
    # Hard conflict zone: d < 280m
    # Smooth transition 280-320m: penalty linearly drops from 1.0 -> 0.35
    # Soft zone 320-500m: penalty linearly drops from 0.35 -> 0
    # Beyond 500m: no penalty
    if distance_km < 0.28:
        return 1.0
    if distance_km < 0.32:
        t = (distance_km - 0.28) / 0.04
        return 1.0 + t * (0.35 - 1.0)
    if distance_km < 0.5:
        scaled = (0.5 - distance_km) / 0.18
        return 0.35 * max(0.0, min(1.0, scaled))
    return 0.0


def _recompute_adjusted_cashflows(base_result: Stage1Result, attenuation_ratio: float) -> Tuple[List[float], float]:
    """
    Attenuate operating cashflows by `attenuation_ratio` while keeping residual
    value untouched (residual is asset recovery, not demand-driven).
    Returns (discounted_cashflows, initial_investment).
    """
    cp = city_params(base_result.store.city)
    discount_rate = float(cp["discount_rate"])
    years = len(base_result.yearly_cashflow_10k)
    residual = base_result.store.initial_investment_10k * float(cp["store_residual_rate"])

    discounted: List[float] = []
    for idx, cf in enumerate(base_result.yearly_cashflow_10k, start=1):
        if idx == years:
            adjusted_cf = (cf - residual) * attenuation_ratio + residual
        else:
            adjusted_cf = cf * attenuation_ratio
        discounted.append(adjusted_cf / ((1.0 + discount_rate) ** idx))
    return discounted, base_result.store.initial_investment_10k


def recompute_adjusted_dpp(base_result: Stage1Result, attenuation_ratio: float) -> Optional[float]:
    discounted, initial = _recompute_adjusted_cashflows(base_result, attenuation_ratio)
    return compute_dpp(discounted, initial)


def recompute_adjusted_npv(base_result: Stage1Result, attenuation_ratio: float) -> float:
    discounted, initial = _recompute_adjusted_cashflows(base_result, attenuation_ratio)
    return -initial + sum(discounted)


def optimize_stage2(
    stage1_results: Sequence[Stage1Result],
    max_new_stores: int = 8,
) -> Dict[str, object]:
    candidates = [r for r in stage1_results if r.passed]
    if not candidates:
        return {
            "selected": [],
            "total_adjusted_npv_10k": 0.0,
            "total_base_npv_10k": 0.0,
            "total_investment_10k": 0.0,
            "distance_alerts": [],
        }

    max_new_stores = max(0, min(max_new_stores, len(candidates)))
    dist = pairwise_distance_km(candidates)

    conflict_pairs = set()
    penalty_pairs: Dict[Tuple[str, str], float] = {}
    for a in candidates:
        for b in candidates:
            if a.store.store_id >= b.store.store_id:
                continue
            if normalize_city(a.store.city) != normalize_city(b.store.city):
                continue
            d = dist.get((a.store.store_id, b.store.store_id), math.inf)
            pen = attenuation_for_pair(d)
            if pen >= 1.0:
                conflict_pairs.add((a.store.store_id, b.store.store_id))
            elif pen > 0.0:
                penalty_pairs[(a.store.store_id, b.store.store_id)] = pen

    candidate_by_id = {c.store.store_id: c for c in candidates}
    ids = [c.store.store_id for c in candidates]

    best_score = -math.inf
    best_bundle: Optional[List[Stage2StoreResult]] = None

    def has_conflict(combo_ids: Sequence[str]) -> bool:
        pool = set(combo_ids)
        for a, b in conflict_pairs:
            if a in pool and b in pool:
                return True
        return False

    for size in range(0, max_new_stores + 1):
        for combo in itertools.combinations(ids, size):
            if has_conflict(combo):
                continue

            combo_set = set(combo)
            score = 0.0
            bundle: List[Stage2StoreResult] = []

            for sid in combo:
                base = candidate_by_id[sid]
                penalty = 0.0
                for oid in combo_set:
                    if oid == sid:
                        continue
                    other = candidate_by_id[oid]
                    if normalize_city(other.store.city) != normalize_city(base.store.city):
                        continue
                    key = tuple(sorted((sid, oid)))
                    penalty += penalty_pairs.get(key, 0.0)

                penalty = min(0.45, penalty)
                attenuation_ratio = max(0.0, 1.0 - penalty)
                adjusted_sales = base.store.rf_sales_10k * attenuation_ratio
                # Only operating cashflows are attenuated; initial capex and
                # residual value are invariant to neighboring cannibalization.
                adjusted_npv = recompute_adjusted_npv(base, attenuation_ratio)
                adjusted_dpp = recompute_adjusted_dpp(base, attenuation_ratio)

                score += adjusted_npv
                bundle.append(
                    Stage2StoreResult(
                        store=base.store,
                        base_npv_10k=base.npv_10k,
                        base_sales_10k=base.store.rf_sales_10k,
                        attenuation_ratio=attenuation_ratio,
                        adjusted_sales_10k=adjusted_sales,
                        adjusted_npv_10k=adjusted_npv,
                        adjusted_dpp_years=adjusted_dpp,
                    )
                )

            if score > best_score:
                best_score = score
                best_bundle = bundle

    if best_bundle is None:
        best_bundle = []
        best_score = 0.0

    distance_alerts = []
    for a, b in conflict_pairs:
        da = candidate_by_id[a]
        db = candidate_by_id[b]
        d = dist.get((a, b), 0.0)
        distance_alerts.append(
            {
                "store_a": a,
                "store_b": b,
                "name_a": da.store.name,
                "name_b": db.store.name,
                "city": da.store.city,
                "distance_m": round(d * 1000.0, 1),
                "rule": "distance below 280m, cannot open together",
            }
        )

    total_base = sum(item.base_npv_10k for item in best_bundle)
    total_investment = sum(item.store.initial_investment_10k for item in best_bundle)

    return {
        "selected": [
            {
                "store_id": item.store.store_id,
                "name": item.store.name,
                "city": item.store.city,
                "base_sales_10k": round(item.base_sales_10k, 4),
                "attenuation_ratio": round(item.attenuation_ratio, 4),
                "adjusted_sales_10k": round(item.adjusted_sales_10k, 4),
                "base_npv_10k": round(item.base_npv_10k, 4),
                "adjusted_npv_10k": round(item.adjusted_npv_10k, 4),
                "adjusted_dpp_years": round(item.adjusted_dpp_years, 4) if item.adjusted_dpp_years else None,
                "lat": item.store.lat,
                "lon": item.store.lon,
                "radius_300_m": 300,
                "radius_500_m": 500,
            }
            for item in sorted(best_bundle, key=lambda x: x.adjusted_npv_10k, reverse=True)
        ],
        "total_adjusted_npv_10k": round(best_score, 4),
        "total_base_npv_10k": round(total_base, 4),
        "total_investment_10k": round(total_investment, 4),
        "distance_alerts": sorted(distance_alerts, key=lambda x: x["distance_m"]),
    }


def rdc_lifecycle_cost_10k(rdc: RDC) -> float:
    """
    Present value of RDC 5-year lifecycle cost:
        CapEx + PV(annual OpEx over horizon) - PV(residual at end-of-life)
    Using the same horizon_years and discount_rate as stores for dimensional
    consistency with `delivery_cost_pv_10k`.
    """
    cp = city_params(rdc.city)
    discount_rate = float(cp["discount_rate"])
    years = int(cp["horizon_years"])

    annual = (
        rdc.annual_rent_10k
        + rdc.annual_property_10k
        + rdc.annual_operating_10k
        + rdc.annual_labor_10k
        + rdc.annual_utility_10k
    )
    pv_annual = 0.0
    for y in range(1, years + 1):
        pv_annual += annual / ((1.0 + discount_rate) ** y)

    residual_nominal = rdc.initial_investment_10k * rdc.residual_rate
    pv_residual = residual_nominal / ((1.0 + discount_rate) ** years)

    return rdc.initial_investment_10k + pv_annual - pv_residual


def rdc_eligibility(rdc: RDC) -> Tuple[bool, List[str]]:
    cp = city_params(rdc.city)
    rent_cap = float(cp["rent_cap_per_sqm_day"])

    reasons: List[str] = []
    if not rdc.blue_access:
        reasons.append("[BLUE_ACCESS] blue plate truck access requirement not met")
    if rdc.core_travel_min > 30.0:
        reasons.append(f"[TRAVEL_TIME] core travel time above 30 min ({rdc.core_travel_min:.1f})")
    if rdc.clear_height_m < 6.0:
        reasons.append(f"[CLEAR_HEIGHT] clear height below 6m ({rdc.clear_height_m:.1f})")
    if not rdc.loading_dock:
        reasons.append("[LOADING_DOCK] missing loading dock")
    if not rdc.can_three_temp:
        reasons.append("[THREE_TEMP] cannot support three-temperature warehouse")
    if not rdc.fire_pass:
        reasons.append("[FIRE_SAFETY] fire safety requirement not met")
    if rdc.disturbance_risk:
        reasons.append("[DISTURBANCE] disturbance risk near residential/school/hospital")
    if rdc.rent_per_sqm_day > rent_cap:
        reasons.append(f"[RENT_CAP] rent exceeds city cap ({rdc.rent_per_sqm_day:.2f}>{rent_cap:.2f})")
    if rdc.lease_years < 5.0:
        reasons.append(f"[LEASE_TERM] remaining lease below 5 years ({rdc.lease_years:.1f})")

    # GIS hard warning: inner-ring placements are forbidden by blue-plate policy.
    rule = point_inner_ring_violation(rdc.city, rdc.lat, rdc.lon)
    if rule.get("violation"):
        reasons.append("[INNER_RING] RDC located inside inner-ring restricted zone")

    return (len(reasons) == 0), reasons


def distance_lookup_km(
    rdc: RDC,
    store: Store,
    matrix: Dict[Tuple[str, str], float],
) -> float:
    if normalize_city(rdc.city) != normalize_city(store.city):
        return math.inf

    key = (rdc.rdc_id, store.store_id)
    if key in matrix and math.isfinite(matrix[key]):
        return matrix[key]
    return haversine_km(rdc.lat, rdc.lon, store.lat, store.lon)


def delivery_cost_pv_10k(distance_km: float, sales_10k: float, area_sqm: float, city: str) -> float:
    cp = city_params(city)
    growth = list(cp["growth"])
    discount_rate = float(cp["discount_rate"])
    delivery_freq = float(cp["delivery_freq"])
    fixed_cost = float(cp["delivery_fixed_cost"])
    variable_cost = float(cp["delivery_var_cost_km"])
    std_sales = float(cp["standard_store_sales_10k"])
    std_area = float(cp.get("standard_store_area_sqm", 650.0))
    area_cost_base = float(cp.get("delivery_area_cost_base", 17.0))

    if std_sales <= 0.0:
        sales_weight = 1.0
    else:
        sales_weight = max(0.08, sales_10k / std_sales)

    if std_area <= 0.0:
        area_weight = 1.0
    else:
        area_weight = max(0.25, area_sqm / std_area)

    # A larger store typically requires higher drop volume and handling effort.
    # Use area as a moderate elasticity on both trip frequency and per-trip handling cost.
    demand_weight = max(0.08, 0.78 * sales_weight + 0.22 * area_weight)
    area_handling_cost = area_cost_base * math.sqrt(area_weight)

    trip_cost_yuan = fixed_cost + variable_cost * distance_km + area_handling_cost
    pv_yuan = 0.0
    for year, g in enumerate(growth, start=1):
        annual_yuan = delivery_freq * demand_weight * trip_cost_yuan * g
        pv_yuan += annual_yuan / ((1.0 + discount_rate) ** year)
    return pv_yuan / 10000.0


def optimize_stage3(
    stores: Sequence[Store],
    selected_new_store_rows: Sequence[Dict[str, object]],
    rdcs: Sequence[RDC],
    distance_matrix: Dict[Tuple[str, str], float],
    p_values: Sequence[int],
) -> Dict[str, object]:
    adjusted_sales_by_store: Dict[str, float] = {
        str(r.get("store_id")): to_float(r.get("adjusted_sales_10k"), to_float(r.get("base_sales_10k"), 0.0))
        for r in selected_new_store_rows
    }
    existing_sales_by_store = _build_existing_sales_proxy_map(stores)
    # Stage-3 network contains selected new stores + existing stores.
    full_network_stores: List[Store] = _build_network_stores(
        stores,
        adjusted_sales_by_store,
        existing_sales_by_store=existing_sales_by_store,
    )

    eligible_rdcs: List[Tuple[RDC, float]] = []
    rejected_rdcs: List[Dict[str, object]] = []

    for rdc in rdcs:
        ok, reasons = rdc_eligibility(rdc)
        lifecycle = rdc_lifecycle_cost_10k(rdc)
        row = {
            "rdc_id": rdc.rdc_id,
            "name": rdc.name,
            "city": rdc.city,
            "lat": rdc.lat,
            "lon": rdc.lon,
            "lifecycle_cost_10k": round(lifecycle, 4),
            "rent_per_sqm_day": rdc.rent_per_sqm_day,
        }
        if ok:
            eligible_rdcs.append((rdc, lifecycle))
        else:
            row["reasons"] = reasons
            rejected_rdcs.append(row)

    scenarios: List[Dict[str, object]] = []
    if not full_network_stores or not eligible_rdcs:
        return {
            "eligible_rdcs": [
                {
                    "rdc_id": r.rdc_id,
                    "name": r.name,
                    "city": r.city,
                    "lat": r.lat,
                    "lon": r.lon,
                    "lifecycle_cost_10k": round(c, 4),
                }
                for r, c in eligible_rdcs
            ],
            "rejected_rdcs": rejected_rdcs,
            "network_stores": [asdict(s) for s in full_network_stores],
            "scenarios": [],
            "best_scenario": None,
        }

    valid_p_values = sorted({p for p in p_values if p > 0})
    for p in valid_p_values:
        if p > len(eligible_rdcs):
            continue

        best_cost = math.inf
        best_plan: Optional[Dict[str, object]] = None

        for combo in itertools.combinations(eligible_rdcs, p):
            open_rdcs = [x[0] for x in combo]
            rdc_cost = sum(x[1] for x in combo)
            delivery_total = 0.0
            assignments: List[Assignment] = []
            unassigned: List[Dict[str, object]] = []

            for store in full_network_stores:
                same_city_rdcs = [r for r in open_rdcs if normalize_city(r.city) == normalize_city(store.city)]
                if not same_city_rdcs:
                    unassigned.append(
                        {
                            "store_id": store.store_id,
                            "store_name": store.name,
                            "city": store.city,
                            "reason": "no opened RDC in same city",
                        }
                    )
                    continue

                best_rdc = None
                best_distance = math.inf
                best_delivery = math.inf
                for rdc in same_city_rdcs:
                    distance_km = distance_lookup_km(rdc, store, distance_matrix)
                    if not math.isfinite(distance_km):
                        continue
                    delivery_cost = delivery_cost_pv_10k(distance_km, store.rf_sales_10k, store.area_sqm, store.city)
                    if delivery_cost < best_delivery:
                        best_rdc = rdc
                        best_distance = distance_km
                        best_delivery = delivery_cost

                if best_rdc is None:
                    unassigned.append(
                        {
                            "store_id": store.store_id,
                            "store_name": store.name,
                            "city": store.city,
                            "reason": "distance lookup failed",
                        }
                    )
                    continue

                delivery_total += best_delivery
                assignments.append(
                    Assignment(
                        store_id=store.store_id,
                        store_name=store.name,
                        store_city=store.city,
                        store_is_existing=store.is_existing,
                        demand_sales_10k=store.rf_sales_10k,
                        rdc_id=best_rdc.rdc_id,
                        rdc_name=best_rdc.name,
                        rdc_city=best_rdc.city,
                        store_lat=store.lat,
                        store_lon=store.lon,
                        rdc_lat=best_rdc.lat,
                        rdc_lon=best_rdc.lon,
                        distance_km=best_distance,
                        delivery_cost_pv_10k=best_delivery,
                    )
                )

            if unassigned:
                continue

            total_cost = rdc_cost + delivery_total
            if total_cost < best_cost:
                best_cost = total_cost
                best_plan = {
                    "p": p,
                    "rdc_cost_10k": rdc_cost,
                    "delivery_cost_10k": delivery_total,
                    "total_cost_10k": total_cost,
                    "open_rdcs": [
                        {
                            "rdc_id": r.rdc_id,
                            "name": r.name,
                            "city": r.city,
                            "lat": r.lat,
                            "lon": r.lon,
                            "lifecycle_cost_10k": round(rdc_lifecycle_cost_10k(r), 4),
                        }
                        for r in open_rdcs
                    ],
                    "assignments": assignments,
                }

        if best_plan is None:
            continue

        assignments = best_plan["assignments"]
        total_weight = sum(a.demand_sales_10k for a in assignments) or 1.0
        avg_distance = sum(a.distance_km * a.demand_sales_10k for a in assignments) / total_weight

        # ROI uses PV of gross profit (revenue * gross_margin) rather than raw
        # revenue, so it is dimensionally comparable with the PV-based total cost.
        total_gross_profit_pv_10k = 0.0
        for store in full_network_stores:
            cp = city_params(store.city)
            growth = list(cp["growth"])
            discount_rate = float(cp["discount_rate"])
            gross_margin = float(cp["gross_margin"])
            for year, g in enumerate(growth, start=1):
                total_gross_profit_pv_10k += (
                    store.rf_sales_10k * g * gross_margin / ((1.0 + discount_rate) ** year)
                )

        roi = 0.0
        if best_plan["total_cost_10k"] > 0:
            roi = (total_gross_profit_pv_10k - best_plan["total_cost_10k"]) / best_plan["total_cost_10k"]

        city_breakdown: Dict[str, Dict[str, float]] = {}
        for a in assignments:
            c = a.store_city
            city_breakdown.setdefault(c, {"delivery_cost_10k": 0.0, "distance_weight": 0.0, "sales_weight": 0.0, "stores": 0})
            city_breakdown[c]["delivery_cost_10k"] += a.delivery_cost_pv_10k
            city_breakdown[c]["distance_weight"] += a.distance_km * a.demand_sales_10k
            city_breakdown[c]["sales_weight"] += a.demand_sales_10k
            city_breakdown[c]["stores"] += 1

        for c in city_breakdown:
            sw = city_breakdown[c]["sales_weight"] or 1.0
            city_breakdown[c]["avg_distance_km"] = city_breakdown[c]["distance_weight"] / sw
            city_breakdown[c]["delivery_cost_10k"] = round(city_breakdown[c]["delivery_cost_10k"], 4)
            city_breakdown[c]["avg_distance_km"] = round(city_breakdown[c]["avg_distance_km"], 4)
            city_breakdown[c]["stores"] = int(city_breakdown[c]["stores"])
            del city_breakdown[c]["distance_weight"]
            del city_breakdown[c]["sales_weight"]

        scenarios.append(
            {
                "p": best_plan["p"],
                "rdc_cost_10k": round(best_plan["rdc_cost_10k"], 4),
                "delivery_cost_10k": round(best_plan["delivery_cost_10k"], 4),
                "total_cost_10k": round(best_plan["total_cost_10k"], 4),
                "avg_distance_km": round(avg_distance, 4),
                "roi": round(roi, 4),
                "open_rdcs": best_plan["open_rdcs"],
                "cost_components": {
                    "rdc_cost_10k": round(best_plan["rdc_cost_10k"], 4),
                    "delivery_cost_10k": round(best_plan["delivery_cost_10k"], 4),
                },
                "city_breakdown": city_breakdown,
                "assignments": [
                    {
                        "store_id": a.store_id,
                        "store_name": a.store_name,
                        "store_city": a.store_city,
                        "store_is_existing": a.store_is_existing,
                        "store_lat": a.store_lat,
                        "store_lon": a.store_lon,
                        "demand_sales_10k": round(a.demand_sales_10k, 4),
                        "rdc_id": a.rdc_id,
                        "rdc_name": a.rdc_name,
                        "rdc_city": a.rdc_city,
                        "rdc_lat": a.rdc_lat,
                        "rdc_lon": a.rdc_lon,
                        "distance_km": round(a.distance_km, 4),
                        "delivery_cost_pv_10k": round(a.delivery_cost_pv_10k, 4),
                    }
                    for a in sorted(best_plan["assignments"], key=lambda x: x.delivery_cost_pv_10k, reverse=True)
                ],
            }
        )

    scenarios = sorted(scenarios, key=lambda x: x["total_cost_10k"])
    best_scenario = scenarios[0] if scenarios else None

    return {
        "eligible_rdcs": [
            {
                "rdc_id": r.rdc_id,
                "name": r.name,
                "city": r.city,
                "lat": r.lat,
                "lon": r.lon,
                "lifecycle_cost_10k": round(c, 4),
            }
            for r, c in sorted(eligible_rdcs, key=lambda x: x[1])
        ],
        "rejected_rdcs": rejected_rdcs,
        "network_stores": [asdict(s) for s in full_network_stores],
        "scenarios": scenarios,
        "best_scenario": best_scenario,
    }


def _serialize_stage2_item(item: Stage2StoreResult) -> Dict[str, object]:
    return {
        "store_id": item.store.store_id,
        "name": item.store.name,
        "city": item.store.city,
        "base_sales_10k": round(item.base_sales_10k, 4),
        "attenuation_ratio": round(item.attenuation_ratio, 4),
        "adjusted_sales_10k": round(item.adjusted_sales_10k, 4),
        "base_npv_10k": round(item.base_npv_10k, 4),
        "adjusted_npv_10k": round(item.adjusted_npv_10k, 4),
        "adjusted_dpp_years": round(item.adjusted_dpp_years, 4) if item.adjusted_dpp_years is not None else None,
        "lat": item.store.lat,
        "lon": item.store.lon,
        "radius_300_m": 300,
        "radius_500_m": 500,
    }


def _comb_count_upto(n: int, k: int) -> int:
    if n <= 0 or k < 0:
        return 0
    k = min(k, n)
    total = 0
    for i in range(0, k + 1):
        total += math.comb(n, i)
    return total


def _build_stage2_bundle_payload(
    combo_ids: Sequence[str],
    candidate_by_id: Dict[str, Stage1Result],
    penalty_pairs: Dict[Tuple[str, str], float],
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> Optional[Dict[str, object]]:
    combo_list = list(combo_ids)
    combo_set = set(combo_list)
    penalties_by_sid: Dict[str, float] = {sid: 0.0 for sid in combo_list}

    # Accumulate pairwise attenuation penalty for each selected store.
    for sid in combo_list:
        for oid in combo_set:
            if oid == sid:
                continue
            key = tuple(sorted((sid, oid)))
            penalties_by_sid[sid] += penalty_pairs.get(key, 0.0)

    bundle_items: List[Stage2StoreResult] = []
    adjusted_sales_by_store: Dict[str, float] = {}
    total_adjusted_npv = 0.0

    for sid in combo_list:
        base = candidate_by_id[sid]
        penalty = min(0.45, penalties_by_sid.get(sid, 0.0))
        attenuation_ratio = max(0.0, 1.0 - penalty)
        adjusted_sales = base.store.rf_sales_10k * attenuation_ratio
        adjusted_npv = recompute_adjusted_npv(base, attenuation_ratio)
        adjusted_dpp = recompute_adjusted_dpp(base, attenuation_ratio)
        npv_threshold, dpp_threshold, _ = resolve_city_thresholds(
            base.store.city,
            threshold_overrides=threshold_overrides,
        )

        # Stage-2 hard financial gate:
        # only keep stores whose post-cannibalization economics still pass.
        if adjusted_npv < npv_threshold:
            return None
        if adjusted_dpp is None or adjusted_dpp > dpp_threshold:
            return None

        total_adjusted_npv += adjusted_npv
        adjusted_sales_by_store[sid] = adjusted_sales
        bundle_items.append(
            Stage2StoreResult(
                store=base.store,
                base_npv_10k=base.npv_10k,
                base_sales_10k=base.store.rf_sales_10k,
                attenuation_ratio=attenuation_ratio,
                adjusted_sales_10k=adjusted_sales,
                adjusted_npv_10k=adjusted_npv,
                adjusted_dpp_years=adjusted_dpp,
            )
        )

    ordered_items = sorted(bundle_items, key=lambda x: x.adjusted_npv_10k, reverse=True)
    return {
        "selected": [_serialize_stage2_item(item) for item in ordered_items],
        "adjusted_sales_by_store": adjusted_sales_by_store,
        "total_adjusted_npv_10k": float(total_adjusted_npv),
        "total_base_npv_10k": float(sum(item.base_npv_10k for item in ordered_items)),
        "total_investment_10k": float(sum(item.store.initial_investment_10k for item in ordered_items)),
    }


def _enumerate_stage2_bundles_exact(
    ids: Sequence[str],
    candidate_by_id: Dict[str, Stage1Result],
    conflict_pairs: set[Tuple[str, str]],
    penalty_pairs: Dict[Tuple[str, str], float],
    max_new_stores: int,
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> Tuple[List[Dict[str, object]], int]:
    def has_conflict(combo_ids: Sequence[str]) -> bool:
        pool = set(combo_ids)
        for a, b in conflict_pairs:
            if a in pool and b in pool:
                return True
        return False

    bundles: List[Dict[str, object]] = []
    evaluated = 0
    for size in range(0, max_new_stores + 1):
        for combo in itertools.combinations(ids, size):
            if has_conflict(combo):
                continue
            evaluated += 1
            payload = _build_stage2_bundle_payload(
                combo,
                candidate_by_id,
                penalty_pairs,
                threshold_overrides=threshold_overrides,
            )
            if payload is None:
                continue
            bundles.append(payload)
    return bundles, evaluated


def _enumerate_stage2_bundles_beam(
    ids: Sequence[str],
    candidate_by_id: Dict[str, Stage1Result],
    conflict_pairs: set[Tuple[str, str]],
    penalty_pairs: Dict[Tuple[str, str], float],
    max_new_stores: int,
    beam_width: int,
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> Tuple[List[Dict[str, object]], int]:
    ranked_ids = sorted(
        ids,
        key=lambda sid: candidate_by_id[sid].npv_10k,
        reverse=True,
    )
    n = len(ranked_ids)
    id_by_idx = ranked_ids

    conflict_adj: Dict[str, set[str]] = {sid: set() for sid in ranked_ids}
    for a, b in conflict_pairs:
        conflict_adj.setdefault(a, set()).add(b)
        conflict_adj.setdefault(b, set()).add(a)

    payload_cache: Dict[Tuple[str, ...], Optional[Dict[str, object]]] = {}
    seen_combos: set[Tuple[str, ...]] = set()
    bundles: List[Dict[str, object]] = []
    evaluated = 0

    # Always include empty bundle.
    empty_payload = _build_stage2_bundle_payload(
        [],
        candidate_by_id,
        penalty_pairs,
        threshold_overrides=threshold_overrides,
    )
    if empty_payload is None:
        empty_payload = {
            "selected": [],
            "adjusted_sales_by_store": {},
            "total_adjusted_npv_10k": 0.0,
            "total_base_npv_10k": 0.0,
            "total_investment_10k": 0.0,
        }
    payload_cache[tuple()] = empty_payload
    seen_combos.add(tuple())
    bundles.append(empty_payload)

    states: List[Tuple[int, ...]] = [tuple()]
    for _size in range(1, max_new_stores + 1):
        candidates_for_next: List[Tuple[float, Tuple[int, ...], Tuple[str, ...]]] = []
        for state in states:
            last_idx = state[-1] if state else -1
            current_ids = [id_by_idx[i] for i in state]
            current_set = set(current_ids)

            for next_idx in range(last_idx + 1, n):
                sid = id_by_idx[next_idx]
                # Early conflict prune via adjacency set.
                if any(x in conflict_adj.get(sid, set()) for x in current_set):
                    continue

                new_state = state + (next_idx,)
                new_ids = tuple(sorted(current_ids + [sid]))
                if new_ids in payload_cache:
                    payload = payload_cache[new_ids]
                else:
                    payload = _build_stage2_bundle_payload(
                        new_ids,
                        candidate_by_id,
                        penalty_pairs,
                        threshold_overrides=threshold_overrides,
                    )
                    payload_cache[new_ids] = payload
                    evaluated += 1
                if payload is None:
                    continue
                score = float(payload.get("total_adjusted_npv_10k", 0.0))
                candidates_for_next.append((score, new_state, new_ids))

        if not candidates_for_next:
            break

        candidates_for_next.sort(key=lambda x: x[0], reverse=True)

        next_states: List[Tuple[int, ...]] = []
        next_seen_ids: set[Tuple[str, ...]] = set()
        for _score, st, combo_ids in candidates_for_next:
            if combo_ids in next_seen_ids:
                continue
            next_seen_ids.add(combo_ids)
            next_states.append(st)
            if combo_ids not in seen_combos:
                bundles.append(payload_cache[combo_ids])
                seen_combos.add(combo_ids)
            if len(next_states) >= beam_width:
                break

        states = next_states
        if not states:
            break

    return bundles, evaluated


def _enumerate_stage2_bundles(
    stage1_results: Sequence[Stage1Result],
    max_new_stores: int = 8,
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, object]:
    candidates = [r for r in stage1_results if r.passed]
    if not candidates:
        return {
            "bundles": [
                {
                    "selected": [],
                    "adjusted_sales_by_store": {},
                    "total_adjusted_npv_10k": 0.0,
                    "total_base_npv_10k": 0.0,
                    "total_investment_10k": 0.0,
                }
            ],
            "distance_alerts": [],
            "search_mode": "exact",
            "theoretical_bundle_count": 1,
            "evaluated_bundle_count": 1,
        }

    max_new_stores = max(0, min(max_new_stores, len(candidates)))
    dist = pairwise_distance_km(candidates)

    conflict_pairs = set()
    penalty_pairs: Dict[Tuple[str, str], float] = {}
    for a in candidates:
        for b in candidates:
            if a.store.store_id >= b.store.store_id:
                continue
            if normalize_city(a.store.city) != normalize_city(b.store.city):
                continue
            d = dist.get((a.store.store_id, b.store.store_id), math.inf)
            pen = attenuation_for_pair(d)
            if pen >= 1.0:
                conflict_pairs.add((a.store.store_id, b.store.store_id))
            elif pen > 0.0:
                penalty_pairs[(a.store.store_id, b.store.store_id)] = pen

    candidate_by_id = {c.store.store_id: c for c in candidates}
    ids = [c.store.store_id for c in candidates]
    theoretical_bundle_count = _comb_count_upto(len(ids), max_new_stores)

    # Adaptive search:
    # - exact for manageable search spaces
    # - beam search when combinations explode
    exact_limit = 250000
    if theoretical_bundle_count <= exact_limit:
        search_mode = "exact"
        bundles, evaluated_bundle_count = _enumerate_stage2_bundles_exact(
            ids=ids,
            candidate_by_id=candidate_by_id,
            conflict_pairs=conflict_pairs,
            penalty_pairs=penalty_pairs,
            max_new_stores=max_new_stores,
            threshold_overrides=threshold_overrides,
        )
    else:
        search_mode = "beam"
        dynamic_beam = max(160, min(1200, 40 * max_new_stores))
        bundles, evaluated_bundle_count = _enumerate_stage2_bundles_beam(
            ids=ids,
            candidate_by_id=candidate_by_id,
            conflict_pairs=conflict_pairs,
            penalty_pairs=penalty_pairs,
            max_new_stores=max_new_stores,
            beam_width=dynamic_beam,
            threshold_overrides=threshold_overrides,
        )

    if not bundles:
        bundles.append(
            {
                "selected": [],
                "adjusted_sales_by_store": {},
                "total_adjusted_npv_10k": 0.0,
                "total_base_npv_10k": 0.0,
                "total_investment_10k": 0.0,
            }
        )

    distance_alerts = []
    for a, b in conflict_pairs:
        da = candidate_by_id[a]
        db = candidate_by_id[b]
        d = dist.get((a, b), 0.0)
        distance_alerts.append(
            {
                "store_a": a,
                "store_b": b,
                "name_a": da.store.name,
                "name_b": db.store.name,
                "city": da.store.city,
                "distance_m": round(d * 1000.0, 1),
                "rule": "distance below 280m, cannot open together",
            }
        )

    return {
        "bundles": bundles,
        "distance_alerts": sorted(distance_alerts, key=lambda x: x["distance_m"]),
        "search_mode": search_mode,
        "theoretical_bundle_count": theoretical_bundle_count,
        "evaluated_bundle_count": evaluated_bundle_count,
    }


def _build_network_stores(
    stores: Sequence[Store],
    adjusted_sales_by_store: Dict[str, float],
    existing_sales_by_store: Optional[Dict[str, float]] = None,
) -> List[Store]:
    existing_sales = existing_sales_by_store or _build_existing_sales_proxy_map(stores)
    out: List[Store] = []
    for store in stores:
        cp = city_params(store.city)
        area_sqm = store.area_sqm if store.area_sqm > 0.0 else float(cp.get("standard_store_area_sqm", 650.0))

        if store.is_existing:
            proxy_sales = existing_sales.get(store.store_id, store.rf_sales_10k)
            if proxy_sales <= 0.0:
                proxy_sales = float(cp.get("standard_store_sales_10k", 800.0))
            out.append(
                Store(
                    store_id=store.store_id,
                    name=store.name,
                    city=store.city,
                    lat=store.lat,
                    lon=store.lon,
                    rf_sales_10k=proxy_sales,
                    area_sqm=area_sqm,
                    initial_investment_10k=store.initial_investment_10k,
                    annual_fixed_cost_10k=store.annual_fixed_cost_10k,
                    is_existing=True,
                )
            )
            continue

        if store.store_id not in adjusted_sales_by_store:
            continue
        out.append(
            Store(
                store_id=store.store_id,
                name=store.name,
                city=store.city,
                lat=store.lat,
                lon=store.lon,
                rf_sales_10k=adjusted_sales_by_store.get(store.store_id, store.rf_sales_10k),
                area_sqm=area_sqm,
                initial_investment_10k=store.initial_investment_10k,
                annual_fixed_cost_10k=store.annual_fixed_cost_10k,
                is_existing=False,
            )
        )
    return out


def _compute_candidate_city_mean_sales(stores: Sequence[Store]) -> Tuple[Dict[str, float], float]:
    by_city: Dict[str, List[float]] = {}
    all_sales: List[float] = []
    for store in stores:
        if store.is_existing or store.rf_sales_10k <= 0.0:
            continue
        city = normalize_city(store.city)
        by_city.setdefault(city, []).append(store.rf_sales_10k)
        all_sales.append(store.rf_sales_10k)

    mean_by_city = {
        city: (sum(values) / len(values))
        for city, values in by_city.items()
        if values
    }
    overall_mean = (sum(all_sales) / len(all_sales)) if all_sales else 0.0
    return mean_by_city, overall_mean


def _build_existing_sales_proxy_map(stores: Sequence[Store]) -> Dict[str, float]:
    mean_by_city, overall_mean = _compute_candidate_city_mean_sales(stores)
    out: Dict[str, float] = {}
    for store in stores:
        if not store.is_existing:
            continue
        city = normalize_city(store.city)
        proxy_sales = mean_by_city.get(city, overall_mean)
        if proxy_sales <= 0.0:
            cp = city_params(city)
            proxy_sales = max(store.rf_sales_10k, float(cp.get("standard_store_sales_10k", 800.0)))
        out[store.store_id] = proxy_sales
    return out


def _evaluate_rdc_pool(rdcs: Sequence[RDC]) -> Tuple[List[Tuple[RDC, float]], List[Dict[str, object]]]:
    eligible_rdcs: List[Tuple[RDC, float]] = []
    rejected_rdcs: List[Dict[str, object]] = []

    for rdc in rdcs:
        ok, reasons = rdc_eligibility(rdc)
        lifecycle = rdc_lifecycle_cost_10k(rdc)
        row = {
            "rdc_id": rdc.rdc_id,
            "name": rdc.name,
            "city": rdc.city,
            "lat": rdc.lat,
            "lon": rdc.lon,
            "lifecycle_cost_10k": round(lifecycle, 4),
            "rent_per_sqm_day": rdc.rent_per_sqm_day,
        }
        if ok:
            eligible_rdcs.append((rdc, lifecycle))
        else:
            row["reasons"] = reasons
            rejected_rdcs.append(row)
    return eligible_rdcs, rejected_rdcs


def _best_network_plan_for_p(
    full_network_stores: Sequence[Store],
    eligible_rdcs: Sequence[Tuple[RDC, float]],
    distance_matrix: Dict[Tuple[str, str], float],
    p: int,
) -> Optional[Dict[str, object]]:
    if p <= 0 or p > len(eligible_rdcs):
        return None

    best_cost = math.inf
    best_plan: Optional[Dict[str, object]] = None

    for combo in itertools.combinations(eligible_rdcs, p):
        open_rdcs = [x[0] for x in combo]
        rdc_cost = sum(x[1] for x in combo)
        delivery_total = 0.0
        assignments: List[Assignment] = []
        unassigned = False

        for store in full_network_stores:
            same_city_rdcs = [r for r in open_rdcs if normalize_city(r.city) == normalize_city(store.city)]
            if not same_city_rdcs:
                unassigned = True
                break

            best_rdc = None
            best_distance = math.inf
            best_delivery = math.inf
            for rdc in same_city_rdcs:
                distance_km = distance_lookup_km(rdc, store, distance_matrix)
                if not math.isfinite(distance_km):
                    continue
                delivery_cost = delivery_cost_pv_10k(distance_km, store.rf_sales_10k, store.area_sqm, store.city)
                if delivery_cost < best_delivery:
                    best_rdc = rdc
                    best_distance = distance_km
                    best_delivery = delivery_cost

            if best_rdc is None:
                unassigned = True
                break

            delivery_total += best_delivery
            assignments.append(
                Assignment(
                    store_id=store.store_id,
                    store_name=store.name,
                    store_city=store.city,
                    store_is_existing=store.is_existing,
                    demand_sales_10k=store.rf_sales_10k,
                    rdc_id=best_rdc.rdc_id,
                    rdc_name=best_rdc.name,
                    rdc_city=best_rdc.city,
                    store_lat=store.lat,
                    store_lon=store.lon,
                    rdc_lat=best_rdc.lat,
                    rdc_lon=best_rdc.lon,
                    distance_km=best_distance,
                    delivery_cost_pv_10k=best_delivery,
                )
            )

        if unassigned:
            continue

        total_cost = rdc_cost + delivery_total
        if total_cost < best_cost:
            best_cost = total_cost
            best_plan = {
                "p": p,
                "rdc_cost_10k": rdc_cost,
                "delivery_cost_10k": delivery_total,
                "total_cost_10k": total_cost,
                "open_rdcs": [
                    {
                        "rdc_id": r.rdc_id,
                        "name": r.name,
                        "city": r.city,
                        "lat": r.lat,
                        "lon": r.lon,
                        "lifecycle_cost_10k": round(c, 4),
                    }
                    for r, c in combo
                ],
                "assignments": assignments,
            }
    return best_plan


def _build_combo_kernel_for_p(
    stores_for_eval: Sequence[Store],
    eligible_rdcs: Sequence[Tuple[RDC, float]],
    distance_matrix: Dict[Tuple[str, str], float],
    p: int,
) -> Dict[str, object]:
    combo_plans: List[Dict[str, object]] = []
    nonnegative_total_cost_bound = True

    for combo in itertools.combinations(eligible_rdcs, p):
        open_rdcs = [x[0] for x in combo]
        rdc_cost = sum(x[1] for x in combo)
        if rdc_cost < 0.0:
            nonnegative_total_cost_bound = False

        store_best: Dict[str, Dict[str, object]] = {}

        for store in stores_for_eval:
            same_city_rdcs = [r for r in open_rdcs if normalize_city(r.city) == normalize_city(store.city)]
            if not same_city_rdcs:
                continue

            best_rdc = None
            best_distance = math.inf
            for rdc in same_city_rdcs:
                d = distance_lookup_km(rdc, store, distance_matrix)
                if not math.isfinite(d):
                    continue
                if d < best_distance:
                    best_distance = d
                    best_rdc = rdc

            if best_rdc is None:
                continue

            if best_distance < 0.0:
                nonnegative_total_cost_bound = False

            store_best[store.store_id] = {
                "rdc": best_rdc,
                "distance_km": best_distance,
            }
        combo_plans.append(
            {
                "p": p,
                "rdc_cost_10k": rdc_cost,
                "open_rdcs": [
                    {
                        "rdc_id": r.rdc_id,
                        "name": r.name,
                        "city": r.city,
                        "lat": r.lat,
                        "lon": r.lon,
                        "lifecycle_cost_10k": round(c, 4),
                    }
                    for r, c in combo
                ],
                "store_best": store_best,
            }
        )

    return {
        "plans": combo_plans,
        "nonnegative_total_cost_bound": nonnegative_total_cost_bound,
    }


def _evaluate_bundle_with_combo_kernel(
    bundle: Dict[str, object],
    combo_kernel: Dict[str, object],
    store_by_id: Dict[str, Store],
    existing_sales_by_store: Dict[str, float],
) -> Optional[Dict[str, object]]:
    adjusted_sales_by_store: Dict[str, float] = dict(bundle.get("adjusted_sales_by_store") or {})
    network_sales_by_store: Dict[str, float] = dict(existing_sales_by_store)
    network_sales_by_store.update(adjusted_sales_by_store)

    best_total_cost = math.inf
    best_delivery_total = 0.0
    best_plan = None
    best_selected_assignments: List[Assignment] = []

    for plan in combo_kernel.get("plans") or []:
        store_best = plan["store_best"]
        selected_assignments: List[Assignment] = []
        selected_delivery = 0.0
        feasible = True

        for sid, sales in network_sales_by_store.items():
            info = store_best.get(sid)
            if info is None:
                feasible = False
                break

            store = store_by_id.get(sid)
            if store is None:
                feasible = False
                break
            rdc = info["rdc"]
            distance_km = float(info["distance_km"])
            dcost = delivery_cost_pv_10k(distance_km, sales, store.area_sqm, store.city)
            selected_delivery += dcost
            selected_assignments.append(
                Assignment(
                    store_id=store.store_id,
                    store_name=store.name,
                    store_city=store.city,
                    store_is_existing=store.is_existing,
                    demand_sales_10k=sales,
                    rdc_id=rdc.rdc_id,
                    rdc_name=rdc.name,
                    rdc_city=rdc.city,
                    store_lat=store.lat,
                    store_lon=store.lon,
                    rdc_lat=rdc.lat,
                    rdc_lon=rdc.lon,
                    distance_km=distance_km,
                    delivery_cost_pv_10k=dcost,
                )
            )

        if not feasible:
            continue

        delivery_total = selected_delivery
        total_cost = float(plan["rdc_cost_10k"]) + delivery_total
        if total_cost < best_total_cost:
            best_total_cost = total_cost
            best_delivery_total = delivery_total
            best_plan = plan
            best_selected_assignments = selected_assignments

    if best_plan is None:
        return None

    return {
        "p": int(best_plan["p"]),
        "rdc_cost_10k": float(best_plan["rdc_cost_10k"]),
        "delivery_cost_10k": float(best_delivery_total),
        "total_cost_10k": float(best_total_cost),
        "open_rdcs": best_plan["open_rdcs"],
        "assignments": best_selected_assignments,
    }


def _build_stage3_scenario(plan: Dict[str, object], full_network_stores: Sequence[Store]) -> Dict[str, object]:
    assignments: List[Assignment] = list(plan["assignments"])
    total_weight = sum(a.demand_sales_10k for a in assignments) or 1.0
    avg_distance = sum(a.distance_km * a.demand_sales_10k for a in assignments) / total_weight

    total_gross_profit_pv_10k = 0.0
    for store in full_network_stores:
        cp = city_params(store.city)
        growth = list(cp["growth"])
        discount_rate = float(cp["discount_rate"])
        gross_margin = float(cp["gross_margin"])
        for year, g in enumerate(growth, start=1):
            total_gross_profit_pv_10k += (
                store.rf_sales_10k * g * gross_margin / ((1.0 + discount_rate) ** year)
            )

    roi = 0.0
    total_cost = float(plan["total_cost_10k"])
    if total_cost > 0.0:
        roi = (total_gross_profit_pv_10k - total_cost) / total_cost

    city_breakdown: Dict[str, Dict[str, float]] = {}
    for a in assignments:
        c = a.store_city
        city_breakdown.setdefault(c, {"delivery_cost_10k": 0.0, "distance_weight": 0.0, "sales_weight": 0.0, "stores": 0})
        city_breakdown[c]["delivery_cost_10k"] += a.delivery_cost_pv_10k
        city_breakdown[c]["distance_weight"] += a.distance_km * a.demand_sales_10k
        city_breakdown[c]["sales_weight"] += a.demand_sales_10k
        city_breakdown[c]["stores"] += 1

    for c in city_breakdown:
        sw = city_breakdown[c]["sales_weight"] or 1.0
        city_breakdown[c]["avg_distance_km"] = city_breakdown[c]["distance_weight"] / sw
        city_breakdown[c]["delivery_cost_10k"] = round(city_breakdown[c]["delivery_cost_10k"], 4)
        city_breakdown[c]["avg_distance_km"] = round(city_breakdown[c]["avg_distance_km"], 4)
        city_breakdown[c]["stores"] = int(city_breakdown[c]["stores"])
        del city_breakdown[c]["distance_weight"]
        del city_breakdown[c]["sales_weight"]

    return {
        "p": int(plan["p"]),
        "rdc_cost_10k": round(float(plan["rdc_cost_10k"]), 4),
        "delivery_cost_10k": round(float(plan["delivery_cost_10k"]), 4),
        "total_cost_10k": round(total_cost, 4),
        "avg_distance_km": round(avg_distance, 4),
        "roi": round(roi, 4),
        "open_rdcs": list(plan["open_rdcs"]),
        "cost_components": {
            "rdc_cost_10k": round(float(plan["rdc_cost_10k"]), 4),
            "delivery_cost_10k": round(float(plan["delivery_cost_10k"]), 4),
        },
        "city_breakdown": city_breakdown,
        "assignments": [
            {
                "store_id": a.store_id,
                "store_name": a.store_name,
                "store_city": a.store_city,
                "store_is_existing": a.store_is_existing,
                "store_lat": a.store_lat,
                "store_lon": a.store_lon,
                "demand_sales_10k": round(a.demand_sales_10k, 4),
                "rdc_id": a.rdc_id,
                "rdc_name": a.rdc_name,
                "rdc_city": a.rdc_city,
                "rdc_lat": a.rdc_lat,
                "rdc_lon": a.rdc_lon,
                "distance_km": round(a.distance_km, 4),
                "delivery_cost_pv_10k": round(a.delivery_cost_pv_10k, 4),
            }
            for a in sorted(assignments, key=lambda x: x.delivery_cost_pv_10k, reverse=True)
        ],
    }


def optimize_stage2_stage3_joint(
    stores: Sequence[Store],
    stage1_results: Sequence[Stage1Result],
    rdcs: Sequence[RDC],
    distance_matrix: Dict[Tuple[str, str], float],
    p_values: Sequence[int],
    max_new_stores: int = 8,
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, object]:
    """
    Joint objective:
        maximize new-store adjusted NPV
                 - delivery network cost (PV)
    """
    stage2_space = _enumerate_stage2_bundles(
        stage1_results,
        max_new_stores=max_new_stores,
        threshold_overrides=threshold_overrides,
    )
    bundles: List[Dict[str, object]] = list(stage2_space["bundles"])
    distance_alerts = list(stage2_space["distance_alerts"])
    stage2_search_mode = str(stage2_space.get("search_mode") or "unknown")
    stage2_theoretical_bundle_count = int(stage2_space.get("theoretical_bundle_count") or 0)
    stage2_evaluated_bundle_count = int(stage2_space.get("evaluated_bundle_count") or 0)

    passed_new_store_ids = {r.store.store_id for r in stage1_results if r.passed}
    existing_store_ids = {s.store_id for s in stores if s.is_existing}
    stores_for_eval = [s for s in stores if (s.store_id in passed_new_store_ids or s.store_id in existing_store_ids)]
    store_by_id = {s.store_id: s for s in stores_for_eval}
    existing_sales_by_store = _build_existing_sales_proxy_map(stores)

    eligible_rdcs, rejected_rdcs = _evaluate_rdc_pool(rdcs)
    eligible_payload = [
        {
            "rdc_id": r.rdc_id,
            "name": r.name,
            "city": r.city,
            "lat": r.lat,
            "lon": r.lon,
            "lifecycle_cost_10k": round(c, 4),
        }
        for r, c in sorted(eligible_rdcs, key=lambda x: x[1])
    ]

    valid_p_values = sorted({p for p in p_values if p > 0 and p <= len(eligible_rdcs)})
    combo_kernel_by_p: Dict[int, Dict[str, object]] = {}
    can_bound_total_cost_nonnegative = True
    for p in valid_p_values:
        kernel = _build_combo_kernel_for_p(
            stores_for_eval=stores_for_eval,
            eligible_rdcs=eligible_rdcs,
            distance_matrix=distance_matrix,
            p=p,
        )
        combo_kernel_by_p[p] = kernel
        can_bound_total_cost_nonnegative = can_bound_total_cost_nonnegative and bool(
            kernel.get("nonnegative_total_cost_bound", False)
        )

    bundles_by_stage2_score = sorted(
        bundles,
        key=lambda b: float(b.get("total_adjusted_npv_10k", 0.0)),
        reverse=True,
    )

    scenarios: List[Dict[str, object]] = []
    for p in valid_p_values:
        combo_kernel = combo_kernel_by_p.get(p) or {}
        if not (combo_kernel.get("plans") or []):
            continue

        best_joint_objective = -math.inf
        best_bundle: Optional[Dict[str, object]] = None
        best_plan: Optional[Dict[str, object]] = None
        best_network_stores: Optional[List[Store]] = None
        evaluated_bundle_count = 0
        pruned_by_upper_bound = 0

        for bundle in bundles_by_stage2_score:
            adjusted_sales_by_store = dict(bundle.get("adjusted_sales_by_store") or {})
            full_network_stores = _build_network_stores(
                stores,
                adjusted_sales_by_store,
                existing_sales_by_store=existing_sales_by_store,
            )
            if not full_network_stores:
                continue

            # Safe pruning when delivery cost is guaranteed non-negative:
            # joint objective upper bound for this bundle is stage2_adjusted_npv.
            stage2_score = float(bundle.get("total_adjusted_npv_10k", 0.0))
            if can_bound_total_cost_nonnegative and stage2_score <= best_joint_objective:
                pruned_by_upper_bound += 1
                continue

            plan = _evaluate_bundle_with_combo_kernel(
                bundle,
                combo_kernel,
                store_by_id,
                existing_sales_by_store=existing_sales_by_store,
            )
            if plan is None:
                continue

            evaluated_bundle_count += 1
            delivery_cost = float(plan.get("delivery_cost_10k", 0.0))
            joint_objective = float(bundle["total_adjusted_npv_10k"]) - delivery_cost

            if joint_objective > best_joint_objective:
                best_joint_objective = joint_objective
                best_bundle = bundle
                best_plan = plan
                best_network_stores = full_network_stores

        if best_bundle is None or best_plan is None or best_network_stores is None:
            continue

        scenario = _build_stage3_scenario(best_plan, best_network_stores)
        scenario.update(
            {
                "selected_new_stores": list(best_bundle["selected"]),
                "selected_store_count": len(best_bundle["selected"]),
                "stage2_adjusted_npv_10k": round(float(best_bundle["total_adjusted_npv_10k"]), 4),
                "stage2_base_npv_10k": round(float(best_bundle["total_base_npv_10k"]), 4),
                "stage2_total_investment_10k": round(float(best_bundle["total_investment_10k"]), 4),
                "network_total_cost_10k": round(float(best_plan["total_cost_10k"]), 4),
                "objective_value_10k": round(float(best_joint_objective), 4),
                "stage2_bundles_evaluated_for_p": evaluated_bundle_count,
                "stage2_bundles_pruned_for_p": pruned_by_upper_bound,
            }
        )
        scenarios.append(scenario)

    scenarios = sorted(
        scenarios,
        key=lambda x: (-float(x.get("objective_value_10k", -math.inf)), float(x.get("total_cost_10k", math.inf))),
    )
    best_scenario = scenarios[0] if scenarios else None

    fallback_bundle = max(bundles, key=lambda b: float(b.get("total_adjusted_npv_10k", 0.0))) if bundles else {
        "selected": [],
        "adjusted_sales_by_store": {},
        "total_adjusted_npv_10k": 0.0,
        "total_base_npv_10k": 0.0,
        "total_investment_10k": 0.0,
    }
    chosen_bundle = best_scenario if best_scenario is not None else {
        "selected_new_stores": list(fallback_bundle["selected"]),
        "stage2_adjusted_npv_10k": round(float(fallback_bundle["total_adjusted_npv_10k"]), 4),
        "stage2_base_npv_10k": round(float(fallback_bundle["total_base_npv_10k"]), 4),
        "stage2_total_investment_10k": round(float(fallback_bundle["total_investment_10k"]), 4),
        "objective_value_10k": None,
    }

    selected_rows = list(chosen_bundle.get("selected_new_stores") or [])
    selected_sales_map = {
        str(r.get("store_id") or ""): to_float(r.get("adjusted_sales_10k"), to_float(r.get("base_sales_10k"), 0.0))
        for r in selected_rows
        if str(r.get("store_id") or "")
    }
    network_stores = _build_network_stores(
        stores,
        selected_sales_map,
        existing_sales_by_store=existing_sales_by_store,
    )

    stage2_payload = {
        "selected": selected_rows,
        "total_adjusted_npv_10k": chosen_bundle.get("stage2_adjusted_npv_10k", 0.0),
        "total_base_npv_10k": chosen_bundle.get("stage2_base_npv_10k", 0.0),
        "total_investment_10k": chosen_bundle.get("stage2_total_investment_10k", 0.0),
        "distance_alerts": distance_alerts,
        "joint_objective_value_10k": chosen_bundle.get("objective_value_10k"),
        "objective_definition": "max(新增门店修正NPV - 全网络配送成本PV[含现存+新增])",
        "search_mode": stage2_search_mode,
        "theoretical_bundle_count": stage2_theoretical_bundle_count,
        "evaluated_bundle_count": stage2_evaluated_bundle_count,
    }

    stage3_payload = {
        "eligible_rdcs": eligible_payload,
        "rejected_rdcs": rejected_rdcs,
        "network_stores": [asdict(s) for s in network_stores],
        "scenarios": scenarios,
        "best_scenario": best_scenario,
        "objective_mode": "joint_stage2_minus_delivery_cost",
        "optimization_scope": "existing_and_selected_new_stores",
        "joint_search_meta": {
            "bundle_order": "stage2_adjusted_npv_desc",
            "upper_bound_pruning_enabled": can_bound_total_cost_nonnegative,
        },
    }
    return {"stage2": stage2_payload, "stage3": stage3_payload}


def filter_rows_by_city(rows: Sequence[Dict[str, object]], city: str) -> List[Dict[str, object]]:
    target = normalize_city(city)
    out: List[Dict[str, object]] = []
    for row in rows:
        c = normalize_city(str(row.get("city") or ""))
        if c == target:
            out.append(dict(row))
    return out


def run_full_model(
    store_rows: Sequence[Dict[str, object]],
    rdc_rows: Sequence[Dict[str, object]],
    distance_rows: Optional[Sequence[Dict[str, object]]] = None,
    max_new_stores: int = 8,
    p_values: Optional[Sequence[int]] = None,
    focus_city: Optional[str] = None,
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, object]:
    focus_city_norm = normalize_city(focus_city or "beijing")
    if focus_city_norm not in CITY_GIS_META:
        focus_city_norm = "beijing"
    store_rows = filter_rows_by_city(store_rows, focus_city_norm)
    rdc_rows = filter_rows_by_city(rdc_rows, focus_city_norm)

    stores = parse_stores(store_rows)
    rdcs = parse_rdcs(rdc_rows)
    distance_matrix = parse_distance_matrix(distance_rows or [])

    stage1 = evaluate_stage1(stores, threshold_overrides=threshold_overrides)

    if p_values is None:
        p_values = [1, 2, 3]
    joint = optimize_stage2_stage3_joint(
        stores=stores,
        stage1_results=stage1,
        rdcs=rdcs,
        distance_matrix=distance_matrix,
        p_values=p_values,
        max_new_stores=max_new_stores,
        threshold_overrides=threshold_overrides,
    )
    stage2 = joint["stage2"]
    stage3 = joint["stage3"]

    selected_ids = {str(s.get("store_id")) for s in stage2.get("selected", [])}

    stage1_rows: List[Dict[str, object]] = []
    for row in stage1:
        stage1_rows.append(
            {
                "store_id": row.store.store_id,
                "name": row.store.name,
                "city": row.store.city,
                "lat": row.store.lat,
                "lon": row.store.lon,
                "rf_sales_10k": round(row.store.rf_sales_10k, 4),
                "npv_10k": round(row.npv_10k, 4),
                "dpp_years": round(row.dpp_years, 4) if row.dpp_years else None,
                "revenue_per_sqm_10k": round(row.revenue_per_sqm_10k, 4),
                "yearly_cashflow_10k": [round(x, 4) for x in row.yearly_cashflow_10k],
                "passed": row.passed,
                "is_selected_stage2": row.store.store_id in selected_ids,
                "reasons": row.reasons,
            }
        )

    best_scenario = stage3.get("best_scenario") or {}
    best_assignments = best_scenario.get("assignments") or []

    gis_stage1_points = [
        {
            "store_id": r["store_id"],
            "name": r["name"],
            "city": r["city"],
            "lat": r["lat"],
            "lon": r["lon"],
            "passed": r["passed"],
            "npv_10k": r["npv_10k"],
            "dpp_years": r["dpp_years"],
            "yearly_cashflow_10k": r["yearly_cashflow_10k"],
        }
        for r in stage1_rows
        if is_valid_coord(float(r["lat"]), float(r["lon"]))
    ]

    gis_stage2_selected = [
        {
            "store_id": s["store_id"],
            "name": s["name"],
            "city": s["city"],
            "lat": s["lat"],
            "lon": s["lon"],
            "radius_300_m": 300,
            "radius_500_m": 500,
            "adjusted_npv_10k": s["adjusted_npv_10k"],
        }
        for s in stage2.get("selected", [])
        if is_valid_coord(float(s.get("lat", 0.0)), float(s.get("lon", 0.0)))
    ]

    gis_network_lines = [
        {
            "store_id": a["store_id"],
            "store_name": a["store_name"],
            "store_city": a["store_city"],
            "store_is_existing": bool(a.get("store_is_existing", False)),
            "store_lat": a["store_lat"],
            "store_lon": a["store_lon"],
            "rdc_id": a["rdc_id"],
            "rdc_name": a["rdc_name"],
            "rdc_city": a["rdc_city"],
            "rdc_lat": a["rdc_lat"],
            "rdc_lon": a["rdc_lon"],
            "distance_km": a["distance_km"],
        }
        for a in best_assignments
    ]

    summary = {
        "total_store_rows": len(stores),
        "existing_stores": sum(1 for s in stores if s.is_existing),
        "new_store_candidates": sum(1 for s in stores if not s.is_existing),
        "optimization_scope": "existing_and_selected_new_stores",
        "stage1_passed": sum(1 for r in stage1 if r.passed),
        "stage2_selected": len(stage2.get("selected", [])),
        "stage2_search_mode": stage2.get("search_mode"),
        "stage2_evaluated_bundle_count": stage2.get("evaluated_bundle_count"),
        "eligible_rdcs": len(stage3.get("eligible_rdcs", [])),
        "best_p": best_scenario.get("p"),
        "best_total_cost_10k": best_scenario.get("total_cost_10k"),
        "best_joint_objective_10k": best_scenario.get("objective_value_10k"),
        "joint_stage2_bundles_evaluated_for_best_p": best_scenario.get("stage2_bundles_evaluated_for_p"),
        "joint_stage2_bundles_pruned_for_best_p": best_scenario.get("stage2_bundles_pruned_for_p"),
        "focus_city": focus_city_norm,
    }

    return {
        "summary": summary,
        "city_configs": get_city_configs(),
        "stage1": {"rows": stage1_rows},
        "stage2": stage2,
        "stage3": stage3,
        "gis": {
            "stage1_points": gis_stage1_points,
            "stage2_selected": gis_stage2_selected,
            "stage3_network_lines": gis_network_lines,
            "stage3_open_rdcs": best_scenario.get("open_rdcs") or [],
            "distance_alerts": stage2.get("distance_alerts", []),
        },
    }

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
        "demand_top_ratio": 0.70,
        "min_pad_area_sqm": 80.0,
        "flights_per_demand_wanyuan": 0.4,
        # Stage2 硬门槛：衰减后覆盖单量（万元/单量），低于则淘汰
        "min_adjusted_demand_10k": 20.0,
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
        "demand_top_ratio": 0.70,
        "min_pad_area_sqm": 80.0,
        "flights_per_demand_wanyuan": 0.4,
        # Stage2 硬门槛：衰减后覆盖单量（万元），低于则淘汰
        "min_adjusted_demand_10k": 20.0,
    },
    "shenzhen": {
        "horizon_years": 10,
        "discount_rate": 0.10,
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
        "npv_threshold_10k": 100.0,
        "dpp_threshold_years": 5.0,
        "revenue_per_sqm_threshold_10k": 1.15,
        "rent_cap_per_sqm_day": 1.8,
        "wacc": 0.10,
        "demand_top_ratio": 0.70,
        "min_pad_area_sqm": 80.0,
        "flights_per_demand_wanyuan": 0.4,
        # Stage2 硬门槛：衰减后覆盖单量（万元），低于则淘汰
        "min_adjusted_demand_10k": 20.0,
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
    "demand_top_ratio": 0.70,
    "min_pad_area_sqm": 80.0,
    "flights_per_demand_wanyuan": 0.4,
        # Stage2 硬门槛：衰减后覆盖单量（万元），低于则淘汰
        "min_adjusted_demand_10k": 20.0,
}

# =====================================================================
# 无人机真实财务参数 —— 源自《联合选址模型参数与结果.xlsx》参数设置汇总 / ROI计算
# 严格照文件原文提取，未引入编造数值。
# =====================================================================
DEFAULT_MATURE_PENETRATION = 0.60             # 前端滑块：成熟期（阶段3）渗透率默认 = Excel 阶段3 60%
STAGE_PENETRATION_FACTORS = {1: 0.133, 2: 0.583, 3: 1.0}  # 阶段1/2/3 相对成熟期等比缩放
UNIT_REVENUE_YUAN = 6.5                       # 每单收益
ENERGY_COST_YUAN_PER_ORDER = 0.8              # 能源成本（电费+电池折旧）/单
VERTIPORT_CONSTRUCTION_10K = 40.0             # 停机坪建设成本 万元/个（一次性投入）
PAD_CONSTRUCTION_10K = 2.0                    # 起降点（外卖柜）建设成本 万元/个
DRONE_COST_10K = 6.0                          # 无人机采购成本 万元/架
DRONES_PER_VERTIPORT = 20                     # 每个停机坪配备无人机数量
DRONE_LIFE_YEARS = 3                          # 无人机使用寿命（年）
VERTIPORT_LABOR_10K_YEAR = 25.0               # 停机坪人力成本 万元/年/个
MAINTENANCE_RATE = 0.08                       # 无人机+设备年度维护费率
RND_YEARLY_10K = 200.0                        # 研发分摊 万元/年
ADMIN_YEARLY_10K = 50.0                       # 行政管理 万元/年
COVERAGE_RADIUS_KM = 5.0                      # 停机坪到起降点最大覆盖半径
PAYBACK_STAGE_YEARS = {1: 2, 2: 5, 3: 10}     # 阶段1(1-2年)、阶段2(3-5年)、阶段3(6-10年)
# —— 无人机运力约束（Excel 参数设置汇总 / 起降点属性计算 原文）——
DRONE_ORDER_RATE_PER_HOUR = 10                # 每架无人机配送能力：10 单/小时
VERTIPORT_MAX_PADS = 11                        # 一个停机坪最多服务的起降点位置数
PAD_CAPACITY_ORDERS_PER_HOUR = 32             # 单个起降点高峰容量：8格×4周转=32 单/小时
PEAK_HOUR_FACTOR = 4.687                       # 峰值小时订单 = 平均小时订单 × 4.687


def stage_penetration(mature_pen: float, year: int) -> float:
    """三阶段渗透率等比缩放：1-2年=13.3%×成熟期、3-5年=58.3%×成熟期、6-10年=100%×成熟期。"""
    if year <= PAYBACK_STAGE_YEARS[1]:
        factor = STAGE_PENETRATION_FACTORS[1]
    elif year <= PAYBACK_STAGE_YEARS[2]:
        factor = STAGE_PENETRATION_FACTORS[2]
    else:
        factor = STAGE_PENETRATION_FACTORS[3]
    return mature_pen * factor


def order_flow_value_yuan(
    covered_orders: float,
    mature_pen: float,
    year: int,
    per_unit_yuan: float,
    days_per_year: float = 365.0,
) -> float:
    """单点某年有效无人机订单对应的金额（元）：
    日均订单=(总覆盖单量/7)×阶段渗透率；年金额=日均×365×每单位金额。"""
    daily_orders = (covered_orders / 7.0) * stage_penetration(mature_pen, year)
    return daily_orders * days_per_year * per_unit_yuan


def vertiport_heavy_lifecycle_pv_10k(city: str, years: Optional[int] = None) -> float:
    """停机坪重资产生命周期成本 PV（万元）：
        一次性建设40 + 无人机采购(20×6) + PV_{y}(人力25/年 + 无人机采购×8%维护)。
    对应 Excel ROI计算 的停机坪侧成本科目；残值不另计（与 Excel 保持一致）。"""
    cp = city_params(city)
    r = float(cp["discount_rate"])
    if years is None:
        years = int(cp["horizon_years"])
    cap_ex_10k = VERTIPORT_CONSTRUCTION_10K + DRONES_PER_VERTIPORT * DRONE_COST_10K
    annual_opex_10k = VERTIPORT_LABOR_10K_YEAR + DRONES_PER_VERTIPORT * DRONE_COST_10K * MAINTENANCE_RATE
    pv_annual = 0.0
    for y in range(1, years + 1):
        pv_annual += annual_opex_10k / ((1.0 + r) ** y)
    return cap_ex_10k + pv_annual


def vertical_project_revenue_pv_10k(
    covered_orders: float,
    city: str,
    mature_pen: float,
    years: Optional[int] = None,
) -> float:
    """单点 10 年项目期营收 PV（万元）：Σ_y 年收益×6.5元 /(1+r)^y。"""
    cp = city_params(city)
    r = float(cp["discount_rate"])
    if years is None:
        years = int(cp["horizon_years"])
    pv = 0.0
    for y in range(1, years + 1):
        pv += order_flow_value_yuan(covered_orders, mature_pen, y, UNIT_REVENUE_YUAN) / ((1.0 + r) ** y)
    return pv / 10000.0


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
    "shenzhen": {
        "label": "深圳",
        "center": [22.5431, 114.0579],
        "zoom": 10.8,
        "inner_ring_radius_km": 6.0,
        "inner_ring_name": "福田-罗湖中心区近似圈",
        "inner_ring_warning": "违反无人机空域管制硬指标，该区域禁止无人机起降。",
        "logistics_belts": [
            {"name": "宝安空港物流带", "lat": 22.63, "lon": 113.81, "radius_km": 6.0},
            {"name": "龙岗平湖物流带", "lat": 22.67, "lon": 114.12, "radius_km": 5.5},
            {"name": "盐田国际物流带", "lat": 22.58, "lon": 114.27, "radius_km": 4.5},
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
        "sz": "shenzhen",
        "shenzhen": "shenzhen",
        "深圳": "shenzhen",
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
class LandingPad:
    pad_id: str
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
class Vertiport:
    vertiport_id: str
    name: str
    city: str
    lat: float
    lon: float
    area_sqm: float
    # —— 无人机新物理字段（Step1 新增，Step2 用于硬约束判定）——
    altitude_limit_m: float       # 净空高度限制（原 clear_height_m 语义，无人机侧）
    is_no_fly_zone: bool          # 是否禁飞区（新增独立列）
    max_flight_radius_km: float   # 最大服务航程（无人机覆盖半径）
    # —— 停机坪财务字段（Step3 语义改为无人机停机坪建设/运维成本）——
    initial_investment_10k: float   # 停机坪建设成本（CapEx）
    annual_operating_10k: float     # 每年固定维护成本
    annual_labor_10k: float         # 每年巡检/人力成本
    annual_utility_10k: float       # 每年换电/能耗成本
    residual_rate: float            # 停机坪建设资产期满残值率
    rent_per_sqm_day: float         # 保留（下游序列化仍在用）


@dataclass
class Stage1Result:
    pad: LandingPad
    # 无人机侧指标：单点覆盖单量 / 预估日均起降架次 / 落地可行性
    covered_demand_10k: float
    est_daily_flights: float
    space_ok: bool
    passed: bool
    reasons: List[str]
    # —— 兼容占位字段（财务），Stage2 过渡期暂留，Stage2 重写时删除 ——
    yearly_cashflow_10k: List[float]
    npv_10k: float
    dpp_years: Optional[float]
    revenue_per_sqm_10k: float


@dataclass
class Stage2PadResult:
    pad: LandingPad
    base_demand_10k: float       # 初始覆盖单量（需求密度）
    attenuation_ratio: float     # 空域/噪声冲突导致的起降承载力衰减系数
    adjusted_demand_10k: float   # 衰减后覆盖单量
    adjusted_daily_flights: float  # 衰减后预估日均起降架次
    passed: bool
    reasons: List[str]


@dataclass
class Assignment:
    pad_id: str
    pad_name: str
    pad_city: str
    pad_is_existing: bool
    demand_sales_10k: float
    vertiport_id: str
    vertiport_name: str
    vertiport_city: str
    pad_lat: float
    pad_lon: float
    vertiport_lat: float
    vertiport_lon: float
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


def parse_pads(records: Iterable[Dict[str, object]]) -> List[LandingPad]:
    out: List[LandingPad] = []
    for row in records:
        pad_id = str(row.get("pad_id") or row.get("id") or "").strip()
        if not pad_id:
            continue

        city = normalize_city(str(row.get("city") or "beijing"))
        lat = to_float(row.get("lat"))
        lon = to_float(row.get("lon"))
        out.append(
            LandingPad(
                pad_id=pad_id,
                name=str(row.get("name") or pad_id),
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


def parse_vertiports(records: Iterable[Dict[str, object]]) -> List[Vertiport]:
    out: List[Vertiport] = []
    for row in records:
        vertiport_id = str(row.get("vertiport_id") or row.get("id") or "").strip()
        if not vertiport_id:
            continue

        city = normalize_city(str(row.get("city") or "beijing"))
        out.append(
            Vertiport(
                vertiport_id=vertiport_id,
                name=str(row.get("name") or vertiport_id),
                city=city,
                lat=to_float(row.get("lat")),
                lon=to_float(row.get("lon")),
                area_sqm=to_float(row.get("area_sqm"), 10000.0),
                # 无人机新物理字段：新列优先，回退到旧列（兼容未加新列的表头）
                altitude_limit_m=to_float(row.get("altitude_limit_m"), to_float(row.get("clear_height_m"), 0.0)),
                is_no_fly_zone=parse_bool(row.get("is_no_fly_zone"), False),
                max_flight_radius_km=to_float(row.get("max_flight_radius_km"), 15.0),
                initial_investment_10k=to_float(row.get("initial_investment_10k"), 0.0),
                annual_operating_10k=to_float(row.get("annual_operating_10k"), 0.0),
                annual_labor_10k=to_float(row.get("annual_labor_10k"), 0.0),
                annual_utility_10k=to_float(row.get("annual_utility_10k"), 0.0),
                residual_rate=to_float(row.get("residual_rate"), 0.25),
                rent_per_sqm_day=to_float(row.get("rent_per_sqm_day"), 0.0),
            )
        )
    return out


def parse_distance_matrix(records: Iterable[Dict[str, object]]) -> Dict[Tuple[str, str], float]:
    matrix: Dict[Tuple[str, str], float] = {}
    for row in records:
        vertiport_id = str(row.get("vertiport_id") or "").strip()
        pad_id = str(row.get("pad_id") or "").strip()
        if not vertiport_id or not pad_id:
            continue
        matrix[(vertiport_id, pad_id)] = to_float(row.get("distance_km"), math.inf)
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
    pads: Sequence[LandingPad],
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
    vertiports: Optional[Sequence[Vertiport]] = None,
    distance_matrix: Optional[Dict[Tuple[str, str], float]] = None,
    mature_penetration: float = DEFAULT_MATURE_PENETRATION,
) -> List[Stage1Result]:
    candidate_pads = [pad for pad in pads if not pad.is_existing]

    # ---- 按城市计算「累计覆盖达 70%」的需求门槛 ----
    # covered_demand 复用 rf_sales_10k 作为单点覆盖单量；按需求降序累计，
    # 累计覆盖达到该城总需求 * demand_top_ratio 时的边界单量即为门槛。
    city_threshold: Dict[str, float] = {}
    by_city: Dict[str, List[LandingPad]] = {}
    for pad in candidate_pads:
        key = normalize_city(pad.city)
        by_city.setdefault(key, []).append(pad)
    for key, city_pads in by_city.items():
        cp = city_params(city_pads[0].city)
        ratio = float(cp.get("demand_top_ratio", 0.70))
        sorted_pads = sorted(city_pads, key=lambda p: p.rf_sales_10k, reverse=True)
        total_demand = sum(p.rf_sales_10k for p in sorted_pads)
        if total_demand <= 0:
            city_threshold[key] = 0.0
            continue
        cum = 0.0
        threshold = float(sorted_pads[-1].rf_sales_10k)
        for p in sorted_pads:
            cum += p.rf_sales_10k
            if cum >= total_demand * ratio:
                threshold = p.rf_sales_10k
                break
        city_threshold[key] = threshold

    # ---- Stage1 轻门槛（已确认口径） ----
    # 重资产（停机坪建设/无人机/人力/维护）不在单点分摊，整体移入 Stage3 网络级 ROI。
    # 单点成本只含：起降点建设 2万（一次性）+ PV(能源 0.8元/单)。
    # 营收 = 单量/7 × 阶段渗透率 × 6.5元。（单量视为周单量，/7 换算日均）

    results: List[Stage1Result] = []
    for pad in candidate_pads:
        cp = city_params(pad.city)
        key = normalize_city(pad.city)
        demand_threshold = city_threshold[key]

        # 无人机侧新指标
        covered_demand_10k = pad.rf_sales_10k
        min_area = float(cp.get("min_pad_area_sqm", 80.0))
        space_ok = pad.area_sqm >= min_area and is_valid_coord(pad.lat, pad.lon)
        est_daily_flights = covered_demand_10k * float(
            cp.get("flights_per_demand_wanyuan", 0.4)
        )

        reasons: List[str] = []
        passed = True
        if covered_demand_10k < demand_threshold:
            passed = False
            reasons.append(
                f"单量密度不足：{covered_demand_10k:.2f} < 覆盖门槛 {demand_threshold:.2f}"
            )
        if not space_ok:
            passed = False
            reasons.append(
                f"落地可行性不足：场地面积 {pad.area_sqm} ㎡ < {min_area} ㎡"
            )

        # —— 纯选址口径：禁用财务筛选（NPV/DPP/坪效不再参与淘汰）。
        # 字段保留中性值以满足下游 Stage2 beam 排序引用，不参与任何门槛判定。 ——
        npv_10k = 0.0
        dpp = None
        yearly_cashflows: List[float] = []
        revenue_per_sqm = 0.0

        results.append(
            Stage1Result(
                pad=pad,
                covered_demand_10k=covered_demand_10k,
                est_daily_flights=est_daily_flights,
                space_ok=space_ok,
                passed=passed,
                reasons=reasons,
                yearly_cashflow_10k=yearly_cashflows,
                npv_10k=npv_10k,
                dpp_years=dpp,
                revenue_per_sqm_10k=revenue_per_sqm,
            )
        )
    return results


def pairwise_distance_km(pads: Sequence[Stage1Result]) -> Dict[Tuple[str, str], float]:
    dist: Dict[Tuple[str, str], float] = {}
    for i, a in enumerate(pads):
        for b in pads[i + 1 :]:
            key1 = (a.pad.pad_id, b.pad.pad_id)
            key2 = (b.pad.pad_id, a.pad.pad_id)
            if normalize_city(a.pad.city) != normalize_city(b.pad.city):
                dist[key1] = math.inf
                dist[key2] = math.inf
                continue
            d = haversine_km(a.pad.lat, a.pad.lon, b.pad.lat, b.pad.lon)
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





def optimize_stage2(
    stage1_results: Sequence[Stage1Result],
    max_new_stores: int = 8,
) -> Dict[str, object]:
    candidates = [r for r in stage1_results if r.passed]
    # Stage2 候选剪枝：真实城市 passed 需求点可能上百，先按覆盖单量降序
    # 截断到前 STAGE2_MAX_CANDIDATES 个，避免后续组合/beam 搜索爆炸。
    candidates = sorted(
        candidates,
        key=lambda c: float(getattr(c, "covered_demand_10k", 0.0)),
        reverse=True,
    )[:STAGE2_MAX_CANDIDATES]
    if not candidates:
        return {
            "selected": [],
            "total_adjusted_demand_10k": 0.0,
            "total_base_demand_10k": 0.0,
            "total_investment_10k": 0.0,
            "distance_alerts": [],
        }

    max_new_stores = max(0, min(max_new_stores, len(candidates)))
    dist = pairwise_distance_km(candidates)

    conflict_pairs = set()
    penalty_pairs: Dict[Tuple[str, str], float] = {}
    for a in candidates:
        for b in candidates:
            if a.pad.pad_id >= b.pad.pad_id:
                continue
            if normalize_city(a.pad.city) != normalize_city(b.pad.city):
                continue
            d = dist.get((a.pad.pad_id, b.pad.pad_id), math.inf)
            pen = attenuation_for_pair(d)
            if pen >= 1.0:
                conflict_pairs.add((a.pad.pad_id, b.pad.pad_id))
            elif pen > 0.0:
                penalty_pairs[(a.pad.pad_id, b.pad.pad_id)] = pen

    candidate_by_id = {c.pad.pad_id: c for c in candidates}
    ids = [c.pad.pad_id for c in candidates]

    best_score = -math.inf
    best_bundle: Optional[List[Stage2PadResult]] = None

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
            bundle: List[Stage2PadResult] = []

            for sid in combo:
                base = candidate_by_id[sid]
                penalty = 0.0
                for oid in combo_set:
                    if oid == sid:
                        continue
                    other = candidate_by_id[oid]
                    if normalize_city(other.pad.city) != normalize_city(base.pad.city):
                        continue
                    key = tuple(sorted((sid, oid)))
                    penalty += penalty_pairs.get(key, 0.0)

                penalty = min(0.45, penalty)
                attenuation_ratio = max(0.0, 1.0 - penalty)
                # 无人机侧：衰减后覆盖单量 = 初始单量 × 空域/噪声冲突承载力衰减系数
                adjusted_demand = base.pad.rf_sales_10k * attenuation_ratio
                cp = city_params(base.pad.city)
                min_adjusted = float(cp.get("min_adjusted_demand_10k", 20.0))
                flights_rate = float(cp.get("flights_per_demand_wanyuan", 0.4))
                adjusted_flights = adjusted_demand * flights_rate

                reasons: List[str] = []
                passed = True
                if adjusted_demand < min_adjusted:
                    passed = False
                    reasons.append(
                        f"衰减后覆盖单量不足：{adjusted_demand:.2f} < {min_adjusted:.2f}"
                    )

                if passed:
                    score += adjusted_demand
                    bundle.append(
                        Stage2PadResult(
                            pad=base.pad,
                            base_demand_10k=base.pad.rf_sales_10k,
                            attenuation_ratio=attenuation_ratio,
                            adjusted_demand_10k=adjusted_demand,
                            adjusted_daily_flights=adjusted_flights,
                            passed=True,
                            reasons=[],
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
                "pad_a": a,
                "pad_b": b,
                "name_a": da.pad.name,
                "name_b": db.pad.name,
                "city": da.pad.city,
                "distance_m": round(d * 1000.0, 1),
                "rule": "distance below 280m, cannot open together",
            }
        )

    total_base = sum(item.base_demand_10k for item in best_bundle)
    total_investment = sum(item.pad.initial_investment_10k for item in best_bundle)

    return {
        "selected": [
            {
                "pad_id": item.pad.pad_id,
                "name": item.pad.name,
                "city": item.pad.city,
                "base_demand_10k": round(item.base_demand_10k, 4),
                "attenuation_ratio": round(item.attenuation_ratio, 4),
                "adjusted_demand_10k": round(item.adjusted_demand_10k, 4),
                "adjusted_daily_flights": round(item.adjusted_daily_flights, 2),
                "passed": bool(item.passed),
                "reasons": item.reasons,
                "lat": item.pad.lat,
                "lon": item.pad.lon,
                "radius_300_m": 300,
                "radius_500_m": 500,
            }
            for item in sorted(best_bundle, key=lambda x: x.adjusted_demand_10k, reverse=True)
        ],
        "total_adjusted_demand_10k": round(best_score, 4),
        "total_base_demand_10k": round(total_base, 4),
        "total_investment_10k": round(total_investment, 4),
        "distance_alerts": sorted(distance_alerts, key=lambda x: x["distance_m"]),
    }


def vertiport_lifecycle_cost_10k(vertiport: Vertiport) -> float:
    """停机坪重资产生命周期成本 PV（万元）。

    按《联合选址模型参数与结果.xlsx》ROI计算 口径：
        停机坪建设40万 + 无人机采购(20架×6万) + PV_{10年}(人力25万/年 + 无人机采购×8%维护)。
    废弃原超市 initial_investment/年度运营/残值 等复用字段。
    """
    return vertiport_heavy_lifecycle_pv_10k(vertiport.city, None)


def vertiport_eligibility(vertiport: Vertiport) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    # —— 无人机物理与空域硬约束 ——
    if vertiport.is_no_fly_zone:
        reasons.append("[NO_FLY_ZONE] Vertiport located inside a no-fly zone")
    if vertiport.altitude_limit_m < 3.0:
        reasons.append(
            f"[ALTITUDE] net height clearance below safe takeoff height (3m) "
            f"({vertiport.altitude_limit_m:.1f}m)"
        )
    # —— 航程占位：max_flight_radius_km 暂不参与复杂配送距离判定 ——
    # Step2 仅预留字段读取；若后续按航程做配送约束，可在此追加判断。

    # GIS hard constraint: inner-ring placements correspond to urban airspace
    # restricted zones (equivalent to drone flight-restricted areas).
    rule = point_inner_ring_violation(vertiport.city, vertiport.lat, vertiport.lon)
    if rule.get("violation"):
        reasons.append("[INNER_RING] Vertiport located inside inner-ring restricted zone")

    return (len(reasons) == 0), reasons


def distance_lookup_km(
    vertiport: Vertiport,
    pad: LandingPad,
    matrix: Dict[Tuple[str, str], float],
) -> float:
    if normalize_city(vertiport.city) != normalize_city(pad.city):
        return math.inf

    key = (vertiport.vertiport_id, pad.pad_id)
    if key in matrix and math.isfinite(matrix[key]):
        return matrix[key]
    return haversine_km(vertiport.lat, vertiport.lon, pad.lat, pad.lon)


def delivery_cost_pv_10k(
    distance_km: float,
    covered_orders: float,
    city: str,
    mature_pen: float = DEFAULT_MATURE_PENETRATION,
) -> float:
    """无人机能源配送成本 PV（万元）。

    按《联合选址模型参数与结果.xlsx》：能源成本=0.8元/单。
        Σ_{10年} 日均订单(覆盖单量/7×阶段渗透率)×365×0.8元 /(1+r)^y
    废弃原超市 delivery_freq/delivery_fixed_cost/面积权重 等参数。
    附加极小距离项仅用于就近分配命中（非虚构成本），保证 Stage3 归属到最近停机坪。
    """
    cp = city_params(city)
    r = float(cp["discount_rate"])
    years = int(cp["horizon_years"])
    pv_yuan = 0.0
    for y in range(1, years + 1):
        pv_yuan += order_flow_value_yuan(covered_orders, mature_pen, y, ENERGY_COST_YUAN_PER_ORDER) / ((1.0 + r) ** y)
    # 极小距离偏爱项：仅用于就近分配命中，不引入虚构成本
    return pv_yuan / 10000.0 + distance_km * 1e-6


def optimize_stage3(
    pads: Sequence[LandingPad],
    selected_new_pad_rows: Sequence[Dict[str, object]],
    vertiports: Sequence[Vertiport],
    distance_matrix: Dict[Tuple[str, str], float],
    p_values: Sequence[int],
) -> Dict[str, object]:
    adjusted_sales_by_pad: Dict[str, float] = {
        str(r.get("pad_id")): to_float(r.get("adjusted_demand_10k"), to_float(r.get("base_demand_10k"), 0.0))
        for r in selected_new_pad_rows
    }
    existing_sales_by_pad = _build_existing_sales_proxy_map(pads)
    # Stage-3 network contains selected new pads + existing pads.
    full_network_stores: List[LandingPad] = _build_network_pads(
        pads,
        adjusted_sales_by_pad,
        existing_sales_by_pad=existing_sales_by_pad,
    )

    eligible_vertiports: List[Tuple[Vertiport, float]] = []
    rejected_vertiports: List[Dict[str, object]] = []

    for vertiport in vertiports:
        ok, reasons = vertiport_eligibility(vertiport)
        lifecycle = vertiport_lifecycle_cost_10k(vertiport)
        row = {
            "vertiport_id": vertiport.vertiport_id,
            "name": vertiport.name,
            "city": vertiport.city,
            "lat": vertiport.lat,
            "lon": vertiport.lon,
            "lifecycle_cost_10k": round(lifecycle, 4),
            "rent_per_sqm_day": vertiport.rent_per_sqm_day,
            # 无人机新物理字段（Step1 新增展示）
            "altitude_limit_m": round(vertiport.altitude_limit_m, 2),
            "is_no_fly_zone": bool(vertiport.is_no_fly_zone),
            "max_flight_radius_km": round(vertiport.max_flight_radius_km, 1),
        }
        if ok:
            eligible_vertiports.append((vertiport, lifecycle))
        else:
            row["reasons"] = reasons
            rejected_vertiports.append(row)

    scenarios: List[Dict[str, object]] = []
    if not full_network_stores or not eligible_vertiports:
        return {
            "eligible_vertiports": [
                {
                    "vertiport_id": r.vertiport_id,
                    "name": r.name,
                    "city": r.city,
                    "lat": r.lat,
                    "lon": r.lon,
                    "lifecycle_cost_10k": round(c, 4),
                }
                for r, c in eligible_vertiports
            ],
            "rejected_vertiports": rejected_vertiports,
            "network_stores": [asdict(s) for s in full_network_stores],
            "scenarios": [],
            "best_scenario": None,
        }

    valid_p_values = sorted({p for p in p_values if p > 0 and p <= STAGE3_MAX_P})
    # 组合爆炸防护：与 _build_combo_kernel_for_p 一致，候选剪枝 + p 上限
    eligible_vertiports = _prune_vertiport_candidates(
        eligible_vertiports,
        full_network_stores,
        distance_matrix,
    )
    for p in valid_p_values:
        if p > len(eligible_vertiports):
            continue

        best_cost = math.inf
        best_plan: Optional[Dict[str, object]] = None

        for combo in itertools.combinations(eligible_vertiports, p):
            open_vertiports = [x[0] for x in combo]
            vertiport_cost = sum(x[1] for x in combo)
            delivery_total = 0.0
            assignments: List[Assignment] = []
            unassigned: List[Dict[str, object]] = []

            for pad in full_network_stores:
                same_city_rdcs = [r for r in open_vertiports if normalize_city(r.city) == normalize_city(pad.city)]
                if not same_city_rdcs:
                    unassigned.append(
                        {
                            "pad_id": pad.pad_id,
                            "pad_name": pad.name,
                            "city": pad.city,
                            "reason": "no opened Vertiport in same city",
                        }
                    )
                    continue

                best_vertiport = None
                best_distance = math.inf
                best_delivery = math.inf
                for vertiport in same_city_rdcs:
                    distance_km = distance_lookup_km(vertiport, pad, distance_matrix)
                    if not math.isfinite(distance_km):
                        continue
                    delivery_cost = delivery_cost_pv_10k(distance_km, pad.rf_sales_10k, pad.city)
                    if delivery_cost < best_delivery:
                        best_vertiport = vertiport
                        best_distance = distance_km
                        best_delivery = delivery_cost

                if best_vertiport is None:
                    unassigned.append(
                        {
                            "pad_id": pad.pad_id,
                            "pad_name": pad.name,
                            "city": pad.city,
                            "reason": "distance lookup failed",
                        }
                    )
                    continue

                delivery_total += best_delivery
                assignments.append(
                    Assignment(
                        pad_id=pad.pad_id,
                        pad_name=pad.name,
                        pad_city=pad.city,
                        pad_is_existing=pad.is_existing,
                        demand_sales_10k=pad.rf_sales_10k,
                        vertiport_id=best_vertiport.vertiport_id,
                        vertiport_name=best_vertiport.name,
                        vertiport_city=best_vertiport.city,
                        pad_lat=pad.lat,
                        pad_lon=pad.lon,
                        vertiport_lat=best_vertiport.lat,
                        vertiport_lon=best_vertiport.lon,
                        distance_km=best_distance,
                        delivery_cost_pv_10k=best_delivery,
                    )
                )

            if unassigned:
                continue

            total_cost = vertiport_cost + delivery_total
            if total_cost < best_cost:
                best_cost = total_cost
                best_plan = {
                    "p": p,
                    "vertiport_cost_10k": vertiport_cost,
                    "delivery_cost_10k": delivery_total,
                    "total_cost_10k": total_cost,
                    "open_vertiports": [
                        {
                            "vertiport_id": r.vertiport_id,
                            "name": r.name,
                            "city": r.city,
                            "lat": r.lat,
                            "lon": r.lon,
                            "lifecycle_cost_10k": round(vertiport_lifecycle_cost_10k(r), 4),
                            "altitude_limit_m": round(r.altitude_limit_m, 2),
                            "is_no_fly_zone": bool(r.is_no_fly_zone),
                            "max_flight_radius_km": round(r.max_flight_radius_km, 1),
                        }
                        for r in open_vertiports
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
        for pad in full_network_stores:
            cp = city_params(pad.city)
            growth = list(cp["growth"])
            discount_rate = float(cp["discount_rate"])
            gross_margin = float(cp["gross_margin"])
            for year, g in enumerate(growth, start=1):
                total_gross_profit_pv_10k += (
                    pad.rf_sales_10k * g * gross_margin / ((1.0 + discount_rate) ** year)
                )

        roi = 0.0
        if best_plan["total_cost_10k"] > 0:
            roi = (total_gross_profit_pv_10k - best_plan["total_cost_10k"]) / best_plan["total_cost_10k"]

        city_breakdown: Dict[str, Dict[str, float]] = {}
        for a in assignments:
            c = a.pad_city
            city_breakdown.setdefault(c, {"delivery_cost_10k": 0.0, "distance_weight": 0.0, "sales_weight": 0.0, "pads": 0})
            city_breakdown[c]["delivery_cost_10k"] += a.delivery_cost_pv_10k
            city_breakdown[c]["distance_weight"] += a.distance_km * a.demand_sales_10k
            city_breakdown[c]["sales_weight"] += a.demand_sales_10k
            city_breakdown[c]["pads"] += 1

        for c in city_breakdown:
            sw = city_breakdown[c]["sales_weight"] or 1.0
            city_breakdown[c]["avg_distance_km"] = city_breakdown[c]["distance_weight"] / sw
            city_breakdown[c]["delivery_cost_10k"] = round(city_breakdown[c]["delivery_cost_10k"], 4)
            city_breakdown[c]["avg_distance_km"] = round(city_breakdown[c]["avg_distance_km"], 4)
            city_breakdown[c]["pads"] = int(city_breakdown[c]["pads"])
            del city_breakdown[c]["distance_weight"]
            del city_breakdown[c]["sales_weight"]

        scenarios.append(
            {
                "p": best_plan["p"],
                "vertiport_cost_10k": round(best_plan["vertiport_cost_10k"], 4),
                "delivery_cost_10k": round(best_plan["delivery_cost_10k"], 4),
                "total_cost_10k": round(best_plan["total_cost_10k"], 4),
                "avg_distance_km": round(avg_distance, 4),
                "roi": round(roi, 4),
                "open_vertiports": best_plan["open_vertiports"],
                "cost_components": {
                    "vertiport_cost_10k": round(best_plan["vertiport_cost_10k"], 4),
                    "delivery_cost_10k": round(best_plan["delivery_cost_10k"], 4),
                },
                "city_breakdown": city_breakdown,
                "assignments": [
                    {
                        "pad_id": a.pad_id,
                        "pad_name": a.pad_name,
                        "pad_city": a.pad_city,
                        "pad_is_existing": a.pad_is_existing,
                        "pad_lat": a.pad_lat,
                        "pad_lon": a.pad_lon,
                        "demand_sales_10k": round(a.demand_sales_10k, 4),
                        "vertiport_id": a.vertiport_id,
                        "vertiport_name": a.vertiport_name,
                        "vertiport_city": a.vertiport_city,
                        "vertiport_lat": a.vertiport_lat,
                        "vertiport_lon": a.vertiport_lon,
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
        "eligible_vertiports": [
            {
                "vertiport_id": r.vertiport_id,
                "name": r.name,
                "city": r.city,
                "lat": r.lat,
                "lon": r.lon,
                "lifecycle_cost_10k": round(c, 4),
            }
            for r, c in sorted(eligible_vertiports, key=lambda x: x[1])
        ],
        "rejected_vertiports": rejected_vertiports,
        "network_stores": [asdict(s) for s in full_network_stores],
        "scenarios": scenarios,
        "best_scenario": best_scenario,
    }


def _serialize_stage2_item(item: Stage2PadResult) -> Dict[str, object]:
    return {
        "pad_id": item.pad.pad_id,
        "name": item.pad.name,
        "city": item.pad.city,
        "base_demand_10k": round(item.base_demand_10k, 4),
        "attenuation_ratio": round(item.attenuation_ratio, 4),
        "adjusted_demand_10k": round(item.adjusted_demand_10k, 4),
        "adjusted_daily_flights": round(item.adjusted_daily_flights, 2),
        "passed": bool(item.passed),
        "reasons": item.reasons,
        "lat": item.pad.lat,
        "lon": item.pad.lon,
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

    # Accumulate pairwise attenuation penalty for each selected pad.
    for sid in combo_list:
        for oid in combo_set:
            if oid == sid:
                continue
            key = tuple(sorted((sid, oid)))
            penalties_by_sid[sid] += penalty_pairs.get(key, 0.0)

    bundle_items: List[Stage2PadResult] = []
    adjusted_sales_by_pad: Dict[str, float] = {}
    total_adjusted_demand = 0.0

    for sid in combo_list:
        base = candidate_by_id[sid]
        penalty = min(0.45, penalties_by_sid.get(sid, 0.0))
        # 无人机侧：衰减系数 = 空域/噪声冲突承载力衰减（相邻起降点共享空域导致承载力下降）
        attenuation_ratio = max(0.0, 1.0 - penalty)
        adjusted_demand = base.pad.rf_sales_10k * attenuation_ratio
        cp = city_params(base.pad.city)
        min_adjusted = float(cp.get("min_adjusted_demand_10k", 20.0))
        flights_rate = float(cp.get("flights_per_demand_wanyuan", 0.4))
        adjusted_flights = adjusted_demand * flights_rate

        # Stage-2 硬门槛：衰减后覆盖单量需达到 min_adjusted_demand_10k 才保留
        if adjusted_demand < min_adjusted:
            return None

        total_adjusted_demand += adjusted_demand
        adjusted_sales_by_pad[sid] = adjusted_demand
        bundle_items.append(
            Stage2PadResult(
                pad=base.pad,
                base_demand_10k=base.pad.rf_sales_10k,
                attenuation_ratio=attenuation_ratio,
                adjusted_demand_10k=adjusted_demand,
                adjusted_daily_flights=adjusted_flights,
                passed=True,
                reasons=[],
            )
        )

    ordered_items = sorted(bundle_items, key=lambda x: x.adjusted_demand_10k, reverse=True)
    return {
        "selected": [_serialize_stage2_item(item) for item in ordered_items],
        "adjusted_sales_by_pad": adjusted_sales_by_pad,
        "total_adjusted_demand_10k": float(total_adjusted_demand),
        "total_base_demand_10k": float(sum(item.base_demand_10k for item in ordered_items)),
        "total_investment_10k": float(sum(item.pad.initial_investment_10k for item in ordered_items)),
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
            "adjusted_sales_by_pad": {},
            "total_adjusted_demand_10k": 0.0,
            "total_base_demand_10k": 0.0,
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
                score = float(payload.get("total_adjusted_demand_10k", 0.0))
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
    # Stage2 候选剪枝：真实城市 passed 需求点可能上百，先按覆盖单量降序
    # 截断到前 STAGE2_MAX_CANDIDATES 个，避免组合/beam 搜索爆炸。
    candidates = sorted(
        candidates,
        key=lambda c: float(getattr(c, "covered_demand_10k", 0.0)),
        reverse=True,
    )[:STAGE2_MAX_CANDIDATES]
    if not candidates:
        return {
            "bundles": [
                {
                    "selected": [],
                    "adjusted_sales_by_pad": {},
                    "total_adjusted_demand_10k": 0.0,
                    "total_base_demand_10k": 0.0,
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
            if a.pad.pad_id >= b.pad.pad_id:
                continue
            if normalize_city(a.pad.city) != normalize_city(b.pad.city):
                continue
            d = dist.get((a.pad.pad_id, b.pad.pad_id), math.inf)
            pen = attenuation_for_pair(d)
            if pen >= 1.0:
                conflict_pairs.add((a.pad.pad_id, b.pad.pad_id))
            elif pen > 0.0:
                penalty_pairs[(a.pad.pad_id, b.pad.pad_id)] = pen

    candidate_by_id = {c.pad.pad_id: c for c in candidates}
    ids = [c.pad.pad_id for c in candidates]
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
                "adjusted_sales_by_pad": {},
                "total_adjusted_demand_10k": 0.0,
                "total_base_demand_10k": 0.0,
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
                "pad_a": a,
                "pad_b": b,
                "name_a": da.pad.name,
                "name_b": db.pad.name,
                "city": da.pad.city,
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


def _build_network_pads(
    pads: Sequence[LandingPad],
    adjusted_sales_by_pad: Dict[str, float],
    existing_sales_by_pad: Optional[Dict[str, float]] = None,
) -> List[LandingPad]:
    existing_sales = existing_sales_by_pad or _build_existing_sales_proxy_map(pads)
    out: List[LandingPad] = []
    for pad in pads:
        cp = city_params(pad.city)
        area_sqm = pad.area_sqm if pad.area_sqm > 0.0 else float(cp.get("standard_store_area_sqm", 650.0))

        if pad.is_existing:
            proxy_sales = existing_sales.get(pad.pad_id, pad.rf_sales_10k)
            if proxy_sales <= 0.0:
                proxy_sales = float(cp.get("standard_store_sales_10k", 800.0))
            out.append(
                LandingPad(
                    pad_id=pad.pad_id,
                    name=pad.name,
                    city=pad.city,
                    lat=pad.lat,
                    lon=pad.lon,
                    rf_sales_10k=proxy_sales,
                    area_sqm=area_sqm,
                    initial_investment_10k=pad.initial_investment_10k,
                    annual_fixed_cost_10k=pad.annual_fixed_cost_10k,
                    is_existing=True,
                )
            )
            continue

        if pad.pad_id not in adjusted_sales_by_pad:
            continue
        out.append(
            LandingPad(
                pad_id=pad.pad_id,
                name=pad.name,
                city=pad.city,
                lat=pad.lat,
                lon=pad.lon,
                rf_sales_10k=adjusted_sales_by_pad.get(pad.pad_id, pad.rf_sales_10k),
                area_sqm=area_sqm,
                initial_investment_10k=pad.initial_investment_10k,
                annual_fixed_cost_10k=pad.annual_fixed_cost_10k,
                is_existing=False,
            )
        )
    return out


def _compute_candidate_city_mean_sales(pads: Sequence[LandingPad]) -> Tuple[Dict[str, float], float]:
    by_city: Dict[str, List[float]] = {}
    all_sales: List[float] = []
    for pad in pads:
        if pad.is_existing or pad.rf_sales_10k <= 0.0:
            continue
        city = normalize_city(pad.city)
        by_city.setdefault(city, []).append(pad.rf_sales_10k)
        all_sales.append(pad.rf_sales_10k)

    mean_by_city = {
        city: (sum(values) / len(values))
        for city, values in by_city.items()
        if values
    }
    overall_mean = (sum(all_sales) / len(all_sales)) if all_sales else 0.0
    return mean_by_city, overall_mean


def _build_existing_sales_proxy_map(pads: Sequence[LandingPad]) -> Dict[str, float]:
    mean_by_city, overall_mean = _compute_candidate_city_mean_sales(pads)
    out: Dict[str, float] = {}
    for pad in pads:
        if not pad.is_existing:
            continue
        city = normalize_city(pad.city)
        proxy_sales = mean_by_city.get(city, overall_mean)
        if proxy_sales <= 0.0:
            cp = city_params(city)
            proxy_sales = max(pad.rf_sales_10k, float(cp.get("standard_store_sales_10k", 800.0)))
        out[pad.pad_id] = proxy_sales
    return out


def _evaluate_vertiport_pool(vertiports: Sequence[Vertiport]) -> Tuple[List[Tuple[Vertiport, float]], List[Dict[str, object]]]:
    eligible_vertiports: List[Tuple[Vertiport, float]] = []
    rejected_vertiports: List[Dict[str, object]] = []

    for vertiport in vertiports:
        ok, reasons = vertiport_eligibility(vertiport)
        lifecycle = vertiport_lifecycle_cost_10k(vertiport)
        row = {
            "vertiport_id": vertiport.vertiport_id,
            "name": vertiport.name,
            "city": vertiport.city,
            "lat": vertiport.lat,
            "lon": vertiport.lon,
            "lifecycle_cost_10k": round(lifecycle, 4),
            "rent_per_sqm_day": vertiport.rent_per_sqm_day,
        }
        if ok:
            eligible_vertiports.append((vertiport, lifecycle))
        else:
            row["reasons"] = reasons
            rejected_vertiports.append(row)
    return eligible_vertiports, rejected_vertiports


def _best_network_plan_for_p(
    full_network_stores: Sequence[LandingPad],
    eligible_vertiports: Sequence[Tuple[Vertiport, float]],
    distance_matrix: Dict[Tuple[str, str], float],
    p: int,
) -> Optional[Dict[str, object]]:
    if p <= 0 or p > len(eligible_vertiports):
        return None

    best_cost = math.inf
    best_plan: Optional[Dict[str, object]] = None

    for combo in itertools.combinations(eligible_vertiports, p):
        open_vertiports = [x[0] for x in combo]
        vertiport_cost = sum(x[1] for x in combo)
        delivery_total = 0.0
        assignments: List[Assignment] = []
        unassigned = False

        for pad in full_network_stores:
            same_city_rdcs = [r for r in open_vertiports if normalize_city(r.city) == normalize_city(pad.city)]
            if not same_city_rdcs:
                unassigned = True
                break

            best_vertiport = None
            best_distance = math.inf
            best_delivery = math.inf
            for vertiport in same_city_rdcs:
                distance_km = distance_lookup_km(vertiport, pad, distance_matrix)
                if not math.isfinite(distance_km):
                    continue
                delivery_cost = delivery_cost_pv_10k(distance_km, pad.rf_sales_10k, pad.city)
                if delivery_cost < best_delivery:
                    best_vertiport = vertiport
                    best_distance = distance_km
                    best_delivery = delivery_cost

            if best_vertiport is None:
                unassigned = True
                break

            delivery_total += best_delivery
            assignments.append(
                Assignment(
                    pad_id=pad.pad_id,
                    pad_name=pad.name,
                    pad_city=pad.city,
                    pad_is_existing=pad.is_existing,
                    demand_sales_10k=pad.rf_sales_10k,
                    vertiport_id=best_vertiport.vertiport_id,
                    vertiport_name=best_vertiport.name,
                    vertiport_city=best_vertiport.city,
                    pad_lat=pad.lat,
                    pad_lon=pad.lon,
                    vertiport_lat=best_vertiport.lat,
                    vertiport_lon=best_vertiport.lon,
                    distance_km=best_distance,
                    delivery_cost_pv_10k=best_delivery,
                )
            )

        if unassigned:
            continue

        total_cost = vertiport_cost + delivery_total
        if total_cost < best_cost:
            best_cost = total_cost
            best_plan = {
                "p": p,
                "vertiport_cost_10k": vertiport_cost,
                "delivery_cost_10k": delivery_total,
                "total_cost_10k": total_cost,
                "open_vertiports": [
                    {
                        "vertiport_id": r.vertiport_id,
                        "name": r.name,
                        "city": r.city,
                        "lat": r.lat,
                        "lon": r.lon,
                        "lifecycle_cost_10k": round(c, 4),
                        "altitude_limit_m": round(r.altitude_limit_m, 2),
                        "is_no_fly_zone": bool(r.is_no_fly_zone),
                        "max_flight_radius_km": round(r.max_flight_radius_km, 1),
                    }
                    for r, c in combo
                ],
                "assignments": assignments,
            }
    return best_plan


# ---- 组合爆炸防护（真实城市规模） ----
# 样例数据只有几十个候选，穷举可跑；深圳等真实城市 passed 需求点/停机坪
# 可达上百个，组合枚举 C(n,p) 会指数爆炸（如 C(235,4)≈1.2 亿）。
# 进入 Stage2/Stage3 搜索前，按覆盖能力降序截断候选到上限，控制规模。
# 对小数据集（候选数不超过上限）静默跳过，行为与原先完全一致。
STAGE2_MAX_CANDIDATES = 45
STAGE3_MAX_CANDIDATES = 60
# P 上限：不再用穷举硬锁 3，改由贪心/局部搜索支撑，支持 P=1..15。
# （折衷值：深圳 235 机坪 + P=25 + 截断 120/80 会算不完接口超时，
#   用户选定 P=15 / 截断 60/45 重试；若仍超时则回滚为 P=10/40/30）
STAGE3_MAX_P = 15
# 贪心构建停机坪集合时每条路径保留的候选宽度（beam），P 越大越接近最优。
STAGE3_GREEDY_BEAM_WIDTH = 3
# 同一批候选停机坪/起降点下的贪心结果缓存，避免对每个 P 重复计算。
_KERNEL_GREEDY_CACHE: Dict[object, Dict[int, List[Dict[str, object]]]] = {}


def _prune_vertiport_candidates(
    eligible_vertiports: Sequence[Tuple[Vertiport, float]],
    pads_for_eval: Sequence[LandingPad],
    distance_matrix: Dict[Tuple[str, str], float],
    max_candidates: int = STAGE3_MAX_CANDIDATES,
) -> List[Tuple[Vertiport, float]]:
    if len(eligible_vertiports) <= max_candidates:
        return list(eligible_vertiports)
    scored: List[Tuple[float, Vertiport, float]] = []
    for vertiport, lifecycle in eligible_vertiports:
        demand = 0.0
        for pad in pads_for_eval:
            if normalize_city(vertiport.city) != normalize_city(pad.city):
                continue
            d = distance_lookup_km(vertiport, pad, distance_matrix)
            if math.isfinite(d):
                demand += pad.rf_sales_10k
        scored.append((demand, vertiport, lifecycle))
    # 可达需求降序，同需求时成本(cost)升序，保证同覆盖度下优先低建设成本
    scored.sort(key=lambda x: (-x[0], x[2]))
    return [(v, c) for _, v, c in scored[:max_candidates]]


def _greedy_build_vertiport_plans(
    candidates: Sequence[Tuple[Vertiport, float]],
    pads_for_eval: Sequence[LandingPad],
    distance_matrix: Dict[Tuple[str, str], float],
    max_p: int,
    drones_per_vertiport: int = DRONES_PER_VERTIPORT,
    drone_order_rate_hour: int = DRONE_ORDER_RATE_PER_HOUR,
) -> Dict[int, List[Dict[str, object]]]:
    """贪心 + 局部搜索（beam 宽度）构建每个 P 的停机坪开放集合。

    贪心启发式：从覆盖需求最大的点出发，每次迭代只尝试能带来最大
    「新增覆盖单量」的候选停机坪，避免穷举 C(n,p) 的上亿组合。同时对每条
    贪心路径保留 beam_width 个备选，接近局部最优解；P 从 1 递增到 max_p。
    """
    beams: List[List[Tuple[Vertiport, float]]] = [[]]  # 当前层的开放集合
    plans_by_p: Dict[int, List[Dict[str, object]]] = {}

    def _subset_demand(subset: Sequence[Tuple[Vertiport, float]]) -> float:
        return sum(pad.rf_sales_10k for pad in _covered_pads(subset))

    def _constrained_assign(
        subset: Sequence[Tuple[Vertiport, float]],
    ) -> Tuple[Dict[str, Dict[str, object]], List[LandingPad]]:
        """带运力约束的把 pad 归属到最近停机坪。

        约束（Excel 原文）：
            - 每个停机坪最多服务 VERTIPORT_MAX_PADS(11) 个起降点位置；
            - 每个停机坪承载订单的峰值小时需求 ≤ 无人机数×单量/小时（可由前端调整）。
        归属按「距离最近 + 单量优先」分配，机坪达到 11 点或峰值运力后不再接新点。
        """
        open_vertiports = [x[0] for x in subset]
        # 每个候选 pad 最近机坪 + 距离（限定覆盖半径 5km）
        pad_candidates: Dict[str, List[Tuple[Vertiport, float, LandingPad]]] = {}
        for pad in pads_for_eval:
            for vertiport in open_vertiports:
                if normalize_city(vertiport.city) != normalize_city(pad.city):
                    continue
                d = distance_lookup_km(vertiport, pad, distance_matrix)
                if not math.isfinite(d) or d > COVERAGE_RADIUS_KM:
                    continue
                pad_candidates.setdefault(vertiport.vertiport_id, []).append((vertiport, d, pad))

        # 单机坪约束：先按距离最近优先，超 11 点或峰值运力后截断
        pad_best: Dict[str, Dict[str, object]] = {}
        covered: List[LandingPad] = []
        # 峰值小时运力（单机坪）：无人机数 × 单量/小时（前端可调）
        vertiport_capacity_hour = drones_per_vertiport * drone_order_rate_hour
        for vid, cands in pad_candidates.items():
            cands.sort(key=lambda x: (x[1], x[0].vertiport_id))  # 距离升序
            assigned_peak = 0.0
            for vertiport, d, pad in cands[:VERTIPORT_MAX_PADS]:
                # 该点峰值小时需求近似：按其在机坪内单量的比例，仅用计数约束
                peak_hour = pad.rf_sales_10k / 7.0 * PEAK_HOUR_FACTOR / 24.0
                if assigned_peak + peak_hour > vertiport_capacity_hour:
                    continue  # 运力满载，该机坪不再接管此点（需另开机坪）
                assigned_peak += peak_hour
                if pad.pad_id in pad_best:
                    continue
                pad_best[pad.pad_id] = {"vertiport": vertiport, "distance_km": d}
                covered.append(pad)
        return pad_best, covered

    def _covered_pads(subset: Sequence[Tuple[Vertiport, float]]) -> List[LandingPad]:
        _, covered = _constrained_assign(subset)
        return covered

    def _make_plan(subset: Sequence[Tuple[Vertiport, float]]) -> Dict[str, object]:
        open_vertiports = [x[0] for x in subset]
        vertiport_cost = sum(x[1] for x in subset)
        pad_best, _ = _constrained_assign(subset)
        return {
            "p": len(subset),
            "vertiport_cost_10k": vertiport_cost,
            "open_vertiports": [
                {
                    "vertiport_id": r.vertiport_id,
                    "name": r.name,
                    "city": r.city,
                    "lat": r.lat,
                    "lon": r.lon,
                    "lifecycle_cost_10k": round(c, 4),
                    "altitude_limit_m": round(r.altitude_limit_m, 2),
                    "is_no_fly_zone": bool(r.is_no_fly_zone),
                    "max_flight_radius_km": round(r.max_flight_radius_km, 1),
                }
                for r, c in subset
            ],
            "pad_best": pad_best,
        }

    for depth in range(1, max_p + 1):
        # 从当前 beam 的每个子集，尝试添加任一未用候选 -> 得到下一层候选子集
        expansions: List[List[Tuple[Vertiport, float]]] = []
        for beam in beams:
            used_ids = {x[0].vertiport_id for x in beam}
            for cand in candidates:
                if cand[0].vertiport_id in used_ids:
                    continue
                expansions.append(beam + [cand])

        if not expansions:
            break

        # 局部搜索排序：按新增覆盖单量的边际收益降序，保留 beam 宽度
        expansions.sort(key=lambda b: _subset_demand(b), reverse=True)
        beams = expansions[:STAGE3_GREEDY_BEAM_WIDTH]
        plans_by_p[depth] = [_make_plan(b) for b in beams]

    return plans_by_p


def _build_combo_kernel_for_p(
    pads_for_eval: Sequence[LandingPad],
    eligible_vertiports: Sequence[Tuple[Vertiport, float]],
    distance_matrix: Dict[Tuple[str, str], float],
    p: int,
    drones_per_vertiport: int = DRONES_PER_VERTIPORT,
    drone_order_rate_hour: int = DRONE_ORDER_RATE_PER_HOUR,
) -> Dict[str, object]:
    combo_plans: List[Dict[str, object]] = []
    nonnegative_total_cost_bound = True

    # 组合爆炸防护：候选剪枝；P 交由贪心/局部搜索支撑，不再穷举全组合。
    candidates = _prune_vertiport_candidates(eligible_vertiports, pads_for_eval, distance_matrix)
    if p > len(candidates):
        return {"p": p, "plans": [], "nonnegative_total_cost_bound": True}

    # 缓存键：候选序列 + 起降点序列 + 运力参数（不同无人机数会得到不同贪心方案）.
    cand_key = tuple(v.vertiport_id for v, _ in candidates)
    pad_key = tuple(p.pad_id for p in pads_for_eval)
    cache_key = (cand_key, pad_key, drones_per_vertiport, drone_order_rate_hour)

    if cache_key not in _KERNEL_GREEDY_CACHE:
        plans_by_p = _greedy_build_vertiport_plans(
            candidates, pads_for_eval, distance_matrix,
            max_p=min(STAGE3_MAX_P, len(candidates)),
            drones_per_vertiport=drones_per_vertiport,
            drone_order_rate_hour=drone_order_rate_hour,
        )
        _KERNEL_GREEDY_CACHE[cache_key] = plans_by_p

    combo_plans = list(_KERNEL_GREEDY_CACHE[cache_key].get(p, []))
    return {
        "plans": combo_plans,
        "nonnegative_total_cost_bound": True,
    }


def _evaluate_bundle_with_combo_kernel(
    bundle: Dict[str, object],
    combo_kernel: Dict[str, object],
    store_by_id: Dict[str, LandingPad],
    existing_sales_by_pad: Dict[str, float],
    mature_pen: float = DEFAULT_MATURE_PENETRATION,
) -> Optional[Dict[str, object]]:
    adjusted_sales_by_pad: Dict[str, float] = dict(bundle.get("adjusted_sales_by_pad") or {})
    network_sales_by_pad: Dict[str, float] = dict(existing_sales_by_pad)
    network_sales_by_pad.update(adjusted_sales_by_pad)

    best_total_cost = math.inf
    best_delivery_total = 0.0
    best_plan = None
    best_selected_assignments: List[Assignment] = []

    for plan in combo_kernel.get("plans") or []:
        pad_best = plan["pad_best"]
        selected_assignments: List[Assignment] = []
        selected_delivery = 0.0
        feasible = True

        for sid, sales in network_sales_by_pad.items():
            info = pad_best.get(sid)
            if info is None:
                feasible = False
                break

            pad = store_by_id.get(sid)
            if pad is None:
                feasible = False
                break
            vertiport = info["vertiport"]
            distance_km = float(info["distance_km"])
            dcost = delivery_cost_pv_10k(distance_km, sales, pad.city, mature_pen)
            selected_delivery += dcost
            selected_assignments.append(
                Assignment(
                    pad_id=pad.pad_id,
                    pad_name=pad.name,
                    pad_city=pad.city,
                    pad_is_existing=pad.is_existing,
                    demand_sales_10k=sales,
                    vertiport_id=vertiport.vertiport_id,
                    vertiport_name=vertiport.name,
                    vertiport_city=vertiport.city,
                    pad_lat=pad.lat,
                    pad_lon=pad.lon,
                    vertiport_lat=vertiport.lat,
                    vertiport_lon=vertiport.lon,
                    distance_km=distance_km,
                    delivery_cost_pv_10k=dcost,
                )
            )

        if not feasible:
            continue

        delivery_total = selected_delivery
        total_cost = float(plan["vertiport_cost_10k"]) + delivery_total
        if total_cost < best_total_cost:
            best_total_cost = total_cost
            best_delivery_total = delivery_total
            best_plan = plan
            best_selected_assignments = selected_assignments

    if best_plan is None:
        return None

    return {
        "p": int(best_plan["p"]),
        "vertiport_cost_10k": float(best_plan["vertiport_cost_10k"]),
        "delivery_cost_10k": float(best_delivery_total),
        "total_cost_10k": float(best_total_cost),
        "open_vertiports": best_plan["open_vertiports"],
        "pad_best": best_plan.get("pad_best") or {},
        "assignments": best_selected_assignments,
    }


def _build_stage3_scenario(
    plan: Dict[str, object],
    full_network_stores: Sequence[LandingPad],
    mature_pen: float = DEFAULT_MATURE_PENETRATION,
) -> Dict[str, object]:
    assignments: List[Assignment] = list(plan["assignments"])
    total_weight = sum(a.demand_sales_10k for a in assignments) or 1.0
    avg_distance = sum(a.distance_km * a.demand_sales_10k for a in assignments) / total_weight

    # —— 纯选址口径：不再计算 ROI / 成本折现。 ——
    # 输出纯选址指标：覆盖起降点数、覆盖单量、平均距离、机坪数与单机坪承载。
    n_vertiports = max(1, len(plan.get("open_vertiports") or []))
    assigned_orders = float(sum(a.demand_sales_10k for a in assignments))
    # 覆盖起降点数取贪心的真实覆盖（pad_best），而非仅统计运营网络选中的点。
    total_pads = int(len(plan.get("pad_best") or {}) or len(assignments))

    # 城市维度：只汇总覆盖单量与平均距离，不再含成本。
    city_breakdown: Dict[str, Dict[str, float]] = {}
    for a in assignments:
        c = a.pad_city
        city_breakdown.setdefault(c, {"sales_weight": 0.0, "distance_weight": 0.0, "pads": 0})
        city_breakdown[c]["sales_weight"] += a.demand_sales_10k
        city_breakdown[c]["distance_weight"] += a.distance_km * a.demand_sales_10k
        city_breakdown[c]["pads"] += 1
    for c in city_breakdown:
        sw = city_breakdown[c]["sales_weight"] or 1.0
        city_breakdown[c]["avg_distance_km"] = city_breakdown[c]["distance_weight"] / sw
        city_breakdown[c]["avg_distance_km"] = round(city_breakdown[c]["avg_distance_km"], 4)
        city_breakdown[c]["pads"] = int(city_breakdown[c]["pads"])
        del city_breakdown[c]["distance_weight"]
        del city_breakdown[c]["sales_weight"]

    return {
        "p": int(plan["p"]),
        "open_vertiport_count": n_vertiports,
        "covered_pad_count": total_pads,
        "covered_orders_10k": round(assigned_orders, 4),
        "avg_distance_km": round(avg_distance, 4),
        "open_vertiports": list(plan["open_vertiports"]),
        "city_breakdown": city_breakdown,
        "assignments": [
            {
                "pad_id": a.pad_id,
                "pad_name": a.pad_name,
                "pad_city": a.pad_city,
                "pad_is_existing": a.pad_is_existing,
                "pad_lat": a.pad_lat,
                "pad_lon": a.pad_lon,
                "demand_sales_10k": round(a.demand_sales_10k, 4),
                "vertiport_id": a.vertiport_id,
                "vertiport_name": a.vertiport_name,
                "vertiport_city": a.vertiport_city,
                "vertiport_lat": a.vertiport_lat,
                "vertiport_lon": a.vertiport_lon,
                "distance_km": round(a.distance_km, 4),
                "delivery_cost_pv_10k": round(a.delivery_cost_pv_10k, 4),
            }
            for a in sorted(assignments, key=lambda x: x.delivery_cost_pv_10k, reverse=True)
        ],
    }


def optimize_stage2_stage3_joint(
    pads: Sequence[LandingPad],
    stage1_results: Sequence[Stage1Result],
    vertiports: Sequence[Vertiport],
    distance_matrix: Dict[Tuple[str, str], float],
    p_values: Sequence[int],
    max_new_stores: int = 8,
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
    mature_penetration: float = DEFAULT_MATURE_PENETRATION,
    drones_per_vertiport: int = DRONES_PER_VERTIPORT,
    drone_order_rate_hour: int = DRONE_ORDER_RATE_PER_HOUR,
) -> Dict[str, object]:
    """
    Joint objective:
        maximize new-pad adjusted NPV
                 - delivery network cost (PV)
    """
    stage2_space = _enumerate_stage2_bundles(
        stage1_results,
        max_new_stores=max_new_stores,
        threshold_overrides=threshold_overrides,
    )
    mature_pen = float(mature_penetration or DEFAULT_MATURE_PENETRATION)
    bundles: List[Dict[str, object]] = list(stage2_space["bundles"])
    distance_alerts = list(stage2_space["distance_alerts"])
    stage2_search_mode = str(stage2_space.get("search_mode") or "unknown")
    stage2_theoretical_bundle_count = int(stage2_space.get("theoretical_bundle_count") or 0)
    stage2_evaluated_bundle_count = int(stage2_space.get("evaluated_bundle_count") or 0)

    passed_new_pad_ids = {r.pad.pad_id for r in stage1_results if r.passed}
    existing_pad_ids = {s.pad_id for s in pads if s.is_existing}
    pads_for_eval = [s for s in pads if (s.pad_id in passed_new_pad_ids or s.pad_id in existing_pad_ids)]
    store_by_id = {s.pad_id: s for s in pads_for_eval}
    existing_sales_by_pad = _build_existing_sales_proxy_map(pads)

    eligible_vertiports, rejected_vertiports = _evaluate_vertiport_pool(vertiports)
    eligible_payload = [
        {
            "vertiport_id": r.vertiport_id,
            "name": r.name,
            "city": r.city,
            "lat": r.lat,
            "lon": r.lon,
            "lifecycle_cost_10k": round(c, 4),
        }
        for r, c in sorted(eligible_vertiports, key=lambda x: x[1])
    ]

    valid_p_values = sorted(
        {p for p in p_values if p > 0 and p <= STAGE3_MAX_P and p <= len(eligible_vertiports)}
    )
    combo_kernel_by_p: Dict[int, Dict[str, object]] = {}
    can_bound_total_cost_nonnegative = True
    for p in valid_p_values:
        kernel = _build_combo_kernel_for_p(
                pads_for_eval=pads_for_eval,
                eligible_vertiports=eligible_vertiports,
                distance_matrix=distance_matrix,
                p=p,
                drones_per_vertiport=drones_per_vertiport,
                drone_order_rate_hour=drone_order_rate_hour,
            )
        combo_kernel_by_p[p] = kernel
        can_bound_total_cost_nonnegative = can_bound_total_cost_nonnegative and bool(
            kernel.get("nonnegative_total_cost_bound", False)
        )

    bundles_by_stage2_score = sorted(
        bundles,
        key=lambda b: float(b.get("total_adjusted_demand_10k", 0.0)),
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
        best_network_stores: Optional[List[LandingPad]] = None
        evaluated_bundle_count = 0
        pruned_by_upper_bound = 0

        for bundle in bundles_by_stage2_score:
            adjusted_sales_by_pad = dict(bundle.get("adjusted_sales_by_pad") or {})
            full_network_stores = _build_network_pads(
                pads,
                adjusted_sales_by_pad,
                existing_sales_by_pad=existing_sales_by_pad,
            )
            if not full_network_stores:
                continue

            # Safe pruning when delivery cost is guaranteed non-negative:
            # joint objective upper bound for this bundle is stage2_adjusted_npv.
            stage2_score = float(bundle.get("total_adjusted_demand_10k", 0.0))
            if can_bound_total_cost_nonnegative and stage2_score <= best_joint_objective:
                pruned_by_upper_bound += 1
                continue

            plan = _evaluate_bundle_with_combo_kernel(
                bundle,
                combo_kernel,
                store_by_id,
                existing_sales_by_pad=existing_sales_by_pad,
                mature_pen=mature_pen,
            )
            if plan is None:
                continue

            evaluated_bundle_count += 1
            delivery_cost = float(plan.get("delivery_cost_10k", 0.0))
            joint_objective = float(bundle["total_adjusted_demand_10k"]) - delivery_cost

            if joint_objective > best_joint_objective:
                best_joint_objective = joint_objective
                best_bundle = bundle
                best_plan = plan
                best_network_stores = full_network_stores

        if best_bundle is None or best_plan is None or best_network_stores is None:
            continue

        scenario = _build_stage3_scenario(best_plan, best_network_stores, mature_pen=mature_pen)
        scenario.update(
            {
                "selected_new_stores": list(best_bundle["selected"]),
                "selected_store_count": len(best_bundle["selected"]),
                "stage2_adjusted_demand_10k": round(float(best_bundle["total_adjusted_demand_10k"]), 4),
                "stage2_base_demand_10k": round(float(best_bundle["total_base_demand_10k"]), 4),
                "stage2_total_investment_10k": round(float(best_bundle["total_investment_10k"]), 4),
                "network_total_cost_10k": round(float(best_plan["total_cost_10k"]), 4),
                "objective_value_10k": round(float(best_joint_objective), 4),
                "stage2_bundles_evaluated_for_p": evaluated_bundle_count,
                "stage2_bundles_pruned_for_p": pruned_by_upper_bound,
            }
        )
        scenarios.append(scenario)

    # —— 纯选址目标：在运力约束下，优先选择覆盖 Stage1 起降点最多的网络 ——
    # 排序键：覆盖起降点数降序 → 平均配送距离升序（覆盖优先，距离次之）。
    scenarios = sorted(
        scenarios,
        key=lambda x: (
            -int(x.get("covered_pad_count", 0) or 0),
            float(x.get("avg_distance_km", math.inf)),
        ),
    )
    best_scenario = scenarios[0] if scenarios else None
    # 覆盖率最高的方案打上「物理网络推荐」标记（前端展示用）。
    if best_scenario is not None:
        best_scenario["recommended"] = True

    fallback_bundle = max(bundles, key=lambda b: float(b.get("total_adjusted_demand_10k", 0.0))) if bundles else {
        "selected": [],
        "adjusted_sales_by_pad": {},
        "total_adjusted_demand_10k": 0.0,
        "total_base_demand_10k": 0.0,
        "total_investment_10k": 0.0,
    }
    chosen_bundle = best_scenario if best_scenario is not None else {
        "selected_new_stores": list(fallback_bundle["selected"]),
        "stage2_adjusted_demand_10k": round(float(fallback_bundle["total_adjusted_demand_10k"]), 4),
        "stage2_base_demand_10k": round(float(fallback_bundle["total_base_demand_10k"]), 4),
        "stage2_total_investment_10k": round(float(fallback_bundle["total_investment_10k"]), 4),
        "objective_value_10k": None,
    }

    selected_rows = list(chosen_bundle.get("selected_new_stores") or [])
    selected_sales_map = {
        str(r.get("pad_id") or ""): to_float(r.get("adjusted_demand_10k"), to_float(r.get("base_demand_10k"), 0.0))
        for r in selected_rows
        if str(r.get("pad_id") or "")
    }
    network_stores = _build_network_pads(
        pads,
        selected_sales_map,
        existing_sales_by_pad=existing_sales_by_pad,
    )

    stage2_payload = {
        "selected": selected_rows,
        "total_adjusted_demand_10k": chosen_bundle.get("stage2_adjusted_demand_10k", 0.0),
        "total_base_demand_10k": chosen_bundle.get("stage2_base_demand_10k", 0.0),
        "total_investment_10k": chosen_bundle.get("stage2_total_investment_10k", 0.0),
        "distance_alerts": distance_alerts,
        "joint_objective_value_10k": chosen_bundle.get("objective_value_10k"),
        "objective_definition": "max(新增起降点修正NPV - 全网络配送成本PV[含现存+新增])",
        "search_mode": stage2_search_mode,
        "theoretical_bundle_count": stage2_theoretical_bundle_count,
        "evaluated_bundle_count": stage2_evaluated_bundle_count,
    }

    stage3_payload = {
        "eligible_vertiports": eligible_payload,
        "rejected_vertiports": rejected_vertiports,
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
    pad_rows: Sequence[Dict[str, object]],
    vertiport_rows: Sequence[Dict[str, object]],
    distance_rows: Optional[Sequence[Dict[str, object]]] = None,
    max_new_stores: int = 8,
    p_values: Optional[Sequence[int]] = None,
    focus_city: Optional[str] = None,
    threshold_overrides: Optional[Dict[str, Dict[str, float]]] = None,
    mature_penetration: float = DEFAULT_MATURE_PENETRATION,
    drones_per_vertiport: int = DRONES_PER_VERTIPORT,
    drone_order_rate_hour: int = DRONE_ORDER_RATE_PER_HOUR,
) -> Dict[str, object]:
    focus_city_norm = normalize_city(focus_city or "beijing")
    if focus_city_norm not in CITY_GIS_META:
        focus_city_norm = "beijing"
    pad_rows = filter_rows_by_city(pad_rows, focus_city_norm)
    vertiport_rows = filter_rows_by_city(vertiport_rows, focus_city_norm)
    mature_pen = float(mature_penetration or DEFAULT_MATURE_PENETRATION)

    pads = parse_pads(pad_rows)
    vertiports = parse_vertiports(vertiport_rows)
    distance_matrix = parse_distance_matrix(distance_rows or [])

    stage1 = evaluate_stage1(
        pads,
        threshold_overrides=threshold_overrides,
        vertiports=vertiports,
        distance_matrix=distance_matrix,
        mature_penetration=mature_pen,
    )

    if p_values is None:
        p_values = [1, 2, 3]
    joint = optimize_stage2_stage3_joint(
        pads=pads,
        stage1_results=stage1,
        vertiports=vertiports,
        distance_matrix=distance_matrix,
        p_values=p_values,
        max_new_stores=max_new_stores,
        threshold_overrides=threshold_overrides,
        mature_penetration=mature_pen,
        drones_per_vertiport=drones_per_vertiport,
        drone_order_rate_hour=drone_order_rate_hour,
    )
    stage2 = joint["stage2"]
    stage3 = joint["stage3"]

    selected_ids = {str(s.get("pad_id")) for s in stage2.get("selected", [])}

    stage1_rows: List[Dict[str, object]] = []
    for row in stage1:
        stage1_rows.append(
            {
                "pad_id": row.pad.pad_id,
                "name": row.pad.name,
                "city": row.pad.city,
                "lat": row.pad.lat,
                "lon": row.pad.lon,
                # 无人机侧 stage1 指标
                "covered_demand_10k": round(row.covered_demand_10k, 4),
                "est_daily_flights": round(row.est_daily_flights, 2),
                "space_ok": bool(row.space_ok),
                "passed": row.passed,
                "is_selected_stage2": row.pad.pad_id in selected_ids,
                "reasons": row.reasons,
            }
        )

    best_scenario = stage3.get("best_scenario") or {}
    best_assignments = best_scenario.get("assignments") or []

    gis_stage1_points = [
        {
            "pad_id": r["pad_id"],
            "name": r["name"],
            "city": r["city"],
            "lat": r["lat"],
            "lon": r["lon"],
            "passed": r["passed"],
            # 无人机侧 stage1 GIS 弹窗指标
            "covered_demand_10k": r["covered_demand_10k"],
            "est_daily_flights": r["est_daily_flights"],
            "space_ok": bool(r["space_ok"]),
        }
        for r in stage1_rows
        if is_valid_coord(float(r["lat"]), float(r["lon"]))
    ]

    gis_stage2_selected = [
        {
            "pad_id": s["pad_id"],
            "name": s["name"],
            "city": s["city"],
            "lat": s["lat"],
            "lon": s["lon"],
            "radius_300_m": 300,
            "radius_500_m": 500,
            "adjusted_demand_10k": s.get("adjusted_demand_10k", 0.0),
            "adjusted_daily_flights": s.get("adjusted_daily_flights", 0.0),
        }
        for s in stage2.get("selected", [])
        if is_valid_coord(float(s.get("lat", 0.0)), float(s.get("lon", 0.0)))
    ]

    gis_network_lines = [
        {
            "pad_id": a["pad_id"],
            "pad_name": a["pad_name"],
            "pad_city": a["pad_city"],
            "pad_is_existing": bool(a.get("pad_is_existing", False)),
            "pad_lat": a["pad_lat"],
            "pad_lon": a["pad_lon"],
            "vertiport_id": a["vertiport_id"],
            "vertiport_name": a["vertiport_name"],
            "vertiport_city": a["vertiport_city"],
            "vertiport_lat": a["vertiport_lat"],
            "vertiport_lon": a["vertiport_lon"],
            "distance_km": a["distance_km"],
        }
        for a in best_assignments
    ]

    summary = {
        "total_pad_rows": len(pads),
        "existing_pads": sum(1 for s in pads if s.is_existing),
        "new_pad_candidates": sum(1 for s in pads if not s.is_existing),
        "optimization_scope": "existing_and_selected_new_stores",
        "stage1_passed": sum(1 for r in stage1 if r.passed),
        "stage2_selected": len(stage2.get("selected", [])),
        "stage2_search_mode": stage2.get("search_mode"),
        "stage2_evaluated_bundle_count": stage2.get("evaluated_bundle_count"),
        "eligible_vertiports": len(stage3.get("eligible_vertiports", [])),
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
            "stage3_open_vertiports": best_scenario.get("open_vertiports") or [],
            "distance_alerts": stage2.get("distance_alerts", []),
        },
    }

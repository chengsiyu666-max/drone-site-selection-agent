"""
agent_tools.py — Agent 的工具注册表。

把现有能力（optimizer.run_full_model / get_city_configs、app 的样例装载与逆地理编码、
rag_retriever 检索）包装成 LLM 可调用的工具函数。每个工具带 OpenAI 函数 JSON Schema。

关键设计：
- run_site_selection 返回**紧凑摘要**而非完整 result，避免把大对象塞进上下文（上下文工程）。
- 所有工具标记 read_only=True；执行层支持 ThreadPoolExecutor 并行（对应「只读并行」）。
- 只读复用现有模块，不修改任何核心算法。
"""
from __future__ import annotations

import json
import math
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Tuple

import rag_retriever

from app import (  # noqa: F401  (触发 .env 加载 + 复用样例装载逻辑)
    BUILTIN_EXISTING_PADS_FILE,
    SAMPLE_DIR,
    _amap_regeo_label,
    _parse_excel_upload,
    merge_pad_rows,
    parse_csv_file,
)
import optimizer as O

# ---------------------------------------------------------------------------
# 装载样例数据（与 app.py /api/run-sample 语义一致，纯复用）
# ---------------------------------------------------------------------------


def _load_sample(city: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    norm = O.normalize_city(city)
    city_dir = SAMPLE_DIR / norm
    if city_dir.exists():
        pad_rows = parse_csv_file(city_dir / "stores.csv")
        vertiport_rows = parse_csv_file(city_dir / "rdcs.csv")
        dist_rows = parse_csv_file(city_dir / "distances.csv")
    else:
        pad_rows = parse_csv_file(SAMPLE_DIR / "stores.csv")
        vertiport_rows = parse_csv_file(SAMPLE_DIR / "rdcs.csv")
        dist_rows = parse_csv_file(SAMPLE_DIR / "distances.csv")
    pad_rows = merge_pad_rows(pad_rows, parse_csv_file(BUILTIN_EXISTING_PADS_FILE))
    return pad_rows, vertiport_rows, dist_rows


# ---------------------------------------------------------------------------
# 用户自定义数据集注册表（load_csv 注册，run_site_selection 按 dataset_id 取用）
# ---------------------------------------------------------------------------

_CUSTOM_DATASETS: Dict[str, Dict[str, Any]] = {}

# 数据契约：必需列（缺了直接报缺列）；可选列有默认值，见 optimizer.parse_pads/parse_vertiports
_PAD_REQUIRED_COLS = ("pad_id", "lat", "lon")
_VERTIPORT_REQUIRED_COLS = ("vertiport_id", "lat", "lon")


def _read_table(path_str: str, label: str) -> List[Dict[str, Any]]:
    """按扩展名读取 CSV 或 Excel（.xlsx/.xls/.xlsm），返回 dict 行列表。"""
    p = Path(path_str).expanduser()
    if not p.exists() or not p.is_file():
        raise ValueError(f"{label} 文件不存在: {path_str}")
    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xls", ".xlsm"):
        return _parse_excel_upload(p.read_bytes(), p.name)
    if suffix == ".csv":
        return parse_csv_file(p)
    raise ValueError(f"{label} 仅支持 .csv/.xlsx/.xls，实际为 {suffix or '(无扩展名)'}")


def dataset_exists(dataset_id: str) -> bool:
    """判断 dataset_id 是否仍在进程内注册表（服务重启后会失效）。"""
    return bool(dataset_id) and dataset_id in _CUSTOM_DATASETS


def _missing_cols(rows: List[Dict[str, Any]], required: Tuple[str, ...]) -> List[str]:
    if not rows:
        return list(required)
    cols = set(rows[0].keys())
    # pad_id/vertiport_id 可用 id 兜底（与 parse_pads/parse_vertiports 语义一致）
    if "pad_id" in cols or "vertiport_id" in cols or "id" in cols:
        required = tuple(c for c in required if c not in ("pad_id", "vertiport_id"))
    return [c for c in required if c not in cols]


def load_csv(
    stores_path: str,
    rdcs_path: str = "",
    distances_path: str = "",
    city: str = "",
) -> Dict[str, Any]:
    """装载用户上传的真实数据文件，注册成数据集并返回 dataset_id。

    stores_path 为候选起降点表（必需），rdcs_path 为候选机坪表（必需，缺省会复用内置样例机坪），
    distances_path 为距离矩阵（可选，缺省时引擎用球面距离兜底）。
    """
    pad_rows = _read_table(stores_path, "stores(候选起降点)")
    if not pad_rows:
        raise ValueError("stores(候选起降点) 文件为空或没有数据行")

    warnings: List[str] = []
    missing_pad = _missing_cols(pad_rows, _PAD_REQUIRED_COLS)
    if missing_pad:
        raise ValueError(
            f"stores 缺少必需列: {', '.join(missing_pad)}；"
            "至少需要 pad_id(或id)/lat/lon，需求量请放在 rf_sales_10k(万) 列"
        )

    # 城市列处理：引擎按 city 列过滤数据，缺列会导致所有行被全部剔除（静默 0 结果）。
    city_norm = ""
    if city:
        city_norm = O.normalize_city(city)
        if city_norm not in O.CITY_GIS_META:
            raise ValueError(f"不支持的城市: {city}，可选 beijing/hangzhou/shenzhen")

    def _ensure_city(rows: List[Dict[str, Any]], label: str) -> None:
        if not rows:
            return
        has_col = "city" in rows[0]
        if not has_col and not city_norm:
            raise ValueError(
                f"{label} 没有 city 列，也未指定城市参数；引擎会按城市过滤数据，"
                "请在上传时选择城市（beijing/hangzhou/shenzhen），或给文件加一列 city"
            )
        if not has_col:
            for r in rows:
                r["city"] = city_norm
            warnings.append(f"{label} 无 city 列，已统一标注为 {city_norm}")
            return
        # 有 city 列但没有填值：用指定城市兜底
        if city_norm:
            filled = 0
            for r in rows:
                if not str(r.get("city") or "").strip():
                    r["city"] = city_norm
                    filled += 1
            if filled:
                warnings.append(f"{label} 有 {filled} 行 city 为空，已按 {city_norm} 补全")

    _ensure_city(pad_rows, "stores(候选起降点)")

    if rdcs_path:
        vertiport_rows = _read_table(rdcs_path, "rdcs(候选机坪)")
        if not vertiport_rows:
            raise ValueError("rdcs(候选机坪) 文件为空或没有数据行")
        missing_vp = _missing_cols(vertiport_rows, _VERTIPORT_REQUIRED_COLS)
        if missing_vp:
            raise ValueError(f"rdcs 缺少必需列: {', '.join(missing_vp)}；至少需要 vertiport_id(或id)/lat/lon")
        _ensure_city(vertiport_rows, "rdcs(候选机坪)")
        # 净空高度缺列会按 0 处理，被 Stage3「净空<3m 剔除」硬约束全部过滤掉 → 静默 0 结果。
        vp_cols = set(vertiport_rows[0].keys())
        if "altitude_limit_m" not in vp_cols and "clear_height_m" not in vp_cols:
            warnings.append(
                "rdcs 缺少 altitude_limit_m(净空高度米) 列：缺失值按 0 处理，"
                "会被 Stage3「净空<3m 剔除」硬约束全部过滤，导致无选址结果；请补上该列"
            )
    else:
        _, vertiport_rows, _ = _load_sample(city or "beijing")
        warnings.append("未提供机坪表，已回退到内置样例机坪（可能与真实城市不符）")

    dist_rows: List[Dict[str, Any]] = []
    if distances_path:
        dist_rows = _read_table(distances_path, "distances(距离矩阵)")
    else:
        warnings.append("未提供距离矩阵，引擎将用 haversine 球面距离兜底")

    if "rf_sales_10k" not in pad_rows[0] and "annual_sales_10k" not in pad_rows[0]:
        warnings.append("stores 没有 rf_sales_10k/annual_sales_10k 需求列，需求量将按 0 处理，选址结果不可用")

    dataset_id = uuid.uuid4().hex[:8]
    _CUSTOM_DATASETS[dataset_id] = {
        "pad_rows": pad_rows,
        "vertiport_rows": vertiport_rows,
        "dist_rows": dist_rows,
    }
    return {
        "dataset_id": dataset_id,
        "stores_rows": len(pad_rows),
        "rdcs_rows": len(vertiport_rows),
        "distances_rows": len(dist_rows),
        "stores_columns": sorted(pad_rows[0].keys()),
        "rdcs_columns": sorted(vertiport_rows[0].keys()),
        "warnings": warnings,
        "hint": f"之后调用 run_site_selection 时传 dataset_id='{dataset_id}' 即可使用这份数据。",
    }


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------


def run_site_selection(
    city: str,
    max_new_stores: int = 10,
    p_values: Any = None,
    drones_per_vertiport: int = 20,
    drone_order_rate_hour: int = 10,
    dataset_id: str = "",
) -> Dict[str, Any]:
    """对指定城市跑三阶段选址引擎，返回紧凑摘要。city ∈ beijing/hangzhou/shenzhen。

    dataset_id 非空时使用 load_csv 注册的自定义数据；否则用内置样例。
    """
    norm = O.normalize_city(city)
    if norm not in O.CITY_GIS_META:
        raise ValueError(f"不支持的城市: {city}，可选 beijing/hangzhou/shenzhen")

    if p_values is None:
        p_list = list(range(1, 11))
    elif isinstance(p_values, str) and "," in p_values:
        p_list = [int(x) for x in p_values.split(",") if str(x).strip().isdigit()] or list(range(1, 11))
    elif isinstance(p_values, list):
        p_list = [int(x) for x in p_values if str(x).isdigit()]
    else:
        p_list = list(range(1, 11))
    if not p_list:
        p_list = list(range(1, 11))

    dataset_id = (dataset_id or "").strip()
    if dataset_id:
        ds = _CUSTOM_DATASETS.get(dataset_id)
        if ds is None:
            raise ValueError(f"未知 dataset_id: {dataset_id}，请先调用 load_csv 注册数据")
        pad_rows, vertiport_rows, dist_rows = ds["pad_rows"], ds["vertiport_rows"], ds["dist_rows"]
    else:
        pad_rows, vertiport_rows, dist_rows = _load_sample(norm)
    result = O.run_full_model(
        pad_rows=pad_rows,
        vertiport_rows=vertiport_rows,
        distance_rows=dist_rows,
        max_new_stores=max_new_stores,
        p_values=p_list,
        focus_city=norm,
        mature_penetration=0.6,
        drones_per_vertiport=drones_per_vertiport,
        drone_order_rate_hour=drone_order_rate_hour,
    )
    return _compact_site_result(result, norm, dataset_id=dataset_id)


def _compact_site_result(result: Dict[str, Any], city: str, dataset_id: str = "") -> Dict[str, Any]:
    summary = result.get("summary") or {}
    st3 = result.get("stage3") or {}
    best = st3.get("best_scenario") or {}
    scenarios = sorted(
        [
            {
                "P": sc.get("p"),
                "covered_pads": sc.get("covered_pad_count"),
                "covered_orders_10k": sc.get("covered_orders_10k"),
                "avg_distance_km": sc.get("avg_distance_km"),
                "open_vertiports": sc.get("open_vertiport_count"),
                "recommended": bool(sc.get("recommended")),
            }
            for sc in (st3.get("scenarios") or [])
        ],
        key=lambda x: x["P"] or 0,
    )

    def _coord(v: Any) -> Any:
        try:
            return round(float(v), 5)
        except (TypeError, ValueError):
            return None

    # 最优方案的机坪/起降点坐标明细：供 LLM 继续调用 regeo_label 打商圈标签。
    vp_details = [
        {
            "vertiport_id": v.get("vertiport_id"),
            "name": v.get("name"),
            "lat": _coord(v.get("lat")),
            "lon": _coord(v.get("lon")),
        }
        for v in (best.get("open_vertiports") or [])
    ]
    pad_details = [
        {
            "pad_id": a.get("pad_id"),
            "vertiport_id": a.get("vertiport_id"),
            "lat": _coord(a.get("pad_lat")),
            "lon": _coord(a.get("pad_lon")),
            "distance_km": a.get("distance_km"),
        }
        for a in (best.get("assignments") or [])[:60]
    ]

    return {
        "city": city,
        "data_source": f"自定义数据集(dataset_id={dataset_id})" if dataset_id else "内置样例",
        "candidate_pads": summary.get("total_pad_rows"),
        "existing_pads": summary.get("existing_pads"),
        "stage1_passed": summary.get("stage1_passed"),
        "stage2_selected": summary.get("stage2_selected"),
        "eligible_vertiports": summary.get("eligible_vertiports"),
        "best": {
            "P": best.get("p"),
            "covered_pads": best.get("covered_pad_count"),
            "covered_orders_10k": best.get("covered_orders_10k"),
            "avg_distance_km": best.get("avg_distance_km"),
            "open_vertiports": best.get("open_vertiport_count"),
            "recommended": bool(best.get("recommended")),
            "open_vertiport_details": vp_details,
            "covered_pad_details": pad_details,
        },
        "scenarios": scenarios,
        "units": "覆盖单量/需求量为样例合成的需求权重rf_sales_10k(万)，非真实日单量；"
                  "平均配送距离含机坪与起降点同址的0距离边，属样例数据结构特性。",
    }


def get_city_configs() -> Dict[str, Any]:
    """列出支持的城市及内环限制区提示。"""
    payload = O.get_city_configs()
    out = {}
    for key, meta in payload.items():
        out[key] = {
            "label": meta.get("label"),
            "center": meta.get("center"),
            "inner_ring_name": meta.get("inner_ring_name"),
            "inner_ring_radius_km": meta.get("inner_ring_radius_km"),
            "inner_ring_warning": meta.get("inner_ring_warning"),
        }
    return {"cities": out}


def regeo_label(lat: float, lon: float) -> Dict[str, Any]:
    """经纬度逆地理编码成「区·街道(商圈)」可读标签。"""
    label = _amap_regeo_label(lat, lon)
    return {"lat": lat, "lon": lon, "label": label or "(无逆地理结果，仅裸坐标)"}


def rag_retrieve(
    query: str,
    top_k: int = 4,
    min_score: float = rag_retriever.DEFAULT_MIN_SCORE,
) -> Dict[str, Any]:
    """从领域知识库按 TF-IDF 余弦相似度检索与查询最相关的片段（带来源与段号）。"""
    k = int(top_k) if str(top_k).isdigit() else 4
    try:
        ms = float(min_score)
    except (TypeError, ValueError):
        ms = rag_retriever.DEFAULT_MIN_SCORE
    hits = rag_retriever.retrieve_knowledge(query, top_k=k, min_score=ms)
    note = ""
    if not hits and rag_retriever.is_out_of_scope(query):
        note = (
            "该话题属于知识库刻意不覆盖的范围（无人机法规/执照/航拍/购机咨询）。"
            "请直接向用户说明「知识库没有这条规则，建议查阅官方渠道」，"
            "不要用通用常识或模型自身记忆作答。"
        )
    return {
        "query": query,
        "top_k": k,
        "hit_count": len(hits),
        "note": note,
        "hits": [
            {
                "ref": f"{h.get('source')}#段{h.get('para')}",
                "score": h.get("score"),
                "text": h.get("text"),
            }
            for h in hits
        ],
    }


# ---------------------------------------------------------------------------
# 工具声明（OpenAI 函数 JSON Schema）
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_site_selection",
            "description": (
                "运行城市无人机低空配送的三阶段选址引擎，返回该城市候选起降点漏斗数、"
                "各 P 值方案覆盖情况与推荐方案。city 只支持 beijing/hangzhou/shenzhen。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "enum": ["beijing", "hangzhou", "shenzhen"],
                        "description": "目标城市",
                    },
                    "max_new_stores": {
                        "type": "integer",
                        "default": 10,
                        "description": "Stage2 最多选中的新建起降点数上限",
                    },
                    "p_values": {
                        "type": "string",
                        "default": "1,2,3,4,5,6,7,8,9,10",
                        "description": "逗号分隔的机坪数 P 列表，例如 '6,8,10'",
                    },
                    "drones_per_vertiport": {
                        "type": "integer",
                        "default": 20,
                        "description": "每个机坪配备的无人机数量",
                    },
                    "drone_order_rate_hour": {
                        "type": "integer",
                        "default": 10,
                        "description": "单架无人机每小时配送单量",
                    },
                    "dataset_id": {
                        "type": "string",
                        "default": "",
                        "description": "load_csv 返回的数据集ID；非空时分析用户上传的真实数据，否则用内置样例",
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_csv",
            "description": (
                "装载用户上传的真实数据文件(CSV/Excel)：stores=候选起降点表(必需，"
                "至少含 pad_id/lat/lon，需求量放 rf_sales_10k 列)，rdcs=候选机坪表"
                "(至少含 vertiport_id/lat/lon)，distances=距离矩阵(可选)。"
                "返回 dataset_id，之后调用 run_site_selection 时传入即可分析这份数据。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stores_path": {"type": "string", "description": "候选起降点表文件路径(必需)"},
                    "rdcs_path": {"type": "string", "default": "", "description": "候选机坪表文件路径"},
                    "distances_path": {"type": "string", "default": "", "description": "距离矩阵文件路径(可选)"},
                    "city": {"type": "string", "default": "", "description": "数据所属城市，如 shenzhen"},
                },
                "required": ["stores_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_city_configs",
            "description": "列出支持的城市及其内环限制区(空域限飞近似圈)信息，用于任务规划。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "regeo_label",
            "description": "把经纬度逆地理编码成可读的区/街道/商圈标签（需配置 AMAP_KEY）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "纬度"},
                    "lon": {"type": "number", "description": "经度"},
                },
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_retrieve",
            "description": "从无人机低空配送领域知识库检索与查询关键词最相关的片段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"},
                    "top_k": {"type": "integer", "default": 4, "description": "返回片段数"},
                },
                "required": ["query"],
            },
        },
    },
]

_TOOL_IMPLS = {
    "run_site_selection": run_site_selection,
    "get_city_configs": get_city_configs,
    "regeo_label": regeo_label,
    "rag_retrieve": rag_retrieve,
    "load_csv": load_csv,
}


# ---------------------------------------------------------------------------
# 执行层（只读并行）
# ---------------------------------------------------------------------------


def _tool_result(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """执行单个工具，统一包裹为可供 LLM 消费的 JSON 结果。"""
    import traceback

    impl = _TOOL_IMPLS.get(tool_name)
    if impl is None:
        return {"tool": tool_name, "error": f"未知工具: {tool_name}"}
    try:
        value = impl(**args)
        return {"tool": tool_name, "ok": True, "result": value}
    except Exception as exc:  # noqa: BLE001 —— 工具错误回喂给 LLM 决策，不中断循环
        detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}"
        return {"tool": tool_name, "ok": False, "error": detail}


def dispatch_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """并行执行一批工具调用（全部只读），返回与 tool_calls 一一对应的结果。

    返回的每个元素 {id, name, content(JSON字符串)}，供组装 assistant/tool 消息。
    """
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(tool_calls)))) as pool:
        futures = [
            (tc, pool.submit(_tool_result, tc["name"], tc.get("arguments") or {})) for tc in tool_calls
        ]
        for tc, fut in futures:
            out = fut.result()
            name = tc["name"]
            content = json.dumps(out, ensure_ascii=False)
            results.append({"id": tc.get("id") or "", "name": name, "content": content})
    return results
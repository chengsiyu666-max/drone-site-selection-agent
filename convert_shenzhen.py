# -*- coding: utf-8 -*-
"""从美团 OD 数据生成深圳选址引擎的 stores.csv / rdcs.csv / distances.csv。"""
import math
from pathlib import Path

import pandas as pd

EXCEL_PATH = r"C:\Users\叶琳\Desktop\od_rfms_score.xlsx"
PROJ = Path(r"d:\123\agent\community_supermarket_site_selection")
OUT_DIR = PROJ / "sample_data" / "shenzhen"

R = 6371.0  # 地球半径 km


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def split_grid(g: str):
    lat, lon = g.split("_")
    return float(lat), float(lon)


def main() -> None:
    df = pd.read_excel(EXCEL_PATH)
    print("Excel 行数:", len(df), "列:", len(df.columns))

    # ---------- 候选停机坪 = pickup_grid 去重 ----------
    vertiports = df.groupby("pickup_grid").size().reset_index(name="_n")
    vertiports["lat"], vertiports["lon"] = zip(*vertiports["pickup_grid"].map(split_grid))

    # ---------- 需求点 = dropoff_grid 去重，rf_sales = order_count 累加 ----------
    pads_raw = df.groupby("dropoff_grid")["order_count"].sum().reset_index()
    pads_raw["lat"], pads_raw["lon"] = zip(*pads_raw["dropoff_grid"].map(split_grid))

    # ---------- 距离矩阵（>15km 剔除） ----------
    rows = []
    for _, v in vertiports.iterrows():
        for _, p in pads_raw.iterrows():
            d = haversine_km(v["lat"], v["lon"], p["lat"], p["lon"])
            if d <= 15.0:
                rows.append((v["lat"], v["lon"], v["pickup_grid"],
                             p["lat"], p["lon"], p["dropoff_grid"], round(d, 3)))
    dist_rows = pd.DataFrame(rows, columns=["vlat", "vlon", "vgrid", "plat", "plon", "pgrid", "distance_km"])
    print(f"[距离矩阵] 有效边(<15km): {len(dist_rows)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- stores.csv (需求点) ----------
    pad_cols = []
    for i, r in pads_raw.iterrows():
        pid = f"SZ-P{i:03d}"
        pad_cols.append({
            "pad_id": pid,
            "name": f"深圳市需求点{i:03d}",
            "city": "shenzhen",
            "district_tag": f"P{i:03d}",
            "lat": round(r["lat"], 5),
            "lon": round(r["lon"], 5),
            "rf_sales_10k": round(float(r["order_count"]), 2),
            "area_sqm": 150.0,
            "initial_investment_10k": 120.0,
            "annual_fixed_cost_10k": 30.0,
            "area_sqm_old": 150.0,
            "initial_investment_10k_old": 120.0,
            "annual_fixed_cost_10k_old": 30.0,
            "location_score": 0.7,
            "is_existing": 0,
        })
    pads_df = pd.DataFrame(pad_cols)
    pads_df.to_csv(OUT_DIR / "stores.csv", index=False, encoding="utf-8-sig")
    print(f"[stores.csv] 需求点数: {len(pads_df)}")

    # ---------- rdcs.csv (候选停机坪) ----------
    v_cols = []
    for i, r in vertiports.iterrows():
        vid = f"SZ-V{i:03d}"
        v_cols.append({
            "vertiport_id": vid,
            "name": f"深圳停机坪{i:03d}",
            "city": "shenzhen",
            "lat": round(r["lat"], 5),
            "lon": round(r["lon"], 5),
            "tier_tag": "primary",
            "center_distance_km": 3.0,
            "belt_distance_km": 1.0,
            "area_sqm": 12000.0,
            "initial_investment_10k": 300.0,
            "annual_operating_10k": 40.0,
            "annual_labor_10k": 25.0,
            "annual_utility_10k": 18.0,
            "residual_rate": 0.3,
            "rent_per_sqm_day": 1.2,
            "altitude_limit_m": 50.0,       # 满足 > 3m
            "is_no_fly_zone": 0,             # 合法
            "max_flight_radius_km": 15.0,
        })
    vert_df = pd.DataFrame(v_cols)
    vert_df.to_csv(OUT_DIR / "rdcs.csv", index=False, encoding="utf-8-sig")
    print(f"[rdcs.csv] 候选停机坪数: {len(vert_df)}")

    # ---------- distances.csv ----------
    # 用 vertiports / pads_raw 的原始 grid 顺序对齐回生成的 id
    vg_order = list(vertiports["pickup_grid"])
    pg_order = list(pads_raw["dropoff_grid"])
    dist_cols = [
        {
            "vertiport_id": f"SZ-V{vg_order.index(t['vgrid']):03d}",
            "pad_id": f"SZ-P{pg_order.index(t['pgrid']):03d}",
            "distance_km": t["distance_km"],
        }
        for _, t in dist_rows.iterrows()
    ]
    dist_df = pd.DataFrame(dist_cols)
    # 某些 pad 若无可达 vertiport 会缺边，导致 P-median 覆盖不到——检查
    dist_df.to_csv(OUT_DIR / "distances.csv", index=False, encoding="utf-8-sig")
    print(f"[distances.csv] 边数: {len(dist_df)}")

    # ---------- 覆盖度检查：每个需求点是否有 >=1 个可达候选 ----------
    reachable = set(dist_df["pad_id"])
    all_pads = set(pads_df["pad_id"])
    stranded = all_pads - reachable
    print(f"需求点总数: {len(all_pads)}, 可达需求点: {len(reachable)}, 孤立需求点(不可达): {len(stranded)}")
    print("深圳数据生成完成。")
    print(f"需求点: {len(pads_df)} 个; 候选停机坪: {len(vert_df)} 个")


if __name__ == "__main__":
    main()
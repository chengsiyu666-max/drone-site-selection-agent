# 模型说明

本文档记录 Community Supermarket Site Selection 的核心优化模型。单位若无特别说明，金额均为“万元人民币”，距离为 km。

## 1. 城市参数

模型支持北京和杭州两套默认参数，配置位于 `optimizer.py` 的 `CITY_PARAMS`。

| 参数 | 北京 | 杭州 | 说明 |
| --- | ---: | ---: | --- |
| `horizon_years` | 10 | 10 | 财务测算周期 |
| `discount_rate` / `wacc` | 12% | 11% | 折现率 |
| `gross_margin` | 18.9% | 18.9% | 毛利率 |
| `variable_cost_rate` | 4.5% | 4.2% | 变动成本率 |
| `tax_rate` | 2.5% | 2.5% | 有效税率 |
| `npv_threshold_10k` | 100 | 105 | Stage 1 默认 NPV 阈值 |
| `dpp_threshold_years` | 5.0 | 5.0 | Stage 1 默认 DPP 阈值 |
| `revenue_per_sqm_threshold_10k` | 1.15 | 1.15 | 坪效阈值 |
| `rent_cap_per_sqm_day` | 1.8 | 1.5 | RDC 租金上限 |

前端支持临时覆盖 NPV、DPP、坪效阈值。

## 2. Stage 1：单店财务筛选

对每个新门店候选点独立计算：

```text
revenue_t = rf_sales_10k * growth_t
gross_profit_t = revenue_t * gross_margin
variable_cost_t = revenue_t * variable_cost_rate
operating_profit_t = gross_profit_t - variable_cost_t - annual_fixed_cost_10k
tax_t = max(0, operating_profit_t) * tax_rate
cashflow_t = operating_profit_t - tax_t
```

最后一年加入门店残值：

```text
cashflow_last += initial_investment_10k * store_residual_rate
```

NPV：

```text
NPV = -initial_investment_10k + sum(cashflow_t / (1 + discount_rate)^t)
```

DPP 使用折现现金流累计转正的年份，并在转正年份内做线性插值。

候选点通过条件：

```text
NPV >= city_threshold
DPP <= city_threshold
rf_sales_10k / area_sqm >= city_threshold
```

既有门店 `is_existing=1` 不参与 Stage 1 和 Stage 2，直接进入 Stage 3 网络规划。

## 3. Stage 2：新店蚕食与排他优化

Stage 2 只在 Stage 1 通过的新门店之间计算同城距离。距离规则：

| 距离 | 规则 |
| --- | --- |
| `< 280m` | 硬冲突，不能同时开店 |
| `280m - 320m` | 衰减从 1.0 线性降至 0.35 |
| `320m - 500m` | 衰减从 0.35 线性降至 0 |
| `>= 500m` | 不施加蚕食惩罚 |

对每个选中门店累计相邻惩罚，并限制最大惩罚为 45%：

```text
attenuation_ratio = max(0, 1 - min(0.45, sum(pair_penalty)))
adjusted_sales = base_sales * attenuation_ratio
```

模型会重新计算调整后的 NPV 和 DPP，并要求调整后仍满足 NPV/DPP 阈值。

搜索策略：

- 组合规模小于阈值时精确枚举。
- 组合规模爆炸时按基础 NPV 排序并使用 beam search。

## 4. Stage 3：RDC + 门店联合优化

RDC 候选点先经过硬约束筛选：

| 约束 | 要求 |
| --- | --- |
| 蓝牌通行 | `blue_access = true` |
| 市区通勤 | `core_travel_min <= 30` |
| 净高 | `clear_height_m >= 6` |
| 装卸月台 | `loading_dock = true` |
| 三温仓 | `can_three_temp = true` |
| 消防 | `fire_pass = true` |
| 扰民风险 | `disturbance_risk = false` |
| 租金 | `rent_per_sqm_day <= city_rent_cap` |
| 租期 | `lease_years >= 5` |
| 禁区 | 不在城市内环/绕城限制圈内 |

RDC 生命周期成本：

```text
rdc_lifecycle_cost =
  initial_investment
  + PV(annual_rent + property + operating + labor + utility)
  - PV(initial_investment * residual_rate)
```

门店配送成本：

```text
trip_cost = fixed_cost + variable_cost_km * distance_km + area_handling_cost
delivery_pv = sum(delivery_freq * demand_weight * trip_cost * growth_t / (1 + discount_rate)^t)
```

同城约束：北京门店只能分配给北京 RDC，杭州同理。

## 5. 联合目标

当前实现不是先固定 Stage 2 结果再优化 Stage 3，而是枚举多个 Stage 2 选店组合，并对每个 P 值寻找联合最优方案：

```text
maximize adjusted_new_store_NPV - delivery_network_cost_PV
```

其中配送网络包含：

- 既有门店
- 被 Stage 2 选中的新增门店

最终输出：

- 每个 P 情景的 RDC 成本、配送成本、总成本
- 平均配送距离
- ROI
- open RDC 列表
- store → RDC assignment
- 被硬约束剔除的 RDC 及原因

## 6. 距离来源

模型按优先级使用：

1. 上传的 `distances.csv`
2. 启用 AMap 且提供 key 时，调用高德驾车距离 API
3. 经纬度 haversine 距离兜底

公开仓库默认不包含任何真实 API key。

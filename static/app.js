const state = {
  cityConfigs: {},
  result: null,
  step: "stage1",
  tableTab: "stage1",
  customRdcMode: false,
  customRdcs: [],
  customViolations: [],
  map: null,
  layers: {},
  markerScale: 1,
  lineOpacity: 0.65,
  showPolicyRings: true,
  autoFitMap: true,
  stageCycleTimer: null,
  stageCycling: false,
};

const els = {
  modelForm: document.getElementById("modelForm"),
  modelSubmitBtn: document.querySelector('#modelForm button[type="submit"]'),
  runSampleBtn: document.getElementById("runSampleBtn"),
  focusCity: document.getElementById("focusCity"),
  pStepper: document.getElementById("pStepper"),
  pValues: document.getElementById("pValues"),
  status: document.getElementById("status"),
  cityWacc: document.getElementById("cityWacc"),
  cityNpvDefault: document.getElementById("cityNpvDefault"),
  cityDppDefault: document.getElementById("cityDppDefault"),
  npvThreshold: document.getElementById("npvThreshold"),
  dppThreshold: document.getElementById("dppThreshold"),
  summaryCards: document.getElementById("summaryCards"),
  costBars: document.getElementById("costBars"),
  scenarioCards: document.getElementById("scenarioCards"),
  hardAlerts: document.getElementById("hardAlerts"),
  tableWrap: document.getElementById("tableWrap"),
  timelineSteps: document.getElementById("timelineSteps"),
  stepIntro: document.getElementById("stepIntro"),
  tableTabs: document.querySelectorAll(".tab"),
  toggleCustomRdc: document.getElementById("toggleCustomRdc"),
  customHint: document.getElementById("customHint"),
  markerScale: document.getElementById("markerScale"),
  lineOpacity: document.getElementById("lineOpacity"),
  showPolicyRings: document.getElementById("showPolicyRings"),
  autoFitMap: document.getElementById("autoFitMap"),
  cycleStagesBtn: document.getElementById("cycleStagesBtn"),
  interactionState: document.getElementById("interactionState"),
};

function inferStatusState(text) {
  if (/(失败|错误|异常|违规|校验失败)/.test(text)) return "error";
  if (/(成功|就绪|已更新|已添加)/.test(text)) return "success";
  if (/(运行中|加载|初始化|正在)/.test(text)) return "loading";
  return "idle";
}

function setStatus(text, statusState = inferStatusState(text)) {
  els.status.textContent = text;
  els.status.dataset.state = statusState;
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toFixed(digits);
}

function fmtPct(value, digits = 1) {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  const sign = num > 0 ? "+" : "";
  return `${sign}${(num * 100).toFixed(digits)}%`;
}

function buildPValues() {
  const maxP = Math.max(1, Math.min(8, Number(els.pStepper.value) || 3));
  const values = [];
  for (let i = 1; i <= maxP; i += 1) values.push(i);
  els.pValues.value = values.join(",");
}

function setRunButtonsBusy(isBusy) {
  if (els.modelSubmitBtn) {
    els.modelSubmitBtn.disabled = isBusy;
    els.modelSubmitBtn.textContent = isBusy ? "运行中..." : "运行上传数据";
  }
  if (els.runSampleBtn) {
    els.runSampleBtn.disabled = isBusy;
    els.runSampleBtn.textContent = isBusy ? "运行中..." : "运行样例";
  }
}

function updateInteractionStateText() {
  if (!els.interactionState) return;
  const mode = state.stageCycling ? "自动轮播中" : "手动模式";
  const ring = state.showPolicyRings ? "圈层显示" : "圈层隐藏";
  const fit = state.autoFitMap ? "自动缩放开" : "自动缩放关";
  els.interactionState.textContent = `当前：${mode} · ${ring} · ${fit}`;
}

function setStageCycling(active) {
  state.stageCycling = Boolean(active);
  if (state.stageCycleTimer) {
    clearInterval(state.stageCycleTimer);
    state.stageCycleTimer = null;
  }

  if (state.stageCycling) {
    const order = ["stage1", "stage2", "stage3"];
    state.stageCycleTimer = window.setInterval(() => {
      const idx = order.indexOf(state.step);
      const next = order[(idx + 1) % order.length];
      setActiveStep(next);
    }, 2800);
  }

  if (els.cycleStagesBtn) {
    els.cycleStagesBtn.textContent = state.stageCycling ? "停止轮播" : "自动轮播";
    els.cycleStagesBtn.classList.toggle("active", state.stageCycling);
  }
  updateInteractionStateText();
}

function sparklineSVG(values) {
  const arr = Array.isArray(values) ? values.map((v) => Number(v) || 0) : [];
  if (!arr.length) return "";

  const w = 150;
  const h = 46;
  const minV = Math.min(...arr);
  const maxV = Math.max(...arr);
  const range = Math.max(1e-9, maxV - minV);

  const points = arr
    .map((v, i) => {
      const x = (i / Math.max(1, arr.length - 1)) * w;
      const y = h - ((v - minV) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return `<svg class="spark" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
    <polyline fill="none" stroke="#0c7973" stroke-width="2" points="${points}" />
  </svg>`;
}

function popupForStage1(point) {
  const cash = sparklineSVG(point.yearly_cashflow_10k || []);
  return `
    <div>
      <b>${point.name}</b><br/>
      城市：${point.city}<br/>
      NPV：${fmt(point.npv_10k)} 万元<br/>
      DPP：${fmt(point.dpp_years)} 年
      ${cash}
    </div>
  `;
}

function createWarehouseIcon(scale = 1) {
  const size = Math.max(14, Math.round(18 * scale));
  const html = `
    <div class="warehouse-pin" style="width:${size}px;height:${size}px;" aria-hidden="true">
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <path d="M6 28L32 10l26 18v24a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4V28z" fill="#2c78d8"/>
        <path d="M16 56V36h32v20" fill="#5aa0f2"/>
        <rect x="26" y="40" width="12" height="16" rx="2" fill="#d9ebff"/>
        <rect x="14" y="40" width="8" height="8" rx="1.2" fill="#d9ebff"/>
        <rect x="42" y="40" width="8" height="8" rx="1.2" fill="#d9ebff"/>
      </svg>
    </div>
  `;
  return L.divIcon({
    className: "warehouse-div-icon",
    html,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function initMap() {
  if (!window.L) {
    setStatus("Leaflet未加载成功，无法显示GIS地图。");
    return;
  }

  state.map = L.map("map", {
    zoomControl: true,
    preferCanvas: true,
  }).setView([39.9042, 116.4074], 10.6);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);

  state.layers.base = L.layerGroup().addTo(state.map);
  state.layers.stage1 = L.layerGroup().addTo(state.map);
  state.layers.stage2 = L.layerGroup().addTo(state.map);
  state.layers.stage3 = L.layerGroup().addTo(state.map);
  state.layers.custom = L.layerGroup().addTo(state.map);

  state.map.on("click", onMapClickAddCustomRdc);

  // Wire up delete buttons inside custom-RDC popups after they open.
  state.map.on("popupopen", (evt) => {
    const root = evt.popup.getElement && evt.popup.getElement();
    if (!root) return;
    const btn = root.querySelector(".custom-rdc-del");
    if (!btn) return;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      state.customRdcs = state.customRdcs.filter((r) => r.rdc_id !== id);
      state.map.closePopup();
      renderStepLayers();
      setStatus(`已删除自定义RDC ${id}`, "success");
    });
  });
}

function clearLayer(layer) {
  if (layer && typeof layer.clearLayers === "function") {
    layer.clearLayers();
  }
}

function getCurrentCityConfigs() {
  const focus = els.focusCity.value;
  return state.cityConfigs[focus] ? [state.cityConfigs[focus]] : [];
}

function updateCityParamPanel() {
  const focus = els.focusCity.value;
  const city = state.cityConfigs[focus];

  if (!city) return;

  const p = city.params || {};
  els.cityWacc.textContent = `${fmt((p.wacc || 0) * 100, 1)}%`;
  els.cityNpvDefault.textContent = fmt(p.npv_threshold_10k, 1);
  els.cityDppDefault.textContent = fmt(p.dpp_threshold_years, 1);

  // Always refresh placeholders so they reflect the current focus city, even
  // if the user has previously typed something.
  els.npvThreshold.placeholder = `默认${fmt(p.npv_threshold_10k, 1)}`;
  els.dppThreshold.placeholder = `默认${fmt(p.dpp_threshold_years, 1)}`;
  const revEl = document.getElementById("revenueThreshold");
  if (revEl && p.revenue_per_sqm_threshold_10k != null) {
    revEl.placeholder = `默认${fmt(p.revenue_per_sqm_threshold_10k, 1)}`;
  }
}

function drawBaseCityOverlays() {
  clearLayer(state.layers.base);
  const configs = getCurrentCityConfigs();

  configs.forEach((cfg) => {
    const center = cfg.center;
    const ring = cfg.inner_ring_radius_km;

    const ringCircle = L.circle(center, {
      radius: ring * 1000,
      color: "#d14d42",
      weight: 1.5,
      fillOpacity: 0.03,
      dashArray: "4 6",
    }).bindTooltip(`${cfg.label} ${cfg.inner_ring_name}`);
    ringCircle.addTo(state.layers.base);

    (cfg.logistics_belts || []).forEach((belt) => {
      L.circle([belt.lat, belt.lon], {
        radius: (belt.radius_km || 4) * 1000,
        color: "#f2a53b",
        weight: 1,
        fillOpacity: 0.06,
      })
        .bindTooltip(`${cfg.label} - ${belt.name}`)
        .addTo(state.layers.base);
    });
  });
}

function cityMatch(value) {
  const focus = els.focusCity.value;
  return String(value || "") === focus;
}

function updateStepIntro() {
  if (!els.stepIntro) return;

  const defaultCopy = {
    stage1: "阶段一：查看候选门店在 NPV、DPP 和坪效阈值下的通过情况。",
    stage2: "阶段二：联合优化选店与网络，目标为新店修正NPV减去配送成本，且入选门店需满足修正NPV/DPP阈值。",
    stage3: "阶段三：对比不同 P 情景下的联合最优方案（选店组合可能因 P 而异）。",
  };

  if (!state.result) {
    els.stepIntro.textContent = defaultCopy[state.step] || defaultCopy.stage1;
    return;
  }

  if (state.step === "stage1") {
    const rows = (state.result.stage1?.rows || []).filter((r) => cityMatch(r.city));
    const passed = rows.filter((r) => Boolean(r.passed)).length;
    els.stepIntro.textContent = `阶段一：当前视图共 ${rows.length} 个候选门店，其中 ${passed} 个通过硬约束筛选。`;
    return;
  }

  if (state.step === "stage2") {
    const selected = (state.result.stage2?.selected || []).filter((r) => cityMatch(r.city));
    els.stepIntro.textContent = `阶段二：当前城市入选门店 ${selected.length} 家，可在地图中查看排他后最终点位。`;
    return;
  }

  const bestScenario = state.result.stage3?.best_scenario;
  if (bestScenario) {
    const assignments = (bestScenario.assignments || []).filter((r) => cityMatch(r.store_city));
    const existingCount = assignments.filter((r) => Boolean(r.store_is_existing)).length;
    const newCount = assignments.length - existingCount;
    els.stepIntro.textContent = `阶段三：最优 P=${bestScenario.p}，当前视图包含 ${assignments.length} 条门店归属关系（现存 ${existingCount}，新增 ${newCount}）。`;
    return;
  }

  els.stepIntro.textContent = defaultCopy.stage3;
}

function fitBoundsIfAny(latlngs) {
  if (!state.map || !latlngs.length) return;
  const bounds = L.latLngBounds(latlngs);
  state.map.fitBounds(bounds.pad(0.2), { maxZoom: 13 });
}

function renderStepLayers() {
  clearLayer(state.layers.stage1);
  clearLayer(state.layers.stage2);
  clearLayer(state.layers.stage3);

  if (!state.result || !state.map) {
    if (state.showPolicyRings) {
      drawBaseCityOverlays();
    } else {
      clearLayer(state.layers.base);
    }
    return;
  }

  if (state.showPolicyRings) {
    drawBaseCityOverlays();
  } else {
    clearLayer(state.layers.base);
  }

  const markerScale = Math.max(0.6, Number(state.markerScale) || 1);
  const lineOpacity = Math.min(1, Math.max(0.15, Number(state.lineOpacity) || 0.65));

  const points = state.result?.gis?.stage1_points || [];
  const selected = state.result?.gis?.stage2_selected || [];
  const lines = state.result?.gis?.stage3_network_lines || [];
  const openRdcs = state.result?.gis?.stage3_open_rdcs || [];

  const fit = [];

  if (state.step === "stage1") {
    points.filter((p) => cityMatch(p.city)).forEach((p) => {
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: 5 * markerScale,
        color: p.passed ? "#1b8f5a" : "#c63f38",
        fillColor: p.passed ? "#1b8f5a" : "#c63f38",
        fillOpacity: 0.9,
        weight: 1,
      })
        .bindPopup(popupForStage1(p))
        .addTo(state.layers.stage1);
      fit.push([p.lat, p.lon]);
      marker.bringToFront();
    });
  }

  if (state.step === "stage2") {
    points.filter((p) => cityMatch(p.city)).forEach((p) => {
      L.circleMarker([p.lat, p.lon], {
        radius: 4 * markerScale,
        color: p.passed ? "#2c9f6a" : "#c9524a",
        fillColor: p.passed ? "#2c9f6a" : "#c9524a",
        fillOpacity: 0.45,
        weight: 1,
      }).addTo(state.layers.stage2);
      fit.push([p.lat, p.lon]);
    });

    selected.filter((s) => cityMatch(s.city)).forEach((s) => {
      L.circle([s.lat, s.lon], {
        radius: 500,
        color: "#f0a32f",
        weight: 1,
        fillOpacity: 0.05,
      }).addTo(state.layers.stage2);

      L.circle([s.lat, s.lon], {
        radius: 300,
        color: "#ce5027",
        weight: 1,
        fillOpacity: 0.08,
      }).addTo(state.layers.stage2);

      L.circleMarker([s.lat, s.lon], {
        radius: 6 * markerScale,
        color: "#f0a32f",
        fillColor: "#f0a32f",
        fillOpacity: 1,
      })
        .bindPopup(`<b>${s.name}</b><br/>修正NPV：${fmt(s.adjusted_npv_10k)} 万元`)
        .addTo(state.layers.stage2);
      fit.push([s.lat, s.lon]);
    });
  }

  if (state.step === "stage3") {
    openRdcs.filter((r) => cityMatch(r.city)).forEach((rdc) => {
      L.marker([rdc.lat, rdc.lon], {
        icon: createWarehouseIcon(markerScale),
      })
        .bindPopup(`<b>${rdc.name}</b><br/>${rdc.city}<br/>全周期折现成本：${fmt(rdc.lifecycle_cost_10k)} 万元`)
        .addTo(state.layers.stage3);
      fit.push([rdc.lat, rdc.lon]);
    });

    lines
      .filter((line) => cityMatch(line.store_city))
      .forEach((line) => {
        const isExisting = Boolean(line.store_is_existing);
        const storeColor = isExisting ? "#177e89" : "#f08a24";
        const storeType = isExisting ? "现存门店" : "新增门店";

        L.polyline(
          [
            [line.store_lat, line.store_lon],
            [line.rdc_lat, line.rdc_lon],
          ],
          {
            color: storeColor,
            weight: 1.6,
            opacity: lineOpacity,
          }
        )
          .bindPopup(
            `<b>${line.store_name}</b>（${storeType}）→ <b>${line.rdc_name}</b><br/>距离：${fmt(line.distance_km)} km`
          )
          .addTo(state.layers.stage3);

        L.circleMarker([line.store_lat, line.store_lon], {
          radius: 4 * markerScale,
          color: storeColor,
          fillColor: storeColor,
          fillOpacity: 0.8,
        })
          .bindPopup(`<b>${line.store_name}</b><br/>门店类型：${storeType}`)
          .addTo(state.layers.stage3);

        fit.push([line.store_lat, line.store_lon], [line.rdc_lat, line.rdc_lon]);
      });
  }

  // custom rdcs always visible
  clearLayer(state.layers.custom);
  state.customRdcs.forEach((rdc) => {
    const popupHtml = `
      <div class="custom-rdc-popup">
        <b>${rdc.name}</b><br/>
        ${rdc.city}<br/>
        自定义候选 RDC<br/>
        <button type="button" class="custom-rdc-del btn btn-small" data-id="${rdc.rdc_id}">删除该点位</button>
      </div>
    `;
    L.circleMarker([rdc.lat, rdc.lon], {
      radius: 7 * markerScale,
      color: "#5a2ca0",
      fillColor: "#7d4ac2",
      fillOpacity: 0.9,
    })
      .bindPopup(popupHtml)
      .addTo(state.layers.custom);
    fit.push([rdc.lat, rdc.lon]);
  });

  if (!fit.length) {
    const cfg = getCurrentCityConfigs()[0];
    if (cfg) {
      state.map.setView(cfg.center, cfg.zoom || 10);
    }
  } else if (state.autoFitMap) {
    fitBoundsIfAny(fit);
  }
}

function renderSummary() {
  const summary = state.result?.summary || {};
  const meta = state.result?.meta || {};
  const entries = [
    ["门店总量", summary.total_store_rows],
    ["现存门店", summary.existing_stores],
    ["阶段一通过", summary.stage1_passed],
    ["阶段二入选", summary.stage2_selected],
    ["合规RDC", summary.eligible_rdcs],
    ["最优P", summary.best_p],
    ["联合最优总成本(万元)", summary.best_total_cost_10k],
    ["联合目标值(万元)", summary.best_joint_objective_10k],
    ["自定义RDC", meta.custom_rdcs || 0],
  ];

  els.summaryCards.innerHTML = entries
    .map(
      ([k, v]) => `
      <div class="kpi">
        <div class="kpi-title">${k}</div>
        <div class="kpi-value">${typeof v === "number" ? fmt(v) : v ?? "-"}</div>
      </div>
    `
    )
    .join("");
}

function renderCostBars() {
  const scenarios = [...(state.result?.stage3?.scenarios || [])]
    .sort((a, b) => Number(a.p) - Number(b.p));
  if (!scenarios.length) {
    els.costBars.innerHTML = "<div>暂无情景成本数据</div>";
    return;
  }

  const maxVal = Math.max(
    ...scenarios.flatMap((s) => [Number(s.rdc_cost_10k) || 0, Number(s.delivery_cost_10k) || 0]),
    1
  );

  els.costBars.innerHTML = scenarios
    .map((s) => {
      const rw = ((Number(s.rdc_cost_10k) || 0) / maxVal) * 100;
      const dw = ((Number(s.delivery_cost_10k) || 0) / maxVal) * 100;
      return `
        <div class="cost-row">
          <div>P${s.p}</div>
          <div class="track"><div class="fill-rdc" style="width:${rw}%;"></div></div>
          <div>${fmt(s.rdc_cost_10k)}</div>
        </div>
        <div class="cost-row">
          <div></div>
          <div class="track"><div class="fill-delivery" style="width:${dw}%;"></div></div>
          <div>${fmt(s.delivery_cost_10k)}</div>
        </div>
      `;
    })
    .join("");
}

function renderScenarioCards() {
  const scenarios = [...(state.result?.stage3?.scenarios || [])]
    .sort((a, b) => Number(a.p) - Number(b.p));
  const bestP = state.result?.stage3?.best_scenario?.p;

  if (!scenarios.length) {
    els.scenarioCards.innerHTML = "<div>暂无情景结果</div>";
    return;
  }

  els.scenarioCards.innerHTML = scenarios
    .map((s) => {
      const isBest = Number(bestP) === Number(s.p);
      return `
        <div class="scenario-card ${isBest ? "best" : ""}">
          <b>P=${s.p}</b><br/>
          总成本：${fmt(s.total_cost_10k)} 万元<br/>
          平均距离：${fmt(s.avg_distance_km)} km<br/>
          ROI：${fmtPct(s.roi, 1)}
        </div>
      `;
    })
    .join("");
}

function renderHardAlerts() {
  const list = [];

  (state.customViolations || []).forEach((msg) => {
    list.push(msg);
  });

  (state.result?.gis?.distance_alerts || []).forEach((a) => {
    list.push(`${a.name_a} 与 ${a.name_b} 距离 ${fmt(a.distance_m, 1)}m，不能同时开店。`);
  });

  (state.result?.stage3?.rejected_rdcs || []).forEach((r) => {
    (r.reasons || []).forEach((reason) => {
      list.push(`${r.name} 被剔除：${reason}`);
    });
  });

  if (!list.length) {
    els.hardAlerts.innerHTML = "<div>暂无硬约束告警</div>";
    return;
  }

  els.hardAlerts.innerHTML = list.slice(0, 18).map((t) => `<div class="alert">${t}</div>`).join("");
}

function buildTable(rows, columns) {
  if (!rows || !rows.length) {
    return "<p style='padding:10px;margin:0;'>暂无数据</p>";
  }

  const head = columns.map((c) => `<th>${c.label}</th>`).join("");
  const body = rows
    .map((r) => {
      const tds = columns
        .map((c) => {
          const v = r[c.key];
          if (Array.isArray(v)) return `<td>${v.join("; ")}</td>`;
          if (typeof v === "boolean") return `<td>${v ? "是" : "否"}</td>`;
          if (typeof v === "number") return `<td>${fmt(v, 3)}</td>`;
          return `<td>${v ?? "-"}</td>`;
        })
        .join("");
      return `<tr>${tds}</tr>`;
    })
    .join("");

  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderTableByTab() {
  if (!state.result) {
    els.tableWrap.innerHTML = "<p style='padding:10px;'>等待运行结果...</p>";
    return;
  }

  if (state.tableTab === "stage1") {
    const rows = (state.result.stage1?.rows || []).filter((r) => cityMatch(r.city));
    els.tableWrap.innerHTML = buildTable(rows, [
      { key: "store_id", label: "门店ID" },
      { key: "name", label: "门店名称" },
      { key: "city", label: "城市" },
      { key: "rf_sales_10k", label: "RF销量(万元)" },
      { key: "npv_10k", label: "NPV(万元)" },
      { key: "dpp_years", label: "DPP(年)" },
      { key: "revenue_per_sqm_10k", label: "坪效" },
      { key: "passed", label: "通过" },
      { key: "reasons", label: "原因" },
    ]);
    return;
  }

  if (state.tableTab === "stage2") {
    const rows = (state.result.stage2?.selected || []).filter((r) => cityMatch(r.city));
    els.tableWrap.innerHTML = buildTable(rows, [
      { key: "store_id", label: "门店ID" },
      { key: "name", label: "门店名称" },
      { key: "city", label: "城市" },
      { key: "base_sales_10k", label: "原始销量" },
      { key: "attenuation_ratio", label: "保留比例" },
      { key: "adjusted_sales_10k", label: "修正销量" },
      { key: "base_npv_10k", label: "原始NPV" },
      { key: "adjusted_npv_10k", label: "修正NPV" },
    ]);
    return;
  }

  const rows = (state.result.stage3?.best_scenario?.assignments || [])
    .filter((r) => cityMatch(r.store_city))
    .map((row) => ({
      ...row,
      store_type: row.store_is_existing ? "现存门店" : "新增门店",
    }));
  els.tableWrap.innerHTML = buildTable(rows, [
    { key: "store_id", label: "门店ID" },
    { key: "store_name", label: "门店" },
    { key: "store_type", label: "门店类型" },
    { key: "store_city", label: "城市" },
    { key: "rdc_id", label: "RDC ID" },
    { key: "rdc_name", label: "RDC" },
    { key: "distance_km", label: "距离(km)" },
  ]);
}

function refreshAllViews() {
  updateCityParamPanel();
  updateStepIntro();
  renderSummary();
  renderCostBars();
  renderScenarioCards();
  renderHardAlerts();
  renderTableByTab();
  renderStepLayers();
}

async function postForm(url, formData) {
  const endpoint = resolveApiUrl(url);
  let resp;
  try {
    resp = await fetch(endpoint, { method: "POST", body: formData });
  } catch (err) {
    throw new Error(`${err.message}（请求地址：${endpoint}）`);
  }

  const contentType = (resp.headers.get("content-type") || "").toLowerCase();
  let data = {};
  if (contentType.includes("application/json")) {
    data = await resp.json();
  } else {
    const text = await resp.text();
    data = { error: text || `HTTP ${resp.status}` };
  }
  if (!resp.ok) {
    throw new Error(data.error || "request failed");
  }
  return data;
}

function resolveApiUrl(path) {
  const raw = String(path || "");
  if (/^https?:\/\//i.test(raw)) return raw;
  const normalized = raw.startsWith("/") ? raw : `/${raw}`;
  const origin = window.location.origin;
  if (!origin || origin === "null" || window.location.protocol === "file:") {
    // Fallback for opening HTML directly from file://
    return `http://127.0.0.1:5001${normalized}`;
  }
  return normalized;
}

function createPayloadFromForm(includeFiles = true) {
  buildPValues();
  const fd = includeFiles ? new FormData(els.modelForm) : new FormData();

  // focusCity lives in the top-nav (outside <form>), make sure it's always sent
  fd.set("focus_city", els.focusCity.value);

  if (!includeFiles) {
    [
      "max_new_stores",
      "p_values",
      "use_road_distance",
      "amap_key",
      "npv_threshold_10k",
      "dpp_threshold_years",
      "revenue_per_sqm_threshold_10k",
    ].forEach((k) => {
      const el = els.modelForm.querySelector(`[name='${k}']`);
      if (!el) return;
      if (el.type === "checkbox") {
        if (el.checked) fd.append(k, "1");
      } else {
        fd.append(k, el.value || "");
      }
    });
  }

  fd.set("p_values", els.pValues.value);
  fd.set("custom_rdcs_json", JSON.stringify(state.customRdcs));
  return fd;
}

async function runModel(url, includeFiles = true) {
  const payload = createPayloadFromForm(includeFiles);
  setRunButtonsBusy(true);
  setStatus("模型运行中，请稍候...", "loading");
  try {
    const result = await postForm(url, payload);
    state.result = result;
    refreshAllViews();
    const info = result?.meta?.distance_source ? `\n距离来源：${result.meta.distance_source}` : "";
    setStatus(`运行成功，已更新GIS视图与看板。${info}`, "success");
  } catch (err) {
    setStatus(`运行失败：${err.message}`, "error");
  } finally {
    setRunButtonsBusy(false);
  }
}

async function fetchCityConfigs() {
  const resp = await fetch(resolveApiUrl("/api/cities"));
  if (!resp.ok) {
    throw new Error(`cities api failed (${resp.status})`);
  }
  const data = await resp.json();
  state.cityConfigs = data.cities || {};
}

function setActiveStep(step) {
  state.step = step;
  document.querySelectorAll(".step").forEach((btn) => {
    const isActive = btn.dataset.step === step;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
  });
  updateStepIntro();
  renderStepLayers();
}

function setActiveTableTab(tab) {
  state.tableTab = tab;
  document.querySelectorAll(".tab").forEach((btn) => {
    const isActive = btn.dataset.tab === tab;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
  });
  renderTableByTab();
}

async function onMapClickAddCustomRdc(evt) {
  if (!state.customRdcMode) return;

  const focus = els.focusCity.value;

  const lat = evt.latlng.lat;
  const lon = evt.latlng.lng;

  try {
    const resp = await fetch("/api/validate-rdc-point", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city: focus, lat, lon }),
    });
    const rule = await resp.json();

    if (rule.violation) {
      const msg = `${focus === "beijing" ? "北京" : "杭州"}自定义RDC点位违规：${rule.message}`;
      state.customViolations.unshift(msg);
      state.customViolations = state.customViolations.slice(0, 8);
      renderHardAlerts();
      setStatus(msg);
      return;
    }

    const idx = state.customRdcs.length + 1;
    state.customRdcs.push({
      rdc_id: `CUSTOM_${idx}`,
      name: `自定义RDC ${idx}`,
      city: focus,
      lat,
      lon,
    });
    renderStepLayers();
    renderHardAlerts();
    setStatus(`已添加自定义RDC ${idx}（${fmt(lat, 4)}, ${fmt(lon, 4)}）`);
  } catch (err) {
    setStatus(`校验自定义RDC失败：${err.message}`);
  }
}

function bindEvents() {
  els.modelForm.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    await runModel("/api/run", true);
  });

  els.runSampleBtn.addEventListener("click", async () => {
    await runModel("/api/run-sample", false);
  });

  els.pStepper.addEventListener("input", buildPValues);

  els.focusCity.addEventListener("change", () => {
    updateCityParamPanel();
    updateStepIntro();
    renderStepLayers();
    renderTableByTab();
  });

  document.querySelectorAll(".step").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (state.stageCycling) setStageCycling(false);
      setActiveStep(btn.dataset.step);
    });
  });

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => setActiveTableTab(btn.dataset.tab));
  });

  els.toggleCustomRdc.addEventListener("click", () => {
    state.customRdcMode = !state.customRdcMode;
    els.toggleCustomRdc.textContent = state.customRdcMode ? "关闭自定义" : "自定义 RDC";
    els.toggleCustomRdc.classList.toggle("active", state.customRdcMode);
    els.customHint.textContent = state.customRdcMode
      ? "自定义模式已开启：点击地图添加候选 RDC 点。"
      : "点击地图可添加候选 RDC；若落入五环 / 绕城内会触发红色告警。";
  });

  if (els.markerScale) {
    els.markerScale.addEventListener("input", () => {
      state.markerScale = Number(els.markerScale.value) || 1;
      renderStepLayers();
    });
  }

  if (els.lineOpacity) {
    els.lineOpacity.addEventListener("input", () => {
      state.lineOpacity = Number(els.lineOpacity.value) || 0.65;
      renderStepLayers();
    });
  }

  if (els.showPolicyRings) {
    els.showPolicyRings.addEventListener("change", () => {
      state.showPolicyRings = Boolean(els.showPolicyRings.checked);
      renderStepLayers();
      updateInteractionStateText();
    });
  }

  if (els.autoFitMap) {
    els.autoFitMap.addEventListener("change", () => {
      state.autoFitMap = Boolean(els.autoFitMap.checked);
      renderStepLayers();
      updateInteractionStateText();
    });
  }

  if (els.cycleStagesBtn) {
    els.cycleStagesBtn.addEventListener("click", () => {
      setStageCycling(!state.stageCycling);
    });
  }

  const dockToggle = document.getElementById("dockToggle");
  const mapDock = document.getElementById("mapDock");
  if (dockToggle && mapDock) {
    dockToggle.addEventListener("click", () => {
      mapDock.classList.toggle("collapsed");
      if (state.map) setTimeout(() => state.map.invalidateSize(), 300);
    });
  }
}

async function boot() {
  setStatus("正在加载城市参数与GIS底图...", "loading");
  buildPValues();
  initMap();

  if (els.markerScale) state.markerScale = Number(els.markerScale.value) || 1;
  if (els.lineOpacity) state.lineOpacity = Number(els.lineOpacity.value) || 0.65;
  if (els.showPolicyRings) state.showPolicyRings = Boolean(els.showPolicyRings.checked);
  if (els.autoFitMap) state.autoFitMap = Boolean(els.autoFitMap.checked);
  updateInteractionStateText();

  try {
    await fetchCityConfigs();
    updateCityParamPanel();
    updateStepIntro();
    drawBaseCityOverlays();
    setStatus("系统就绪。可上传CSV运行，或直接运行样例。", "success");
  } catch (err) {
    setStatus(`初始化失败：${err.message}`, "error");
  }

  bindEvents();
}

boot();

// ---- AI Chat Panel (3-mode: mini / expand / focus) ----
const chat = {
  panel: document.getElementById("chatPanel"),
  fab: document.getElementById("chatFab"),
  closeBtn: document.getElementById("chatPanelClose"),
  sizeBtn: document.getElementById("chatSizeBtn"),
  historyBtn: document.getElementById("chatHistoryBtn"),
  newBtn: document.getElementById("chatNewBtn"),
  sidebar: document.getElementById("chatSidebar"),
  sessionList: document.getElementById("chatSessionList"),
  messages: document.getElementById("chatMessages"),
  input: document.getElementById("chatInput"),
  sendBtn: document.getElementById("chatSendBtn"),
  modelBadge: document.getElementById("chatModelBadge"),
  history: [],
  model: "",
  sessionKey: "",
  activeId: "",
  mode: "mini",
};

// ---- Chat persistence (localStorage) ----
const CHAT_STORE_KEY = "hm_chat_sessions_v1";

const chatStore = {
  data: { activeId: "", sessions: [] },

  load() {
    try {
      const raw = localStorage.getItem(CHAT_STORE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && Array.isArray(parsed.sessions)) {
          this.data = { activeId: parsed.activeId || "", sessions: parsed.sessions };
        }
      }
    } catch {}
    return this.data;
  },

  save() {
    try {
      localStorage.setItem(CHAT_STORE_KEY, JSON.stringify(this.data));
    } catch {}
  },

  list() {
    return [...this.data.sessions].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  },

  get(id) {
    return this.data.sessions.find((s) => s.id === id) || null;
  },

  create() {
    const id = "c_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    const now = Date.now();
    const sess = { id, title: "新对话", sessionKey: "", messages: [], createdAt: now, updatedAt: now };
    this.data.sessions.push(sess);
    this.data.activeId = id;
    this.save();
    return sess;
  },

  update(id, patch) {
    const s = this.get(id);
    if (!s) return null;
    Object.assign(s, patch, { updatedAt: Date.now() });
    this.save();
    return s;
  },

  setActive(id) {
    this.data.activeId = id;
    this.save();
  },

  remove(id) {
    const idx = this.data.sessions.findIndex((s) => s.id === id);
    if (idx < 0) return;
    this.data.sessions.splice(idx, 1);
    if (this.data.activeId === id) {
      const next = this.list()[0];
      this.data.activeId = next ? next.id : "";
    }
    this.save();
  },
};

function fmtRelTime(ts) {
  if (!ts) return "";
  const diff = Date.now() - ts;
  const min = 60 * 1000;
  const hr = 60 * min;
  const day = 24 * hr;
  if (diff < min) return "刚刚";
  if (diff < hr) return `${Math.floor(diff / min)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hr)} 小时前`;
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`;
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function renderSessionList() {
  const list = chatStore.list();
  chat.sessionList.innerHTML = "";
  if (list.length === 0) {
    const empty = document.createElement("div");
    empty.className = "chat-session-empty";
    empty.textContent = "暂无历史对话\n点击上方新建";
    chat.sessionList.appendChild(empty);
    return;
  }
  for (const s of list) {
    const item = document.createElement("div");
    item.className = "chat-session-item" + (s.id === chat.activeId ? " active" : "");
    item.title = s.title;

    const title = document.createElement("span");
    title.className = "title";
    title.textContent = s.title || "新对话";

    const time = document.createElement("span");
    time.className = "time";
    time.textContent = fmtRelTime(s.updatedAt);

    const actions = document.createElement("div");
    actions.className = "session-actions";

    const rename = document.createElement("button");
    rename.className = "action-btn";
    rename.type = "button";
    rename.title = "重命名";
    rename.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M11.5 2.5l2 2L5 13l-3 1 1-3 8.5-8.5z"/></svg>';
    rename.addEventListener("click", (e) => {
      e.stopPropagation();
      const next = prompt("重命名对话", s.title || "");
      if (next == null) return;
      const trimmed = next.trim();
      if (!trimmed) return;
      chatStore.update(s.id, { title: trimmed });
      renderSessionList();
    });

    const del = document.createElement("button");
    del.className = "action-btn del";
    del.type = "button";
    del.title = "删除此对话";
    del.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4l8 8M12 4l-8 8"/></svg>';
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!confirm("删除这条对话记录？")) return;
      chatStore.remove(s.id);
      if (chat.activeId === s.id) {
        const next = chatStore.list()[0];
        if (next) loadSession(next.id);
        else startNewSession();
      } else {
        renderSessionList();
      }
    });

    actions.appendChild(rename);
    actions.appendChild(del);

    item.addEventListener("click", () => loadSession(s.id));
    item.appendChild(title);
    item.appendChild(time);
    item.appendChild(actions);
    chat.sessionList.appendChild(item);
  }
}

function clearMessagesDom() {
  chat.messages.innerHTML = "";
}

function loadSession(id) {
  const s = chatStore.get(id);
  if (!s) return;
  chat.activeId = id;
  chat.sessionKey = s.sessionKey || "";
  chat.history = s.messages.map((m) => ({ role: m.role, content: m.content }));
  chatStore.setActive(id);

  clearMessagesDom();
  for (const m of s.messages) {
    if (m.role === "user" || m.role === "assistant") {
      chatAppendMsg(m.role, m.content);
    }
  }
  renderSessionList();
}

function startNewSession() {
  const s = chatStore.create();
  chat.activeId = s.id;
  chat.sessionKey = "";
  chat.history = [];
  clearMessagesDom();
  renderSessionList();
}

function setChatMode(mode) {
  chat.mode = mode;
  chat.panel.setAttribute("data-mode", mode);
  if (mode === "expand") {
    chat.panel.classList.add("show-history");
  } else {
    chat.panel.classList.remove("show-history");
  }
  // invalidate leaflet size after transition finishes so map re-renders
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 340);
  }
}

function toggleChatSize() {
  setChatMode(chat.mode === "expand" ? "mini" : "expand");
}

function openChat() {
  chat.panel.classList.add("open");
  chat.panel.setAttribute("aria-hidden", "false");
  document.body.classList.add("chat-open");
}
function closeChat() {
  chat.panel.classList.remove("open");
  chat.panel.setAttribute("aria-hidden", "true");
  document.body.classList.remove("chat-open");
  if (state.map) setTimeout(() => state.map.invalidateSize(), 340);
}

chat.fab.addEventListener("click", openChat);
chat.closeBtn.addEventListener("click", closeChat);
if (chat.sizeBtn) chat.sizeBtn.addEventListener("click", toggleChatSize);
if (chat.historyBtn) {
  chat.historyBtn.addEventListener("click", () => {
    chat.panel.classList.toggle("show-history");
    if (state.map) setTimeout(() => state.map.invalidateSize(), 340);
  });
}
if (chat.newBtn) chat.newBtn.addEventListener("click", () => startNewSession());

chat.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatSend();
  }
});
chat.sendBtn.addEventListener("click", chatSend);

function renderMarkdown(text) {
  if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
    const html = marked.parse(text || "");
    return DOMPurify.sanitize(html);
  }
  // fallback: escape HTML and keep plain text
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

function chatAppendMsg(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "assistant") {
    div.innerHTML = renderMarkdown(text);
  } else {
    div.textContent = text;
  }
  chat.messages.appendChild(div);
  chat.messages.scrollTop = chat.messages.scrollHeight;
  return div;
}

function buildSystemContext() {
  const r = state.result;
  if (!r) return "你是某硬折扣社区超市选址展示系统的AI分析助手，请用中文简洁回答用户问题。当前尚无分析结果，可回答选址相关的通用问题。";

  const stage1 = r.stage1 || {};
  const stage2 = r.stage2 || {};
  const stage3 = r.stage3 || {};

  // Backend contract: stage1.rows[].passed, stage2.selected[], stage3.best_scenario
  const rows = stage1.rows || [];
  const passCount = rows.filter((row) => Boolean(row.passed)).length;
  const selectedCount = (stage2.selected || []).length;
  const eligibleCount = (stage3.eligible_rdcs || []).length;
  const rejectedCount = (stage3.rejected_rdcs || []).length;

  let ctx = `你是某硬折扣社区超市选址展示系统的AI分析助手，请用中文简洁回答用户问题。\n\n当前分析结果摘要：\n`;
  ctx += `- 阶段一：共 ${rows.length} 个候选门店，${passCount} 个通过筛选，${rows.length - passCount} 个淘汰\n`;
  ctx += `- 阶段二：排他后优选出 ${selectedCount} 家新开门店\n`;
  ctx += `- 阶段三：合规 RDC ${eligibleCount} 个（被剔除 ${rejectedCount} 个）\n`;

  const best = stage3.best_scenario;
  if (best && best.p != null) {
    ctx += `- 最优情景：P=${best.p}，总成本 ${fmt(best.total_cost_10k)} 万元，`;
    ctx += `平均配送距离 ${fmt(best.avg_distance_km)} km，ROI ${fmtPct(best.roi, 1)}\n`;
  }

  return ctx;
}

async function chatSend() {
  const text = chat.input.value.trim();
  if (!text || chat.sendBtn.disabled) return;

  if (!chat.activeId || !chatStore.get(chat.activeId)) {
    startNewSession();
  }

  chat.input.value = "";
  chat.sendBtn.disabled = true;
  chatAppendMsg("user", text);
  const thinking = chatAppendMsg("thinking", "思考中...");
  chat.history.push({ role: "user", content: text });

  const isFirstMessage = chat.history.filter((m) => m.role === "user").length === 1;
  const patch = {
    messages: chat.history.slice(),
  };
  if (isFirstMessage) {
    patch.title = text.length > 10 ? text.slice(0, 10) + "…" : text;
  }
  chatStore.update(chat.activeId, patch);
  renderSessionList();

  const messages = [
    { role: "system", content: buildSystemContext() },
    ...chat.history,
  ];

  let assistantBubble = null;
  let finalText = "";
  let errored = false;

  const ensureAssistantBubble = () => {
    if (assistantBubble) return;
    thinking.remove();
    assistantBubble = chatAppendMsg("assistant", "");
  };

  const handleEvent = (ev) => {
    if (!ev || !ev.type) return;
    if (ev.type === "session") {
      if (ev.session_key) {
        chat.sessionKey = ev.session_key;
        if (chat.activeId) chatStore.update(chat.activeId, { sessionKey: ev.session_key });
      }
      return;
    }
    if (ev.type === "delta") {
      ensureAssistantBubble();
      finalText = ev.text || "";
      assistantBubble.innerHTML = renderMarkdown(finalText);
      chat.messages.scrollTop = chat.messages.scrollHeight;
      return;
    }
    if (ev.type === "done") {
      ensureAssistantBubble();
      if (ev.text) finalText = ev.text;
      assistantBubble.innerHTML = renderMarkdown(finalText || "(无回复内容)");
      if (ev.session_key) chat.sessionKey = ev.session_key;
      return;
    }
    if (ev.type === "error") {
      errored = true;
      if (assistantBubble) assistantBubble.remove();
      thinking.remove();
      chatAppendMsg("assistant", `错误：${ev.message || "未知错误"}`);
      return;
    }
  };

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: chat.model, messages, session_key: chat.sessionKey }),
    });

    if (!res.ok || !res.body) {
      throw new Error(`HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    // 手工解析 SSE:每个事件以 "\n\n" 分隔,行内以 "data: " 开头
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIdx;
      while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
        const rawFrame = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);

        for (const line of rawFrame.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const jsonStr = line.slice(5).trimStart();
          if (!jsonStr) continue;
          try {
            handleEvent(JSON.parse(jsonStr));
          } catch (err) {
            console.warn("SSE parse error", err, jsonStr);
          }
        }
      }
    }

    if (!errored) {
      if (!assistantBubble) {
        thinking.remove();
        const fallback = chatAppendMsg("assistant", "");
        fallback.innerHTML = renderMarkdown("(无回复内容)");
      }
      if (finalText) {
        chat.history.push({ role: "assistant", content: finalText });
      }
      if (chat.activeId) {
        chatStore.update(chat.activeId, {
          messages: chat.history.slice(),
          sessionKey: chat.sessionKey,
        });
        renderSessionList();
      }
    }
  } catch (e) {
    if (assistantBubble) assistantBubble.remove();
    thinking.remove();
    chatAppendMsg("assistant", `网络错误：${e.message}`);
  }

  chat.sendBtn.disabled = false;
}

// Configure marked for safe, clean rendering
if (typeof marked !== "undefined") {
  marked.setOptions({ breaks: true, gfm: true });
}

async function chatInit() {
  chatStore.load();
  const list = chatStore.list();
  if (list.length > 0) {
    const activeId = chatStore.data.activeId && chatStore.get(chatStore.data.activeId)
      ? chatStore.data.activeId
      : list[0].id;
    loadSession(activeId);
  } else {
    renderSessionList();
  }

  try {
    const res = await fetch("/api/chat/models");
    const data = await res.json();
    const models = data.data || [];
    if (models.length > 0) {
      chat.model = models[0].id;
      chat.modelBadge.textContent = `模型: ${chat.model}`;
    } else {
      chat.model = "";
      chat.modelBadge.textContent = "已连接 OpenClaw";
    }
  } catch {
    chat.modelBadge.textContent = "OpenClaw 连接异常，请检查服务";
  }
}

chatInit();

// ---- Agent 分析报告列表 ----
const agentReports = {
  toggle: document.getElementById("agentReportsToggle"),
  list: document.getElementById("agentReportsList"),
  loaded: false,
};

if (agentReports.toggle) {
  agentReports.toggle.addEventListener("click", async () => {
    const hidden = agentReports.list.hasAttribute("hidden");
    if (hidden) {
      await loadAgentReports();
      agentReports.list.removeAttribute("hidden");
      agentReports.toggle.textContent = "📄 收起报告列表";
    } else {
      agentReports.list.setAttribute("hidden", "");
      agentReports.toggle.textContent = "📄 查看分析报告";
    }
  });
}

async function loadAgentReports() {
  try {
    const res = await fetch("/api/agent-outputs");
    const data = await res.json();
    const files = data.files || [];
    if (files.length === 0) {
      agentReports.list.innerHTML = '<p class="empty">暂无分析报告，先让AI 助手生成一份吧</p>';
      return;
    }
    agentReports.list.innerHTML = files
      .map((f) => {
        const dt = new Date(f.mtime * 1000).toLocaleString("zh-CN", { hour12: false });
        const kb = (f.size / 1024).toFixed(1);
        return `<a class="report-link" href="/api/agent-outputs/${encodeURIComponent(f.name)}" target="_blank"><span class="fname">${f.name}</span><span class="fmeta">${dt} · ${kb} KB</span></a>`;
      })
      .join("");
  } catch (e) {
    agentReports.list.innerHTML = `<p class="empty">加载失败：${e.message}</p>`;
  }
}

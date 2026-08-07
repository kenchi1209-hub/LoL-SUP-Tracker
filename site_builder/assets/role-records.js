(function (global) {
  "use strict";

  const text = (tag, value, className) => {
    const element = global.document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    return element;
  };
  const date = (value) => value ? String(value).slice(0, 10).replace(/-/g, "/") : "-";
  const queue = (value) => String(value) === "420" ? "Ranked" : String(value) === "400" ? "Draft" : String(value);

  function valueText(record, item) {
    if (!item) return "-";
    if (record.streak) return `${item.length}連${record.win ? "勝" : "敗"}`;
    const value = record.value(item);
    return record.format === "duration"
      ? global.RoleMetrics.formatDuration(value)
      : global.RoleMetrics.formatDecimal(value, record.digits);
  }

  function matchDetail(record, item, version) {
    const match = item.match;
    const detail = text("div", "", "record-detail");
    const head = text("div", "", "record-detail-head");
    const image = global.document.createElement("img");
    image.src = global.RolePatchAnalysis.championImageUrl(version, match.champion_icon_id);
    image.alt = match.champion;
    head.append(image, text("span", `${date(match.date)} ${match.win ? "WIN" : "LOSS"} ${match.champion}`));
    const metrics = item.metrics;
    const stats = text("div", "", "record-detail-stats");
    stats.append(
      text("div", `記録: ${valueText(record, item)}`, "record-detail-value"),
      text("div", `${match.kills}/${match.deaths}/${match.assists} · CS ${match.cs} (${global.RoleMetrics.formatDecimal(metrics.cspm, 2)}/m)`),
      text("div", `VS ${match.vision_score} (${global.RoleMetrics.formatDecimal(metrics.vspm, 2)}/m) · Damage ${match.damage_to_champions} (${global.RoleMetrics.formatDecimal(metrics.damagePerMinute, 0)}/m)`),
      text("div", `${global.RoleMetrics.formatDuration(match.game_duration_seconds)} · ${queue(match.queue_id)}`)
    );
    detail.append(head, stats);
    return detail;
  }

  function streakDetail(record, run) {
    const detail = text("div", "", "record-detail");
    detail.append(
      text("div", `${date(run.startDate)}～${date(run.endDate)} · ${run.length}連${record.win ? "勝" : "敗"}`, "record-detail-value"),
      text("div", record.win
        ? `区間KDA ${global.RoleMetrics.formatDecimal(run.metrics.kda, 2)} · VS/m ${global.RoleMetrics.formatDecimal(run.metrics.vspm, 2)}`
        : `区間KDA ${global.RoleMetrics.formatDecimal(run.metrics.kda, 2)} · Death ${global.RoleMetrics.formatDecimal(run.metrics.avgDeaths, 2)}`,
        "record-detail-stats")
    );
    return detail;
  }

  function recordCard(record, version) {
    const card = text("article", "", "card record-card");
    card.dataset.record = record.key;
    card.append(text("div", record.label, "stat-label"));
    const main = text("div", "", "record-main");
    main.append(text("div", valueText(record, record.winner), "stat-value"));
    if (record.winner) {
      const sub = record.streak
        ? `${date(record.winner.startDate)}～${date(record.winner.endDate)}`
        : `${date(record.winner.match.date)} · ${record.winner.match.champion} · ${record.winner.match.win ? "WIN" : "LOSS"}`;
      main.append(text("div", sub, "stat-sub"));
    }
    card.append(main);
    if (record.ties.length > 1) {
      const details = text("details", "", "record-ties");
      details.append(text("summary", `ほか同率${record.ties.length - 1}件`));
      const list = text("div", "", "record-detail-list");
      record.ties.forEach((item) => list.append(
        record.streak ? streakDetail(record, item) : matchDetail(record, item, version)
      ));
      details.append(list);
      card.append(details);
    }
    return card;
  }

  function renderRecords(matches) {
    const section = global.document.querySelector(".records-analysis");
    if (!section) return [];
    const records = global.RoleRecordsMetrics.analyzeRecords(matches);
    global.document.getElementById("records-grid").replaceChildren(
      ...records.map((record) => recordCard(record, section.dataset.ddragonVersion))
    );
    return records;
  }

  if (global.document) {
    global.document.addEventListener("role-filter:change", (event) => renderRecords(event.detail.matches));
    global.document.addEventListener("DOMContentLoaded", () => {
      if (global.rolePageFilters) renderRecords(global.rolePageFilters.getMatches());
    });
  }

  const api = { render: renderRecords, valueText };
  global.RoleRecords = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

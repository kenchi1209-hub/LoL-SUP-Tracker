(function (global) {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const TIER_NAMES = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"];
  const DIVISIONS = ["IV", "III", "II", "I"];

  function el(name, attrs, text) {
    const node = global.document.createElementNS(SVG_NS, name);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function htmlEl(name, className, text) {
    const node = global.document.createElement(name);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function localDate(value) {
    return String(value || "").slice(0, 10);
  }

  function dateLabel(value) {
    const valueDate = localDate(value);
    const parts = valueDate.split("-");
    return parts.length === 3 ? `${Number(parts[1])}/${Number(parts[2])}` : "-";
  }

  function dateTimeLabel(value) {
    return String(value || "").replace("T", " ").slice(0, 16);
  }

  function rankLabel(rank) {
    if (!rank) return "-";
    return `${rank.tier}${rank.division ? ` ${rank.division}` : ""} ${rank.lp} LP`;
  }

  function resultLabel(win) {
    return win ? "WIN" : "LOSS";
  }

  function signed(value) {
    if (!Number.isFinite(value)) return "-";
    return `${value >= 0 ? "+" : ""}${value}`;
  }

  function percentage(wins, games) {
    return games ? `${((wins / games) * 100).toFixed(1)}%` : "-";
  }

  function inRange(value, range) {
    const day = localDate(value);
    return (!range.start || day >= range.start) && (!range.end || day <= range.end);
  }

  function activeSeason(data) {
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo" }).format(new Date());
    return data.seasons.find((season) => season.start_jst <= today && (!season.end_jst || season.end_jst >= today)) || data.seasons.at(-1) || null;
  }

  function chartStart(data) {
    const historical = data.historical?.points || [];
    const dates = [data.tracking_started_jst, ...historical.map((point) => point.timestamp_jst)]
      .map(localDate)
      .filter(Boolean)
      .sort();
    return dates[0] || "";
  }

  function rangeFor(period, data, controls) {
    const start = chartStart(data);
    if (period === "30d") {
      const current = new Date();
      current.setDate(current.getDate() - 29);
      const recent = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo" }).format(current);
      return { start: start > recent ? start : recent, end: "" };
    }
    if (period === "season") {
      const season = activeSeason(data);
      return { start: start > (season?.start_jst || start) ? start : season.start_jst, end: season?.end_jst || "" };
    }
    if (period === "custom") return { start: controls.start.value, end: controls.end.value };
    return { start, end: "" };
  }

  function filterMatches(data, range, patch) {
    return data.matches.filter((match) => inRange(match.game_datetime_jst, range) && (patch === "all" || match.patch === patch));
  }

  function filterPoints(data, range, patch) {
    return data.points.filter((point) => {
      if (!inRange(point.timestamp_jst, range)) return false;
      if (patch === "all") return true;
      return point.kind === "exact" && point.patch === patch;
    });
  }

  function filterHistoricalPoints(data, range, patch) {
    return (data.historical?.points || []).filter((point) => (
      inRange(point.timestamp_jst, range) && (patch === "all" || point.patch === patch)
    ));
  }

  function usableMatches(data) {
    return Array.isArray(data.usable_matches) ? data.usable_matches : data.matches;
  }

  function filterUsableMatches(data, range, patch) {
    return usableMatches(data).filter((match) => (
      inRange(match.game_datetime_jst, range) && (patch === "all" || match.patch === patch)
    ));
  }

  function statCard(label, value, sub, valueClass) {
    const card = htmlEl("article", "card");
    card.append(htmlEl("div", "stat-label", label));
    const strong = htmlEl("div", `stat-value${valueClass ? ` ${valueClass}` : ""}`, value);
    card.append(strong);
    if (sub) card.append(htmlEl("div", "stat-sub", sub));
    return card;
  }

  function record(matches) {
    const known = matches.filter((match) => typeof match.win === "boolean");
    const wins = known.filter((match) => match.win).length;
    return { games: matches.length, known: known.length, wins, losses: known.length - wins };
  }

  function exactCoverage(matches) {
    const exact = matches.filter((match) => Number.isFinite(match.lp_delta));
    return { exact, delta: exact.length ? exact.reduce((total, match) => total + match.lp_delta, 0) : null };
  }

  function usableCoverage(matches) {
    const available = matches.filter((match) => Number.isFinite(match.lp_delta));
    return { available, delta: available.length ? available.reduce((total, match) => total + match.lp_delta, 0) : null };
  }

  function usableMetrics(matches) {
    const ordered = [...matches].filter((match) => match.rank).sort((left, right) => (
      (left.game_number ?? Infinity) - (right.game_number ?? Infinity) || String(left.game_datetime_jst).localeCompare(String(right.game_datetime_jst))
    ));
    const result = record(ordered);
    const coverage = usableCoverage(ordered);
    return {
      ordered,
      result,
      coverage,
      start: ordered[0]?.before || ordered[0]?.rank || null,
      end: ordered.at(-1)?.rank || null,
    };
  }

  function renderOverall(data) {
    const container = global.document.getElementById("lp-overall");
    const summary = data.usable_summary || {};
    const recordSummary = summary.record || { wins: 0, losses: 0 };
    const totalGames = recordSummary.wins + recordSummary.losses;
    const recent = [...usableMatches(data)].filter((match) => Number.isFinite(match.game_number)).sort((left, right) => left.game_number - right.game_number).slice(-10);
    const coverage = usableCoverage(recent);
    container.replaceChildren(
      statCard("Current Rank", rankLabel(data.latest_rank), "最新の正式LP point"),
      statCard("All-period record", `${recordSummary.wins}W-${recordSummary.losses}L`, `${summary.games_tracked || 0} / ${totalGames || summary.games_total || 0} games tracked`),
      statCard("All-period win rate", percentage(recordSummary.wins, totalGames), "取得できたLP履歴全体"),
      statCard("Net LP", signed(summary.net_lp), "最古の利用可能pointから現在rank", Number.isFinite(summary.net_lp) ? summary.net_lp >= 0 ? "good" : "bad" : ""),
      statCard("Peak Rank", rankLabel(summary.peak_rank), summary.peak_game_number ? `第${summary.peak_game_number}戦` : "利用可能履歴内"),
      statCard("Recent 10 LP", signed(coverage.delta), `${coverage.available.length} / ${recent.length} games LP available`, Number.isFinite(coverage.delta) ? coverage.delta >= 0 ? "good" : "bad" : "")
    );
  }

  function renderFiltered(matches) {
    const container = global.document.getElementById("lp-filtered");
    const metrics = usableMetrics(matches);
    const { result, coverage, start, end } = metrics;
    container.replaceChildren(
      statCard("LP delta", signed(coverage.delta), `${coverage.available.length} / ${metrics.ordered.length} games LP available`, Number.isFinite(coverage.delta) ? coverage.delta >= 0 ? "good" : "bad" : ""),
      statCard("Record", `${result.wins}W-${result.losses}L`, `${result.games} games`),
      statCard("Win Rate", percentage(result.wins, result.known), result.known === result.games ? "" : `${result.known}/${result.games} games available`),
      statCard("Start Rank", rankLabel(start), "表示中の利用可能point"),
      statCard("End Rank", rankLabel(end), "表示中の利用可能point")
    );
  }

  function rankTick(score) {
    const tier = Math.floor(score / 400);
    const within = score - tier * 400;
    const division = Math.min(3, Math.floor(within / 100));
    return `${TIER_NAMES[tier] || "MASTER+"} ${DIVISIONS[division] || ""}`.trim();
  }

  function pointLabel(point) {
    const game = Number.isFinite(point.game_number) ? `第${point.game_number}戦\n` : "";
    if (point.kind === "baseline") return `${game}Baseline\n${rankLabel(point.rank)}\n${dateTimeLabel(point.timestamp_jst)}`;
    if (point.kind === "checkpoint") return `${game}Checkpoint\n${rankLabel(point.rank)}\nGap: ${point.gap.games} games (${point.gap.wins}W-${point.gap.losses}L)`;
    if (point.kind === "historical") {
      const delta = Number.isFinite(point.candidate_lp_delta) ? `\nCandidate LP: ${signed(point.candidate_lp_delta)}` : "";
      return `${game}Blitz復元（参考・非公式）\n${rankLabel(point.rank)}${delta}\nChampion: ${point.champion_name}\nResult: ${resultLabel(point.win)}\nDate: ${dateTimeLabel(point.timestamp_jst)}\nPatch: ${point.patch || "-"}\nQueue: Solo/Duo`;
    }
    return `${game}${rankLabel(point.rank)}\nLP: ${signed(point.lp_delta)}\nChampion: ${point.champion_name}\nResult: ${resultLabel(point.win)}\nDate: ${dateTimeLabel(point.timestamp_jst)}\nPatch: ${point.patch}\nQueue: Solo/Duo`;
  }

  function pointMatchUrl(point) {
    return typeof point.match_url === "string" && point.match_url.startsWith("history.html#match-")
      ? point.match_url
      : "";
  }

  function openMatchDetail(point) {
    const url = pointMatchUrl(point);
    if (url) global.location.assign(url);
  }

  function showTooltip(point, event) {
    const tooltip = global.document.getElementById("lp-tooltip");
    tooltip.textContent = pointLabel(point);
    tooltip.hidden = false;
    const chart = global.document.getElementById("lp-chart");
    const rect = chart.getBoundingClientRect();
    const x = event?.clientX ? event.clientX - rect.left : rect.width / 2;
    tooltip.style.left = `${Math.max(8, Math.min(rect.width - 236, x - 105))}px`;
    tooltip.style.top = "10px";
  }

  function pointShape(point, x, y) {
    if (point.kind === "checkpoint") return el("circle", { cx: x, cy: y, r: 6, fill: "#171d2b", stroke: "#f0b429", "stroke-width": 3 });
    if (point.kind === "baseline") return el("path", { d: `M ${x} ${y - 7} L ${x + 7} ${y} L ${x} ${y + 7} L ${x - 7} ${y} Z`, fill: "#e7ecf4", stroke: "#5b8cff", "stroke-width": 2 });
    if (point.kind === "historical") return el("circle", { cx: x, cy: y, r: 4, fill: "#171d2b", stroke: "#5b8cff", "stroke-width": 2, "stroke-opacity": .65 });
    if (point.win) return el("path", { d: `M ${x} ${y - 7} L ${x + 7} ${y + 6} L ${x - 7} ${y + 6} Z`, fill: "#38d39f", stroke: "#e7ecf4", "stroke-width": 1 });
    return el("rect", { x: x - 5, y: y - 5, width: 10, height: 10, rx: 1, fill: "#ff6b81", stroke: "#e7ecf4", "stroke-width": 1 });
  }

  function renderChart(officialPoints, historicalPoints) {
    const chart = global.document.getElementById("lp-chart");
    const empty = global.document.getElementById("lp-empty");
    const tooltip = global.document.getElementById("lp-tooltip");
    const points = [...officialPoints, ...historicalPoints]
      .filter((point) => Number.isFinite(point.game_number))
      .sort((left, right) => left.game_number - right.game_number || Date.parse(left.timestamp_jst) - Date.parse(right.timestamp_jst));
    tooltip.hidden = true;
    chart.replaceChildren();
    if (!points.length) { empty.hidden = false; return; }
    empty.hidden = true;
    const width = 800, height = 360, margin = { top: 32, right: 26, bottom: 54, left: 86 };
    const values = points.map((point) => point.score).filter(Number.isFinite);
    if (!values.length) { empty.hidden = false; return; }
    let min = Math.floor(Math.min(...values) / 100) * 100;
    let max = Math.ceil(Math.max(...values) / 100) * 100;
    if (min === max) { min -= 100; max += 100; }
    let first = Math.min(...points.map((point) => point.game_number));
    let last = Math.max(...points.map((point) => point.game_number));
    if (first === last) { first -= 1; last += 1; }
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;
    const x = (point) => margin.left + ((point.game_number - first) / (last - first)) * chartWidth;
    const y = (score) => margin.top + ((max - score) / (max - min)) * chartHeight;
    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Solo/Duo LP推移" });
    for (let score = min; score <= max; score += 25) {
      const boundary = score % 100 === 0;
      svg.append(el("line", { x1: margin.left, y1: y(score), x2: width - margin.right, y2: y(score), stroke: boundary ? "#3b4861" : "#252e40", "stroke-width": boundary ? 1.2 : 1 }));
      if (boundary) svg.append(el("text", { x: margin.left - 9, y: y(score) + 4, fill: "#aeb9ca", "font-size": 10, "text-anchor": "end" }, `${rankTick(score)} ${score % 100}`));
    }
    const desiredTicks = global.innerWidth <= 430 ? 4 : 6;
    const rawStep = Math.max(1, Math.ceil((last - first) / desiredTicks));
    const magnitude = 10 ** Math.floor(Math.log10(rawStep));
    const normalized = rawStep / magnitude;
    const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
    const tickValues = new Set([first, last]);
    for (let game = Math.ceil(first / step) * step; game <= last; game += step) tickValues.add(game);
    [...tickValues].sort((left, right) => left - right).forEach((game) => {
      svg.append(el("text", { x: margin.left + ((game - first) / (last - first)) * chartWidth, y: height - 21, fill: "#8a94a7", "font-size": 11, "text-anchor": "middle" }, String(game)));
    });
    svg.append(el("text", { x: margin.left + chartWidth / 2, y: height - 5, fill: "#8a94a7", "font-size": 11, "text-anchor": "middle" }, "累積ランク試合数（第N戦）"));
    const exact = officialPoints.filter((point) => point.kind === "exact");
    let priorPatch = "";
    exact.forEach((point) => {
      if (point.patch && point.patch !== priorPatch) {
        priorPatch = point.patch;
        const pointX = x(point);
        svg.append(el("line", { x1: pointX, y1: margin.top, x2: pointX, y2: height - margin.bottom, stroke: "#f0b429", "stroke-opacity": .55, "stroke-dasharray": "4 4" }));
        svg.append(el("text", { x: pointX + 4, y: margin.top - 10, fill: "#f0b429", "font-size": 11 }, point.patch));
      }
    });
    function renderSegments(series, attrs) {
      const segments = new Map();
      series.forEach((point) => {
        if (!segments.has(point.segment_id)) segments.set(point.segment_id, []);
        segments.get(point.segment_id).push(point);
      });
      segments.forEach((segment) => {
        if (segment.length < 2) return;
        svg.append(el("polyline", {
          points: segment.map((point) => `${x(point)},${y(point.score)}`).join(" "),
          fill: "none",
          "stroke-linejoin": "round",
          "stroke-linecap": "round",
          ...attrs,
        }));
      });
    }

    renderSegments(historicalPoints, { stroke: "#5b8cff", "stroke-width": 2, "stroke-opacity": .55, "stroke-dasharray": "6 4" });
    renderSegments(officialPoints, { stroke: "#5b8cff", "stroke-width": 3 });
    [...historicalPoints, ...officialPoints].forEach((point) => {
      const marker = pointShape(point, x(point), y(point.score));
      const matchUrl = pointMatchUrl(point);
      const label = pointLabel(point).replaceAll("\n", ", ");
      marker.setAttribute("tabindex", "0");
      marker.setAttribute("role", matchUrl ? "link" : "img");
      marker.setAttribute("aria-label", matchUrl ? `${label}、試合詳細を見る` : label);
      if (matchUrl) marker.classList.add("lp-point-link");
      marker.append(el("title", {}, pointLabel(point)));
      marker.addEventListener("pointerdown", (event) => showTooltip(point, event));
      marker.addEventListener("focus", () => showTooltip(point));
      if (matchUrl) {
        marker.addEventListener("click", () => openMatchDetail(point));
        marker.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openMatchDetail(point);
          }
        });
      } else {
        marker.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            showTooltip(point);
          }
        });
      }
      svg.append(marker);
    });
    chart.append(svg);
  }

  function championSummary(matches) {
    const groups = new Map();
    matches.forEach((match) => {
      const key = match.champion || "Unknown";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(match);
    });
    return [...groups.entries()].map(([champion, values]) => {
      const result = record(values);
      const coverage = usableCoverage(values);
      const stats = values.filter((match) => [match.kills, match.deaths, match.assists].every(Number.isFinite));
      const totals = stats.reduce((total, match) => ({
        kills: total.kills + match.kills,
        deaths: total.deaths + match.deaths,
        assists: total.assists + match.assists,
      }), { kills: 0, deaths: 0, assists: 0 });
      const average = (key) => {
        const available = values.map((match) => match[key]).filter(Number.isFinite);
        return available.length ? available.reduce((total, value) => total + value, 0) / available.length : null;
      };
      return {
        champion,
        name: values[0].champion_name || champion,
        icon: values[0].champion_icon_id,
        result,
        coverage,
        stats,
        averages: stats.length ? {
          kills: totals.kills / stats.length,
          deaths: totals.deaths / stats.length,
          assists: totals.assists / stats.length,
          kda: (totals.kills + totals.assists) / Math.max(totals.deaths, 1),
        } : null,
        kp: average("kp_pct"),
        vision: average("vision_score"),
        vspm: average("vision_score_per_min"),
      };
    }).sort((a, b) => b.result.games - a.result.games || (b.coverage.delta ?? -Infinity) - (a.coverage.delta ?? -Infinity) || a.name.localeCompare(b.name, "ja"));
  }

  function renderChampionTable(matches, version) {
    const body = global.document.getElementById("lp-champion-body");
    const empty = global.document.getElementById("lp-champion-empty");
    const rows = championSummary(matches);
    body.replaceChildren(); empty.hidden = rows.length !== 0;
    rows.forEach((row) => {
      const tr = global.document.createElement("tr");
      const champ = htmlEl("td", "lp-champ");
      if (row.icon) { const image = global.document.createElement("img"); image.loading = "lazy"; image.alt = ""; image.src = `https://ddragon.leagueoflegends.com/cdn/${version}/img/champion/${row.icon}.png`; champ.append(image); }
      champ.append(htmlEl("span", "", row.name));
      const kda = row.averages;
      const kdaText = kda ? `${kda.kills.toFixed(1)} / ${kda.deaths.toFixed(1)} / ${kda.assists.toFixed(1)}` : "-";
      const formatDecimal = (value, digits) => Number.isFinite(value) ? value.toFixed(digits) : "-";
      const formatPercent = (value) => Number.isFinite(value) ? `${value.toFixed(1)}%` : "-";
      tr.append(
        champ,
        htmlEl("td", "", String(row.result.games)),
        htmlEl("td", "", `${row.result.wins}-${row.result.losses}`),
        htmlEl("td", "", percentage(row.result.wins, row.result.known)),
        htmlEl("td", "", kda ? kda.kda.toFixed(2) : "-"),
        htmlEl("td", "lp-kda", kdaText),
        htmlEl("td", "", formatPercent(row.kp)),
        htmlEl("td", "", formatDecimal(row.vision, 1)),
        htmlEl("td", "", formatDecimal(row.vspm, 2)),
      );
      const lp = htmlEl("td", Number.isFinite(row.coverage.delta) ? row.coverage.delta >= 0 ? "good" : "bad" : "", signed(row.coverage.delta));
      tr.append(lp, htmlEl("td", "", `${row.coverage.available.length} / ${row.result.games}`));
      body.append(tr);
    });
  }

  function init(data) {
    const controls = { period: global.document.getElementById("lp-period"), patch: global.document.getElementById("lp-patch"), start: global.document.getElementById("lp-start"), end: global.document.getElementById("lp-end"), custom: global.document.getElementById("lp-custom") };
    const historicalPoints = data.historical?.points || [];
    const patches = [...new Set([
      ...data.matches.map((match) => match.patch),
      ...historicalPoints.map((point) => point.patch),
    ].filter(Boolean))].sort().reverse();
    patches.forEach((patch) => { const option = global.document.createElement("option"); option.value = patch; option.textContent = patch; controls.patch.append(option); });
    global.document.getElementById("lp-tracking").textContent = `LP履歴開始：${localDate(data.history_started_jst || data.tracking_started_jst).replaceAll("-", "/")}`;
    const legend = global.document.getElementById("lp-chart-legend");
    const notice = global.document.getElementById("lp-historical-notice");
    if (historicalPoints.length) {
      legend.hidden = false;
      notice.hidden = false;
      notice.textContent = data.historical.notice;
    }
    renderOverall(data);
    function render() {
      controls.custom.hidden = controls.period.value !== "custom";
      const range = rangeFor(controls.period.value, data, controls);
      const matches = filterMatches(data, range, controls.patch.value);
      const usable = filterUsableMatches(data, range, controls.patch.value);
      let points = filterPoints(data, range, controls.patch.value);
      if (controls.patch.value === "all") points = points.filter((point) => inRange(point.timestamp_jst, range));
      const historical = filterHistoricalPoints(data, range, controls.patch.value);
      renderFiltered(usable); renderChart(points, historical); renderChampionTable(usable, data.ddragon_version);
    }
    [controls.period, controls.patch, controls.start, controls.end].forEach((control) => control.addEventListener("change", render));
    render();
  }

  global.LPProgress = { rankLabel, record, exactCoverage, usableCoverage, championSummary, filterMatches, filterUsableMatches, pointMatchUrl };
  try {
    const source = global.document.getElementById("lp-progress-data");
    if (!source) throw new Error("payload unavailable");
    init(JSON.parse(source.textContent));
  } catch (_error) {
    const empty = global.document.getElementById("lp-empty");
    empty.textContent = "LP Progressデータを読み込めませんでした";
    empty.hidden = false;
  }
})(window);

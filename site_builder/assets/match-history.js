(function (global) {
  "use strict";

  const PAGE_SIZE = 20;
  const ROLE_NAMES = { UTILITY: "SUP", MIDDLE: "MID", TOP: "TOP", BOTTOM: "ADC", JUNGLE: "JG" };
  const text = (tag, value, className) => {
    const element = global.document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    return element;
  };
  const decimal = (value, digits) => global.SiteUtils.formatDecimal(value, digits);
  const duration = (seconds) => {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
  };

  function card(match, version) {
    const metrics = global.MatchHistoryMetrics;
    const element = text("article", "", `match ${match.win ? "win" : "loss"}`);
    const result = text("div", match.win ? "WIN" : "LOSS", "m-result");
    const champion = text("div", "", "m-champ");
    const image = global.document.createElement("img");
    image.loading = "lazy";
    image.src = global.SiteUtils.championImageUrl(version, match.champion_icon_id);
    image.alt = match.champion_name || match.champion;
    const identity = text("div", "");
    identity.append(
      text("div", match.champion_name || match.champion, "m-champ-name"),
      text("div", `${ROLE_NAMES[match.role] || match.role} · ${match.queue_name || match.queue_id}`, "m-meta")
    );
    champion.append(image, identity);
    const kda = text("div", `${match.kills} / ${match.deaths} / ${match.assists}`, "m-kda");
    const stats = text("div", "", "m-stats");
    stats.append(
      text("div", `CS ${Math.round(match.cs)} (${decimal(metrics.rate(match.cs, match), 2)}/m) · VS ${Math.round(match.vision_score)} (${decimal(metrics.rate(match.vision_score, match), 2)}/m)`),
      text("div", `Damage ${Math.round(match.damage_to_champions)} (${decimal(metrics.rate(match.damage_to_champions, match), 0)}/m) · Time ${duration(match.game_duration_seconds)}`)
    );
    const when = text("div", "", "m-date");
    when.append(text("div", `Patch ${match.patch || "-"}`), text("div", String(match.date || "").slice(0, 16)));
    element.append(result, champion, kda, stats, when);
    return element;
  }

  function create(section, initialMatches) {
    const mode = section.dataset.matchHistoryMode;
    const resultControl = section.querySelector("[data-match-history-result]");
    const sortControl = section.querySelector("[data-match-history-sort]");
    const directionControl = section.querySelector("[data-match-history-direction]");
    Object.entries(global.MatchHistoryMetrics.SORTS).forEach(([value, definition]) => {
      const option = global.document.createElement("option");
      option.value = value; option.textContent = definition.label; sortControl.append(option);
    });
    sortControl.value = "date";
    directionControl.value = "desc";
    let source = initialMatches.slice();
    let visible = PAGE_SIZE;

    const topControls = mode === "top" ? {
      period: section.querySelector("#mh-period"), champion: section.querySelector("#mh-champion"),
      queue: section.querySelector("#mh-queue"), role: section.querySelector("#mh-role"),
      start: section.querySelector("#mh-start"), end: section.querySelector("#mh-end"), custom: section.querySelector("#mh-custom"),
    } : null;

    function selectedMatches() {
      let matches = source;
      if (topControls) {
        matches = global.MatchHistoryMetrics.filterTopMatches(source, {
          period: topControls.period.value, champion: topControls.champion.value,
          queue: topControls.queue.value, role: topControls.role.value,
          result: resultControl.value, start: topControls.start.value, end: topControls.end.value,
        });
      } else if (resultControl.value !== "ALL") {
        matches = matches.filter((match) => match.win === (resultControl.value === "WIN"));
      }
      return global.MatchHistoryMetrics.sortMatches(matches, sortControl.value, directionControl.value);
    }

    function render(reset) {
      if (reset) visible = PAGE_SIZE;
      if (topControls) topControls.custom.hidden = topControls.period.value !== "custom";
      const matches = selectedMatches();
      const shown = matches.slice(0, visible);
      section.querySelector("[data-match-history-list]").replaceChildren(...shown.map((match) => card(match, section.dataset.ddragonVersion)));
      section.querySelector("[data-match-history-summary]").textContent = `${matches.length}件中 ${shown.length}件を表示`;
      section.querySelector("[data-match-history-empty]").hidden = matches.length !== 0;
      section.querySelector("[data-match-history-more]").hidden = shown.length >= matches.length;
      return matches;
    }

    [resultControl, sortControl, directionControl].forEach((control) => control.addEventListener("change", () => render(true)));
    if (topControls) {
      [topControls.period, topControls.champion, topControls.queue, topControls.role, topControls.start, topControls.end]
        .forEach((control) => control.addEventListener("change", () => render(true)));
    }
    section.querySelector("[data-match-history-more]").addEventListener("click", () => { visible += PAGE_SIZE; render(false); });
    return { render, setMatches(matches) { source = matches.slice(); return render(true); }, getMatches: selectedMatches };
  }

  function init() {
    const section = global.document.querySelector(".match-history");
    if (!section) return;
    const mode = section.dataset.matchHistoryMode;
    const data = mode === "top" ? global.document.getElementById("match-history-data") : global.document.getElementById("role-match-data");
    const initial = mode === "role" ? [] : JSON.parse(data.textContent);
    const component = create(section, initial);
    global.MatchHistory = component;
    if (mode === "role") {
      global.document.addEventListener("role-filter:change", (event) => component.setMatches(event.detail.matches));
    } else {
      component.render(true);
    }
  }

  if (global.document) init();
  const api = { PAGE_SIZE, card, create };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

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
  const clock = (milliseconds) => duration((Number(milliseconds) || 0) / 1000);
  const personName = (person) => {
    if (typeof person === "string") return person;
    if (!person) return "Unknown";
    return person.champion_name || person.champion || "Unknown";
  };
  const FIGHT_LABELS = {
    EARLY: "序盤", MID: "中盤", LATE: "終盤",
    SOLO: "単独戦", SMALL: "小規模戦", SKIRMISH: "小集団戦", TEAMFIGHT: "集団戦",
    WIN: "勝利", EVEN: "五分", LOSS: "敗北",
    SURVIVED: "生存", DIED: "死亡",
    GAIN: "獲得", NONE: "なし",
  };
  const OBJECTIVE_LABELS = {
    DRAGON: "ドラゴン", BARON_NASHOR: "バロン", RIFTHERALD: "ヘラルド", HORDE: "ヴォイドグラブ",
    TOWER_BUILDING: "タワー", INHIBITOR_BUILDING: "インヒビター",
    AIR_DRAGON: "クラウドドラゴン", CHEMTECH_DRAGON: "ケミテックドラゴン",
    EARTH_DRAGON: "マウンテンドラゴン", ELDER_DRAGON: "エルダードラゴン",
    FIRE_DRAGON: "インファーナルドラゴン", HEXTECH_DRAGON: "ヘクステックドラゴン",
    WATER_DRAGON: "オーシャンドラゴン",
    TOP_LANE: "トップ", MID_LANE: "ミッド", BOT_LANE: "ボット",
  };
  const PERIOD_LABELS = { BEFORE: "戦闘前", DURING: "戦闘中", AFTER: "戦闘後" };
  const RELATION_LABELS = { FRIENDLY: "味方", ENEMY: "敵", UNKNOWN: "不明" };
  const localized = (value, labels) => labels[value] || value || "-";
  const badge = (value, type) => text("span", localized(value, FIGHT_LABELS), `fight-badge fight-${type}-${String(value || "unknown").toLowerCase()}`);

  function objectiveName(objective) {
    if (objective.type === "BUILDING_KILL") {
      const building = localized(objective.building_type || "TOWER_BUILDING", OBJECTIVE_LABELS);
      const lane = objective.lane_type ? `（${localized(objective.lane_type, OBJECTIVE_LABELS)}）` : "";
      return `${building}${lane}`;
    }
    const monster = localized(objective.monster_type || "OBJECTIVE", OBJECTIVE_LABELS);
    const subtype = objective.monster_sub_type ? `（${localized(objective.monster_sub_type, OBJECTIVE_LABELS)}）` : "";
    return `${monster}${subtype}`;
  }

  function fightCard(fight) {
    const item = text("section", "", `fight-item fight-item-${String(fight.result || "even").toLowerCase()}`);
    const header = text("div", "", "fight-item-header");
    header.append(
      text("strong", `戦闘 #${fight.fight_id ?? "-"}`, "fight-title"),
      text("span", `${clock(fight.start_timestamp)}–${clock(fight.end_timestamp)}`, "fight-time"),
      badge(fight.phase, "phase"),
      badge(fight.scale, "scale"),
      badge(fight.result, "result"),
      badge(fight.survival, "survival")
    );

    const kda = fight.my_kda || {};
    const metrics = text("div", "", "fight-metrics");
    metrics.append(
      text("span", `K/D/A ${Number(kda.kills) || 0}/${Number(kda.deaths) || 0}/${Number(kda.assists) || 0}`),
      text("span", `キル交換 ${Number(fight.friendly_kills) || 0}-${Number(fight.enemy_kills) || 0}`),
      text("span", `参加者 ${Number(fight.participant_count) || 0}`),
      text("span", `戦闘時間 ${Math.round((Number(fight.duration_ms) || 0) / 1000)}秒`)
    );

    const participants = text("div", "", "fight-participants");
    const participantGroups = text("div", "", "fight-participant-groups");
    const people = fight.participants || [];
    const participantRows = [
      ["味方", people.filter((person) => person.relation === "FRIENDLY")],
      ["敵", people.filter((person) => person.relation === "ENEMY")],
    ];
    const unknown = people.filter(
      (person) => person.relation !== "FRIENDLY" && person.relation !== "ENEMY"
    );
    if (unknown.length) participantRows.push(["不明", unknown]);
    participantRows.forEach(([label, members]) => {
      const row = text("div", "", "fight-participant-row");
      row.append(
        text("strong", `${label}:`, "fight-participant-label"),
        text("span", members.map(personName).join(" / ") || "-")
      );
      participantGroups.append(row);
    });
    participants.append(
      text("strong", "参加者", "fight-participants-heading"),
      participantGroups
    );

    const kills = text("div", "", "fight-subsection");
    kills.append(text("strong", "キル経過", "fight-subheading"));
    const killEvents = (fight.events || []).filter((event) => event.type === "CHAMPION_KILL");
    if (!killEvents.length) {
      kills.append(text("div", "チャンピオンキルなし", "fight-empty"));
    } else {
      const list = text("div", "", "fight-event-list");
      killEvents.forEach((event) => {
        const assists = (event.assists || []).map(personName);
        const assistText = assists.length ? ` [アシスト: ${assists.join(", ")}]` : "";
        list.append(text("div", `${clock(event.timestamp)} ${personName(event.killer)} → ${personName(event.victim)}${assistText}`));
      });
      kills.append(list);
    }

    const objectives = text("div", "", "fight-subsection");
    objectives.append(text("strong", "オブジェクト状況", "fight-subheading"));
    const context = fight.objective_context || {};
    objectives.append(text("div", `戦闘前: ${localized(context.before || "NONE", FIGHT_LABELS)} · 戦闘中: ${localized(context.during || "NONE", FIGHT_LABELS)} · 戦闘後: ${localized(context.after || "NONE", FIGHT_LABELS)}`, "fight-objective-context"));
    const objectiveList = text("div", "", "fight-event-list");
    [
      ["BEFORE", fight.objectives_before],
      ["DURING", fight.objectives_during],
      ["AFTER", fight.objectives_after],
    ].forEach(([period, events]) => {
      (events || []).forEach((objective) => {
        objectiveList.append(text("div", `${localized(period, PERIOD_LABELS)} ${clock(objective.timestamp)} ${localized(objective.relation || "UNKNOWN", RELATION_LABELS)} ${objectiveName(objective)}`));
      });
    });
    if (!objectiveList.children.length) objectiveList.append(text("div", "オブジェクトイベントなし", "fight-empty"));
    objectives.append(objectiveList);

    item.append(header, metrics, participants, kills, objectives);
    return item;
  }

  function addFightDetail(element, when, match) {
    const fights = Array.isArray(match.fights) ? match.fights : [];
    if (!fights.length) return;
    const detailId = `fight-detail-${String(match.match_id || "match").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const button = text("button", `戦闘詳細 (${fights.length})`, "m-fight-toggle");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", detailId);
    const detail = text("div", "", "fight-detail");
    detail.id = detailId;
    detail.hidden = true;
    button.addEventListener("click", () => {
      const opening = detail.hidden;
      if (opening && detail.dataset.rendered !== "true") {
        detail.replaceChildren(...fights.map(fightCard));
        detail.dataset.rendered = "true";
      }
      detail.hidden = !opening;
      button.setAttribute("aria-expanded", String(opening));
      button.textContent = `${opening ? "戦闘詳細を閉じる" : "戦闘詳細"} (${fights.length})`;
    });
    when.append(button);
    element.append(detail);
  }

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
    const kda = text("div", "", "m-kda");
    kda.append(
      text("div", `${match.kills} / ${match.deaths} / ${match.assists}`),
      text("div", `(${match.team_kills} / ${match.team_deaths} / ${match.team_assists})`)
    );
    const stats = text("div", "", "m-stats");
    stats.append(
      text(
        "div",
        `CS ${Math.round(match.cs)} (${decimal(metrics.rate(match.cs, match), 2)}/m) · ` +
        `VS ${Math.round(match.vision_score)} (${decimal(metrics.rate(match.vision_score, match), 2)}/m)`
      ),
      text(
        "div",
        `Damage ${Math.round(match.damage_to_champions)} ` +
        `(${decimal(metrics.rate(match.damage_to_champions, match), 0)}/m) · ` +
        `Time ${duration(match.game_duration_seconds)}`
      ),
      text(
        "div",
        `戦闘 ${Number(match.fight_wins) || 0}W-` +
        `${Number(match.fight_evens) || 0}E-` +
        `${Number(match.fight_losses) || 0}L · ` +
        `生存 ${Number(match.survived_fights) || 0}/${Number(match.my_fights) || 0} · ` +
        `集団戦 ${Number(match.teamfights) || 0}`,
        "m-fight"
      )
    );
    const when = text("div", "", "m-date");
    when.append(text("div", `Patch ${match.patch || "-"}`), text("div", String(match.date || "").slice(0, 16)));
    element.append(result, champion, kda, stats, when);
    addFightDetail(element, when, match);
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

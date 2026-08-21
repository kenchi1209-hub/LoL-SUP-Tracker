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
  const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
  const percent = (numerator, denominator) => denominator ? `${decimal(number(numerator) / number(denominator) * 100, 1)}%` : "-";
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
  const fightPersonName = (person) => {
    const role = person && person.role && person.role !== "UNKNOWN" ? person.role : "不明";
    return `${role}:${personName(person)}`;
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
    const people = Array.isArray(fight.participants) ? fight.participants : [];
    const friendlyCount = people.filter((person) => person.relation === "FRIENDLY").length;
    const enemyCount = people.filter((person) => person.relation === "ENEMY").length;
    const metrics = text("div", "", "fight-metrics");
    metrics.append(
      text("span", `K/D/A：${Number(kda.kills) || 0}/${Number(kda.deaths) || 0}/${Number(kda.assists) || 0}`),
      text("span", `キル交換：${Number(fight.friendly_kills) || 0}-${Number(fight.enemy_kills) || 0}`),
      text("span", `参加者：${people.length} (${friendlyCount}-${enemyCount})`),
      text("span", `戦闘時間：${Math.round((Number(fight.duration_ms) || 0) / 1000)}秒`)
    );

    const participants = text("div", "", "fight-participants");
    const participantGroups = text("div", "", "fight-participant-groups");
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
        text("span", members.map(fightPersonName).join(" / ") || "-")
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

  function metricGroup(title, entries) {
    const section = text("section", "", "match-detail-group");
    section.append(text("h4", title));
    const list = text("dl", "", "match-detail-metrics");
    entries.forEach(([label, value]) => {
      const item = text("div", "", "match-detail-metric");
      item.append(text("dt", label), text("dd", value));
      list.append(item);
    });
    section.append(list);
    return section;
  }

  function playerCell(label, value, className) {
    const cell = text("span", value, className || "");
    cell.dataset.label = label;
    cell.setAttribute("role", "cell");
    return cell;
  }

  function playerComparison(match) {
    const detail = match.detail || {};
    const participants = Array.isArray(detail.participants) ? detail.participants : [];
    const table = text("div", "", "match-player-table");
    table.setAttribute("role", "table");
    table.setAttribute("aria-label", "味方・敵10人比較");
    const header = text("div", "", "match-player-header");
    header.setAttribute("role", "row");
    ["Team", "Role", "Champ", "K/D/A", "CS/m (CS)", "VS/m (VS)", "DPM (DMG)"].forEach((label) => {
      const cell = text("span", label);
      cell.setAttribute("role", "columnheader");
      header.append(cell);
    });
    table.append(header);
    const seconds = number(detail.game_duration_seconds) || number(match.game_duration_seconds);
    participants.forEach((participant) => {
      const row = text("div", "", `match-player-row match-player-${String(participant.relation || "unknown").toLowerCase()}`);
      row.setAttribute("role", "row");
      if (participant.is_self) row.classList.add("match-player-self");
      const cs = number(participant.cs);
      const vision = number(participant.vision_score);
      const damage = number(participant.damage_to_champions);
      const perMinute = (value, digits) => seconds ? decimal(value / (seconds / 60), digits) : "-";
      row.append(
        playerCell("Team", participant.relation || "-", "match-player-team"),
        playerCell("Role", ROLE_NAMES[participant.role] || participant.role || "-"),
        playerCell("Champ", participant.champion_name || participant.champion || "-", "match-player-champion"),
        playerCell("K/D/A", `${number(participant.kills)}/${number(participant.deaths)}/${number(participant.assists)}`),
        playerCell("CS/m (CS)", `${perMinute(cs, 1)} (${Math.round(cs)})`),
        playerCell("VS/m (VS)", `${perMinute(vision, 2)} (${Math.round(vision)})`),
        playerCell("DPM (DMG)", `${perMinute(damage, 0)} (${Math.round(damage).toLocaleString("ja-JP")})`)
      );
      table.append(row);
    });
    if (!participants.length) table.append(text("div", "10人比較データなし", "match-detail-empty"));
    return table;
  }

  function matchDetailContent(match) {
    const detail = match.detail || {};
    const participants = Array.isArray(detail.participants) ? detail.participants : [];
    const self = participants.find((participant) => participant.is_self);
    const allyDamage = participants
      .filter((participant) => participant.relation === "ALLY")
      .reduce((sum, participant) => sum + number(participant.damage_to_champions), 0);
    const fights = number(match.my_fights);
    const fightWins = number(match.fight_wins);
    const survived = number(match.survived_fights);
    const ownKda = (number(match.kills) + number(match.assists)) / Math.max(number(match.deaths), 1);
    const root = text("div", "", "match-detail-content");
    const overview = text("div", "", "match-detail-overview");
    overview.append(
      metricGroup("試合情報", [
        ["日時", String(match.date || "-").slice(0, 16)],
        ["Patch", match.patch || "-"],
        ["Queue", match.queue_name || match.queue_id || "-"],
        ["Role", ROLE_NAMES[match.role] || match.role || "-"],
        ["Champion", match.champion_name || match.champion || "-"],
        ["結果", match.win ? "WIN" : "LOSS"],
        ["Game Time", duration(match.game_duration_seconds)],
      ]),
      metricGroup("自分の成績", [
        ["K/D/A", `${number(match.kills)} / ${number(match.deaths)} / ${number(match.assists)}`],
        ["KDA", decimal(ownKda, 2)],
        ["CS/m (CS)", `${decimal(global.MatchHistoryMetrics.rate(match.cs, match), 2)} (${Math.round(number(match.cs))})`],
        ["VS/m (VS)", `${decimal(global.MatchHistoryMetrics.rate(match.vision_score, match), 2)} (${Math.round(number(match.vision_score))})`],
        ["DPM (DMG)", `${decimal(global.MatchHistoryMetrics.rate(match.damage_to_champions, match), 0)} (${Math.round(number(match.damage_to_champions)).toLocaleString("ja-JP")})`],
      ]),
      metricGroup("チーム内比較", [
        ["Team K/D/A", `${number(match.team_kills)} / ${number(match.team_deaths)} / ${number(match.team_assists)}`],
        ["KP", percent(number(match.kills) + number(match.assists), number(match.team_kills))],
        ["Damage Share", percent(number(match.damage_to_champions), allyDamage)],
        ["Death Share", percent(number(match.deaths), number(match.team_deaths))],
      ]),
      metricGroup("視界", [
        ["Ward設置", String(number(match.wards_placed))],
        ["Ward破壊", String(number(match.wards_killed))],
        ["Control Ward購入", String(number(match.control_wards_bought))],
      ]),
      metricGroup("Fight Summary", [
        ["My Fights", String(fights)],
        ["W-E-L", `${fightWins}W-${number(match.fight_evens)}E-${number(match.fight_losses)}L`],
        ["Fight勝率", percent(fightWins, fights)],
        ["生存率", fights ? `${percent(survived, fights)} (${survived}/${fights})` : "-"],
        ["Teamfight", String(number(match.teamfights))],
      ])
    );
    root.append(overview, text("h4", "味方・敵10人比較", "match-player-title"), playerComparison(match));
    if (!self && participants.length) root.prepend(text("p", "自分の参加者データを確認できません", "match-detail-empty"));
    return root;
  }

  function addMatchDetail(element, actions, match) {
    const detail = match.detail || {};
    const participants = Array.isArray(detail.participants) ? detail.participants : [];
    const detailId = `match-detail-${String(match.match_id || "match").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const button = text("button", "試合詳細 ▼", "m-detail-toggle");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", detailId);
    button.setAttribute("aria-label", "試合詳細を開く");
    const panel = text("div", "", "match-detail");
    panel.id = detailId;
    panel.hidden = true;
    if (!participants.length) button.disabled = true;
    button.addEventListener("click", () => {
      const opening = panel.hidden;
      if (opening && panel.dataset.rendered !== "true") {
        panel.append(matchDetailContent(match));
        panel.dataset.rendered = "true";
      }
      panel.hidden = !opening;
      button.setAttribute("aria-expanded", String(opening));
      button.setAttribute("aria-label", opening ? "試合詳細を閉じる" : "試合詳細を開く");
      button.textContent = opening ? "▲" : "試合詳細 ▼";
    });
    actions.append(button);
    element.append(panel);
  }

  function addFightDetail(element, actions, match) {
    const fights = Array.isArray(match.fights) ? match.fights : [];
    const detailId = `fight-detail-${String(match.match_id || "match").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const button = text("button", "戦闘詳細 ▼", "m-fight-toggle");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", detailId);
    button.setAttribute("aria-label", `戦闘詳細を開く（${fights.length}件）`);
    if (!fights.length) button.disabled = true;
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
      button.setAttribute("aria-label", opening ? `戦闘詳細を閉じる（${fights.length}件）` : `戦闘詳細を開く（${fights.length}件）`);
      button.textContent = opening ? "▲" : "戦闘詳細 ▼";
    });
    actions.append(button);
    element.append(detail);
  }

  function card(match, version) {
    const metrics = global.MatchHistoryMetrics;
    const element = text("article", "", `match ${match.win ? "win" : "loss"}`);
    element.dataset.matchId = match.match_id || "";
    const result = text("div", match.win ? "WIN" : "LOSS", "m-result");
    const champion = text("div", "", "m-champ");
    const image = global.document.createElement("img");
    image.loading = "lazy";
    image.src = global.SiteUtils.championImageUrl(version, match.champion_icon_id);
    image.alt = match.champion_name || match.champion;
    const identity = text("div", "");
    identity.append(
      text("div", match.champion_name || match.champion, "m-champ-name"),
      text("div", `${ROLE_NAMES[match.role] || match.role}：${match.queue_name || match.queue_id}`, "m-meta")
    );
    champion.append(image, identity);
    const kda = text("div", "", "m-kda");
    kda.append(
      text("span", `${match.kills} / ${match.deaths} / ${match.assists}`, "m-kda-my"),
      text("span", "｜", "m-kda-separator"),
      text("span", `(${match.team_kills} / ${match.team_deaths} / ${match.team_assists})`, "m-kda-team")
    );
    const primary = text("div", "", "m-primary");
    primary.append(champion, kda);
    const stats = text("div", "", "m-stats");
    const statRow = (label, value, rate) => {
      const row = text("div", "", "m-stat-row");
      row.append(
        text("span", `${label}：`, "m-stat-label"),
        text("span", String(value), "m-stat-value"),
        text("span", `(${rate}/m)`, "m-stat-rate")
      );
      return row;
    };
    stats.append(
      statRow("CS", Math.round(match.cs), decimal(metrics.rate(match.cs, match), 2)),
      statRow("VS", Math.round(match.vision_score), decimal(metrics.rate(match.vision_score, match), 2))
    );
    const when = text("div", "", "m-date");
    when.append(
      text("div", `Time ${duration(match.game_duration_seconds)}`),
      text("div", String(match.date || "").slice(0, 16)),
      text("div", `Patch ${match.patch || "-"}`)
    );
    const actions = text("div", "", "m-actions");
    element.append(result, primary, stats, when, actions);
    addMatchDetail(element, actions, match);
    addFightDetail(element, actions, match);
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

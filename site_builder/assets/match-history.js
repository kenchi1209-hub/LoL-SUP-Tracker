(function (global) {
  "use strict";

  const PAGE_SIZE = 20;
  const ROLE_NAMES = { UTILITY: "SUP", MIDDLE: "MID", TOP: "TOP", BOTTOM: "ADC", JUNGLE: "JG" };
  const matchAnchorId = (matchId) => `match-${encodeURIComponent(String(matchId || ""))}`;
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
  const fightEventPersonName = (person, rolesByChampion) => {
    const champion = personName(person);
    const role = person && rolesByChampion.get(person.champion);
    return role ? `${role}:${champion}` : champion;
  };
  const fightPersonName = (person) => {
    const role = person && person.role && person.role !== "UNKNOWN" ? person.role : "不明";
    return `${role}:${personName(person)}`;
  };
  const FIGHT_LABELS = {
    EARLY: "序盤", MID: "中盤", LATE: "終盤",
    SOLO: "単独戦", SMALL: "小規模戦", SKIRMISH: "小集団戦", TEAMFIGHT: "集団戦",
    WIN: "勝利", EVEN: "五分", LOSS: "敗北",
    SURVIVED: "生存", DIED: "死亡", NOT_INVOLVED: "非参加",
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
    const titleLine = text("div", "", "fight-title-line");
    titleLine.append(
      text("strong", `戦闘 #${fight.fight_id ?? "-"}`, "fight-title"),
      text("span", `(${clock(fight.start_timestamp)}–${clock(fight.end_timestamp)})`, "fight-time")
    );
    const tags = text("div", "", "fight-tags");
    [
      badge(fight.phase, "phase"),
      badge(fight.scale, "scale"),
      badge(fight.result, "result"),
      badge(fight.survival, "survival"),
    ].forEach((tag, index) => {
      if (index) tags.append(text("span", "/", "fight-tag-separator"));
      tags.append(tag);
    });
    header.append(titleLine, tags);

    const notInvolved = fight.player_involved === false || fight.my_kda === null;
    const kda = fight.my_kda || {};
    const people = Array.isArray(fight.participants) ? fight.participants : [];
    const rolesByChampion = new Map(
      people
        .filter((person) => person && person.champion && ["TOP", "JG", "MID", "ADC", "SUP"].includes(person.role))
        .map((person) => [person.champion, person.role])
    );
    const friendlyCount = people.filter((person) => person.relation === "FRIENDLY").length;
    const enemyCount = people.filter((person) => person.relation === "ENEMY").length;
    const metrics = text("div", "", "fight-metrics");
    const sizeAndTime = text("div", "", "fight-metric-row");
    sizeAndTime.append(
      text("span", `参加者：${people.length} (${friendlyCount}-${enemyCount})`),
      text("span", "/", "fight-metric-separator"),
      text("span", `戦闘時間：${Math.round((Number(fight.duration_ms) || 0) / 1000)}秒`)
    );
    const exchangeAndKda = text("div", "", "fight-metric-row");
    exchangeAndKda.append(
      text("span", `キル交換：${Number(fight.friendly_kills) || 0}-${Number(fight.enemy_kills) || 0}`),
      text("span", "/", "fight-metric-separator"),
      text(
        "span",
        notInvolved
          ? "My K/D/A：非参加"
          : `My K/D/A：${Number(kda.kills) || 0}/${Number(kda.deaths) || 0}/${Number(kda.assists) || 0}`
      )
    );
    metrics.append(sizeAndTime, exchangeAndKda);

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
        text("strong", `${label}：`, "fight-participant-label"),
        text("span", members.map(fightPersonName).join(" / ") || "-")
      );
      participantGroups.append(row);
    });
    participants.append(participantGroups);

    const info = text("div", "", "fight-info");
    info.append(text("strong", "戦闘情報", "fight-info-heading"), metrics, participants);

    const kills = text("div", "", "fight-subsection");
    kills.append(text("strong", "キル経過", "fight-subheading"));
    const killEvents = (fight.events || []).filter((event) => event.type === "CHAMPION_KILL");
    if (!killEvents.length) {
      kills.append(text("div", "チャンピオンキルなし", "fight-empty"));
    } else {
      const list = text("div", "", "fight-event-list");
      killEvents.forEach((event) => {
        const assists = (event.assists || []).map((person) => fightEventPersonName(person, rolesByChampion));
        const assistText = assists.length ? ` [A: ${assists.join(", ")}]` : "";
        list.append(text("div", `${clock(event.timestamp)} K:${fightEventPersonName(event.killer, rolesByChampion)} → D:${fightEventPersonName(event.victim, rolesByChampion)}${assistText}`));
      });
      kills.append(list);
    }

    const objectives = text("div", "", "fight-subsection");
    objectives.append(text("strong", "オブジェクト状況", "fight-subheading"));
    const context = fight.objective_context || {};
    objectives.append(text("div", `戦闘前：${localized(context.before || "NONE", FIGHT_LABELS)} / 戦闘中：${localized(context.during || "NONE", FIGHT_LABELS)} / 戦闘後：${localized(context.after || "NONE", FIGHT_LABELS)}`, "fight-objective-context"));
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
    if (!objectiveList.children.length) objectiveList.append(text("div", "オブジェクトイベント：なし", "fight-empty"));
    objectives.append(objectiveList);

    item.append(header, info, kills, objectives);
    return item;
  }

  function metricGroup(title, entries, className) {
    const section = text("section", "", `match-detail-group${className ? ` ${className}` : ""}`);
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

  function matchRate(value, match, digits = 1) {
    const seconds = number(match.game_duration_seconds);
    return seconds ? decimal(number(value) / (seconds / 60), digits) : "-";
  }

  function selfParticipant(match) {
    const participants = Array.isArray(match.detail?.participants) ? match.detail.participants : [];
    return participants.find((participant) => participant.is_self) || null;
  }

  function allyDamage(match) {
    const participants = Array.isArray(match.detail?.participants) ? match.detail.participants : [];
    return participants
      .filter((participant) => participant.relation === "ALLY")
      .reduce((sum, participant) => sum + number(participant.damage_to_champions), 0);
  }

  function kdaText(match) {
    return `${number(match.kills)} / ${number(match.deaths)} / ${number(match.assists)}`;
  }

  function ownKda(match) {
    return (number(match.kills) + number(match.assists)) / Math.max(number(match.deaths), 1);
  }

  const ROLE_SUMMARY_DEFINITIONS = {
    UTILITY: {
      title: "視界 / 支援",
      fields: (match) => [
        ["Vision Score", String(number(match.vision_score))],
        ["VS/min", matchRate(match.vision_score, match, 2)],
        ["Ward設置", String(number(match.wards_placed))],
        ["Ward破壊", String(number(match.wards_killed))],
        ["Control Ward購入", String(number(match.control_wards_bought))],
      ],
    },
    BOTTOM: {
      title: "レーン / 火力",
      fields: (match) => [
        ["CS/m (CS)", `${matchRate(match.cs, match, 2)} (${Math.round(number(match.cs))})`],
        ["Gold", number(match.gold_earned).toLocaleString("ja-JP")],
        ["Gold/min", matchRate(match.gold_earned, match, 0)],
        ["DMG", number(match.damage_to_champions).toLocaleString("ja-JP")],
        ["DPM", matchRate(match.damage_to_champions, match, 0)],
      ],
    },
    MIDDLE: {
      title: "レーン / ローム",
      fields: (match) => [
        ["CS/m (CS)", `${matchRate(match.cs, match, 2)} (${Math.round(number(match.cs))})`],
        ["Gold/min", matchRate(match.gold_earned, match, 0)],
        ["K/D/A", kdaText(match)],
        ["KP", percent(number(match.kills) + number(match.assists), number(match.team_kills))],
        ["DPM", matchRate(match.damage_to_champions, match, 0)],
      ],
    },
    TOP: {
      title: "レーン / 耐久",
      fields: (match) => [
        ["CS/m (CS)", `${matchRate(match.cs, match, 2)} (${Math.round(number(match.cs))})`],
        ["Gold", number(match.gold_earned).toLocaleString("ja-JP")],
        ["K/D/A", kdaText(match)],
        ["Damage", number(match.damage_to_champions).toLocaleString("ja-JP")],
        ["Death", String(number(match.deaths))],
      ],
    },
    JUNGLE: {
      title: "ガンク / オブジェクト",
      fields: (match) => [
        ["K/D/A", kdaText(match)],
        ["KP", percent(number(match.kills) + number(match.assists), number(match.team_kills))],
        ["CS/m (CS)", `${matchRate(match.cs, match, 2)} (${Math.round(number(match.cs))})`],
        ["Objective獲得", String(number(match.objective_before_gain) + number(match.objective_during_gain) + number(match.objective_after_gain))],
        ["DPM", matchRate(match.damage_to_champions, match, 0)],
      ],
    },
  };

  function roleSummaryDefinition(role) {
    return ROLE_SUMMARY_DEFINITIONS[role] || {
      title: "試合概要",
      fields: (match) => [
        ["K/D/A", kdaText(match)],
        ["CS/m", matchRate(match.cs, match, 2)],
        ["VS/m", matchRate(match.vision_score, match, 2)],
        ["Gold/min", matchRate(match.gold_earned, match, 0)],
        ["DPM", matchRate(match.damage_to_champions, match, 0)],
      ],
    };
  }

  function fightSummaryEntries(match) {
    const allFights = Array.isArray(match.all_fights) ? match.all_fights : [];
    const fights = allFights.length
      ? allFights.filter((fight) => fight.player_involved === true).length
      : number(match.my_fights);
    const totalFights = allFights.length;
    const fightWins = number(match.fight_wins);
    const survived = number(match.survived_fights);
    const teamfights = number(match.teamfights);
    const countWithPercent = (numerator, denominator) => {
      const counts = `${numerator} / ${denominator}`;
      return denominator ? `${counts}（${percent(numerator, denominator)}）` : counts;
    };
    return [
      ["My Fights", countWithPercent(fights, totalFights)],
      ["W-E-L", `${fightWins}W-${number(match.fight_evens)}E-${number(match.fight_losses)}L`],
      ["Fight勝率", fights ? `${percent(fightWins, fights)} (${fightWins}/${fights})` : "-"],
      ["生存率", fights ? `${percent(survived, fights)} (${survived}/${fights})` : "-"],
      ["Teamfight", countWithPercent(teamfights, fights)],
    ];
  }

  function overviewGroups(match) {
    const detail = match.detail || {};
    return [
      ["試合情報", [
        ["日時", String(match.date || "-").slice(0, 16)],
        ["Patch", match.patch || "-"],
        ["Queue", match.queue_name || match.queue_id || "-"],
        ["Game Time", duration(match.game_duration_seconds)],
        ["Role", ROLE_NAMES[match.role] || match.role || "-"],
        ["Champion", match.champion_name || match.champion || "-"],
        ["Side", detail.side || "-"],
        ["結果", match.win ? "WIN" : "LOSS"],
      ], "match-detail-info"],
      ["パフォーマンス", [
        ["K/D/A (KDA)", `${kdaText(match)} (${decimal(ownKda(match), 2)})`],
        ["CS/m (CS)", `${matchRate(match.cs, match, 2)} (${Math.round(number(match.cs))})`],
        ["VS/m (VS)", `${matchRate(match.vision_score, match, 2)} (${Math.round(number(match.vision_score))})`],
        ["DPM (DMG)", `${matchRate(match.damage_to_champions, match, 0)} (${Math.round(number(match.damage_to_champions)).toLocaleString("ja-JP")})`],
        ["Team K/D/A", `${number(match.team_kills)} / ${number(match.team_deaths)} / ${number(match.team_assists)}`],
        ["KP", percent(number(match.kills) + number(match.assists), number(match.team_kills))],
        ["Damage Share", percent(number(match.damage_to_champions), allyDamage(match))],
        ["Death Share", percent(number(match.deaths), number(match.team_deaths))],
      ], "match-detail-performance"],
      [roleSummaryDefinition(match.role).title, roleSummaryDefinition(match.role).fields(match), "match-detail-role-summary"],
    ];
  }

  function detailStatGroups(match) {
    const self = selfParticipant(match);
    return [
      ["Combat", [
        ["K/D/A", kdaText(match)],
        ["KDA", decimal(ownKda(match), 2)],
        ["Damage to Champions", number(match.damage_to_champions).toLocaleString("ja-JP")],
        ["DPM", matchRate(match.damage_to_champions, match, 0)],
      ], "match-detail-combat"],
      ["Economy", [
        ["Gold Earned", number(match.gold_earned).toLocaleString("ja-JP")],
        ["Gold/min", matchRate(match.gold_earned, match, 0)],
        ["CS", String(Math.round(number(match.cs)))],
        ["CS/min", matchRate(match.cs, match, 2)],
      ], "match-detail-economy"],
      ["Vision", [
        ["Vision Score", String(number(match.vision_score))],
        ["VS/min", matchRate(match.vision_score, match, 2)],
        ["Wards Placed", String(number(match.wards_placed))],
        ["Wards Killed", String(number(match.wards_killed))],
        ["Control Ward", String(number(match.control_wards_bought))],
      ], "match-detail-vision"],
      ["Team Contribution", [
        ["Team K/D/A", `${number(match.team_kills)} / ${number(match.team_deaths)} / ${number(match.team_assists)}`],
        ["KP", percent(number(match.kills) + number(match.assists), number(match.team_kills))],
        ["Team Damage%", percent(number(match.damage_to_champions), allyDamage(match))],
        ["Death Share", percent(number(match.deaths), number(match.team_deaths))],
        ["Rank snapshot", self?.rank || "-"],
      ], "match-detail-team"],
    ];
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
    const playerSide = detail.side === "BLUE" || detail.side === "RED" ? detail.side : "";
    const table = text("div", "", "match-player-table");
    table.setAttribute("role", "table");
    table.setAttribute("aria-label", "味方・敵10人比較");
    const header = text("div", "", "match-player-header");
    header.setAttribute("role", "row");
    ["Role", "Champ", "Rank", "K/D/A", "KP%", "CS/m", "VS/m", "DMG%", "DPM"].forEach((label) => {
      const cell = text("span", label);
      cell.setAttribute("role", "columnheader");
      header.append(cell);
    });
    table.append(header);
    const seconds = number(detail.game_duration_seconds) || number(match.game_duration_seconds);
    participants.forEach((participant) => {
      const row = text("div", "", `match-player-row match-player-${String(participant.relation || "unknown").toLowerCase()}`);
      row.setAttribute("role", "row");
      const participantSide = participant.relation === "ALLY"
        ? playerSide
        : participant.relation === "ENEMY" && playerSide
          ? (playerSide === "BLUE" ? "RED" : "BLUE")
          : "";
      if (participantSide) row.classList.add(`match-player-side-${participantSide.toLowerCase()}`);
      if (participant.is_self) row.classList.add("match-player-self");
      const cs = number(participant.cs);
      const vision = number(participant.vision_score);
      const damage = number(participant.damage_to_champions);
      const perMinute = (value, digits) => seconds ? decimal(value / (seconds / 60), digits) : "-";
      const storedPercent = (value) => Number.isFinite(Number(value))
        ? `${decimal(value, 1)}%`
        : "-";
      row.append(
        playerCell("Role", ROLE_NAMES[participant.role] || participant.role || "-", "match-player-role"),
        playerCell("Champ", participant.champion_name || participant.champion || "-", "match-player-champion"),
        playerCell("Rank", participant.rank || "-", "match-player-rank"),
        playerCell("K/D/A", `${number(participant.kills)}/${number(participant.deaths)}/${number(participant.assists)}`),
        playerCell("KP%", storedPercent(participant.kp_pct)),
        playerCell("CS/m (CS)", `${perMinute(cs, 1)} (${Math.round(cs)})`),
        playerCell("VS/m (VS)", `${perMinute(vision, 2)} (${Math.round(vision)})`),
        playerCell("DMG%", storedPercent(participant.dmg_pct)),
        playerCell("DPM (DMG)", `${perMinute(damage, 0)} (${Math.round(damage).toLocaleString("ja-JP")})`)
      );
      table.append(row);
    });
    if (!participants.length) table.append(text("div", "10人比較データなし", "match-detail-empty"));
    return table;
  }

  function overviewContent(match) {
    const detail = match.detail || {};
    const participants = Array.isArray(detail.participants) ? detail.participants : [];
    const root = text("div", "", "match-detail-content");
    const overview = text("div", "", "match-detail-overview");
    overviewGroups(match).forEach(([title, entries, className]) => overview.append(metricGroup(title, entries, className)));
    root.append(overview);
    if (!selfParticipant(match) && participants.length) root.prepend(text("p", "自分の参加者データを確認できません", "match-detail-empty"));
    return root;
  }

  function detailedStatsContent(match) {
    const root = text("div", "", "match-detail-content match-detail-stats-content");
    const groups = text("div", "", "match-detail-overview match-detail-stats-grid");
    detailStatGroups(match).forEach(([title, entries, className]) => groups.append(metricGroup(title, entries, className)));
    const comparisonTitle = text("h4", "味方・敵10人比較", "match-player-title");
    const rankNote = text("p", "※ Rankはデータ取得時点のSolo/Duo Rank", "match-player-rank-note");
    root.append(groups, comparisonTitle, rankNote, playerComparison(match));
    return root;
  }

  function fightSummaryContent(match) {
    const root = text("section", "", "fight-summary");
    root.append(metricGroup("Fight Summary", fightSummaryEntries(match), "fight-summary-metrics"));
    return root;
  }

  function metricText(title, entries) {
    return [`【${title}】`, ...entries.map(([label, value]) => `${label}: ${value}`)].join("\n");
  }

  function fightText(fight) {
    const kda = fight.my_kda || {};
    const people = Array.isArray(fight.participants) ? fight.participants : [];
    const playerKda = fight.player_involved === false || fight.my_kda === null
      ? "非参加"
      : `${number(kda.kills)}/${number(kda.deaths)}/${number(kda.assists)}`;
    const lines = [
      `戦闘 #${fight.fight_id ?? "-"} (${clock(fight.start_timestamp)}–${clock(fight.end_timestamp)})`,
      `分類: ${localized(fight.phase, FIGHT_LABELS)} / ${localized(fight.scale, FIGHT_LABELS)} / ${localized(fight.result, FIGHT_LABELS)} / ${localized(fight.survival, FIGHT_LABELS)}`,
      `My K/D/A: ${playerKda}`,
      `キル交換: ${number(fight.friendly_kills)}-${number(fight.enemy_kills)}`,
      `参加者: ${people.map(fightPersonName).join(" / ") || "-"}`,
    ];
    const kills = (fight.events || []).filter((event) => event.type === "CHAMPION_KILL");
    if (kills.length) {
      lines.push("キル経過:");
      kills.forEach((event) => {
        const assists = (event.assists || []).map(personName);
        lines.push(`- ${clock(event.timestamp)} ${personName(event.killer)} → ${personName(event.victim)}${assists.length ? ` [Assist: ${assists.join(", ")}]` : ""}`);
      });
    }
    const context = fight.objective_context || {};
    lines.push(`オブジェクト状況: 戦闘前 ${localized(context.before || "NONE", FIGHT_LABELS)} / 戦闘中 ${localized(context.during || "NONE", FIGHT_LABELS)} / 戦闘後 ${localized(context.after || "NONE", FIGHT_LABELS)}`);
    [["戦闘前", fight.objectives_before], ["戦闘中", fight.objectives_during], ["戦闘後", fight.objectives_after]].forEach(([period, events]) => {
      (events || []).forEach((objective) => lines.push(`- ${period} ${clock(objective.timestamp)} ${localized(objective.relation || "UNKNOWN", RELATION_LABELS)} ${objectiveName(objective)}`));
    });
    return lines.join("\n");
  }

  function fightSectionText(title, fights) {
    return [`【${title}】`, ...(fights.length ? fights.map(fightText) : ["戦闘データなし"])].join("\n\n");
  }

  function playerComparisonText(match) {
    const participants = Array.isArray(match.detail?.participants) ? match.detail.participants : [];
    if (!participants.length) return "【味方・敵10人比較】\nデータなし";
    return ["【味方・敵10人比較】", ...participants.map((participant) => {
      const seconds = number(match.game_duration_seconds);
      const perMinute = (value, digits) => seconds ? decimal(number(value) / (seconds / 60), digits) : "-";
      return [
        participant.relation || "-",
        ROLE_NAMES[participant.role] || participant.role || "-",
        participant.champion_name || participant.champion || "-",
        `Rank ${participant.rank || "-"}`,
        `K/D/A ${number(participant.kills)}/${number(participant.deaths)}/${number(participant.assists)}`,
        `CS/m ${perMinute(participant.cs, 1)}`,
        `VS/m ${perMinute(participant.vision_score, 2)}`,
        `DPM ${perMinute(participant.damage_to_champions, 0)}`,
      ].join(" | ");
    })].join("\n");
  }

  function copyTextForSelection(match, selected) {
    const sections = [];
    if (selected.overview) sections.push([
      "【試合概要】",
      `Match ID: ${match.match_id || "-"}`,
      ...overviewGroups(match).map(([title, entries]) => metricText(title, entries)),
    ].join("\n\n"));
    if (selected.selfFights) sections.push(fightSectionText("戦闘詳細（自分）", Array.isArray(match.fights) ? match.fights : []));
    if (selected.allFights) sections.push(fightSectionText("戦闘詳細（全体）", Array.isArray(match.all_fights) ? match.all_fights : []));
    if (selected.details) sections.push(["【試合詳細】", ...detailStatGroups(match).map(([title, entries]) => metricText(title, entries)), playerComparisonText(match)].join("\n\n"));
    return sections.join("\n\n");
  }

  async function writeClipboard(value) {
    if (global.navigator?.clipboard?.writeText && global.isSecureContext) {
      await global.navigator.clipboard.writeText(value);
      return;
    }
    const area = global.document.createElement("textarea");
    area.value = value;
    area.setAttribute("aria-hidden", "true");
    area.style.cssText = "position:fixed;opacity:0;pointer-events:none;";
    global.document.body.append(area);
    area.select();
    const copied = global.document.execCommand?.("copy");
    area.remove();
    if (!copied) throw new Error("Clipboard API is unavailable");
  }

  function setDetailButtonLabel(button, label, shortLabel, opening) {
    button.replaceChildren(
      text("span", label, "m-action-label"),
      text("span", shortLabel, "m-action-label-short"),
      text("span", opening ? " ▲" : " ▼", "m-action-arrow")
    );
  }

  function createDetailController() {
    const entries = [];
    return (entry) => {
      entries.push(entry);
      entry.button.addEventListener("click", () => {
        const opening = entry.panel.hidden;
        entries.forEach((other) => {
          if (other === entry || other.panel.hidden) return;
          other.panel.hidden = true;
          other.button.setAttribute("aria-expanded", "false");
          other.button.setAttribute("aria-label", `${other.label}を開く`);
          setDetailButtonLabel(other.button, other.label, other.shortLabel, false);
        });
        if (opening && entry.panel.dataset.rendered !== "true") {
          entry.render();
          entry.panel.dataset.rendered = "true";
        }
        entry.panel.hidden = !opening;
        entry.button.setAttribute("aria-expanded", String(opening));
        entry.button.setAttribute("aria-label", `${entry.label}を${opening ? "閉じる" : "開く"}`);
        setDetailButtonLabel(entry.button, entry.label, entry.shortLabel, opening);
      });
    };
  }

  function addOverviewDetail(element, actions, match, registerDetail) {
    const detailId = `match-overview-${String(match.match_id || "match").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const button = text("button", "", "m-detail-toggle");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", detailId);
    button.setAttribute("aria-label", "試合概要を開く");
    const panel = text("div", "", "match-detail");
    panel.id = detailId;
    panel.hidden = true;
    setDetailButtonLabel(button, "試合概要", "概要", false);
    registerDetail({
      button,
      panel,
      label: "試合概要",
      shortLabel: "概要",
      render: () => panel.append(overviewContent(match)),
    });
    actions.append(button);
    element.append(panel);
  }

  function addDetailedStats(element, actions, match, registerDetail) {
    const detailId = `match-stats-${String(match.match_id || "match").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const button = text("button", "", "m-detail-toggle");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", detailId);
    button.setAttribute("aria-label", "試合詳細を開く");
    const panel = text("div", "", "match-detail");
    panel.id = detailId;
    panel.hidden = true;
    setDetailButtonLabel(button, "試合詳細", "詳細", false);
    registerDetail({
      button,
      panel,
      label: "試合詳細",
      shortLabel: "詳細",
      render: () => panel.append(detailedStatsContent(match)),
    });
    actions.append(button);
    element.append(panel);
  }

  function addFightDetail(element, actions, match, registerDetail, mode) {
    const isAll = mode === "all";
    const fights = Array.isArray(isAll ? match.all_fights : match.fights)
      ? (isAll ? match.all_fights : match.fights)
      : [];
    const suffix = isAll ? "all" : "self";
    const label = isAll ? "戦闘詳細（全体）" : "戦闘詳細（自分）";
    const shortLabel = isAll ? "戦闘（全体）" : "戦闘（自分）";
    const detailId = `fight-detail-${suffix}-${String(match.match_id || "match").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const button = text("button", "", "m-fight-toggle");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", detailId);
    button.setAttribute("aria-label", `${label}を開く（${fights.length}件）`);
    if (!fights.length) button.disabled = true;
    const detail = text("div", "", "fight-detail");
    detail.id = detailId;
    detail.hidden = true;
    setDetailButtonLabel(button, label, shortLabel, false);
    registerDetail({
      button,
      panel: detail,
      label,
      shortLabel,
      render: () => detail.replaceChildren(...(
        isAll ? fights.map(fightCard) : [fightSummaryContent(match), ...fights.map(fightCard)]
      )),
    });
    actions.append(button);
    element.append(detail);
  }

  function addCopyPanel(element, actions, match, registerDetail) {
    const copyId = `match-copy-${String(match.match_id || "match").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const button = text("button", "", "m-copy-toggle");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", copyId);
    button.setAttribute("aria-label", "コピー設定を開く");
    const panel = text("div", "", "match-copy");
    panel.id = copyId;
    panel.hidden = true;
    setDetailButtonLabel(button, "コピー", "コピー", false);
    registerDetail({
      button,
      panel,
      label: "コピー",
      shortLabel: "コピー",
      render: () => {
        const root = text("div", "", "match-copy-content");
        root.append(text("h4", "コピーする内容"));
        const options = [
          ["overview", "試合概要", true],
          ["selfFights", "戦闘詳細（自分）", false],
          ["allFights", "戦闘詳細（全体）", true],
          ["details", "試合詳細", true],
        ];
        const controls = text("div", "", "match-copy-options");
        const inputs = {};
        options.forEach(([key, label, checked]) => {
          const optionId = `${copyId}-${key}`;
          const labelElement = text("label", "", "match-copy-option");
          const input = global.document.createElement("input");
          input.type = "checkbox";
          input.id = optionId;
          input.checked = checked;
          inputs[key] = input;
          labelElement.htmlFor = optionId;
          labelElement.append(input, text("span", label));
          controls.append(labelElement);
        });
        const copyButton = text("button", "選択内容をコピー", "match-copy-submit");
        copyButton.type = "button";
        const feedback = text("p", "", "match-copy-feedback");
        feedback.setAttribute("role", "status");
        feedback.hidden = true;
        let feedbackTimer = null;
        const showFeedback = (message, failed = false) => {
          if (feedbackTimer) global.clearTimeout(feedbackTimer);
          feedback.textContent = message;
          feedback.hidden = false;
          feedback.classList.toggle("is-error", failed);
          feedbackTimer = global.setTimeout(() => { feedback.hidden = true; }, 1600);
        };
        copyButton.addEventListener("click", async () => {
          const selected = Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.checked]));
          const value = copyTextForSelection(match, selected);
          if (!value) {
            showFeedback("コピーする項目を選択してください", true);
            return;
          }
          try {
            await writeClipboard(value);
            showFeedback("コピーしました");
          } catch (_error) {
            showFeedback("コピーに失敗しました", true);
          }
        });
        root.append(controls, copyButton, feedback);
        panel.append(root);
      },
    });
    actions.append(button);
    element.append(panel);
  }

  function card(match, version) {
    const metrics = global.MatchHistoryMetrics;
    const element = text("article", "", `match ${match.win ? "win" : "loss"}`);
    element.id = matchAnchorId(match.match_id);
    element.tabIndex = -1;
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
    const summary = text("div", "", "m-summary");
    const stats = text("div", "", "m-stats");
    const summarySeparator = () => text("span", "｜", "m-summary-separator");
    const statRow = (label, value, total = "") => {
      const row = text("div", "", "m-stat-row");
      row.append(
        text("span", `${label}：`, "m-stat-label"),
        text("span", String(value), "m-stat-value"),
        text("span", total === "" ? "" : `(${total})`, "m-stat-total")
      );
      return row;
    };
    stats.append(
      statRow("CS/m", decimal(metrics.rate(match.cs, match), 2), Math.round(match.cs)),
      summarySeparator(),
      statRow("VS/m", decimal(metrics.rate(match.vision_score, match), 2), Math.round(match.vision_score)),
      summarySeparator(),
      statRow("DPM", decimal(metrics.rate(match.damage_to_champions, match), 0))
    );
    const when = text("div", "", "m-date");
    when.append(
      text("div", `Time ${duration(match.game_duration_seconds)}`),
      summarySeparator(),
      text("div", String(match.date || "").slice(0, 16)),
      summarySeparator(),
      text("div", `Patch ${match.patch || "-"}`)
    );
    summary.append(stats, when);
    const actions = text("div", "", "m-actions");
    const registerDetail = createDetailController();
    element.append(result, primary, summary, actions);
    addOverviewDetail(element, actions, match, registerDetail);
    addFightDetail(element, actions, match, registerDetail, "self");
    addFightDetail(element, actions, match, registerDetail, "all");
    addDetailedStats(element, actions, match, registerDetail);
    addCopyPanel(element, actions, match, registerDetail);
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

    function hashMatchId() {
      const hash = global.location?.hash || "";
      if (!hash.startsWith("#match-")) return "";
      try { return decodeURIComponent(hash.slice("#match-".length)); } catch (_error) { return ""; }
    }

    function applyHashTargetFilters() {
      const matchId = hashMatchId();
      const target = source.find((match) => match.match_id === matchId);
      if (!target || !topControls) return target;
      topControls.period.value = "custom";
      topControls.champion.value = "ALL";
      topControls.queue.value = "all";
      topControls.role.value = "ALL";
      resultControl.value = "ALL";
      sortControl.value = "date";
      directionControl.value = "desc";
      const date = String(target.date || "").slice(0, 10);
      topControls.start.value = date;
      topControls.end.value = date;
      return target;
    }

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

    function showHashTarget() {
      const target = applyHashTargetFilters();
      if (!target) return false;
      const targetIndex = selectedMatches().findIndex((match) => match.match_id === target.match_id);
      visible = Math.max(PAGE_SIZE, targetIndex + 1);
      render(false);
      const cardElement = global.document.getElementById(matchAnchorId(target.match_id));
      if (!cardElement) return false;
      const detailButton = cardElement.querySelector(".m-detail-toggle:not(:disabled)");
      if (detailButton?.getAttribute("aria-expanded") !== "true") detailButton.click();
      cardElement.scrollIntoView({ block: "start" });
      cardElement.focus({ preventScroll: true });
      return true;
    }

    [resultControl, sortControl, directionControl].forEach((control) => control.addEventListener("change", () => render(true)));
    if (topControls) {
      [topControls.period, topControls.champion, topControls.queue, topControls.role, topControls.start, topControls.end]
        .forEach((control) => control.addEventListener("change", () => render(true)));
    }
    section.querySelector("[data-match-history-more]").addEventListener("click", () => { visible += PAGE_SIZE; render(false); });
    return {
      render,
      showHashTarget,
      setMatches(matches) { source = matches.slice(); return render(true); },
      getMatches: selectedMatches,
    };
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
      if (!component.showHashTarget()) component.render(true);
      global.addEventListener("hashchange", () => component.showHashTarget());
    }
  }

  if (global.document) init();
  const api = {
    PAGE_SIZE, card, create, matchAnchorId, roleSummaryDefinition,
    fightSummaryEntries, overviewGroups, detailStatGroups, copyTextForSelection,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

(function (global) {
  "use strict";

  const CARD_DEFINITIONS = [
    ["current", "現在の連勝 / 連敗"],
    ["condition", "現在の調子"],
    ["max-win", "最大連勝"],
    ["max-loss", "最大連敗"],
    ["avg-win", "平均連勝長"],
    ["avg-loss", "平均連敗長"],
    ["after-win", "2連勝後勝率"],
    ["after-loss", "2連敗後勝率"],
  ];

  function streakText(streak) {
    if (!streak) return "-";
    return `${streak.length}連${streak.win ? "勝" : "敗"}`;
  }

  function lengthText(length, result) {
    return length === null ? "-" : `${length}連${result}`;
  }

  function averageText(value) {
    return value === null
      ? "-"
      : `${global.RoleMetrics.formatDecimal(value, 1)}戦`;
  }

  function afterTwoText(result) {
    if (!result.games) return { value: "-", sub: "" };
    return {
      value: `${global.RoleMetrics.formatDecimal(result.winrate, 1)}%`,
      sub: `${result.wins}勝 ${result.losses}敗`,
    };
  }

  function conditionText(form) {
    const classification = form.classification;
    const label = classification.reference
      ? `${classification.label}（参考）`
      : classification.label;
    if (!form.games) return { value: label, sub: "-", tone: classification.tone };
    return {
      value: label,
      sub: `${global.RoleMetrics.formatDecimal(form.winrate, 1)}%（${form.wins}勝${form.losses}敗 / ${form.games}戦）`,
      tone: classification.tone,
    };
  }

  function cardValues(analysis) {
    const condition = conditionText(analysis.form);
    const afterWins = afterTwoText(analysis.afterTwoWins);
    const afterLosses = afterTwoText(analysis.afterTwoLosses);
    return {
      current: { value: streakText(analysis.currentStreak) },
      condition,
      "max-win": { value: lengthText(analysis.maxWinStreak, "勝") },
      "max-loss": { value: lengthText(analysis.maxLossStreak, "敗") },
      "avg-win": { value: averageText(analysis.avgWinStreak) },
      "avg-loss": { value: averageText(analysis.avgLossStreak) },
      "after-win": afterWins,
      "after-loss": afterLosses,
    };
  }

  function renderCards(analysis) {
    const values = cardValues(analysis);
    const container = global.document.getElementById("form-streak-cards");
    container.replaceChildren(
      ...CARD_DEFINITIONS.map(([key, labelText]) => {
        const card = global.document.createElement("div");
        card.className = "card";
        const label = global.document.createElement("div");
        label.className = "stat-label";
        label.textContent = labelText;
        const value = global.document.createElement("div");
        value.className = "stat-value";
        if (values[key].tone === "good" || values[key].tone === "bad") {
          value.classList.add(values[key].tone);
        }
        value.dataset.formMetric = key;
        value.textContent = values[key].value;
        card.append(label, value);
        if (values[key].sub) {
          const sub = global.document.createElement("div");
          sub.className = "stat-sub";
          sub.dataset.formMetricSub = key;
          sub.textContent = values[key].sub;
          card.append(sub);
        }
        return card;
      })
    );
  }

  function renderRecentForm(form) {
    const container = global.document.getElementById("recent-form");
    container.replaceChildren(
      ...form.matches.map((match, index) => {
        const dot = global.document.createElement("span");
        dot.className = `dot ${match.win ? "win" : "loss"}`;
        const result = match.win ? "WIN" : "LOSS";
        const date = String(match.date || "").slice(0, 10).replace(/-/g, "/");
        const champion = match.champion_name || match.champion || "Champion不明";
        const label = `${index + 1}戦目、${result}、${date || "日付不明"}、${champion}`;
        dot.title = label;
        dot.setAttribute("role", "img");
        dot.setAttribute("aria-label", label);
        return dot;
      })
    );
    const summary = global.document.getElementById("recent-form-summary");
    summary.textContent = form.games
      ? `${form.wins}勝 ${form.losses}敗 / ${form.games}戦`
      : "-";
  }

  function renderFormStreak(matches) {
    const analysis = global.RoleStreaks.analyzeForm(matches);
    renderCards(analysis);
    renderRecentForm(analysis.form);
    return analysis;
  }

  if (global.document) {
    global.document.addEventListener("role-filter:change", (event) => {
      renderFormStreak(event.detail.matches);
    });
  }

  const api = { render: renderFormStreak };
  global.RoleFormStreak = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);

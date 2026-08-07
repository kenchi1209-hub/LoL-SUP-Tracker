(function (global) {
  "use strict";

  const VALID_PERIODS = new Set([
    "season",
    "two_months",
    "current_month",
    "previous_month",
    "recent20",
    "custom",
  ]);
  const VALID_QUEUES = new Set(["all", "ranked", "draft"]);

  function localDate(year, month, day) {
    return [
      String(year).padStart(4, "0"),
      String(month + 1).padStart(2, "0"),
      String(day).padStart(2, "0"),
    ].join("-");
  }

  function monthBounds(now) {
    const year = now.getFullYear();
    const month = now.getMonth();
    const currentStart = localDate(year, month, 1);
    const nextStartDate = new Date(year, month + 1, 1);
    const previousStartDate = new Date(year, month - 1, 1);
    return {
      currentStart,
      nextStart: localDate(
        nextStartDate.getFullYear(),
        nextStartDate.getMonth(),
        1
      ),
      previousStart: localDate(
        previousStartDate.getFullYear(),
        previousStartDate.getMonth(),
        1
      ),
    };
  }

  function filterByPeriod(matches, filters, now) {
    if (filters.period === "season" || filters.period === "recent20") {
      return matches;
    }
    const bounds = monthBounds(now);
    return matches.filter((match) => {
      const date = String(match.date || "").slice(0, 10);
      if (filters.period === "two_months") {
        return date >= bounds.previousStart && date < bounds.nextStart;
      }
      if (filters.period === "current_month") {
        return date >= bounds.currentStart && date < bounds.nextStart;
      }
      if (filters.period === "previous_month") {
        return date >= bounds.previousStart && date < bounds.currentStart;
      }
      if (filters.period === "custom") {
        const afterStart = !filters.start || date >= filters.start;
        const beforeEnd = !filters.end || date <= filters.end;
        return afterStart && beforeEnd;
      }
      return true;
    });
  }

  function filterMatches(matches, filters, now) {
    const referenceDate = now || new Date();
    let filtered = matches.filter((match) => match.role === filters.role);
    if (filters.champ !== "ALL") {
      filtered = filtered.filter((match) => match.champion === filters.champ);
    }
    if (filters.queue === "ranked") {
      filtered = filtered.filter((match) => String(match.queue_id) === "420");
    } else if (filters.queue === "draft") {
      filtered = filtered.filter((match) => String(match.queue_id) === "400");
    } else {
      filtered = filtered.filter((match) =>
        ["400", "420"].includes(String(match.queue_id))
      );
    }
    filtered = filterByPeriod(filtered, filters, referenceDate);
    filtered.sort((left, right) =>
      String(right.date).localeCompare(String(left.date))
    );
    return filters.period === "recent20" ? filtered.slice(0, 20) : filtered;
  }

  function readFilters(params, controls, role) {
    const periodParam = params.get("period") || "season";
    const queueParam = params.get("queue") || "all";
    const champParam = params.get("champ") || "ALL";
    const championValues = new Set(
      Array.from(controls.champ.options, (option) => option.value)
    );
    return {
      role,
      period: VALID_PERIODS.has(periodParam) ? periodParam : "season",
      champ: championValues.has(champParam) ? champParam : "ALL",
      queue: VALID_QUEUES.has(queueParam) ? queueParam : "all",
      start: params.get("start") || "",
      end: params.get("end") || "",
    };
  }

  function writeFilters(filters) {
    const params = new URLSearchParams();
    params.set("period", filters.period);
    params.set("champ", filters.champ);
    params.set("queue", filters.queue);
    if (filters.period === "custom") {
      if (filters.start) params.set("start", filters.start);
      if (filters.end) params.set("end", filters.end);
    }
    global.history.replaceState(
      null,
      "",
      `${global.location.pathname}?${params.toString()}`
    );
  }

  function initRoleFilters() {
    const dataElement = global.document.getElementById("role-match-data");
    if (!dataElement) return;

    const matches = JSON.parse(dataElement.textContent);
    const role = dataElement.dataset.role;
    const controls = {
      period: global.document.getElementById("period-filter"),
      champ: global.document.getElementById("champ-filter"),
      queue: global.document.getElementById("queue-filter"),
      start: global.document.getElementById("custom-start"),
      end: global.document.getElementById("custom-end"),
      custom: global.document.getElementById("custom-period"),
      count: global.document.getElementById("filtered-match-count"),
    };
    const restored = readFilters(
      new URLSearchParams(global.location.search),
      controls,
      role
    );
    controls.period.value = restored.period;
    controls.champ.value = restored.champ;
    controls.queue.value = restored.queue;
    controls.start.value = restored.start;
    controls.end.value = restored.end;

    let currentMatches = [];

    function currentFilters() {
      return {
        role,
        period: controls.period.value,
        champ: controls.champ.value,
        queue: controls.queue.value,
        start: controls.start.value,
        end: controls.end.value,
      };
    }

    function applyFilters() {
      const filters = currentFilters();
      controls.custom.hidden = filters.period !== "custom";
      currentMatches = filterMatches(matches, filters);
      controls.count.textContent = String(currentMatches.length);
      writeFilters(filters);
      global.document.dispatchEvent(
        new CustomEvent("role-filter:change", {
          detail: { filters, matches: currentMatches.slice() },
        })
      );
      return currentMatches.slice();
    }

    [controls.period, controls.champ, controls.queue, controls.start, controls.end]
      .forEach((control) => control.addEventListener("change", applyFilters));

    global.rolePageFilters = {
      apply: applyFilters,
      getMatches: () => currentMatches.slice(),
    };
    applyFilters();
  }

  const api = { filterMatches, monthBounds };
  global.RoleFilters = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (global.document) {
    global.document.addEventListener("DOMContentLoaded", initRoleFilters);
  }
})(typeof window !== "undefined" ? window : globalThis);

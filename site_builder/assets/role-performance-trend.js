(function (global) {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  function svgElement(name, attributes, text) {
    const element = global.document.createElementNS(SVG_NS, name);
    Object.entries(attributes || {}).forEach(([key, value]) =>
      element.setAttribute(key, value)
    );
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function formatMetric(metric, value) {
    if (value === null || value === undefined) return "-";
    const definition = global.RoleTrendMetrics.METRICS[metric];
    return `${global.RoleMetrics.formatDecimal(value, definition.digits)}${definition.suffix}`;
  }

  function formatDifference(metric, value) {
    if (value === null || value === undefined) return "-";
    const formatted = formatMetric(metric, Math.abs(value));
    return `${value >= 0 ? "+" : "-"}${formatted}`;
  }

  function renderEmpty(container, message) {
    const empty = global.document.createElement("div");
    empty.className = "trend-empty";
    empty.textContent = message;
    container.replaceChildren(empty);
  }

  function renderChart(container, trend) {
    if (!trend.points.length) {
      renderEmpty(container, "選択した集計に必要な試合数がありません");
      return;
    }

    const width = 760;
    const height = 300;
    const margin = { top: 24, right: 24, bottom: 46, left: 58 };
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;
    const values = trend.points.map((point) => point.value).concat(trend.overall);
    let minimum = Math.min(...values);
    let maximum = Math.max(...values);
    if (minimum === maximum) {
      const padding = minimum === 0 ? 1 : Math.abs(minimum) * 0.1;
      minimum -= padding;
      maximum += padding;
    } else {
      const padding = (maximum - minimum) * 0.12;
      minimum = Math.max(0, minimum - padding);
      maximum += padding;
    }
    const x = (index) =>
      margin.left +
      (trend.points.length === 1 ? chartWidth / 2 : (index / (trend.points.length - 1)) * chartWidth);
    const y = (value) =>
      margin.top + ((maximum - value) / (maximum - minimum)) * chartHeight;
    const svg = svgElement("svg", {
      viewBox: `0 0 ${width} ${height}`,
      "aria-hidden": "true",
    });

    for (let tick = 0; tick <= 4; tick += 1) {
      const value = minimum + ((maximum - minimum) * tick) / 4;
      const tickY = y(value);
      svg.append(
        svgElement("line", {
          x1: margin.left,
          y1: tickY,
          x2: width - margin.right,
          y2: tickY,
          stroke: "#2a3346",
        }),
        svgElement(
          "text",
          { x: margin.left - 8, y: tickY + 4, fill: "#8a94a7", "font-size": 11, "text-anchor": "end" },
          formatMetric(trend.metric, value)
        )
      );
    }

    const averageY = y(trend.overall);
    svg.append(
      svgElement("line", {
        x1: margin.left,
        y1: averageY,
        x2: width - margin.right,
        y2: averageY,
        stroke: "#f6c85f",
        "stroke-width": 2,
        "stroke-dasharray": "7 6",
      })
    );

    const linePoints = trend.points
      .map((point, index) => `${x(index)},${y(point.value)}`)
      .join(" ");
    svg.append(
      svgElement("polyline", {
        points: linePoints,
        fill: "none",
        stroke: "#5b8cff",
        "stroke-width": 3,
        "stroke-linejoin": "round",
        "stroke-linecap": "round",
      })
    );

    const labelStep = Math.max(1, Math.ceil(trend.points.length / 6));
    trend.points.forEach((point, index) => {
      const circle = svgElement("circle", {
        cx: x(index),
        cy: y(point.value),
        r: 4,
        fill: "#e7ecf4",
        stroke: "#5b8cff",
        "stroke-width": 2,
      });
      circle.append(
        svgElement(
          "title",
          {},
          `${point.label}\n${point.games}戦 (${point.wins}勝 ${point.losses}敗)\n${formatMetric(trend.metric, point.value)}`
        )
      );
      svg.append(circle);
      if (index % labelStep === 0 || index === trend.points.length - 1) {
        svg.append(
          svgElement(
            "text",
            { x: x(index), y: height - 18, fill: "#8a94a7", "font-size": 11, "text-anchor": "middle" },
            point.label
          )
        );
      }
    });
    container.replaceChildren(svg);
  }

  function renderAccessibleSeries(container, trend) {
    const definition = global.RoleTrendMetrics.METRICS[trend.metric];
    const heading = global.document.createElement("h3");
    heading.textContent = `${definition.label}系列データ`;
    const summary = global.document.createElement("p");
    summary.textContent = `現在値 ${formatMetric(trend.metric, trend.current)}、期間平均との差 ${formatDifference(trend.metric, trend.difference)}`;
    const list = global.document.createElement("ol");
    trend.points.forEach((point) => {
      const item = global.document.createElement("li");
      item.textContent = `${point.label}: ${formatMetric(trend.metric, point.value)}、${point.games}戦、${point.wins}勝${point.losses}敗`;
      list.append(item);
    });
    container.replaceChildren(heading, summary, list);
  }

  function updateGroupingAvailability(groupingControl, games) {
    const moving5 = groupingControl.querySelector('option[value="moving5"]');
    const moving10 = groupingControl.querySelector('option[value="moving10"]');
    moving5.disabled = games < 5;
    moving10.disabled = games < 10;
    if (groupingControl.selectedOptions[0].disabled) {
      groupingControl.value = games >= 5 ? "moving5" : "monthly";
    }
  }

  function initPerformanceTrend() {
    const dataElement = global.document.getElementById("role-match-data");
    const metricControl = global.document.getElementById("trend-metric");
    const groupingControl = global.document.getElementById("trend-grouping");
    const chart = global.document.getElementById("trend-chart");
    const accessibleSeries = global.document.getElementById("trend-accessible-series");
    if (!dataElement || !metricControl || !groupingControl || !chart || !accessibleSeries) return;

    metricControl.value =
      global.RoleTrendMetrics.DEFAULT_METRICS[dataElement.dataset.role] || "winrate";
    let currentMatches = [];

    function render(matches) {
      if (matches) currentMatches = matches.slice();
      updateGroupingAvailability(groupingControl, currentMatches.length);
      const trend = global.RoleTrendMetrics.buildTrend(
        currentMatches,
        metricControl.value,
        groupingControl.value
      );
      const definition = global.RoleTrendMetrics.METRICS[metricControl.value];
      global.document.getElementById("trend-current-label").textContent =
        `${definition.label} 現在`;
      global.document.getElementById("trend-current").textContent =
        formatMetric(trend.metric, trend.current);
      const difference = global.document.getElementById("trend-difference");
      difference.textContent = formatDifference(trend.metric, trend.difference);
      difference.className = trend.difference === null
        ? ""
        : trend.difference >= 0 ? "good" : "bad";
      chart.setAttribute(
        "aria-label",
        `${definition.label}の成績推移。期間平均 ${formatMetric(trend.metric, trend.overall)}`
      );
      renderChart(chart, trend);
      renderAccessibleSeries(accessibleSeries, trend);
      return trend;
    }

    metricControl.addEventListener("change", () => render());
    groupingControl.addEventListener("change", () => render());
    global.document.addEventListener("role-filter:change", (event) =>
      render(event.detail.matches)
    );
    global.RolePerformanceTrend = { render };
  }

  if (global.document) initPerformanceTrend();
})(typeof window !== "undefined" ? window : globalThis);

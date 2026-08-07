(function (global) {
  "use strict";

  function numberValue(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function formatDecimal(value, digits) {
    const factor = 10 ** digits;
    const scaled = numberValue(value) * factor;
    const lower = Math.floor(scaled);
    const fraction = scaled - lower;
    const rounded = Math.abs(fraction - 0.5) < 1e-9
      ? (lower % 2 === 0 ? lower : lower + 1)
      : Math.round(scaled);
    return (rounded / factor).toFixed(digits);
  }

  function championImageUrl(version, iconId) {
    return `https://ddragon.leagueoflegends.com/cdn/${encodeURIComponent(version)}/img/champion/${encodeURIComponent(iconId)}.png`;
  }

  const api = { championImageUrl, formatDecimal, numberValue };
  global.SiteUtils = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

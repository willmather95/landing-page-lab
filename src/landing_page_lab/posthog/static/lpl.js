/* landing-page-lab runtime: flag-driven variant routing + event capture.
 * Reads window.LPL_CONFIG (written at build time). With a PostHog project key it loads
 * posthog-js, asks the experiment's feature flag for this visitor's variant, and captures
 * events with the $feature/<flag> property PostHog experiments read. Without a key it runs
 * in local mode: sticky hash bucketing and events logged to localStorage, so previews work
 * offline and nothing leaves the browser. ?lpl_variant=<key> forces a variant for QA.
 */
(function () {
  "use strict";
  var C = window.LPL_CONFIG;
  if (!C) return;
  var store = (function () { try { localStorage.setItem("lpl_t", "1"); return localStorage; } catch (e) { return null; } })();
  var current = null;
  var ph = null;

  function fnv1a(str) {
    var h = 0x811c9dc5;
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return h >>> 0;
  }
  function visitorId() {
    var id = store && store.getItem("lpl_id");
    if (!id) {
      id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now();
      if (store) store.setItem("lpl_id", id);
    }
    return id;
  }
  function isVariant(key) { return C.variants.some(function (v) { return v.key === key; }); }
  /* Flag value ("control", "b", ...) -> page key ("a", "b", ...). Unknown values -> null. */
  function fromFlag(value) {
    for (var i = 0; i < C.variants.length; i++) { if (C.variants[i].flag === String(value)) return C.variants[i].key; }
    return null;
  }
  function flagOf(key) {
    for (var i = 0; i < C.variants.length; i++) { if (C.variants[i].key === key) return C.variants[i].flag; }
    return null;
  }
  function localVariant() {
    var total = C.variants.reduce(function (s, v) { return s + v.weight; }, 0);
    var x = (fnv1a(visitorId() + ":" + C.flagKey) / 4294967296) * total;
    for (var i = 0; i < C.variants.length; i++) { x -= C.variants[i].weight; if (x < 0) return C.variants[i].key; }
    return C.control;
  }
  function forced() {
    var f = new URLSearchParams(location.search).get("lpl_variant");
    return f && isVariant(f) ? f : null;
  }
  function loadPosthog(cb) {
    if (!C.apiKey) { cb(null); return; }
    var done = false;
    var finish = function (v) { if (!done) { done = true; cb(v); } };
    setTimeout(function () { finish(null); }, C.flagTimeoutMs);
    var s = document.createElement("script");
    s.async = true;
    s.src = C.assetHost + "/static/array.js";
    s.onerror = function () { finish(null); };
    s.onload = function () {
      window.posthog.init(C.apiKey, {
        api_host: C.apiHost,
        person_profiles: "identified_only",
        capture_pageview: true,
        loaded: function (p) {
          ph = p;
          p.onFeatureFlags(function () { finish(p.getFeatureFlag(C.flagKey)); });
        }
      });
    };
    document.head.appendChild(s);
  }
  function capture(event, props) {
    var p = Object.assign({ lpl_experiment: C.flagKey, lpl_variant: current }, props || {});
    p["$feature/" + C.flagKey] = flagOf(current);
    if (ph) { ph.capture(event, p); return; }
    var log = [];
    try { log = JSON.parse((store && store.getItem("lpl_events")) || "[]"); } catch (e) { log = []; }
    log.push({ event: event, props: p, ts: new Date().toISOString() });
    if (store) store.setItem("lpl_events", JSON.stringify(log.slice(-200)));
    if (window.console) console.info("[lpl local]", event, p);
  }
  function go(key) {
    var params = new URLSearchParams(location.search);
    params.delete("lpl_variant");
    var qs = params.toString();
    location.replace(C.basePath + key + "/" + (qs ? "?" + qs : "") + location.hash);
  }

  window.lpl = {
    /* Router page: resolve the variant, then send the visitor there. */
    route: function () {
      var f = forced();
      if (f) { go(f); return; }
      loadPosthog(function (flag) {
        var key = fromFlag(flag) || (C.apiKey ? C.control : localVariant());
        go(key);
      });
    },
    /* Variant page: keep assignment sticky, then wire events. */
    page: function (key) {
      current = key;
      var f = forced();
      loadPosthog(function (flag) {
        // Only a real flag answer can move a visitor. Local previews of /b/ always show b.
        var assigned = fromFlag(flag);
        if (!f && C.enforceAssignment && assigned && assigned !== key) { go(assigned); return; }
        capture("lpl_view", { forced: !!f });
      });
      document.addEventListener("click", function (e) {
        var el = e.target.closest && e.target.closest("[data-lpl-cta]");
        if (el) capture("lpl_cta_click", { cta: el.getAttribute("data-lpl-cta") });
      });
      document.addEventListener("submit", function (e) {
        var form = e.target.closest && e.target.closest("form[data-lpl-form]");
        if (!form) return;
        e.preventDefault();
        capture(C.primaryEvent, { form: form.getAttribute("data-lpl-form") });
        var box = form.closest(".cta");
        if (box) box.classList.add("done");
      });
    },
    capture: capture,
    _bucket: localVariant,
    _fromFlag: fromFlag
  };
})();

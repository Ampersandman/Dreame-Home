/*
 * Local icons for the Dreame Home Laundry row in HACS 2.0.5.
 *
 * That HACS release reads icons from the public brands CDN rather than the
 * integration's local brand files. This adapter only changes our own image URL
 * in its existing Lit template. No Home Assistant or HACS files are modified.
 */
const HACS_VERSION = "2.0.5";
const HACS_SCRIPT = "/hacsfiles/frontend/entrypoint.js?hacstag=20250128065759";
const OWN_REPOSITORIES = new Set([
  "Ampersandman/Dreame-Home-Laundry",
  "Ampersandman/Dreame-Home",
]);
const ADAPTER_MARKER = Symbol.for("dreame_home.branding.hacs_2_0_5");
const ICON_TEMPLATES = [
  [
    '<img style="height:32px;width:32px" slot="item-icon" src="',
    '" referrerpolicy="no-referrer">',
  ],
  [
    '<img style="height: 32px; width: 32px" slot="item-icon" src=',
    'referrerpolicy="no-referrer" />',
  ],
];
const observedParentRegistries = new WeakMap();
const observedIframeRegistries = new WeakMap();

export function assetVersion(moduleUrl) {
  try {
    const version = new URL(moduleUrl).searchParams.get("v");
    return typeof version === "string" && /^[A-Za-z0-9._-]{1,64}$/.test(version)
      ? version : null;
  } catch {
    return null;
  }
}

export function localIconUrl(dark, version = null) {
  const filename = dark === true ? "dark_icon.png" : "icon.png";
  const suffix = typeof version === "string" && /^[A-Za-z0-9._-]{1,64}$/.test(version)
    ? `?v=${encodeURIComponent(version)}` : "";
  return `/dreame_home/brand/${filename}${suffix}`;
}

export function isOwnRepository(repository) {
  return repository?.category === "integration"
    && repository.domain === "dreame_home"
    && OWN_REPOSITORIES.has(repository.full_name);
}

export function isSupportedPanel(panel, origin) {
  const custom = panel?.config?._panel_custom;
  if (panel?.url_path !== "hacs" || panel.component_name !== "custom"
      || custom?.name !== "hacs-frontend" || custom.embed_iframe !== true
      || typeof custom.js_url !== "string") return false;
  try {
    const script = new URL(custom.js_url, origin);
    return script.origin === new URL(origin).origin
      && `${script.pathname}${script.search}` === HACS_SCRIPT
      && script.hash === "" && script.username === "" && script.password === "";
  } catch {
    return false;
  }
}

export function replaceOwnIcon(result, repository, dark, version = null) {
  if (!isOwnRepository(repository) || result?._$litType$ !== 1
      || !Array.isArray(result.strings) || result.strings.length !== 2
      || !ICON_TEMPLATES.some(template => result.strings.every((part, index) => typeof part === "string"
        && part.replace(/\s+/g, " ").trim() === template[index]))
      || !Array.isArray(result.values) || result.values.length !== 1
      || typeof result.values[0] !== "string"
      || !/^https:\/\/brands\.home-assistant\.io\/_\/dreame_home\/(?:dark_)?icon(?:@2x)?\.png$/.test(result.values[0])) {
    return result;
  }
  // Keep the original template strings and all other Lit metadata intact.
  return {...result, values: [localIconUrl(dark, version)]};
}

function wrapColumns(dashboard, context) {
  if (dashboard.hacs?.info?.version !== HACS_VERSION
      || typeof dashboard._columns !== "function"
      || dashboard._columns[ADAPTER_MARKER]) return;
  const original = dashboard._columns;
  const wrapped = function (...args) {
    const columns = Reflect.apply(original, this, args);
    if (dashboard.hacs?.info?.version !== HACS_VERSION
        || !columns || typeof columns !== "object" || Array.isArray(columns)
        || typeof columns.icon?.template !== "function") return columns;
    const icon = columns.icon;
    return {...columns, icon: {...icon, template: function (...templateArgs) {
      const result = Reflect.apply(icon.template, this, templateArgs);
      if (dashboard.hacs?.info?.version !== HACS_VERSION) return result;
      return replaceOwnIcon(result, templateArgs[0], dashboard.hass?.themes?.darkMode, context.version);
    }}};
  };
  Object.defineProperty(wrapped, ADAPTER_MARKER, {value: true});
  dashboard._columns = wrapped;
}

export function installDashboardAdapter(Dashboard, version = null) {
  const prototype = Dashboard?.prototype;
  const original = prototype?.willUpdate;
  if (typeof original !== "function") return false;
  const previous = original[ADAPTER_MARKER];
  if (previous) {
    if (previous.kind === "dashboard") previous.version = version;
    return false;
  }
  const context = {kind: "dashboard", version};
  const wrapped = function (...args) {
    // A changed HACS API fails closed, while its normal lifecycle still runs.
    try { wrapColumns(this, context); } catch { /* Optional branding only. */ }
    return Reflect.apply(original, this, args);
  };
  Object.defineProperty(wrapped, ADAPTER_MARKER, {value: context});
  try {
    prototype.willUpdate = wrapped;
    return prototype.willUpdate === wrapped;
  } catch {
    return false;
  }
}

export function attachHacsIframe(panelHost, origin, version = null) {
  try {
    if (!isSupportedPanel(panelHost?.panel, origin)) return false;
    // This is the one iframe owned by the verified HACS custom panel. Accessing
    // another origin's registry throws; inherited-origin blank frames work.
    const registry = panelHost.querySelector("iframe")?.contentWindow?.customElements;
    if (!registry || typeof registry.whenDefined !== "function"
        || typeof registry.get !== "function") return false;
    const previous = observedIframeRegistries.get(registry);
    if (previous) {
      previous.version = version;
      installDashboardAdapter(registry.get("hacs-dashboard"), version);
      return false;
    }
    const context = {version};
    observedIframeRegistries.set(registry, context);
    const Dashboard = registry.get("hacs-dashboard");
    if (Dashboard) {
      installDashboardAdapter(Dashboard, version);
    } else {
      Promise.resolve(registry.whenDefined("hacs-dashboard")).then(() => {
        installDashboardAdapter(registry.get("hacs-dashboard"), context.version);
      }, () => {}).catch(() => {});
    }
    return true;
  } catch {
    return false;
  }
}

export function installPanelAdapter(Panel, origin, version = null) {
  const prototype = Panel?.prototype;
  const original = prototype?.registerIframe;
  if (typeof original !== "function") return false;
  const previous = original[ADAPTER_MARKER];
  if (previous) {
    if (previous.kind === "panel") { previous.origin = origin; previous.version = version; }
    return false;
  }
  const context = {kind: "panel", origin, version};
  const wrapped = function (...args) {
    // registerIframe's initialize callback starts the iframe application. Patch
    // its already defined dashboard before that callback queues its first paint.
    attachHacsIframe(this, context.origin, context.version);
    const result = Reflect.apply(original, this, args);
    // Preserve the original return value, including promise identity. The
    // second attachment handles a frame created after an asynchronous load.
    try {
      if (result && typeof result.then === "function") {
        result.then(() => { attachHacsIframe(this, context.origin, context.version); }, () => {});
      }
    } catch { /* Optional branding cannot interrupt panel initialization. */ }
    return result;
  };
  Object.defineProperty(wrapped, ADAPTER_MARKER, {value: context});
  try {
    prototype.registerIframe = wrapped;
    return prototype.registerIframe === wrapped;
  } catch {
    return false;
  }
}

export function installBranding(windowRef, moduleUrl = import.meta.url) {
  try {
    const registry = windowRef?.customElements;
    const origin = windowRef?.location?.origin;
    if (!registry || typeof registry.whenDefined !== "function"
        || typeof registry.get !== "function"
        || typeof origin !== "string") return false;
    const version = assetVersion(moduleUrl);
    const previous = observedParentRegistries.get(registry);
    if (previous) {
      previous.version = version;
      installPanelAdapter(registry.get("ha-panel-custom"), origin, version);
      attachHacsIframe(windowRef.customPanel, origin, version);
      return false;
    }
    const context = {version};
    observedParentRegistries.set(registry, context);
    // HA keeps the mounted custom panel here. Do not scan the page or traverse
    // unrelated shadow roots to find integration or repository elements.
    attachHacsIframe(windowRef.customPanel, origin, version);
    Promise.resolve(registry.whenDefined("ha-panel-custom")).then(() => {
      installPanelAdapter(registry.get("ha-panel-custom"), origin, context.version);
      attachHacsIframe(windowRef.customPanel, origin, context.version);
    }, () => {}).catch(() => {});
    return true;
  } catch {
    return false;
  }
}

if (typeof window !== "undefined") installBranding(window);

import assert from "node:assert/strict";
import {after, test} from "node:test";
import {mkdtempSync, readFileSync, writeFileSync, unlinkSync, rmdirSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {pathToFileURL} from "node:url";

const sourcePath = new URL("../../custom_components/dreame_home/frontend/dreame-home-branding.js", import.meta.url);
const temporary = mkdtempSync(join(tmpdir(), "dreame-branding-test-"));
const modulePath = join(temporary, "branding.mjs");
writeFileSync(modulePath, readFileSync(sourcePath, "utf8"));
after(() => { unlinkSync(modulePath); rmdirSync(temporary); });

const {
  assetVersion, localIconUrl, localLogoUrl, isOwnRepository, isSupportedPanel,
  replaceOwnIcon, replaceReadmeBranding, replaceOwnDescription,
  installDashboardAdapter, installDescriptionAdapter, attachHacsIframe,
  installPanelAdapter, installBranding,
} = await import(pathToFileURL(modulePath).href);

const ORIGIN = "https://ha.example.invalid";
const VERSION = "0.4.0b8";
const OWN = {category: "integration", domain: "dreame_home", full_name: "Ampersandman/Dreame-Home-Laundry"};
const LEGACY_ICON = "https://brands.home-assistant.io/_/dreame_home/icon.png";
const LEGACY_DARK_ICON = "https://brands.home-assistant.io/_/dreame_home/dark_icon.png";
const LEGACY_README_PICTURE = `<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/dreame_home/brand/dark_icon.png">
  <img src="custom_components/dreame_home/brand/icon.png" alt="Dreame Home Laundry" width="96" height="96">
</picture>`;
const README_PICTURE = `<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Ampersandman/Dreame-Home-Laundry/main/custom_components/dreame_home/brand/dark_logo.png">
  <img src="https://raw.githubusercontent.com/Ampersandman/Dreame-Home-Laundry/main/custom_components/dreame_home/brand/logo.png" alt="Dreame Home Laundry" width="96" height="96">
</picture>`;
const README_IMAGE = '<img src="https://raw.githubusercontent.com/Ampersandman/Dreame-Home-Laundry/main/custom_components/dreame_home/brand/logo.png" alt="Dreame Home Laundry" width="96" height="96">';
const README_PREFIX = "# Dreame Home Laundry for Home Assistant\n\n";
const README_SUFFIX = "\n\nUseful integration description.\n\n[Installation](docs/installation.md)\n";

function html(strings, ...values) { return {_$litType$: 1, strings, values}; }
// The minified production template shipped with HACS 2.0.5 (Lit 2.8.0).
function iconTemplate(url) {
  return html` <img style="height:32px;width:32px" slot="item-icon" src="${url}" referrerpolicy="no-referrer"> `;
}
function sourceIconTemplate(url) {
  return html`<img style="height: 32px; width: 32px" slot="item-icon" src=${url} referrerpolicy="no-referrer" />`;
}

function descriptionTemplate(markdown, untouched = {untouched: true}) {
  return html` <hass-subpage .hass="${untouched}"> <div class="content"> <ha-card> <ha-chip-set>${untouched}</ha-chip-set> <ha-markdown .content="${markdown}"></ha-markdown> </ha-card> </div> </hass-subpage> `;
}

function descriptionClass(version = "2.0.5", repository = OWN, picture = README_IMAGE) {
  return class RepositoryDashboard {
    constructor() {
      this.hacs = {info: {version}};
      this.hass = {themes: {darkMode: false}};
      this._repository = Object.freeze({...repository, additional_info: README_PREFIX + picture + README_SUFFIX});
      this.renderCalls = [];
    }
    render(...args) {
      this.renderCalls.push({receiver: this, args});
      this.originalResult = descriptionTemplate(this._repository.additional_info, this.hass);
      return this.originalResult;
    }
  };
}

function panelConfig() {
  return {component_name: "custom", url_path: "hacs", config: {_panel_custom: {
    name: "hacs-frontend", embed_iframe: true,
    js_url: "/hacsfiles/frontend/entrypoint.js?hacstag=20250128065759",
  }}};
}

function registry() {
  const classes = new Map();
  const pending = new Map();
  return {
    requests: [],
    get(name) { return classes.get(name); },
    whenDefined(name) {
      this.requests.push(name);
      if (classes.has(name)) return Promise.resolve(classes.get(name));
      return new Promise(resolve => {
        if (!pending.has(name)) pending.set(name, []);
        pending.get(name).push(resolve);
      });
    },
    define(name, Class) {
      classes.set(name, Class);
      for (const resolve of pending.get(name) || []) resolve(Class);
      pending.delete(name);
    },
  };
}

function dashboardClass(version = "2.0.5") {
  return class Dashboard {
    constructor() {
      this.hacs = {info: {version}};
      this.hass = {themes: {darkMode: false}};
      this.columnsCalls = [];
      this.templateCalls = [];
      this.lifecycleCalls = [];
      this.lifecycleResult = {untouched: true};
      const dashboard = this;
      this.memoizedColumns = Object.freeze({
        icon: Object.freeze({
          type: "icon", title: "", label: "Icon", hidden: false,
          template: function (...args) {
            dashboard.templateCalls.push({receiver: this, args});
            const row = args[0];
            return iconTemplate(`https://brands.home-assistant.io/_/${row.domain}/${dashboard.hass.themes.darkMode ? "dark_" : ""}icon.png`);
          },
        }),
        name: Object.freeze({title: "Name"}),
      });
      this._columns = function (...args) {
        dashboard.columnsCalls.push({receiver: this, args});
        return dashboard.memoizedColumns;
      };
    }
    willUpdate(...args) {
      this.lifecycleCalls.push(args);
      return this.lifecycleResult;
    }
  };
}

function panelClass(frameRegistry, register = function (initialize, setProperties) {
  this.forwarded = {receiver: this, initialize, setProperties};
  return initialize?.(this.panel, {hass: this.hass});
}) {
  return class Panel {
    constructor() {
      this.panel = panelConfig();
      this.hass = {untouched: true};
      this.frame = {contentWindow: {customElements: frameRegistry}};
      this.queries = [];
    }
    querySelector(selector) { this.queries.push(selector); return this.frame; }
    registerIframe(...args) { return Reflect.apply(register, this, args); }
  };
}

async function flush() { await Promise.resolve(); await Promise.resolve(); }

test("bundled image URLs use only a safe version from the module query", () => {
  assert.equal(assetVersion(`${ORIGIN}/dreame_home/branding.js?v=${VERSION}`), VERSION);
  assert.equal(localIconUrl(false, VERSION), `/dreame_home/brand/icon.png?v=${VERSION}`);
  assert.equal(localIconUrl(true, VERSION), `/dreame_home/brand/dark_icon.png?v=${VERSION}`);
  assert.equal(localLogoUrl(false, VERSION), `/dreame_home/brand/logo.png?v=${VERSION}`);
  assert.equal(localLogoUrl(true, VERSION), `/dreame_home/brand/dark_logo.png?v=${VERSION}`);
  for (const invalid of [null, "", "a/b", "a?b", "\" onerror=alert(1)", "a".repeat(65)]) {
    assert.equal(localIconUrl(true, invalid), "/dreame_home/brand/dark_icon.png");
  }
  assert.equal(assetVersion("not a URL"), null);
  assert.equal(assetVersion(`${ORIGIN}/module.js?v=invalid%2Fpath`), null);
});

test("only exact current and previous integration repository identities match", () => {
  assert.equal(isOwnRepository(OWN), true);
  assert.equal(isOwnRepository({...OWN, full_name: "Ampersandman/Dreame-Home"}), true);
  for (const row of [null, {}, {...OWN, category: "plugin"}, {...OWN, domain: "dreame_vacuum"},
    {...OWN, full_name: "someone-else/Dreame-Home-Laundry"}]) {
    assert.equal(isOwnRepository(row), false);
  }
});

test("only the pinned same-origin HACS custom iframe panel matches", () => {
  const panel = panelConfig();
  assert.equal(isSupportedPanel(panel, ORIGIN), true);
  panel.config._panel_custom.js_url = `${ORIGIN}${panel.config._panel_custom.js_url}`;
  assert.equal(isSupportedPanel(panel, ORIGIN), true);
  const variants = [
    p => p.url_path = "another-panel", p => p.component_name = "iframe",
    p => p.config._panel_custom.name = "other-frontend",
    p => p.config._panel_custom.embed_iframe = false,
    p => p.config._panel_custom.js_url = "/hacsfiles/frontend/entrypoint.js?hacstag=changed",
    p => p.config._panel_custom.js_url += "#fragment",
    p => p.config._panel_custom.js_url += "&other=1",
    p => p.config._panel_custom.js_url = "https://other.example.invalid/hacsfiles/frontend/entrypoint.js?hacstag=20250128065759",
  ];
  for (const mutate of variants) {
    const changed = panelConfig(); mutate(changed);
    assert.equal(isSupportedPanel(changed, ORIGIN), false);
  }
});

test("the exact HACS Lit image preserves strings and metadata without changing its original values", () => {
  const original = iconTemplate(LEGACY_ICON);
  const result = replaceOwnIcon(original, OWN, true, VERSION);
  assert.notEqual(result, original);
  assert.equal(result.strings, original.strings);
  assert.equal(result._$litType$, original._$litType$);
  assert.deepEqual(original.values, [LEGACY_ICON]);
  assert.deepEqual(result.values, [`/dreame_home/brand/dark_icon.png?v=${VERSION}`]);
  for (const url of [LEGACY_ICON, LEGACY_DARK_ICON, LEGACY_ICON.replace("icon.png", "icon@2x.png")]) {
    assert.equal(replaceOwnIcon(iconTemplate(url), OWN, false).values[0], "/dreame_home/brand/icon.png");
  }
  assert.equal(replaceOwnIcon(sourceIconTemplate(LEGACY_ICON), OWN, false).values[0], "/dreame_home/brand/icon.png");
  assert.deepEqual(original.strings.map(part => part.trim()), [
    '<img style="height:32px;width:32px" slot="item-icon" src="',
    '" referrerpolicy="no-referrer">',
  ]);
});

test("unknown template shapes, URLs and other repositories pass through by identity", () => {
  const original = iconTemplate(LEGACY_ICON);
  const changed = [
    null, "text", {...original, _$litType$: 2}, {...original, values: []},
    {...original, values: [LEGACY_ICON, "another-value"]},
    {...original, strings: ["<span>", "</span>"]},
    iconTemplate("https://brands.home-assistant.io/_/dreame_vacuum/icon.png"),
    iconTemplate(`${LEGACY_ICON}?unexpected=1`),
    iconTemplate("https://other.example.invalid/_/dreame_home/icon.png"),
  ];
  for (const result of changed) assert.equal(replaceOwnIcon(result, OWN, true, VERSION), result);
  assert.equal(replaceOwnIcon(original, {...OWN, full_name: "another/repo"}, true, VERSION), original);
});

test("known current image and cached README picture blocks become theme-selected local logos", () => {
  for (const picture of [README_IMAGE, README_PICTURE, LEGACY_README_PICTURE]) {
    for (const dark of [false, true]) {
      const original = README_PREFIX + picture + README_SUFFIX;
      const expectedImage = `<img src="/dreame_home/brand/${dark ? "dark_" : ""}logo.png?v=${VERSION}" alt="Dreame Home Laundry" width="96" height="96">`;
      assert.equal(replaceReadmeBranding(original, dark, VERSION), README_PREFIX + expectedImage + README_SUFFIX);
    }
  }
});

test("current README header keeps every other byte and handles Windows line endings", () => {
  const original = README_PREFIX + README_IMAGE + README_SUFFIX;
  const withWindowsLines = original.replaceAll("\n", "\r\n");
  const expectedImage = `<img src="/dreame_home/brand/dark_logo.png?v=${VERSION}" alt="Dreame Home Laundry" width="96" height="96">`;
  assert.equal(replaceReadmeBranding(withWindowsLines, true, VERSION), withWindowsLines.replace(README_IMAGE, expectedImage));
  for (const unchanged of [
    original.replace("# Dreame Home Laundry for Home Assistant", "# Another integration"),
    original.replace(README_IMAGE, README_IMAGE.replace("logo.png", "another.png")),
    original.replace('width="96"', 'width="192"'),
    "Body text with the same image outside the recognized header.\n" + README_IMAGE,
  ]) assert.equal(replaceReadmeBranding(unchanged, true, VERSION), unchanged);
});

test("unrecognized picture markup and unrelated descriptions remain byte-for-byte unchanged", () => {
  const variants = [
    "README without a picture", null, {unexpected: true},
    README_PICTURE.replace("dark_logo.png", "another-dark.png"),
    README_PICTURE.replace('alt="Dreame Home Laundry"', 'alt="Something else"'),
    README_PICTURE.replace('width="96"', 'width="192"'),
    README_PICTURE.replace('height="96">', 'height="96" onerror="alert(1)">'),
    README_PICTURE.replace("Ampersandman/", "another-owner/"),
    README_PICTURE.replace("/main/", "/other-branch/"),
  ];
  for (const original of variants) assert.equal(replaceReadmeBranding(original, true, VERSION), original);
});

test("only the own repository's production ha-markdown interpolation changes", () => {
  const markdown = README_PREFIX + README_IMAGE + README_SUFFIX;
  const original = descriptionTemplate(markdown);
  const result = replaceOwnDescription(original, OWN, true, VERSION);
  assert.notEqual(result, original);
  assert.equal(result.strings, original.strings);
  assert.equal(result.values[0], original.values[0]);
  assert.equal(result.values[1], original.values[1]);
  assert.equal(original.values[2], markdown);
  assert.equal(result.values[2], replaceReadmeBranding(markdown, true, VERSION));
  assert.equal(replaceOwnDescription(original, {...OWN, full_name: "another/repo"}, true, VERSION), original);
  for (const changed of [
    {...original, _$litType$: 2}, {...original, strings: []},
    html`<ha-markdown .other="${markdown}"></ha-markdown>`,
    html`<another-element .content="${markdown}"></another-element>`,
    html`<ha-markdown .content="${{unexpected: true}}"></ha-markdown>`,
  ]) assert.equal(replaceOwnDescription(changed, OWN, true, VERSION), changed);
});

test("repository render preserves receiver, arguments and immutable source metadata", () => {
  const RepositoryDashboard = descriptionClass();
  const component = new RepositoryDashboard();
  const metadata = component._repository;
  const markdown = metadata.additional_info;
  assert.equal(installDescriptionAdapter(RepositoryDashboard, VERSION), true);
  const result = component.render("argument", 1);
  assert.equal(component.renderCalls[0].receiver, component);
  assert.deepEqual(component.renderCalls[0].args, ["argument", 1]);
  assert.equal(result.strings, component.originalResult.strings);
  assert.equal(component._repository, metadata);
  assert.equal(metadata.additional_info, markdown);
  assert.equal(component.originalResult.values[2], markdown);
  assert.equal(result.values[2], replaceReadmeBranding(markdown, false, VERSION));
});

test("repository description follows live themes and version guards on every render", () => {
  const RepositoryDashboard = descriptionClass();
  installDescriptionAdapter(RepositoryDashboard, VERSION);
  const component = new RepositoryDashboard();
  assert.match(component.render().values[2], /src="\/dreame_home\/brand\/logo\.png/);
  component.hass = {themes: {darkMode: true}};
  assert.match(component.render().values[2], /src="\/dreame_home\/brand\/dark_logo\.png/);
  component.hacs.info.version = "2.0.6";
  assert.equal(component.render(), component.originalResult);
  component.hacs.info.version = "2.0.5";
  assert.match(component.render().values[2], /src="\/dreame_home\/brand\/dark_logo\.png/);
  component._repository = {...component._repository, full_name: "another/repo"};
  assert.equal(component.render(), component.originalResult);
});

test("repository description installation is idempotent and upgrades its saved version", () => {
  const RepositoryDashboard = descriptionClass();
  assert.equal(installDescriptionAdapter(RepositoryDashboard, VERSION), true);
  const render = RepositoryDashboard.prototype.render;
  const component = new RepositoryDashboard();
  assert.match(component.render().values[2], /\?v=0\.4\.0b8/);
  assert.equal(installDescriptionAdapter(RepositoryDashboard, "0.4.0b9"), false);
  assert.equal(RepositoryDashboard.prototype.render, render);
  assert.match(component.render().values[2], /\?v=0\.4\.0b9/);
});

test("missing, immutable and throwing repository renderers preserve framework behavior", () => {
  assert.equal(installDescriptionAdapter(undefined), false);
  assert.equal(installDescriptionAdapter(class {}), false);
  const Frozen = descriptionClass(); Object.freeze(Frozen.prototype);
  assert.equal(installDescriptionAdapter(Frozen), false);
  class Throws { render() { throw new Error("original render"); } }
  installDescriptionAdapter(Throws, VERSION);
  assert.throws(() => new Throws().render(), /original render/);
  class UnknownShape {
    constructor() { this.hacs = {info: {version: "2.0.5"}}; this._repository = OWN; this.original = {unknown: true}; }
    render() { return this.original; }
  }
  installDescriptionAdapter(UnknownShape, VERSION);
  const component = new UnknownShape(); assert.equal(component.render(), component.original);
});

test("the columns wrapper preserves lifecycle arguments, memoized data and template receiver", () => {
  const Dashboard = dashboardClass();
  const dashboard = new Dashboard();
  const originalColumns = dashboard._columns;
  assert.equal(installDashboardAdapter(Dashboard, VERSION), true);
  assert.equal(dashboard.willUpdate("changed", 1), dashboard.lifecycleResult);
  assert.deepEqual(dashboard.lifecycleCalls, [["changed", 1]]);
  const columns = dashboard._columns("localize", false);
  assert.notEqual(columns, dashboard.memoizedColumns);
  assert.equal(columns.name, dashboard.memoizedColumns.name);
  assert.equal(columns.icon.type, dashboard.memoizedColumns.icon.type);
  assert.equal(columns.icon.label, "Icon");
  assert.equal(dashboard.columnsCalls[0].receiver, dashboard);
  assert.deepEqual(dashboard.columnsCalls[0].args, ["localize", false]);
  const receiver = {untouched: true};
  const result = columns.icon.template.call(receiver, OWN, "extra argument");
  assert.equal(dashboard.templateCalls[0].receiver, receiver);
  assert.deepEqual(dashboard.templateCalls[0].args, [OWN, "extra argument"]);
  assert.equal(result.values[0], `/dreame_home/brand/icon.png?v=${VERSION}`);
  assert.notEqual(dashboard._columns, originalColumns);
  assert.equal(dashboard.memoizedColumns.icon.template(OWN).values[0], LEGACY_ICON);
});

test("light and dark theme changes use current hass without rebuilding memoized columns", () => {
  const Dashboard = dashboardClass();
  installDashboardAdapter(Dashboard, VERSION);
  const dashboard = new Dashboard(); dashboard.willUpdate();
  const template = dashboard._columns().icon.template;
  assert.equal(template(OWN).values[0], `/dreame_home/brand/icon.png?v=${VERSION}`);
  dashboard.hass = {themes: {darkMode: true}};
  dashboard.willUpdate(new Map([["hass", {}]]));
  assert.equal(template(OWN).values[0], `/dreame_home/brand/dark_icon.png?v=${VERSION}`);
  const foreign = {...OWN, domain: "another_domain", full_name: "another/repo"};
  assert.equal(template(foreign).values[0], "https://brands.home-assistant.io/_/another_domain/dark_icon.png");
});

test("repeated lifecycle and adapter installation wrap each function once", () => {
  const Dashboard = dashboardClass();
  assert.equal(installDashboardAdapter(Dashboard, VERSION), true);
  const lifecycle = Dashboard.prototype.willUpdate;
  assert.equal(installDashboardAdapter(Dashboard, VERSION), false);
  assert.equal(Dashboard.prototype.willUpdate, lifecycle);
  const dashboard = new Dashboard(); dashboard.willUpdate();
  const columns = dashboard._columns;
  dashboard.willUpdate(); dashboard.willUpdate();
  assert.equal(dashboard._columns, columns);
  assert.equal(dashboard.lifecycleCalls.length, 3);
});

test("module version upgrades update saved templates without wrapping a lifecycle again", () => {
  const Dashboard = dashboardClass();
  installDashboardAdapter(Dashboard, VERSION);
  const lifecycle = Dashboard.prototype.willUpdate;
  const dashboard = new Dashboard(); dashboard.willUpdate();
  const columnsFunction = dashboard._columns;
  const savedTemplate = dashboard._columns().icon.template;
  assert.equal(savedTemplate(OWN).values[0], `/dreame_home/brand/icon.png?v=${VERSION}`);
  assert.equal(installDashboardAdapter(Dashboard, "0.4.0b9"), false);
  assert.equal(Dashboard.prototype.willUpdate, lifecycle);
  assert.equal(dashboard._columns, columnsFunction);
  assert.equal(savedTemplate(OWN).values[0], "/dreame_home/brand/icon.png?v=0.4.0b9");
});

test("unsupported HACS versions and changed column shapes retain original behavior", () => {
  const Dashboard = dashboardClass("2.1.0");
  const dashboard = new Dashboard(); const original = dashboard._columns;
  installDashboardAdapter(Dashboard, VERSION); dashboard.willUpdate();
  assert.equal(dashboard._columns, original);
  assert.equal(dashboard._columns().icon.template(OWN).values[0], LEGACY_ICON);
  dashboard.hacs.info.version = "2.0.5"; dashboard.willUpdate();
  assert.notEqual(dashboard._columns, original);
  const savedTemplate = dashboard._columns().icon.template;
  dashboard.hacs.info.version = "3.0.0";
  assert.equal(dashboard._columns(), dashboard.memoizedColumns);
  assert.equal(savedTemplate(OWN).values[0], LEGACY_ICON);
  const Changed = dashboardClass(); installDashboardAdapter(Changed, VERSION);
  const changed = new Changed(); const array = [{key: "icon"}];
  changed._columns = () => array; changed.willUpdate();
  assert.equal(changed._columns(), array);
});

test("original lifecycle and template exceptions are preserved", () => {
  class Throws { willUpdate() { throw new Error("original lifecycle"); } }
  installDashboardAdapter(Throws, VERSION);
  assert.throws(() => new Throws().willUpdate(), /original lifecycle/);
  const Dashboard = dashboardClass(); installDashboardAdapter(Dashboard, VERSION);
  const dashboard = new Dashboard();
  dashboard._columns = () => ({icon: {template() { throw new Error("original template"); }}});
  dashboard.willUpdate();
  assert.throws(() => dashboard._columns().icon.template(OWN), /original template/);
});

test("missing or immutable framework classes safely decline installation", () => {
  assert.equal(installDashboardAdapter(undefined), false);
  assert.equal(installDashboardAdapter(class {}), false);
  const Frozen = dashboardClass(); Object.freeze(Frozen.prototype);
  assert.equal(installDashboardAdapter(Frozen), false);
  assert.equal(installPanelAdapter(undefined, ORIGIN), false);
  const FrozenPanel = panelClass(registry()); Object.freeze(FrozenPanel.prototype);
  assert.equal(installPanelAdapter(FrozenPanel, ORIGIN), false);
});

test("registerIframe adapts before initialize and preserves arguments, receiver and result", () => {
  const childRegistry = registry(); const Dashboard = dashboardClass();
  childRegistry.define("hacs-dashboard", Dashboard);
  const Panel = panelClass(childRegistry); const panel = new Panel();
  assert.equal(installPanelAdapter(Panel, ORIGIN, VERSION), true);
  const originalLifecycle = Dashboard.prototype.willUpdate;
  const result = {untouched: true}; const setProperties = () => {};
  const initialize = (config, properties) => {
    assert.notEqual(Dashboard.prototype.willUpdate, originalLifecycle);
    assert.equal(config, panel.panel); assert.equal(properties.hass, panel.hass);
    const dashboard = new Dashboard(); dashboard.willUpdate();
    assert.equal(dashboard._columns().icon.template(OWN).values[0], `/dreame_home/brand/icon.png?v=${VERSION}`);
    return result;
  };
  assert.equal(panel.registerIframe(initialize, setProperties), result);
  assert.equal(panel.forwarded.receiver, panel);
  assert.equal(panel.forwarded.initialize, initialize);
  assert.equal(panel.forwarded.setProperties, setProperties);
  assert.deepEqual(panel.queries, ["iframe"]);
  assert.equal(installPanelAdapter(Panel, ORIGIN, VERSION), false);
});

test("asynchronous frame creation retains promise identity and adapts after completion", async () => {
  const childRegistry = registry(); const Dashboard = dashboardClass();
  childRegistry.define("hacs-dashboard", Dashboard);
  let resolve;
  const pending = new Promise(done => { resolve = done; });
  const Panel = panelClass(childRegistry, () => pending);
  installPanelAdapter(Panel, ORIGIN, VERSION);
  const panel = new Panel(); const frame = panel.frame; panel.frame = null;
  assert.equal(panel.registerIframe(), pending);
  panel.frame = frame; resolve(); await flush();
  const dashboard = new Dashboard(); dashboard.willUpdate();
  assert.equal(dashboard._columns().icon.template(OWN).values[0], `/dreame_home/brand/icon.png?v=${VERSION}`);
});

test("late iframe element definitions install once and do not access other realms", async () => {
  const childRegistry = registry(); const Panel = panelClass(childRegistry); const panel = new Panel();
  assert.equal(attachHacsIframe(panel, ORIGIN, VERSION), true);
  assert.equal(attachHacsIframe(panel, ORIGIN, VERSION), false);
  assert.deepEqual(childRegistry.requests, ["hacs-dashboard", "hacs-repository-dashboard"]);
  const Dashboard = dashboardClass(); childRegistry.define("hacs-dashboard", Dashboard); await flush();
  const dashboard = new Dashboard(); dashboard.willUpdate();
  assert.equal(dashboard._columns().icon.template(OWN).values[0], `/dreame_home/brand/icon.png?v=${VERSION}`);
  const RepositoryDashboard = descriptionClass();
  childRegistry.define("hacs-repository-dashboard", RepositoryDashboard); await flush();
  const repository = new RepositoryDashboard();
  assert.match(repository.render().values[2], /src="\/dreame_home\/brand\/logo\.png/);
});

test("cross-origin errors and unrelated panels leave panel initialization untouched", () => {
  const childRegistry = registry(); const Panel = panelClass(childRegistry);
  installPanelAdapter(Panel, ORIGIN, VERSION);
  const panel = new Panel();
  panel.frame = {contentWindow: Object.create(null, {
    customElements: {get() { throw new Error("SecurityError: another origin"); }},
  })};
  assert.equal(attachHacsIframe(panel, ORIGIN, VERSION), false);
  const value = {unchanged: true};
  assert.equal(panel.registerIframe(() => value), value);
  panel.queries = []; panel.panel.url_path = "another-panel";
  assert.equal(panel.registerIframe(() => value), value);
  assert.deepEqual(panel.queries, []);
  assert.deepEqual(childRegistry.requests, []);
});

test("bootstrap covers an already mounted panel and future iframe registrations without scanning", async () => {
  const childRegistry = registry(); const Dashboard = dashboardClass();
  childRegistry.define("hacs-dashboard", Dashboard);
  const parentRegistry = registry(); const Panel = panelClass(childRegistry);
  const windowRef = {customElements: parentRegistry, location: {origin: ORIGIN}, customPanel: new Panel()};
  assert.equal(installBranding(windowRef, `${ORIGIN}/dreame_home/branding.js?v=${VERSION}`), true);
  const dashboard = new Dashboard(); dashboard.willUpdate();
  assert.equal(dashboard._columns().icon.template(OWN).values[0], `/dreame_home/brand/icon.png?v=${VERSION}`);
  parentRegistry.define("ha-panel-custom", Panel); await flush();
  const anotherRegistry = registry(); const LaterDashboard = dashboardClass();
  anotherRegistry.define("hacs-dashboard", LaterDashboard);
  const later = new Panel(); later.frame.contentWindow.customElements = anotherRegistry;
  later.registerIframe(() => "unchanged");
  const laterDashboard = new LaterDashboard(); laterDashboard.willUpdate();
  assert.equal(laterDashboard._columns().icon.template(OWN).values[0], `/dreame_home/brand/icon.png?v=${VERSION}`);
  assert.equal(installBranding(windowRef, `${ORIGIN}/another.js?v=${VERSION}`), false);
  assert.deepEqual(parentRegistry.requests, ["ha-panel-custom"]);
  assert.ok(windowRef.customPanel.queries.every(selector => selector === "iframe"));
});

test("bootstrap tolerates unavailable and rejected registries", async () => {
  assert.equal(installBranding(undefined), false);
  assert.equal(installBranding({location: {origin: ORIGIN}}), false);
  const rejected = {get() {}, whenDefined() { return Promise.reject(new Error("not available")); }};
  assert.equal(installBranding({customElements: rejected, location: {origin: ORIGIN}}), true);
  await flush();
});

test("reloading a module version updates existing and future frame assets without duplicate listeners", async () => {
  const childRegistry = registry(); const Dashboard = dashboardClass();
  childRegistry.define("hacs-dashboard", Dashboard);
  const parentRegistry = registry(); const Panel = panelClass(childRegistry);
  parentRegistry.define("ha-panel-custom", Panel);
  const windowRef = {customElements: parentRegistry, location: {origin: ORIGIN}, customPanel: new Panel()};
  installBranding(windowRef, `${ORIGIN}/module.js?v=${VERSION}`); await flush();
  const dashboard = new Dashboard(); dashboard.willUpdate();
  const savedTemplate = dashboard._columns().icon.template;
  const panelLifecycle = Panel.prototype.registerIframe;
  assert.equal(installBranding(windowRef, `${ORIGIN}/module.js?v=0.4.0b9`), false);
  assert.equal(Panel.prototype.registerIframe, panelLifecycle);
  assert.equal(savedTemplate(OWN).values[0], "/dreame_home/brand/icon.png?v=0.4.0b9");
  const laterRegistry = registry(); const LaterDashboard = dashboardClass();
  laterRegistry.define("hacs-dashboard", LaterDashboard);
  const laterPanel = new Panel(); laterPanel.frame.contentWindow.customElements = laterRegistry;
  laterPanel.registerIframe(() => {});
  const later = new LaterDashboard(); later.willUpdate();
  assert.equal(later._columns().icon.template(OWN).values[0], "/dreame_home/brand/icon.png?v=0.4.0b9");
  assert.deepEqual(parentRegistry.requests, ["ha-panel-custom"]);
});

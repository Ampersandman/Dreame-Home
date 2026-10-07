/* Original Dreame Home laundry card. No external fonts, assets or libraries. */
const TYPE = "custom:dreame-home-laundry-card";
const MODEL_TYPES = {"dreame.washer.l9nacn": "washer", "dreame.dryer.l9nacn": "dryer"};
const KEYS = ["status", "progress", "remaining", "duration", "program", "start", "pause", "stop"];
const TEXT = {
  en: {status:"Status",washer:"Washing machine",dryer:"Tumble dryer",laundry:"Laundry",ready:"Ready",running:"Running",paused:"Paused",off:"Powered off",offline:"Unavailable",unknown:"Status unknown",stale:"Waiting for live status",remaining:"Remaining",duration:"Duration",progress:"Cycle progress",program:"Current program",start:"Start",resume:"Resume",pause:"Pause",stop:"Power off",wash:"Wash",dry:"Dry",care:"Care",programs:"Programs",more:"All programs",less:"Show fewer",estimate:"Reference",settings:"Settings",advanced:"Advanced settings",noSettings:"No setting entities are available for this device.",noPrograms:"Program options will appear when the device reports them.",choose:"Choose a laundry device in the card editor.",pending:"Sending command…",sent:"Command sent. Waiting for the device to update.",failed:"The command could not be completed. Check the device and try again.",notAvailable:"This control is currently unavailable.",apply:"Apply",minutes:"min",device:"Device",name:"Display name (optional)",appliance:"Appliance",automatic:"Automatic",overrides:"Entity overrides (optional)",entity:"Entity",illustration:"Illustration of a front-loading appliance",on:"On",offSetting:"Off",temp:"Temperature",spin:"Spin speed",rinse:"Extra rinses",detergent:"Detergent",softener:"Softener",dryness:"Dryness level",airflow:"Airflow",delay:"Delay",extra:"Extra time",child_lock:"Child lock",night_mode:"Night mode",uv_mode:"UV care",anticrease:"Anti-crease",low_temp_dry:"Low temperature",accelerate:"Accelerate",steam:"Steam"},
  de: {status:"Status",washer:"Waschmaschine",dryer:"Wäschetrockner",laundry:"Wäsche",ready:"Bereit",running:"Läuft",paused:"Pausiert",off:"Ausgeschaltet",offline:"Nicht verfügbar",unknown:"Status unbekannt",stale:"Warte auf aktuellen Status",remaining:"Verbleibend",duration:"Dauer",progress:"Programmfortschritt",program:"Aktuelles Programm",start:"Starten",resume:"Fortsetzen",pause:"Pause",stop:"Ausschalten",wash:"Waschen",dry:"Trocknen",care:"Pflegen",programs:"Programme",more:"Alle Programme",less:"Weniger anzeigen",estimate:"Richtwert",settings:"Einstellungen",advanced:"Weitere Einstellungen",noSettings:"Für dieses Gerät sind keine Einstellungen verfügbar.",noPrograms:"Programme erscheinen, sobald das Gerät sie meldet.",choose:"Wähle im Karteneditor ein Wäschegerät aus.",pending:"Befehl wird gesendet…",sent:"Befehl gesendet. Warte auf die Aktualisierung des Geräts.",failed:"Der Befehl konnte nicht ausgeführt werden. Prüfe das Gerät und versuche es erneut.",notAvailable:"Diese Funktion ist gerade nicht verfügbar.",apply:"Übernehmen",minutes:"Min.",device:"Gerät",name:"Anzeigename (optional)",appliance:"Gerätetyp",automatic:"Automatisch",overrides:"Entitäten überschreiben (optional)",entity:"Entität",illustration:"Illustration eines Frontladers",on:"An",offSetting:"Aus",temp:"Temperatur",spin:"Schleuderdrehzahl",rinse:"Zusätzliche Spülgänge",detergent:"Waschmittel",softener:"Weichspüler",dryness:"Trocknungsgrad",airflow:"Luftstrom",delay:"Startverzögerung",extra:"Zusätzliche Zeit",child_lock:"Kindersicherung",night_mode:"Nachtmodus",uv_mode:"UV-Pflege",anticrease:"Knitterschutz",low_temp_dry:"Niedrige Temperatur",accelerate:"Beschleunigen",steam:"Dampf"}
};
const SETTING_LABELS = {temperature:"temp",spin_speed:"spin",extra_rinse:"rinse",rinse_cycles:"rinse",detergent:"detergent",detergent_dosing:"detergent",softener:"softener",softener_dosing:"softener",dryness:"dryness",dryness_level:"dryness",airflow:"airflow",delay:"delay",delay_time:"delay",extra_time:"extra",child_lock:"child_lock",night_mode:"night_mode",uv_mode:"uv_mode",anticrease:"anticrease",wrinkle_care:"anticrease",low_temp_dry:"low_temp_dry",low_temperature:"low_temp_dry",accelerate:"accelerate",speed_mode:"accelerate",steam:"steam",steam_level:"steam"};

export function language(hass) { return String(hass?.locale?.language || hass?.language || "en").toLowerCase().startsWith("de") ? "de" : "en"; }
function t(hass, key) { return TEXT[language(hass)][key] || key; }
function escape(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
export function isAvailable(state) { return !!state && !["unknown","unavailable",""].includes(state.state) && state.state != null; }
// HA buttons report unknown until their first press; this is not unavailable.
export function isButtonAvailable(state) { return !!state && state.state !== "unavailable"; }
export function statusCode(state) {
  if (!isAvailable(state)) return null;
  const raw = state.attributes?.raw_code;
  if (Object.prototype.hasOwnProperty.call(state.attributes || {},"raw_code")) return Number.isInteger(raw) && raw >= 0 && raw <= 3 ? raw : null;
  return /^[0-3]$/.test(String(state.state)) ? Number(state.state) : null;
}
export function isFreshStatus(state, now = Date.now()) {
  if (statusCode(state) === null || state.attributes?.observation_fresh !== true || state.attributes?.last_reply_null === true) return false;
  const code = state.attributes?.last_code;
  if (code !== undefined && code !== null && code !== 0 && code !== "0") return false;
  const received = Date.parse(state.attributes?.observed_at || "");
  return Number.isFinite(received) && now - received >= -5000 && now - received <= 180000;
}
export function isRunning(state, now = Date.now()) { return isFreshStatus(state, now) && statusCode(state) === 3; }
export function numericValue(state, max = Infinity) {
  if (!isAvailable(state) || typeof state.state !== "string" && typeof state.state !== "number" || String(state.state).trim() === "") return null;
  const value = Number(state.state);
  return Number.isFinite(value) && value >= 0 && value <= max ? value : null;
}
function stateFor(hass, id) { return id && hass?.states?.[id]; }
function entityRows(hass, deviceId) {
  return Object.entries(hass?.entities || {}).map(([id,row]) => ({...row,entity_id:row.entity_id || id}))
    .filter(row => !deviceId || row.device_id === deviceId);
}
export function resolveEntities(hass, config) {
  const device = hass?.devices?.[config.device_id];
  const appliance = config.appliance || MODEL_TYPES[device?.model] || "washer";
  const result = {appliance,device,settings:[]};
  for (const key of KEYS) if (config[`${key}_entity`]) result[key] = config[`${key}_entity`];
  if (config.device_id) {
    for (const row of entityRows(hass, config.device_id)) {
      const id = row.entity_id, state = stateFor(hass,id), attrs = state?.attributes || {};
      const uid = typeof row.unique_id === "string" ? row.unique_id : "";
      const control = attrs.control_key || uid.match(/:control:(?:select|button|number|switch):([^:]+)$/)?.[1];
      if (["program","start","pause","stop"].includes(control) && !result[control]) result[control] = id;
      if (attrs.cycle_metric === "progress" || uid.endsWith(":cycle:progress")) result.progress ||= id;
      const coordinate = attrs.field_path == null && Number.isInteger(attrs.siid) && Number.isInteger(attrs.piid)
        ? `${attrs.siid}.${attrs.piid}` : uid.match(/:prop:([0-9]+\.[0-9]+):state$/)?.[1];
      if (coordinate === "2.1" && id.startsWith("sensor.")) result.status ||= id;
      if (coordinate === (appliance === "dryer" ? "2.11" : "2.13")) result.remaining ||= id;
      if (coordinate === (appliance === "dryer" ? "2.9" : "2.12")) result.duration ||= id;
      if (control && control !== "program" && ["select","number","switch"].includes(id.split(".")[0])) result.settings.push(id);
    }
  }
  if (Array.isArray(config.settings_entities)) result.settings = config.settings_entities.filter(id => typeof id === "string" && /^(select|number|switch)\./.test(id));
  result.settings = [...new Set(result.settings)];
  return result;
}
export function programRows(state, appliance, lang = "en") {
  const options = Array.isArray(state?.attributes?.options) ? state.attributes.options.filter(v => typeof v === "string").slice(0,256) : [];
  const catalog = Array.isArray(state?.attributes?.program_catalog) ? state.attributes.program_catalog.slice(0,256) : [];
  const rows = [], used = new Set(), codes = new Set();
  for (const source of catalog) {
    if (!source || !Number.isInteger(source.value) || codes.has(source.value)) continue;
    codes.add(source.value);
    const option = typeof source.option === "string" && options.includes(source.option) ? source.option : null;
    if (option) used.add(option);
    const group = ["wash","dry","care"].includes(source.group) ? source.group : appliance === "dryer" ? "dry" : "wash";
    rows.push({code:source.value,option,group,label:source.labels?.[lang] || source.label || option || String(source.value),
      selectable:!!option && source.selectable !== false,reference:Number.isInteger(source.reference_duration_minutes) && source.reference_duration_minutes > 0 ? source.reference_duration_minutes : null,
      selected:Number.isInteger(state?.attributes?.raw_code) ? state.attributes.raw_code === source.value : !!option && state.state === option,
      icon:source.icon});
  }
  for (const option of options) if (!used.has(option)) rows.push({option,code:null,group:appliance === "dryer" ? "dry" : "wash",label:option,selectable:true,reference:null,selected:state?.state === option});
  return rows;
}
export function serviceRequest(hass, config, action, value, now = Date.now()) {
  const entities = resolveEntities(hass,config);
  if (!isFreshStatus(stateFor(hass,entities.status),now)) throw new Error("notAvailable");
  if (["start","pause","stop"].includes(action)) {
    const id = entities[action];
    if (!id?.startsWith("button.") || !isButtonAvailable(stateFor(hass,id))) throw new Error("notAvailable");
    return {domain:"button",service:"press",data:{entity_id:id}};
  }
  if (action === "program") {
    const id = entities.program, state = stateFor(hass,id);
    if (!id?.startsWith("select.") || !isAvailable(state) || typeof value !== "string" || !state.attributes?.options?.includes(value)) throw new Error("notAvailable");
    return {domain:"select",service:"select_option",data:{entity_id:id,option:value}};
  }
  if (action === "setting") {
    const {id,choice} = value || {}, state = stateFor(hass,id);
    if (!entities.settings.includes(id) || !isAvailable(state)) throw new Error("notAvailable");
    const domain = id.split(".")[0];
    if (domain === "select" && typeof choice === "string" && state.attributes?.options?.includes(choice)) return {domain,service:"select_option",data:{entity_id:id,option:choice}};
    if (domain === "switch" && ["on","off"].includes(state.state) && typeof choice === "boolean") return {domain,service:choice ? "turn_on" : "turn_off",data:{entity_id:id}};
    if (domain === "number" && typeof choice === "number" && Number.isFinite(choice)) {
      const {min,max,step} = state.attributes || {};
      if (typeof min !== "number" || typeof max !== "number" || typeof step !== "number" || step <= 0 || choice < min || choice > max) throw new Error("notAvailable");
      const count = (choice-min)/step;
      if (Math.abs(count-Math.round(count)) > 1e-7) throw new Error("notAvailable");
      return {domain,service:"set_value",data:{entity_id:id,value:choice}};
    }
  }
  throw new Error("notAvailable");
}
function duration(value,hass) { if (value === null) return "—"; const n=Math.round(value); return n>=60 ? `${Math.floor(n/60)} h${n%60 ? ` ${n%60} ${t(hass,"minutes")}` : ""}` : `${n} ${t(hass,"minutes")}`; }
const ICONS = {
  play:'<path d="m9 5 11 7-11 7z"/>',pause:'<path d="M8 5v14M16 5v14"/>',power:'<path d="M12 3v9m-6-7a9 9 0 1 0 12 0"/>',settings:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',shirt:'<path d="m8 3-5 3-2 5 5 2v8h12v-8l5-2-2-5-5-3c0 5-8 5-8 0z"/>',leaf:'<path d="M20 3c0 12-3 18-11 18A7 7 0 0 1 3 9c4-5 10-2 17-6ZM4 21 16 9"/>',check:'<path d="m5 12 4 4L19 6"/>',chevron:'<path d="m6 9 6 6 6-6"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',sparkles:'<path d="m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3Z"/>'
};
function icon(kind,cls="") { return `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[kind] || ICONS.shirt}</svg>`; }

/* Drawn for this integration: metallic cabinet, smoked door and moving drum. */
function applianceSvg(type,running,label) {
  return `<svg class="appliance-art ${running ? "running" : ""}" viewBox="0 0 340 380" role="img" aria-label="${escape(label)}">
  <defs><linearGradient id="cabinet" x1="0" x2="1" y2="1"><stop stop-color="#d1d1cf"/><stop offset=".25" stop-color="#f0efeb"/><stop offset=".68" stop-color="#b5b6b5"/><stop offset="1" stop-color="#929695"/></linearGradient><linearGradient id="panel" x2="0" y2="1"><stop stop-color="#252a2c"/><stop offset="1" stop-color="#080b0d"/></linearGradient><radialGradient id="glass"><stop stop-color="#192328"/><stop offset=".65" stop-color="#10181d"/><stop offset="1" stop-color="#050a0d"/></radialGradient><linearGradient id="rim" x1="0" x2="1" y2="1"><stop stop-color="#b9c0c0"/><stop offset=".22" stop-color="#6e777c"/><stop offset=".55" stop-color="#101719"/><stop offset=".8" stop-color="#353e41"/><stop offset="1" stop-color="#b5bdbd"/></linearGradient><radialGradient id="drum"><stop stop-color="#36444a"/><stop offset=".85" stop-color="#202b30"/><stop offset="1" stop-color="#050b0e"/></radialGradient><pattern id="holes" width="10" height="10" patternUnits="userSpaceOnUse"><circle cx="3" cy="3" r="1.05" fill="#071115"/><circle cx="3" cy="3" r=".6" fill="#46575d"/></pattern><filter id="shadow"><feGaussianBlur stdDeviation="8"/></filter></defs>
  <ellipse cx="170" cy="355" rx="124" ry="13" fill="#000" opacity=".65" filter="url(#shadow)"/>
  <path d="M56 29h231l8 11v303l-9 9H55l-9-9V40Z" fill="url(#cabinet)"/>
  <rect x="49" y="32" width="243" height="45" rx="6" fill="url(#panel)"/><path d="M50 76h241" stroke="#777e7e" opacity=".6"/>
  <path d="M61 43h65v21H61" fill="#111618" stroke="#505a5d" stroke-width=".6"/><text x="74" y="57" fill="#b7c0bf" font-size="6" letter-spacing="1.6" font-family="Arial,sans-serif">dreame</text>
  <circle cx="159" cy="55" r="13" fill="#2f3537" stroke="#707778" stroke-width="1.1"/><circle cx="159" cy="55" r="10" fill="#161e21"/><path d="M159 45v4" stroke="#d8e1dc" stroke-width="1.4"/>
  <rect x="188" y="41" width="91" height="26" rx="3" fill="#080e11"/><text x="201" y="57" fill="${type==="dryer" ? "#e6dac0" : "#b6d3ea"}" font-size="11" font-family="Arial,sans-serif" letter-spacing="1.5">L9</text><circle cx="263" cy="54" r="2" fill="${running ? "#a3c1be" : "#536466"}"/>
  <path d="M53 82h235v230H53Z" fill="#e4e4df" opacity=".19"/><path d="M61 84v218" stroke="#fff" opacity=".18"/><path d="M286 83v241" stroke="#4e5a5d" opacity=".2"/>
  <circle cx="170" cy="198" r="102" fill="#919a9b"/><circle cx="170" cy="198" r="99" fill="url(#rim)"/><circle cx="170" cy="198" r="88" fill="#070d10" stroke="#545f62" stroke-width="1"/><circle cx="170" cy="198" r="79" fill="url(#glass)"/>
  <g class="drum-rotation"><circle cx="170" cy="198" r="69" fill="url(#drum)"/><circle cx="170" cy="198" r="65" fill="url(#holes)"/><g fill="#718083" opacity=".52"><path d="m163 133 7-3 7 3-3 44h-8Z"/><path d="m222 237-1 8-7 4-36-25 4-7Z"/><path d="m118 239-6-5 1-8 41-17 4 7Z"/></g><path d="M129 205c10-20 26-7 35-16 13-13 37-2 38 9s19 8 17 28c-10 20-45 12-64 10-22-1-39-10-26-31" fill="${type==="dryer" ? "#a49b88" : "#677f90"}" opacity=".56"/><path d="M145 211c11 3 25-17 40-13m-39 30c13-12 24 1 48-7" fill="none" stroke="#d2d3c9" stroke-width="5" opacity=".15"/></g>
  <circle cx="170" cy="198" r="78" fill="none" stroke="#b6c4c7" stroke-width=".8" opacity=".28"/><path d="M115 153a72 72 0 0 1 89-17" stroke="#dbe8e9" stroke-width="6" fill="none" stroke-linecap="round" opacity=".16"/><path d="M110 255a76 76 0 0 0 90 14" stroke="#6a858e" stroke-width="3" fill="none" opacity=".2"/><path d="M247 185v27" stroke="#d2d9d8" stroke-width="5" stroke-linecap="round" opacity=".52"/>
  <path d="M59 318h222" stroke="#616d6e" stroke-width=".7" opacity=".35"/><rect x="230" y="323" width="43" height="19" rx="2" fill="#9da5a3" stroke="#909a99" stroke-width=".6"/><path d="M68 352v5h30v-5m145 0v5h30v-5" fill="#404849"/>
  </svg>`;
}

const STYLES = `
 :host{display:block;container-type:inline-size;color:#edf0ef;font-family:var(--primary-font-family,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif);--accent:#b6d4eb;--care:#bed0b7;--accent-ink:#15222c;--muted:#929a9d}
 *{box-sizing:border-box}ha-card{display:block;overflow:hidden;border:1px solid #35393b;border-radius:28px!important;background:#15181a!important;color:#edf0ef;box-shadow:0 14px 34px #0002}button,input,select{font:inherit}button{cursor:pointer}button:disabled,select:disabled,input:disabled{cursor:not-allowed;opacity:.38}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:4px}button{border:0}svg.icon{width:21px;height:21px;flex-shrink:0}.header{display:flex;align-items:flex-start;gap:14px;padding:25px 26px 0}.brand{font-size:10px;letter-spacing:.25em;color:#a7adb0;font-weight:650;margin:0 0 7px}.title{font-size:23px;letter-spacing:-.035em;line-height:1.2;font-weight:560;margin:0}.heading{min-width:0;flex:1}.status{display:inline-flex;align-items:center;gap:7px;color:#b7bdbe;font-size:12px;margin-top:10px}.status-dot{width:6px;height:6px;border-radius:50%;background:#697174}.live .status-dot{background:var(--accent);box-shadow:0 0 10px #b6d4eb44}.icon-button{width:37px;height:37px;display:grid;place-items:center;background:#252a2d;border:1px solid #353d40;border-radius:12px;color:#b9c2c3}.layout{display:grid;grid-template-columns:minmax(0,1fr)}.machine-section{padding:0 24px 21px;min-width:0}.art-stage{height:280px;position:relative;display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse at 50% 55%,#30383b40,transparent 70%);margin:5px -10px 0}.appliance-art{height:278px;max-width:100%;overflow:visible;filter:drop-shadow(0 7px 10px #0003)}.drum-rotation{transform-origin:170px 198px}.running .drum-rotation{animation:drum-spin 5.8s linear infinite}@keyframes drum-spin{to{transform:rotate(360deg)}}.current-program{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:0;margin-bottom:16px}.eyebrow{display:block;color:var(--muted);font-size:10px;font-weight:500;letter-spacing:.025em;margin-bottom:5px}.current-name{font-size:16px;letter-spacing:-.02em;line-height:1.35;display:block;max-width:230px}.program-mark{width:35px;height:35px;border:1px solid #414b50;border-radius:11px;display:grid;place-items:center;color:var(--accent)}.progress-heading{display:flex;justify-content:space-between;gap:12px;font-size:11px;color:#a3acae;margin-bottom:8px}.progress-value{font-variant-numeric:tabular-nums;color:var(--accent);font-weight:600}.track{height:4px;border-radius:8px;background:#333b3e;overflow:hidden}.track-fill{height:100%;background:var(--accent);border-radius:8px;transition:width .35s ease}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-top:16px}.metric strong{font-size:23px;font-weight:500;letter-spacing:-.035em;font-variant-numeric:tabular-nums;white-space:nowrap}.metric:last-child{text-align:right}.actions{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:20px}.action{min-height:45px;display:flex;align-items:center;justify-content:center;gap:6px;padding:10px 5px;border-radius:13px;background:#2b3236;color:#dde3e2;font-size:11px;font-weight:600;border:1px solid #3a4348}.action .icon{width:17px;height:17px}.action.primary{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}.action.power{background:#222729;color:#a8b0b2;border-color:#353e42}.feedback{padding:12px 14px;margin:13px 0 0;background:#232e31;border:1px solid #3e5054;border-radius:12px;font-size:12px;line-height:1.5;color:#d2dfdf}.feedback.error{background:#352426;border-color:#654347;color:#edc0bf}.program-section{padding:23px 24px 25px;background:#111416;border-top:1px solid #2a3033;min-width:0}.section-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:17px}.section-heading h2{font-weight:500;font-size:15px;margin:0;letter-spacing:-.02em}.section-caption{font-size:10px;color:#778387}.tabs{display:flex;gap:6px;margin:-2px 0 16px}.tab{background:transparent;color:#859196;border:1px solid #303b40;min-height:33px;padding:7px 14px;border-radius:11px;font-size:11px}.tab.selected{background:#293a44;border-color:#435d6d;color:var(--accent)}.tab.care.selected{background:#2c362b;border-color:#53664e;color:var(--care)}.program-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:9px}.program-tile{position:relative;display:flex;align-items:flex-start;gap:11px;text-align:left;min-height:84px;padding:15px 12px;border-radius:16px;border:1px solid #303b40;color:#d8dedf;background:#20292e;transition:border-color .15s,background .15s}.program-tile:hover:not(:disabled){border-color:#638294;background:#293842}.program-tile.care{background:#242b22;border-color:#394235}.program-tile.selected{border-color:var(--accent);background:#2d3d48;box-shadow:inset 0 0 0 .3px var(--accent)}.program-tile.care.selected{border-color:var(--care);background:#303d2d;box-shadow:inset 0 0 0 .3px var(--care)}.tile-icon{width:24px;height:24px;color:var(--accent);margin-top:3px}.care .tile-icon{color:var(--care)}.tile-text{min-width:0;flex:1}.tile-title{display:block;font-weight:500;font-size:12px;line-height:1.4;word-break:normal}.tile-sub{display:block;color:#8fa0aa;font-size:9px;line-height:1.4;margin-top:5px}.care .tile-sub{color:#9ca796}.tile-check{position:absolute;top:7px;right:7px;width:13px!important;height:13px!important;color:var(--accent)}.care .tile-check{color:var(--care)}.more{display:flex;align-items:center;justify-content:center;gap:6px;color:#aab5b8;background:transparent;border:0;width:100%;margin-top:14px;font-size:11px;min-height:29px}.more .icon{width:15px;height:15px}.empty{color:#a0aaad;font-size:13px;line-height:1.6;padding:18px 0}.advanced{padding:21px 24px 25px;border-top:1px solid #2c3438;background:#171c1f}.advanced h2{font-size:15px;font-weight:500;margin:0 0 15px}.settings-grid{display:grid;gap:13px;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.setting{display:flex;flex-direction:column;gap:7px;min-width:0}.setting-label{font-size:11px;color:#a6b1b5;line-height:1.4}.setting select,.setting input{width:100%;min-height:39px;border-radius:10px;border:1px solid #3b484f;background:#252f35;color:#dce4e6;padding:8px;font-size:11px}.number-line{display:flex;gap:5px}.number-line input{min-width:0}.number-apply{background:#31434e;border:1px solid #51626d;border-radius:9px;color:#d4e0e7;padding:7px;font-size:10px}.switch{display:flex;align-items:center;gap:8px;color:#bac5c8;background:#263138;border:1px solid #3b4b54;border-radius:10px;padding:10px;min-height:39px;font-size:11px}.switch-dot{width:25px;height:14px;border-radius:10px;background:#566067;position:relative}.switch-dot:after{content:"";position:absolute;width:10px;height:10px;border-radius:50%;left:2px;top:2px;background:#d1d9db}.switch[aria-checked=true] .switch-dot{background:#8eabbf}.switch[aria-checked=true] .switch-dot:after{left:13px}.dryer{--accent:#e3d7bb;--accent-ink:#302c23}.dryer .tab.selected{background:#39372e;border-color:#6c6451}.dryer .program-tile{background:#2d2c27;border-color:#454337}.dryer .program-tile.selected{background:#39372d}.dryer .program-tile:hover:not(:disabled){background:#36352d;border-color:#746c57}.dryer .tile-sub{color:#a59e8d}.dryer .program-tile.care{background:#242b22;border-color:#394235}.dryer .program-tile.care.selected{background:#303d2d;border-color:var(--care)}
 @container(min-width:660px){.layout{grid-template-columns:minmax(285px,.85fr) minmax(310px,1fr)}.program-section{border-top:0;border-left:1px solid #2a3033;padding-top:25px}.art-stage{height:302px}.appliance-art{height:300px}.header{padding-bottom:18px}.machine-section{padding-bottom:26px}.settings-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
 @container(max-width:340px){.header{padding:22px 18px 0}.machine-section,.program-section,.advanced{padding-left:18px;padding-right:18px}.title{font-size:21px}.program-tile{gap:7px;padding:14px 9px}.tile-title{font-size:11px}.action{font-size:10px;gap:3px}.action .icon{width:15px}.metric strong{font-size:20px}}
 @media(prefers-reduced-motion:reduce){.running .drum-rotation{animation:none}.track-fill{transition:none}.program-tile{transition:none}}
`;

export class DreameHomeLaundryCard extends (globalThis.HTMLElement || class {}) {
  constructor() {
    super(); this._config={type:TYPE}; this._pending=false; this._advanced=false; this._expanded=false; this._group=null; this._drafts=new Map();
    if (this.attachShadow) {this.attachShadow({mode:"open"});this.shadowRoot.addEventListener("click",e=>this._click(e));this.shadowRoot.addEventListener("change",e=>this._change(e));this.shadowRoot.addEventListener("input",e=>{const target=e.target;if(target.dataset?.number)this._drafts.set(target.dataset.number,target.value);});}
  }
  setConfig(config) { if (!config || typeof config !== "object" || Array.isArray(config)) throw new Error("Card configuration must be an object"); if (config.appliance && !["washer","dryer"].includes(config.appliance)) throw new Error("appliance must be washer or dryer"); this._config={...config,type:TYPE}; this._render(); }
  set hass(hass) { this._hass=hass;this._render(); }
  get hass() {return this._hass;}
  connectedCallback() { if (!this._timer) this._timer=setInterval(()=>this._render(),15000);this._render(); }
  disconnectedCallback() {clearInterval(this._timer);this._timer=null;}
  getCardSize() {return 11;}
  getGridOptions() {return {columns:12,rows:"auto",min_columns:6};}
  static getConfigElement() {return document.createElement("dreame-home-laundry-card-editor");}
  static getStubConfig(hass) { const device=Object.values(hass?.devices || {}).find(d=>MODEL_TYPES[d.model]);return {type:TYPE,...(device?.id ? {device_id:device.id} : {})}; }
  async _perform(action,value) {
    if (this._pending) return false;
    let request;
    try {request=serviceRequest(this._hass,this._config,action,value);} catch {this._feedback={kind:"error",key:"notAvailable"};this._render();return false;}
    this._pending=true;this._feedback=null;this._render();
    try { await this._hass.callService(request.domain,request.service,request.data); this._feedback={kind:"success",key:"sent"}; if(action==="setting")this._drafts.delete(value.id);return true; }
    catch {this._feedback={kind:"error",key:"failed"};return false;}
    finally {this._pending=false;this._render();}
  }
  _target(event) {return (event.composedPath?.() || [event.target]).find(node=>node?.dataset?.action || node?.dataset?.setting || node?.dataset?.number);}
  _click(event) {
    const target=this._target(event);if(!target || target.disabled)return;
    const action=target.dataset.action;
    if(action==="settings"){this._advanced=!this._advanced;this._render();}
    else if(action==="more"){this._expanded=!this._expanded;this._render();}
    else if(action==="group"){this._group=target.dataset.group;this._expanded=false;this._render();}
    else if(action==="program")this._perform("program",target.dataset.option);
    else if(["start","pause","stop"].includes(action))this._perform(action);
    else if(action==="switch"){const state=stateFor(this._hass,target.dataset.setting);this._perform("setting",{id:target.dataset.setting,choice:state?.state!=="on"});}
    else if(action==="number"){const id=target.dataset.setting,raw=this._drafts.get(id);if(raw!==undefined && String(raw).trim()!=="")this._perform("setting",{id,choice:Number(raw)});}
  }
  _change(event) { const target=event.target;if(target.dataset?.setting && target.tagName==="SELECT")this._perform("setting",{id:target.dataset.setting,choice:target.value}); }
  _settings(entities,fresh) {
    const hass=this._hass;
    return entities.settings.map(id=>{const state=stateFor(hass,id),attrs=state?.attributes || {},kind=id.split(".")[0];const disabled=this._pending || !fresh || !isAvailable(state);const label=t(hass,SETTING_LABELS[attrs.control_key] || "") || attrs.friendly_name || id;let control="";
      if(kind==="select")control=`<select data-setting="${escape(id)}" data-focus="${escape(id)}" aria-label="${escape(label)}" ${disabled?"disabled":""}>${(Array.isArray(attrs.options)?attrs.options:[]).filter(v=>typeof v==="string").map(option=>`<option value="${escape(option)}" ${state.state===option?"selected":""}>${escape(option)}</option>`).join("")}</select>`;
      else if(kind==="switch")control=`<button class="switch" role="switch" aria-label="${escape(label)}" aria-checked="${state?.state==="on"}" data-action="switch" data-setting="${escape(id)}" data-focus="${escape(id)}" ${disabled || !["on","off"].includes(state?.state)?"disabled":""}><span class="switch-dot"></span>${t(hass,state?.state==="on"?"on":"offSetting")}</button>`;
      else if(kind==="number")control=`<div class="number-line"><input type="number" data-number="${escape(id)}" data-focus="${escape(id)}" aria-label="${escape(label)}" value="${escape(this._drafts.get(id) ?? (isAvailable(state)?state.state:""))}" min="${escape(attrs.min)}" max="${escape(attrs.max)}" step="${escape(attrs.step)}" ${disabled?"disabled":""}><button class="number-apply" data-action="number" data-setting="${escape(id)}" aria-label="${escape(t(hass,"apply")+": "+label)}" ${disabled?"disabled":""}>${t(hass,"apply")}</button></div>`;
      return `<div class="setting"><span class="setting-label">${escape(label)}</span>${control}</div>`;
    }).join("");
  }
  _render() {
    if(!this.shadowRoot || !this._hass)return;
    const hass=this._hass,config=this._config,entities=resolveEntities(hass,config),status=stateFor(hass,entities.status),code=statusCode(status),fresh=isFreshStatus(status),running=isRunning(status),program=stateFor(hass,entities.program),rows=programRows(program,entities.appliance,language(hass));
    const groups=[...new Set(rows.map(row=>row.group))],group=groups.includes(this._group)?this._group:groups.find(g=>g!=="care") || groups[0];
    const visible=rows.filter(row=>row.group===group),tiles=this._expanded?visible:visible.slice(0,8),selected=rows.find(row=>row.selected),name=config.name || entities.device?.name_by_user || entities.device?.name || t(hass,entities.appliance);
    const progress=numericValue(stateFor(hass,entities.progress),100),remaining=numericValue(stateFor(hass,entities.remaining)),total=numericValue(stateFor(hass,entities.duration));
    const statusLabel=!isAvailable(status)?t(hass,"offline"):code===null?t(hass,"unknown"):!fresh?t(hass,"stale"):t(hass,["off","ready","paused","running"][code]);
    const feedback=this._pending?{kind:"pending",key:"pending"}:this._feedback;
    const focus=this.shadowRoot.activeElement?.dataset?.focus;
    this.shadowRoot.innerHTML=`<style>${STYLES}</style><ha-card class="${entities.appliance}" aria-label="${escape(name)}"><header class="header"><div class="heading"><p class="brand">DREAME HOME · L9</p><h1 class="title">${escape(name)}</h1><div class="status ${running?"live":""}"><span class="status-dot"></span><span>${escape(statusLabel)}</span></div></div><button class="icon-button" data-action="settings" aria-label="${escape(t(hass,"settings"))}" aria-expanded="${this._advanced}" title="${escape(t(hass,"settings"))}">${icon("settings")}</button></header><div class="layout"><section class="machine-section"><div class="art-stage">${applianceSvg(entities.appliance,running,t(hass,"illustration"))}</div><div class="current-program"><div><span class="eyebrow">${t(hass,"program")}</span><strong class="current-name">${escape(selected?.label || (isAvailable(program)?program.state:"—"))}</strong></div><span class="program-mark">${icon(selected?.group==="care"?"leaf":"shirt")}</span></div><div class="progress-heading"><span>${t(hass,"progress")}</span><span class="progress-value">${progress===null?"—":`${Math.round(progress)} %`}</span></div><div class="track" role="progressbar" aria-label="${escape(t(hass,"progress"))}" aria-valuemin="0" aria-valuemax="100" ${progress!==null?`aria-valuenow="${progress}"`:'aria-valuetext="—"'}><div class="track-fill" style="width:${progress ?? 0}%"></div></div><div class="metrics"><div class="metric"><span class="eyebrow">${t(hass,"remaining")}</span><strong>${duration(remaining,hass)}</strong></div><div class="metric"><span class="eyebrow">${t(hass,"duration")}</span><strong>${duration(total,hass)}</strong></div></div><div class="actions">${["start","pause","stop"].map(action=>`<button class="action ${action==="start"?"primary":action==="stop"?"power":""}" data-action="${action}" ${this._pending || !fresh || !isButtonAvailable(stateFor(hass,entities[action]))?"disabled":""} aria-label="${escape(t(hass,action==="start" && code===2?"resume":action))}">${icon(action==="start"?"play":action==="stop"?"power":"pause")}<span>${t(hass,action==="start" && code===2?"resume":action)}</span></button>`).join("")}</div>${feedback?`<div class="feedback ${feedback.kind}" role="${feedback.kind==="error"?"alert":"status"}" aria-live="polite">${escape(t(hass,feedback.key))}</div>`:""}</section><section class="program-section"><div class="section-heading"><h2>${t(hass,"programs")}</h2><span class="section-caption">${escape(t(hass,entities.appliance))}</span></div>${groups.length>1?`<div class="tabs" role="group" aria-label="${escape(t(hass,"programs"))}">${groups.map(g=>`<button class="tab ${g} ${g===group?"selected":""}" data-action="group" data-group="${g}" aria-pressed="${g===group}">${escape(t(hass,g))}</button>`).join("")}</div>`:""}<div class="program-grid">${tiles.map(row=>`<button class="program-tile ${row.group} ${row.selected?"selected":""}" data-action="program" data-option="${escape(row.option || "")}" aria-pressed="${row.selected}" aria-label="${escape(row.label)}" ${this._pending || !fresh || !isAvailable(program) || !row.selectable?"disabled":""}>${icon(row.icon || (row.group==="care"?"leaf":"shirt"),"tile-icon")}<span class="tile-text"><span class="tile-title">${escape(row.label)}</span>${row.reference!==null?`<span class="tile-sub">${duration(row.reference,hass)} · ${t(hass,"estimate")}</span>`:""}</span>${row.selected?icon("check","tile-check"):""}</button>`).join("")}</div>${visible.length>8?`<button class="more" data-action="more" aria-expanded="${this._expanded}">${t(hass,this._expanded?"less":"more")}${!this._expanded?` (${visible.length})`:""}${icon("chevron")}</button>`:""}${!rows.length?`<div class="empty">${escape(t(hass,config.device_id || entities.status?"noPrograms":"choose"))}</div>`:""}</section></div>${this._advanced?`<section class="advanced"><h2>${t(hass,"advanced")}</h2>${entities.settings.length?`<div class="settings-grid">${this._settings(entities,fresh)}</div>`:`<div class="empty">${t(hass,"noSettings")}</div>`}</section>`:""}</ha-card>`;
    if(focus)this.shadowRoot.querySelectorAll?.("[data-focus]").forEach(node=>{if(node.dataset.focus===focus)node.focus();});
  }
}

const EDITOR_CSS=`:host{display:block;font-family:var(--primary-font-family,system-ui);color:var(--primary-text-color,#222)}.fields{display:grid;gap:16px;padding:5px 0}label{display:flex;flex-direction:column;gap:7px;font-size:13px}input,select{box-sizing:border-box;min-height:43px;border-radius:9px;border:1px solid var(--divider-color,#ccc);background:var(--card-background-color,#fff);color:inherit;padding:10px;font:inherit;width:100%}details{margin-top:3px}summary{cursor:pointer;min-height:35px;font-size:13px}details .fields{padding-top:10px}.description{font-size:12px;color:var(--secondary-text-color,#666);line-height:1.6;margin:0}`;
export class DreameHomeLaundryCardEditor extends (globalThis.HTMLElement || class {}) {
  constructor(){super();this._config={type:TYPE};if(this.attachShadow){this.attachShadow({mode:"open"});this.shadowRoot.addEventListener("change",event=>this._changed(event));}}
  setConfig(config){this._config={...config};this._render();}
  set hass(hass){this._hass=hass;this._render();}
  _changed(event){const key=event.target?.dataset?.key;if(!key)return;const config={...this._config};const value=event.target.value;if(value)config[key]=value;else delete config[key];if(key==="device_id" && value!==this._config.device_id){for(const k of KEYS)delete config[`${k}_entity`];delete config.settings_entities;}this._config=config;this.dispatchEvent(new CustomEvent("config-changed",{detail:{config},bubbles:true,composed:true}));this._render();}
  _render(){if(!this.shadowRoot || !this._hass)return;const hass=this._hass,config=this._config;const devices=Object.entries(hass.devices || {}).filter(([,d])=>MODEL_TYPES[d.model] || d.id===config.device_id);const options=(items,current)=>`<option value="">—</option>${items.map(([value,label])=>`<option value="${escape(value)}" ${current===value?"selected":""}>${escape(label)}</option>`).join("")}`;const rows=entityRows(hass,config.device_id);this.shadowRoot.innerHTML=`<style>${EDITOR_CSS}</style><div class="fields"><label>${t(hass,"device")}<select data-key="device_id">${options(devices.map(([id,d])=>[id,d.name_by_user || d.name || t(hass,MODEL_TYPES[d.model] || "laundry")]),config.device_id)}</select></label><label>${t(hass,"name")}<input data-key="name" value="${escape(config.name || "")}"></label><label>${t(hass,"appliance")}<select data-key="appliance"><option value="">${t(hass,"automatic")}</option>${["washer","dryer"].map(kind=>`<option value="${kind}" ${config.appliance===kind?"selected":""}>${t(hass,kind)}</option>`).join("")}</select></label><details><summary>${t(hass,"overrides")}</summary><div class="fields">${KEYS.map(key=>{const domain=key==="program"?"select.":["start","pause","stop"].includes(key)?"button.":"sensor.";return `<label>${t(hass,key)}<select data-key="${key}_entity">${options(rows.filter(r=>r.entity_id.startsWith(domain)).map(r=>[r.entity_id,stateFor(hass,r.entity_id)?.attributes?.friendly_name || r.entity_id]),config[`${key}_entity`])}</select></label>`;}).join("")}</div></details></div>`;}
}
if(globalThis.customElements){if(!customElements.get("dreame-home-laundry-card"))customElements.define("dreame-home-laundry-card",DreameHomeLaundryCard);if(!customElements.get("dreame-home-laundry-card-editor"))customElements.define("dreame-home-laundry-card-editor",DreameHomeLaundryCardEditor);}
if(globalThis.window){window.customCards=window.customCards || [];if(!window.customCards.some(card=>card.type==="dreame-home-laundry-card"))window.customCards.push({type:"dreame-home-laundry-card",name:"Dreame Home Laundry",description:"Live L9 laundry status, programs and controls",preview:true});}

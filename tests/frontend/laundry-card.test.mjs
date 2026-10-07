import assert from "node:assert/strict";
import {after, test} from "node:test";
import {mkdtempSync, readFileSync, writeFileSync, unlinkSync, rmdirSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {pathToFileURL} from "node:url";

// Import a standalone .mjs copy so these tests also work on Node20.18 without
// package-wide ESM flags. This mock never opens a connection to Home Assistant.
const sourcePath = new URL("../../custom_components/dreame_home/frontend/dreame-home-laundry-card.js", import.meta.url);
const source = readFileSync(sourcePath,"utf8");
const temporary = mkdtempSync(join(tmpdir(),"dreame-card-test-"));
const modulePath = join(temporary,"card.mjs");
writeFileSync(modulePath,source);
after(()=>{unlinkSync(modulePath);rmdirSync(temporary);});

class FakeElement {
  constructor(){this.events=[];}
  attachShadow(){this.shadowRoot={innerHTML:"",activeElement:null,listeners:{},addEventListener(type,fn){this.listeners[type]=fn;},querySelectorAll(){return [];}};return this.shadowRoot;}
  dispatchEvent(event){this.events.push(event);return true;}
}
globalThis.HTMLElement=FakeElement;
globalThis.CustomEvent=class {constructor(type,options){this.type=type;Object.assign(this,options);}};
const registered=new Map();
globalThis.customElements={get:name=>registered.get(name),define:(name,constructor)=>registered.set(name,constructor)};
globalThis.window={customCards:[]};
globalThis.document={createElement:name=>new (registered.get(name))()};
const cardModule=await import(pathToFileURL(modulePath).href);
const {DreameHomeLaundryCard:Card,DreameHomeLaundryCardEditor:Editor,
  resolveEntities,programRows,serviceRequest,isRunning,isFreshStatus,isButtonAvailable,
  numericValue,language,statusCode,appliancePhotoUrl,applianceSvg}=cardModule;

const MODEL="dreame.washer.l9nacn";
const CONFIG={type:"custom:dreame-home-laundry-card",device_id:"synthetic-device"};
function status(raw=1){return {state:["Powered off","Standby","Paused","Running"][raw],attributes:{siid:2,piid:1,raw_code:raw,last_code:0,observation_fresh:true,observed_at:new Date().toISOString()}};}
function fixture(){
  const states={
    "sensor.test_status":status(),
    "sensor.test_progress":{state:"40",attributes:{cycle_metric:"progress"}},
    "sensor.test_remaining":{state:"18",attributes:{siid:2,piid:13}},
    "sensor.test_duration":{state:"45",attributes:{siid:2,piid:12}},
    "select.test_program":{state:"Cotton",attributes:{control_key:"program",raw_code:2,options:["Cotton","Quick wash","Wool care"],program_catalog:[
      {value:2,label:"Cotton",labels:{en:"Cotton",de:"Baumwolle"},group:"wash",option:"Cotton",selectable:true,reference_duration_minutes:90},
      {value:4,label:"Quick wash",labels:{en:"Quick wash",de:"Schnellwäsche"},group:"wash",option:"Quick wash",selectable:true,reference_duration_minutes:15},
      {value:12,label:"Wool care",labels:{en:"Wool care",de:"Wollpflege"},group:"care",option:"Wool care",selectable:true,reference_duration_minutes:30}]}},
    "button.test_start":{state:"unknown",attributes:{control_key:"start"}},
    "button.test_pause":{state:"unavailable",attributes:{control_key:"pause"}},
    "button.test_stop":{state:"unknown",attributes:{control_key:"stop"}},
    "select.test_temperature":{state:"Cold",attributes:{control_key:"temperature",options:["Cold","40 °C"]}},
    "number.test_delay":{state:"30",attributes:{control_key:"delay_time",min:0,max:120,step:30}},
    "switch.test_lock":{state:"off",attributes:{control_key:"child_lock"}},
    "sensor.other_status":status(3)
  };
  const entities=Object.fromEntries(Object.keys(states).map(id=>[id,{entity_id:id,device_id:id.startsWith("sensor.other")?"another-synthetic-device":"synthetic-device"}]));
  const calls=[];
  return {locale:{language:"en"},devices:{"synthetic-device":{id:"synthetic-device",model:MODEL,name:"Laundry test appliance"}},states,entities,calls,async callService(domain,service,data){calls.push({domain,service,data});}};
}
function makeCard(hass=fixture(),config=CONFIG){const card=new Card();card.setConfig(config);card.hass=hass;return card;}

test("card and visual editor register once with HA picker metadata",()=>{
  assert.equal(registered.get("dreame-home-laundry-card"),Card);
  assert.equal(registered.get("dreame-home-laundry-card-editor"),Editor);
  assert.equal(window.customCards.length,1);
  assert.equal(window.customCards[0].name,"Dreame Home Laundry");
  assert.ok(Card.getConfigElement() instanceof Editor);
  assert.equal(Card.getStubConfig(fixture()).device_id,"synthetic-device");
});

test("device discovery uses attributes without registry unique_id or English name guesses",()=>{
  const hass=fixture();
  for(const state of Object.values(hass.states))state.attributes.friendly_name="A deliberately unrelated translated name";
  const found=resolveEntities(hass,CONFIG);
  assert.equal(found.status,"sensor.test_status");
  assert.equal(found.program,"select.test_program");
  assert.equal(found.progress,"sensor.test_progress");
  assert.equal(found.remaining,"sensor.test_remaining");
  assert.equal(found.duration,"sensor.test_duration");
  assert.equal(found.start,"button.test_start");
  assert.deepEqual(found.settings.sort(),["number.test_delay","select.test_temperature","switch.test_lock"]);
  assert.ok(!Object.values(found).includes("sensor.other_status"));
  delete hass.states["button.test_start"].attributes.control_key;
  assert.equal(resolveEntities(hass,CONFIG).start,undefined);
});

test("explicit entities and optional settings overrides work without registry access",()=>{
  const hass=fixture();hass.entities={};
  const config={appliance:"dryer",status_entity:"sensor.test_status",remaining_entity:"sensor.test_remaining",program_entity:"select.test_program",start_entity:"button.test_start",settings_entities:["switch.test_lock","button.test_stop","switch.test_lock"]};
  const found=resolveEntities(hass,config);
  assert.equal(found.appliance,"dryer");
  assert.equal(found.start,"button.test_start");
  assert.deepEqual(found.settings,["switch.test_lock"]);
  assert.equal(serviceRequest(hass,config,"start").service,"press");
});

test("dryer discovery uses its source duration and remaining coordinates",()=>{
  const hass=fixture();hass.devices[CONFIG.device_id].model="dreame.dryer.l9nacn";
  hass.states["sensor.test_remaining"].attributes.piid=11;
  hass.states["sensor.test_duration"].attributes.piid=9;
  const found=resolveEntities(hass,CONFIG);
  assert.equal(found.appliance,"dryer");assert.equal(found.remaining,"sensor.test_remaining");assert.equal(found.duration,"sensor.test_duration");
});

test("drum spins only on fresh explicit Running and stops on every invalid context",()=>{
  assert.equal(isRunning(status(3)),true);
  for(const code of [0,1,2])assert.equal(isRunning(status(code)),false);
  for(const mutate of [
    s=>s.state="unavailable",s=>s.state="unknown",s=>s.attributes.observation_fresh=false,
    s=>delete s.attributes.observation_fresh,s=>delete s.attributes.observed_at,
    s=>s.attributes.observed_at=new Date(Date.now()-181000).toISOString(),
    s=>s.attributes.observed_at=new Date(Date.now()+10000).toISOString(),
    s=>s.attributes.raw_code=true,s=>s.attributes.raw_code=null,s=>s.attributes.raw_code="3",
    s=>s.attributes.last_code=false,s=>s.attributes.last_code=-1,s=>s.attributes.last_reply_null=true
  ]){const s=status(3);mutate(s);assert.equal(isRunning(s),false);}
  const exact={state:"3",attributes:{observation_fresh:true,observed_at:new Date().toISOString()}};
  assert.equal(isRunning(exact),true);
  exact.state="Running";assert.equal(isRunning(exact),false);
  exact.state="running";assert.equal(statusCode(exact),null);
  const hass=fixture();hass.states["sensor.test_status"]=status(3);const card=makeCard(hass);
  assert.match(card.shadowRoot.innerHTML,/class="appliance-art running"/);
  hass.states["sensor.test_status"].attributes.observation_fresh=false;card.hass=hass;
  assert.doesNotMatch(card.shadowRoot.innerHTML,/class="appliance-art running"/);
});

test("unknown HA buttons are available before first press, unavailable buttons stay disabled",()=>{
  const hass=fixture();assert.equal(isButtonAvailable(hass.states["button.test_start"]),true);
  assert.equal(serviceRequest(hass,CONFIG,"start").data.entity_id,"button.test_start");
  assert.equal(serviceRequest(hass,CONFIG,"stop").data.entity_id,"button.test_stop");
  assert.throws(()=>serviceRequest(hass,CONFIG,"pause"),/notAvailable/);
  const html=makeCard(hass).shadowRoot.innerHTML;
  assert.match(html,/data-action="start"\s+aria-label/);
  assert.match(html,/data-action="stop"\s+aria-label/);
  assert.match(html,/data-action="pause"\s+disabled/);
});

test("all card text stays English while select calls retain exact reported option strings",()=>{
  const hass=fixture();hass.locale.language="de-DE";
  assert.equal(language(hass),"en");
  const state=hass.states["select.test_program"];
  state.attributes.options=["Baumwolle","Schnellwäsche","Wollpflege"];
  state.state="Baumwolle";
  state.attributes.program_catalog.forEach((row,index)=>{row.option=state.attributes.options[index];});
  const rows=programRows(hass.states["select.test_program"],"washer","de");
  assert.equal(rows[0].label,"Cotton");assert.equal(rows[1].label,"Quick wash");
  assert.equal(rows[2].group,"care");
  const request=serviceRequest(hass,CONFIG,"program",rows[1].option);
  assert.deepEqual(request,{domain:"select",service:"select_option",data:{entity_id:"select.test_program",option:"Schnellwäsche"}});
  assert.throws(()=>serviceRequest(hass,CONFIG,"program","Quick wash"),/notAvailable/);
  assert.throws(()=>serviceRequest(hass,CONFIG,"program",4),/notAvailable/);
  const card=makeCard(hass),html=card.shadowRoot.innerHTML;
  assert.match(html,/>Cotton</);assert.match(html,/>Quick wash</);
  assert.match(html,/Reference/);assert.match(html,/Remaining/);assert.match(html,/>Start</);
  assert.doesNotMatch(html,/>Baumwolle</);assert.doesNotMatch(html,/Richtwert|Verbleibend|Starten/);
  card._group="care";card._render();
  assert.match(card.shadowRoot.innerHTML,/>Care</);assert.match(card.shadowRoot.innerHTML,/>Wool care</);
  card._advanced=true;card._render();
  assert.match(card.shadowRoot.innerHTML,/Advanced settings/);assert.match(card.shadowRoot.innerHTML,/Child lock/);
});

test("appliance photos inherit only the module cache version and use the right appliance",()=>{
  const moduleUrl="https://ha.example/dreame_home/dreame-home-laundry-card.js?v=0.4.0b3&other=ignored";
  for(const appliance of ["washer","dryer"]){
    assert.equal(appliancePhotoUrl(appliance,moduleUrl),`https://ha.example/dreame_home/${appliance}.png?v=0.4.0b3`);
  }
  assert.equal(appliancePhotoUrl("washer","https://ha.example/dreame_home/card.js"),"https://ha.example/dreame_home/washer.png");
  assert.equal(appliancePhotoUrl("other",moduleUrl),"https://ha.example/dreame_home/washer.png?v=0.4.0b3");
});

test("photo animation turns an identical image inside a fixed drum window, leaving the cabinet still",()=>{
  for(const appliance of ["washer","dryer"]){
    const html=applianceSvg(appliance,true,"Supplied appliance photo");
    assert.match(html,/class="appliance-art running"/);
    assert.match(html,/<image class="appliance-photo"[^>]+\/>\s*<g class="drum-window" clip-path="url\(#[^)]+\)"><g class="drum-rotation"><image class="drum-photo"/);
    const references=[...html.matchAll(/href="([^"]+)"/g)].map(match=>match[1]);
    assert.equal(references.length,2);assert.equal(references[0],references[1]);
    assert.match(references[0],new RegExp(`${appliance}\\.png$`));
    assert.match(html,/<clipPath[^>]+clipPathUnits="userSpaceOnUse"><circle /);
    assert.doesNotMatch(html,/<g class="drum-rotation"[^>]*clip-path/);
    assert.match(html,/--drum-center-x:[\d.]+px;--drum-center-y:[\d.]+px/);
    assert.doesNotMatch(applianceSvg(appliance,false,"Photo"),/class="appliance-art running"/);
  }
  const first=applianceSvg("washer",true,"One"),second=applianceSvg("washer",true,"Two");
  assert.notEqual(first.match(/<clipPath id="([^"]+)"/)[1],second.match(/<clipPath id="([^"]+)"/)[1]);
  assert.match(source,/\.drum-rotation\{transform-origin:var\(--drum-center-x\) var\(--drum-center-y\);transform-box:view-box\}/);
  assert.match(source,/\.appliance-art\{[^}]*overflow:hidden/);
});

test("English default appliance names preserve explicit user customization",()=>{
  const hass=fixture();hass.devices[CONFIG.device_id].name="Waschmaschine";
  assert.match(makeCard(hass).shadowRoot.innerHTML,/<h1 class="title">Washing machine<\/h1>/);
  hass.devices[CONFIG.device_id].name_by_user="My laundry room";
  assert.match(makeCard(hass).shadowRoot.innerHTML,/<h1 class="title">My laundry room<\/h1>/);
  assert.match(makeCard(hass,{...CONFIG,name:"My chosen card title"}).shadowRoot.innerHTML,/<h1 class="title">My chosen card title<\/h1>/);
});

test("unreported metadata options are disabled and duplicate raw-code rows are ignored",()=>{
  const hass=fixture(),state=hass.states["select.test_program"];
  state.attributes.program_catalog.push({value:22,label:"Unreported",labels:{en:"Unreported"},option:"Never reported",selectable:true,group:"wash"});
  state.attributes.program_catalog.push({...state.attributes.program_catalog[0],label:"Duplicate"});
  const rows=programRows(state,"washer");
  assert.equal(rows.filter(r=>r.code===2).length,1);
  assert.equal(rows.find(r=>r.code===22).selectable,false);
  assert.equal(rows.find(r=>r.code===22).option,null);
  assert.throws(()=>serviceRequest(hass,CONFIG,"program","Never reported"),/notAvailable/);
});

test("tile selection submits one select call and never implicitly starts or mutates state",async()=>{
  const hass=fixture(),before=JSON.stringify(hass.states),card=makeCard(hass);
  assert.equal(await card._perform("program","Quick wash"),true);
  assert.deepEqual(hass.calls,[{domain:"select",service:"select_option",data:{entity_id:"select.test_program",option:"Quick wash"}}]);
  assert.equal(JSON.stringify(hass.states),before);
  assert.match(card.shadowRoot.innerHTML,/Waiting for the device/);
  assert.equal(programRows(hass.states["select.test_program"],"washer").find(r=>r.selected).option,"Cotton");
});

test("pending commands block double submission and errors are visible without retry",async()=>{
  const hass=fixture();let finish;
  hass.callService=(domain,service,data)=>{hass.calls.push({domain,service,data});return new Promise(resolve=>{finish=resolve;});};
  const card=makeCard(hass),first=card._perform("start");
  assert.equal(card._pending,true);assert.match(card.shadowRoot.innerHTML,/Sending command/);
  assert.equal(await card._perform("stop"),false);assert.equal(hass.calls.length,1);
  finish();assert.equal(await first,true);assert.equal(card._pending,false);
  hass.callService=async()=>{hass.calls.push("rejected");throw new Error("Synthetic failure; no appliance call");};
  assert.equal(await card._perform("start"),false);
  assert.equal(hass.calls.length,2);assert.equal(card._pending,false);assert.match(card.shadowRoot.innerHTML,/role="alert"/);
  assert.match(card.shadowRoot.innerHTML,/could not be completed/);
});

test("all writes require live status and the target entity's reported availability",()=>{
  const hass=fixture();hass.states["sensor.test_status"].attributes.observation_fresh=false;
  for(const action of ["start","pause","stop","program","setting"])assert.throws(()=>serviceRequest(hass,CONFIG,action,"Cotton"),/notAvailable/);
  hass.states["sensor.test_status"]=status();hass.states["select.test_program"].state="unavailable";
  assert.throws(()=>serviceRequest(hass,CONFIG,"program","Cotton"),/notAvailable/);
});

test("advanced settings validate exact choices, numeric steps and observed switch states",()=>{
  const hass=fixture();
  assert.deepEqual(serviceRequest(hass,CONFIG,"setting",{id:"select.test_temperature",choice:"40 °C"}),{domain:"select",service:"select_option",data:{entity_id:"select.test_temperature",option:"40 °C"}});
  assert.deepEqual(serviceRequest(hass,CONFIG,"setting",{id:"number.test_delay",choice:60}),{domain:"number",service:"set_value",data:{entity_id:"number.test_delay",value:60}});
  assert.deepEqual(serviceRequest(hass,CONFIG,"setting",{id:"switch.test_lock",choice:true}),{domain:"switch",service:"turn_on",data:{entity_id:"switch.test_lock"}});
  for(const choice of [NaN,Infinity,-30,150,31,"60"])assert.throws(()=>serviceRequest(hass,CONFIG,"setting",{id:"number.test_delay",choice}),/notAvailable/);
  assert.throws(()=>serviceRequest(hass,CONFIG,"setting",{id:"select.test_temperature",choice:"90 °C"}),/notAvailable/);
  assert.throws(()=>serviceRequest(hass,CONFIG,"setting",{id:"switch.not-selected",choice:true}),/notAvailable/);
  hass.states["switch.test_lock"].state="unknown";
  assert.throws(()=>serviceRequest(hass,CONFIG,"setting",{id:"switch.test_lock",choice:true}),/notAvailable/);
});

test("dynamic display escapes names/options and never injects metadata markup",()=>{
  const hass=fixture(),payload='<img src=x onerror="alert(1)">';
  hass.devices[CONFIG.device_id].name_by_user=payload;
  hass.states["select.test_program"].attributes.program_catalog[0].labels.en=payload;
  const html=makeCard(hass).shadowRoot.innerHTML;
  assert.doesNotMatch(html,/<img src=x/);assert.match(html,/&lt;img src=x/);
  assert.doesNotMatch(source,/https?:\/\//);
});

test("progress/time invalid values remain unknown without fabricated percentages",()=>{
  for(const raw of ["unknown","unavailable","NaN","Infinity","-1",true,null,"",{},"101"]){assert.equal(numericValue({state:raw},100),null);}
  assert.equal(numericValue({state:"40"},100),40);
  const hass=fixture();hass.states["sensor.test_progress"].state="unavailable";
  const html=makeCard(hass).shadowRoot.innerHTML;
  assert.doesNotMatch(html,/aria-valuenow=/);assert.match(html,/aria-valuetext="—"/);
  assert.match(html,/style="width:0%"/);
});

test("responsive layout follows card width and respects reduced motion",()=>{
  assert.match(source,/container-type:inline-size/);
  assert.match(source,/@container\(min-width:660px\)/);
  assert.doesNotMatch(source,/@media\(min-width:660px\)/);
  assert.match(source,/@media\(prefers-reduced-motion:reduce\)/);
  assert.match(source,/\.running \.drum-rotation\{animation:none\}/);
});

test("editor uses English native selectors and emits composed config changes",()=>{
  const hass=fixture();hass.locale.language="de";const editor=new Editor();
  editor.setConfig({...CONFIG,start_entity:"button.test_start"});editor.hass=hass;
  assert.match(editor.shadowRoot.innerHTML,/Display name/);assert.match(editor.shadowRoot.innerHTML,/data-key="device_id"/);
  editor._changed({target:{dataset:{key:"name"},value:"Synthetic display name"}});
  assert.equal(editor.events.at(-1).type,"config-changed");assert.equal(editor.events.at(-1).composed,true);
  assert.equal(editor.events.at(-1).detail.config.name,"Synthetic display name");
  editor._changed({target:{dataset:{key:"device_id"},value:"new-synthetic-device"}});
  assert.equal(editor.events.at(-1).detail.config.start_entity,undefined);
  assert.equal(editor.events.at(-1).detail.config.device_id,"new-synthetic-device");
});

test("refresh timers are released when card disconnects",()=>{
  const card=makeCard();card.connectedCallback();assert.ok(card._timer);card.disconnectedCallback();assert.equal(card._timer,null);
});

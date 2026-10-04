# Home Assistant / HACS implementation handoff

A read-only HACS beta exists under `custom_components/dreame_home`, with its extracted API backend included. It discovers the whole Dreame Home account and uses exact app-plugin definitions for the L9 washer and dryer. Live cloud reads and verified MQTT succeeded on all three confirmed appliances. Running Home Assistant acceptance, appliance controls and maps remain pending. See [live coverage](live-coverage.md) for the capture evidence and its limits.

## Current validated API coverage

| Appliance | Exact model | Firmware | Initial addressed read plan | Combined non-null observations |
| --- | --- | --- | --- | --- |
| L9 washer | `dreame.washer.l9nacn` | `3017` | 24 source-backed candidates | 27 coordinates |
| L9 Twin Inverter dryer | `dreame.dryer.l9nacn` | `3029` | 17 source-backed candidates | 22 coordinates |
| L10s Ultra Gen 3 | `dreame.vacuum.r5023a` | `1304` | 15 bounded vacuum properties | 15 coordinates |

All three MQTT connections passed TLS verification. Initial L9 read items use the actual device ID, matching their exact plugins. Source definitions and successful runtime observations remain separate evidence: an app subscription establishes a candidate address, while a successful returned value establishes observed device support. These counts cover the captured state; they do not establish every program, phase, event or internal appliance sensor.

The washer's initial plan excludes three source write-only fields: `2.5`, `2.19` and `3.5`. All three appeared in live MQTT, so the beta can expose their observed state. The dryer's final RPC pass returned 23 successful property codes with 20 non-null values; `3.11`, `5.1` and `4.7` were null. Earlier MQTT supplied non-null `5.1` and `4.7` values, giving 22 combined observed coordinates. Only `3.11` remains without a non-null observation. Null RPC replies preserve earlier successful state without advancing its freshness; `last_reply_null` identifies the latest null reply.

The dryer plugin's subscription at `3.11` conflicts with the control UI's night-mode binding at `3.13`. Keep those addresses distinct, and preserve unknown `4.7` without inventing a meaning. Exact catalogs supply friendly names, explicit enum mappings and confirmed units. The pinned dryer plugin selects `ProgramMode_W` through its literal export flag; firmware-dependent default durations do not change enum IDs or labels. The beta does not apply related-model schemas, infer units from names or convert inferred numeric Boolean flags into binary sensors. Unknown enum codes retain their raw scalar state, and translated enums retain `raw_code`.

## Implemented account and device lifecycle

One config entry represents a Dreame Home account and region. An account coordinator performs complete paginated discovery, metadata retrieval and bounded property reads; per-device state and errors remain separate. Device and entity identities retain region and stable device ID, including negative laundry IDs. Metadata provides the exact model, device name and firmware.

Config flow validates local username/password entry and region selection, saves a refresh token rather than the password or access token, persists rotated refresh tokens and handles reauthentication. Home Assistant's managed HTTP session supplies the async transport. MQTT connection work stays outside the HA event loop; subscriptions, tasks and listeners have unload/shutdown paths. Offline tests cover protocol and isolated lifecycle boundaries, with real HA execution still required.

Account API availability, cloud-reported appliance online state and MQTT connectivity remain distinct. A working account listing or broker connection does not prove fresh appliance state. Discovery refreshes every ten minutes, so a stale cloud online flag can delay visibility of a physical power change by up to ten minutes. Property reads run about once a minute for appliances that are not reported offline. Authentication, rate limits and per-device transport failures have separate handling.

## Implemented telemetry entities

The first refresh validates the exact initial read plan. Only successful non-null observations create entities; failed per-property codes remain diagnostic information. Later polling uses successfully observed coordinates, bounded to 240 addresses per refresh, and dynamic MQTT discovery adds previously unseen addresses.

Actual Boolean observations produce `binary_sensor` entities. Other scalar values produce `sensor` entities, with model-specific labels and explicit enum translations where available. The known vacuum battery property receives the battery device class and percentage unit. Laundry state does not acquire guessed energy, water, temperature or recorder statistics classes.

Both exact L9 plugins identify the additional cloud userdata setting `prop.s_auto_upgrade`. The beta reads only this extracted key through `get_device_data` at discovery cadence. A returned value creates an **Automatic firmware updates** sensor, retaining raw wire strings such as `'0'` and `'1'`. Missing values remain absent; no default or write is sent. A setting-specific failure does not affect appliance telemetry availability. Live HTTP acceptance of this setting path remains separate from the completed property/MQTT capture.

Compound values retain their complete original representation in the private property store. Their entity-facing root attributes are redacted. Dictionary leaves and uniquely keyed setting lists receive stable paths; ordinary arrays remain on the root. Leaf expansion is bounded to 256 fields per property and reports truncation. Structured roots are disabled by default to limit duplicated recorder data. Sensitive cached keys and semantic credential values are filtered or redacted before entity projection.

Unknown MQTT messages remain in a bounded private observation store and generate a redacted `dreame_home_message` bus event. This preserves evidence for later event adapters; it is not yet a typed Home Assistant event interface. Diagnostics omit arbitrary text, credentials and raw account envelopes while retaining useful coordinates, codes and coverage gaps.

## Remaining model work

Validate labels, values and timing against the app throughout normal washer and dryer operation: standby, running, pause, completion, faults, dosing warnings and changes of program. Distinguish transient nulls, stale values, missing replies and unsupported fields. Verify the semantics of numeric Boolean flags before changing their platform. Keep unpublished or physically present but cloud-unexposed sensors as explicit coverage gaps.

Source command definitions are extracted separately from state telemetry. The beta never invokes `reportAll`, starts or stops an appliance, or writes settings. Before adding controls, establish the exact model's permitted values, program-dependent ranges, prerequisites and resulting state changes through deliberate live acceptance.

| Verified future capability | Candidate Home Assistant representation |
| --- | --- |
| Boolean setting with validated writes | `switch` |
| Enumerated setting with validated writes | `select`, preserving raw codes |
| Numeric setting with validated limits and units | `number` |
| Meaningful writable string | `text` |
| Action with no inputs | `button` after checking prerequisites |
| Action with inputs | Validated service/action interface |
| Native device events | `event` entity or documented integration event |
| Schedule/time data | `time` or a validated schedule interface |
| Proprietary compound data | Exact model parser and derived entities |

For the vacuum, port capabilities, availability rules, command encoders and model-specific transformations together before introducing a rich `vacuum` entity. The existing 15-property telemetry plan does not reproduce Tasshack's full vacuum integration. Map rendering and vacuum controls remain unimplemented.

## Runtime and release acceptance

The beta has a manifest, config flow, translations, coordinator, sensor platforms, diagnostics, self-contained API backend and `hacs.json`. `tools/build_component.py --archive` produces the local `dist/dreame_home.zip`. Its `dreame_home` domain allows coexistence with the upstream `dreame_vacuum` integration.

Metadata selects Home Assistant Core 2026.9.4 as the baseline. That release requires Python 3.14; Windows Python 3.12 can run protocol and isolated component checks but cannot prove real HA runtime compatibility. GitHub CI runs offline checks on Python 3.12/3.14 and official hassfest/HACS validation. Validate setup, reauth, shared-device access, token rotation, rate-limit retry, state transitions, dynamic entity creation, stale/offline behavior, reconnect and unload/reload against the actual appliances.

The repository is [Ampersandman/Dreame-Home](https://github.com/Ampersandman/Dreame-Home), with actual publishing metadata and local brand assets. HACS can install its default branch through a custom repository; a release is optional. Actual Home Assistant acceptance remains pending. Completing coverage of everything the API exposes requires continued capture of unfamiliar states and events, exact semantic adapters and verification of the resulting HA entities.

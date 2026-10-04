# Dreame Home HACS component design

Design date: 2026-10-04. Version `0.3.0b1` implements the account/telemetry foundation, named L9 controls and a native vacuum entity. The earlier telemetry revision has user-confirmed HACS installation, authentication, discovery and updating values on HA OS 18.3 / Core 2026.9.4. Supplied diagnostics prove complete discovery, valued properties and all three MQTT connections; see the [HA diagnostics review](ha-diagnostics-review.md). Genuine HACS, hassfest and Python 3.12/3.14 offline CI passed for that earlier revision. New controls have no hardware execution evidence. See [appliance controls](appliance-controls.md) and [verification](verification.md) for current implementation and checks; lifecycle acceptance, richer commands and maps remain pending.

The confirmed cloud models are `dreame.washer.l9nacn`, `dreame.dryer.l9nacn` and `dreame.vacuum.r5023a`. Their exact device IDs remain in the ignored local identification report. Treat device IDs as strings, including the negative washer and dryer IDs. No device IDs should be compiled into an integration or public fixture.

## Compatibility baseline and packaging

Use **Home Assistant Core 2026.9.4** as the explicit compatibility baseline. Its released project metadata requires **Python 3.14.2 or newer**. The baseline is supported by source review and the user's initial installation report; the local Python 3.12 environment cannot run that Home Assistant release. GitHub offline CI passed on Python 3.12 and 3.14 without installing Home Assistant. [Released Core metadata](https://github.com/home-assistant/core/blob/2026.9.4/pyproject.toml)

Current configuration-flow examples use `probatio.Schema`. Build the first flow against the chosen release's own schema and selector APIs rather than copying an older `voluptuous` example. A lower Home Assistant minimum or compatibility shim should only be advertised after a separate runtime test. [Official configuration-flow documentation](https://developers.home-assistant.io/docs/core/integration/config_flow/)

Use the independent domain `dreame_home`; preserve coexistence with `dreame_vacuum`. The repository contains one integration under `custom_components/`, with all runtime files in that component directory. Its manifest identifies `Ampersandman/Dreame-Home` for documentation and issues, `@Ampersandman` as code owner, and original local brand assets. HACS uses source installation from the default branch; no release asset is required. [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/)

The extracted `dreamehome-api-extracted` package is not published. The component deterministically vendors its runtime and catalogs under `custom_components/dreame_home/api/`, with relative imports, MIT notices and a source-hash manifest. It does not modify `sys.path` or assume that HACS downloads the top-level `src/` directory. Once the standalone API has a published release, vendoring can be replaced by an exact manifest requirement in a reviewed migration. Current requirements are `pycryptodome==3.24.0` and `paho-mqtt>=2.1.0,<3`; the user reports successful initial setup with this component. Home Assistant already pins paho-mqtt; its custom-integration validator requires a compatible range instead of another exact pin. HTTP uses Home Assistant's provided aiohttp session.

Implemented component layout:

```text
custom_components/dreame_home/
  __init__.py
  manifest.json
  const.py
  config_flow.py
  coordinator.py
  transport.py
  entity.py
  sensor.py
  binary_sensor.py
  control.py
  switch.py
  select.py
  number.py
  button.py
  vacuum.py
  diagnostics.py
  strings.json
  translations/en.json
  api/
    ...protocol runtime, exact generated catalogs and licenses...
hacs.json
tools/build_component.py
tests/test_component_contract.py
tests/test_laundry_adapter.py
tests/test_entity_lifecycle.py
```

Switch/select/button controls and the exact-model native vacuum entity are implemented. The number platform exposes no definitions without proven bounds. Text, typed events and map/image platforms remain future work; an empty platform file does not establish support. Named controls require successful recognized context no older than 180 seconds, exact program constraints and model-specific prerequisites; uncertain failures are never replayed.

## Config entry and authentication

Use one config entry per `(account_type, region, authenticated account UID)`. The account UID obtained after successful authentication gives a stable duplicate-entry key; custom device names and email casing do not define appliance identity. Provide app-account type, region, username and a password selector in the initial flow, then enumerate every device-list page before offering optional device selection.

Save the username, account type, region, account UID, visitor ID and current refresh token in the entry. Keep passwords and access tokens in memory for initial validation only. Home Assistant configuration storage contains secrets and must not be described as encrypted by this integration. The client already accepts an `on_session` callback; use it to persist rotated refresh tokens through `hass.config_entries.async_update_entry`, comparing against the current entry data to avoid unnecessary writes. The callback is synchronous and runs on the asyncio event loop. Do not install a persistence callback on a temporary validation client before an entry exists.

Use a fresh runtime client configured with the saved refresh token after entry creation. If refresh is rejected, raise `ConfigEntryAuthFailed`; reauthentication accepts a new local password, validates that the account key is unchanged, updates the existing entry and reloads it. A network or certificate failure should produce a connection error, not an invalid-password message. [Reauthentication and unique-ID guidance](https://developers.home-assistant.io/docs/core/integration/config_flow/)

Store a typed runtime object in `ConfigEntry.runtime_data`, containing the API client, account coordinator, per-device coordinators, MQTT subscriptions and cleanup callbacks. Do not keep a parallel untyped `hass.data` object for the same runtime. [Official runtime-data guidance](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/runtime-data/)

## Transport, discovery and updates

Implement an aiohttp adapter satisfying the existing `Transport` protocol. Obtain the managed HA session with `async_get_clientsession(hass)`; preserve supplied signed body bytes and headers; use a per-request timeout; refuse credential-bearing redirects; normalize response headers to lowercase; and return the existing `Response` model for non-2xx responses. Keep certificate and hostname verification enabled. Storage downloads use their dedicated unsigned request and never inherit cloud authentication headers.

The first account refresh performs login, complete paginated listing, and bounded metadata reads. A single selected-device metadata failure should mark that device's discovery incomplete without silently dropping it. Newly registered devices should be discovered during later account refreshes and receive entities without a configuration reload. Register dynamic listeners with an unload callback, and track added device/property keys to prevent duplication. [Official dynamic-device pattern](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/dynamic-devices/)

Use an account coordinator for inventory and one device coordinator per appliance. This avoids marking every appliance unavailable when a single device request fails. Keep cloud connectivity, device online state, MQTT connectivity, and each property's freshness distinct. A successful account listing does not prove that a powered-off appliance has current state.

Seed device state only from a verified exact schema, previously observed successful addresses, or an explicitly captured cloud snapshot. Start verified-TLS `DeviceSubscription` instances and feed their callbacks into the matching device coordinator. Poll only readable addresses with an evidence-backed source, in batches of at most 15; retain per-address response codes. Use conservative configurable intervals until live behavior is measured, and honor rate-limit backoff. Account rediscovery can start at ten minutes; appliance polling should not start more frequently than once a minute without evidence that it is necessary and accepted.

The coordinator keeps all entity getters free of network I/O. Push updates use `async_set_updated_data`, and regular polling uses `DataUpdateCoordinator`. Be aware that pushing data resets its polling timer: account rediscovery must remain independent of a busy device's push stream. Catch authentication errors as `ConfigEntryAuthFailed`; temporary device/API errors become `UpdateFailed`. [Official coordinator and push guidance](https://developers.home-assistant.io/docs/integration_fetching_data/)

The extracted MQTT code places callbacks on the asyncio loop and runs socket operations in a worker. Verified TLS and authenticated connections succeeded for all three devices on the EU broker during the standalone capture; the washer and dryer supplied live updates. Supplied HA diagnostics subsequently confirmed all three MQTT clients connected: the washer and dryer property observations originated from MQTT, while the vacuum's observations originated from RPC. The component also includes an HTTP-only mode and separate MQTT status when subscriptions fail. Cleanup cancels credential-refresh tasks, stops/disconnects paho clients, removes listeners and stops device refreshes after unload or partial setup failure. HA reconnect, reauthentication and unload/reload behavior remain to be checked. No retry may replay an ambiguous appliance write or action.

## Property state and model adapters

Keep a device property store independent of HA classes. A property record contains its address, raw value, last successful observation time, last error code, origin (`mqtt`, `rpc`, `cloud_snapshot`), and definition provenance. Store values by `(siid, piid)`, not the read request's `did` correlation field. Preserve missing values, JSON nulls, per-property failures and unknown methods as distinct conditions. Persist only a bounded known-address/definition catalog needed for startup discovery; do not persist entire appliance histories or account envelopes.

Definition evidence has separate levels:

| Evidence | Automatic behavior |
| --- | --- |
| Exact model and version schema, successful read/notify | Typed state entity with that verified metadata |
| Exact model schema, unobserved property | Retain definition; do not claim current device support |
| Unfamiliar address with successful observation | Neutral read-only entity or structured diagnostic value |
| Related model or debug candidate only | Research evidence; no automatic property queries or controls |
| Explicitly reviewed model command encoder | Named control with enforced prerequisites; report live execution acceptance separately |

The L9 washer and dryer have no exact public MIoT schema in the saved index. `dreame.washer.r1111` and `r1112` remain unrelated research candidates. `laundry.py` supplies exact plugin state definitions and `laundry_controls.py` supplies bounded encoders with program restrictions. A value or control on the washer must not be copied to the dryer merely because both products are called L9.

The vacuum adapter may draw on the pinned `r5023a` capability row and protocol/property catalogs. It must port model-specific remapping, packed-state parsing and command encoders explicitly; generated upstream source expressions are documentation, not executable runtime configuration. A naive loop over 370 global vacuum properties will query capabilities that the vacuum may not support and does not recreate the 245 upstream entity definitions. Generic observed telemetry is useful while the complete vacuum adapter is developed, but it is not a substitute for the upstream map decoder and behaviors.

## Entity identity and coverage

Use stable unique IDs such as `dreame:eu:<did>:prop:<siid>:<piid>:state`, with a distinct `control` suffix when a read-only state and a control are both useful. Negative IDs remain intact. Device registry identifiers use `(DOMAIN, account_type + region + did)`. Product names, custom names, schema versions and entity display labels may change without changing IDs. If multiple account entries share an appliance, apply a documented deduplication rule so the same property is not registered twice.

Expose unknown integer or floating-point values as unclassified read-only sensors without invented units or statistics classes; expose actual JSON booleans as binary sensors. Retain an unknown enumeration's raw value until the value-list is verified. Do not silently reinterpret `0`/`1` integers as booleans. Large strings, dictionaries, lists and packed blobs require a bounded structured view or a verified parser rather than an oversized sensor state. Add scalar JSON-path entities only where the payload format and path stability are demonstrated.

Assign temperature, duration, energy, water or other HA classes only after confirming the schema unit, scaling and accumulation behavior. In particular, energy/water totals, per-cycle amounts and remaining consumption estimates require different statistics behavior. Entity getters return memory state; numerical classes require compatible values and units. [Official sensor rules](https://developers.home-assistant.io/docs/core/entity/sensor/)

Each device's coverage report should enumerate discovered definitions, observed property addresses, unsupported/error addresses, exposed state entities, reviewed controls, events, compound payloads and unresolved meanings. Define the target as **all observable fields made accessible, with friendly typed entities where their meaning is verified**. Neither matching a device ID nor observing a few MQTT updates proves complete API coverage. Events and controls that never occur during a recording remain explicit coverage gaps.

Unknown telemetry defaults to diagnostic entities with neutral names. Do not convert an unknown writable property into a control merely because its value happens to look like a setting. Once definitions are verified, writable booleans map to switches, enums to selects, ranged numbers to number entities, and no-input actions to buttons; action inputs must be validated against the actual definition. Preserve exact raw enum values when translating labels. Do not run appliances merely to test controls without a separate deliberate acceptance step.

Diagnostics should contain exact model, firmware, schema provenance, coordinates, per-property result codes, transport status and coverage gaps. Apply the existing recursive redactor, then an allowlist for network/account metadata and unknown string fields; privacy redaction is best effort and must be tested against recorded fixtures. Exclude all credentials, session UID, device IDs, custom names, LAN secrets and signed URLs. [Official diagnostics guidance](https://developers.home-assistant.io/docs/core/integration/diagnostics/)

## Validation and acceptance

The local environment can run offline protocol tests, pure property-store/adapter tests, deterministic vendoring checks, JSON checks, source compilation and packaging checks. The user reports successful HACS installation, authentication, discovery of all three devices and updating values on HA OS 18.3 / Core 2026.9.4. Supplied diagnostics from Core 2026.9.4 / Python 3.14.6 confirm complete account discovery and a successful API update, with all three devices present, reported online and MQTT connected. Metadata, property-read and cloud-data errors were absent; no dropped or truncated observations were reported. No agent-operated HA runtime test was performed.

The diagnostic snapshot has 27 usable washer property roots, 22 usable dryer roots among 23 recorded coordinates, and 15 vacuum RPC roots. Dryer `3.11` has no observed value; `4.7` remains a source-unknown coordinate. These are property coordinates, not actual HA entity counts. No compound property values occur in this snapshot, so compound leaves and their metadata remain unvalidated. Configured cloud-data keys and the cached-key count do not establish that the firmware-update setting returned a value. See the [HA diagnostics review](ha-diagnostics-review.md) for these evidence boundaries. Cycle, recorder and full per-property semantic acceptance remain outstanding.

Genuine GitHub HACS validation, hassfest and offline Python 3.12/3.14 CI passed for the published repository. Those CI jobs do not install Home Assistant. A Linux Python 3.14.2+ job against the exact HA release would provide automated framework integration tests; a mocked HA-module shim does not replace importing and running the real HA platform.

The initial authentication and three-device discovery portions below have user-reported confirmation; supplied diagnostics also confirm initial HA MQTT connectivity and the observed property roots. The remaining details still require acceptance evidence:

1. Initial credential validation, complete listing, stable duplicate-account detection, saving only a refresh token, and rotation persistence.
2. Authentication rejection starts reauth; a transient HTTP/TLS error retries setup; reauth preserves identity and changes the existing entry only.
3. All three confirmed models remain discoverable. Negative IDs, shared ownership and unknown models survive pagination and metadata merging.
4. A laundry device receives no vacuum or unrelated debug-schema queries. New observed addresses create one stable neutral entity; repeated messages do not create duplicates.
5. Successful values, nulls, unsupported codes, missing replies and stale values have distinct state/availability outcomes. One device failure does not mark the other devices unavailable.
6. MQTT push, credential rotation, broker rejection, reconnect and HTTP-only operation preserve the correct owner topic and account identity.
7. A newly registered device appears without reloading the entry. Removed devices are handled deliberately rather than deleting registrations on one incomplete response.
8. Failed setup and repeated unload/reload leave no paho threads, refresh tasks, listeners or dangling entity callbacks.
9. Confirmed writable ranges/enums and action inputs validate correctly; ambiguous write failures are never automatically replayed.
10. Diagnostics from sanitized washer, dryer and vacuum fixtures contain no original secrets or signed network endpoints.

Further live acceptance needs read-only observations of the actual L9 washer/dryer and vacuum beyond the reported initial setup. Record idle states and ordinary app-driven state changes to identify status, remaining time, door/lock, program, temperature and consumable fields only where the devices actually expose them. Do not infer a sensor from the product's marketing description. Compare app-visible values to raw API values before assigning friendly metadata, and report cloud fields that remain unidentified. Full control and map support require their own subsequent acceptance evidence.

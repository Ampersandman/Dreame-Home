# Home Assistant diagnostic review: 2026-10-06

This review concerns a supplied diagnostic from integration `0.3.0b1`. The user clarified that it was downloaded **after the laundry cycles had ended**. It must not be treated as a running-cycle capture. This report contains sanitized technical findings; the full diagnostic, account identifiers, file identifiers, runtime inventory and private property values are not reproduced.

The [2026-10-04 review](ha-diagnostics-review.md) remains separate historical evidence: the earlier telemetry beta had fresh laundry values, successful account discovery and MQTT connectivity for all three exact models. The later snapshot does not revoke that result.

## What the later snapshot shows

Account discovery is complete and the last coordinator API update succeeded. All three devices are present and their MQTT clients are connected. This establishes broker connectivity, not fresh appliance state or a live property write.

| Exact model | Property rows | Retained value coverage | State at download |
| --- | --- | --- | --- |
| `dreame.washer.l9nacn` | 27 | 27 valued roots | Cloud offline; retained run status `2.1=0` (Power off); values older than the 180-second command limit |
| `dreame.dryer.l9nacn` | 23 | 22 valued roots; `3.11` unvalued | Cloud offline; retained run status `2.1=0` (Power off); values older than the 180-second command limit |
| `dreame.vacuum.r5023a` | 167 | 145 coordinates have source mappings; 22 remain neutral | Cloud online with recent RPC observations; the snapshot also retains older MQTT observations |

The laundry devices record property-read `ApiError` while offline. With the post-cycle clarification, their power-off state and retained old values are consistent with switching off after completion. This snapshot does not demonstrate stalled running telemetry, a wrong control mapping or an online-recovery failure. Source control rules correctly disable commands for offline/stale context. MQTT connectivity alone cannot override those rules.

These are property-coordinate counts, not Home Assistant entity totals. A mapped coordinate means source display metadata is available; it does not mean every write or operating state has been accepted. Unknown vacuum coordinates retain neutral labels. Dryer `4.7` remains source-unknown, and the `3.11`/`3.13` night-mode ambiguity remains unresolved for writes.

## Controls: support and availability

Exact source encoders define 13 washer writable property coordinates and 9 dryer writable property coordinates, plus start/resume, pause and power-off buttons on each. Their payloads and options remain bound to their exact models. The native vacuum has source-backed named commands. See [appliance controls](appliance-controls.md).

The supplied diagnostic records no current command status. A null `last_command_status` does not prove that the user never used controls, nor does it establish an accepted write. Accepted commands require acknowledgement and subsequent actual-state evidence; that acceptance is not established by this file.

Version `0.3.0b2` diagnostics separate `supported_commands` from `available_commands`, with `gateway_ready` and a fresh-coordinate count. This replaces the misleading static `controls_enabled: false` coverage flag. A source-supported control can be unavailable because the device is off, required state is stale, a program restricts the setting, authorization is missing or a status/phase guard applies.

## Changes justified independently of this snapshot

Code review proved a candidate-retry defect: after an initial empty/null/error response, the old one-shot read plan could stop querying an exact known candidate until a new MQTT value or reload. A previously valued address could also stop being polled after an error. `0.3.0b2` reserves known candidates on every eligible refresh and rotates other valued exact-model addresses within the 240-address budget. Unknown models receive no guessed seed addresses. The existing cloud-online gate, cooldowns, coordinate correlation, per-device lock and write validation remain unchanged. The offline tests exercise recovery; the post-cycle snapshot is not evidence that this defect occurred during the user's cycles.

The version also adds source-backed L9 **Cycle progress** and **Elapsed cycle time**, corrects dryer **Program duration**/ **Remaining time** labels and minute units, and preserves existing property identities. See [cycle sensors](cycle-progress.md) for coordinates, formulas and unknown-state rules.

Vacuum cleaning time/area receive source units and labels. The 22-candidate vacuum seed includes cleaning progress `4.63` and mop-drying progress `4.64`. Neither coordinate is present in this diagnostic, so acceptance of those reads and live progress values remains unverified. No value is inferred from their absence.

## Remaining evidence

Fresh running-cycle snapshots and app comparisons are needed for the new time/progress sensors, including AI estimates, revisions and completion/refresh phases. Accepted setting/action writes, reload/unload, reauthentication, stored-token restart, reconnect and recorder behavior remain separate checks. The configured cloud-userdata keys and cache counts do not establish an accepted automatic-firmware-update value. No map functionality is claimed. See [verification](verification.md).

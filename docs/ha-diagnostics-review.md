# Home Assistant diagnostic review

Reviewed on 2026-10-04. Evidence is an integration diagnostic supplied after the user installed through HACS and confirmed values updating on all three appliances. The diagnostic identifies Home Assistant OS, Core 2026.9.4 and Python 3.14.6. The complete original file stays local under ignored `ha-diag/`; this report contains only selected technical findings.

## Account, transport and property coverage

Account discovery is complete and the last coordinator API update succeeded. All three devices are present, cloud-online and connected to MQTT. No metadata, property-read or cloud-userdata errors are reported at the time of the snapshot. No observations were dropped or reported as truncated.

| Appliance | Property rows | Rows with a value | Last value source | Initial read result |
| --- | --- | --- | --- | --- |
| L9 washer (`dreame.washer.l9nacn`) | 27 | 27 | MQTT for all 27 | Complete |
| L9 dryer (`dreame.dryer.l9nacn`) | 23 | 22 | MQTT for all 22 valued rows | Partial: 16 of 17 initial candidates have values |
| L10s Ultra Gen 3 (`dreame.vacuum.r5023a`) | 15 | 15 | RPC for all 15 | Complete |

All recorded property result codes are zero. Laundry values were last successfully observed within 0–4 seconds of the diagnostic; vacuum values were 21 seconds old. These ages describe one snapshot, not a measured polling interval or a continuous freshness guarantee. A connected vacuum MQTT client does not establish a vacuum push: the recorded vacuum values originated from RPC.

These are property-coordinate counts, not Home Assistant entity totals. Connectivity entities and eligible cached values can add entities; disabled structured roots and Boolean/scalar platform selection can also affect totals. All valued property roots in this snapshot are integers, so compound-field expansion was not exercised.

## Dryer gap and source ambiguity

The washer supplies a value for every one of its 27 exact source definitions. The dryer supplies 21 of its 22 source-defined coordinates plus the additional, source-unknown `4.7`, giving 22 usable coordinates overall.

Dryer `3.11` has a code-zero row but no value. Its source subscription name suggests night mode, while the app's actual night-mode control binds to `3.13`, which has a value. This is the same ambiguity found in the exact model plugin and earlier standalone capture. Preserve both addresses separately; the missing value does not justify manufacturing a sensor state or relabelling `4.7`. The dryer's partial initial-read result is therefore accurate.

## Limits and next checks

The snapshot demonstrates real Home Assistant discovery, usable property values and MQTT connectivity for all three models, including MQTT-originated laundry observations. It shows no runtime failure requiring a code fix.

The diagnostics list the configured `prop.s_auto_upgrade` cloud key and cache counts, but do not include accepted cloud-setting identities or values. A missing error alone does not establish that the automatic firmware-update setting was returned. Its exact returned value remains unverified by this file.

Normal-cycle state changes, completion/door events, optional properties, unknown enum states, reconnect, token rotation, reauthentication, stored-token restart, reload/unload and recorder behavior still require acceptance. The vacuum currently starts from 15 addressed telemetry properties; this is a baseline, not the complete upstream vacuum feature set. Controls, writable entities and maps remain unimplemented.

The privacy review found no account credentials, device IDs, MAC addresses, assigned device names or account UID in the supplied diagnostic. Home Assistant's wrapper includes runtime information and installed-integration metadata, so the full file remains private. No property values, environment inventory or diagnostic filename identifiers are included in this report.

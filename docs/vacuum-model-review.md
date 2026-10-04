# L10s Ultra Gen 3 observation adapter

The account identifies this vacuum as `dreame.vacuum.r5023a`. It occurs in the
upstream model table pinned at commit
`9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb`, with model row `[0, 0, 104, 5]`:
capability table 104 and map key table 5. This identifies the model's upstream
adapter. It does not prove that every property in the shared vacuum catalog
exists on this particular firmware.

The common property mapping is declared at
[device.py:302](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/device.py#L302).
No per-model coordinate remap for `r5023a` was found. The capability loader uses
both the model table and successful property observations, including whether
the self-wash base, automatic emptying, drainage, and mop-related properties
actually exist. It also uses the numeric firmware suffix for capability gates.
See
[types.py:3100](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/types.py#L3100).

The model's static capability row includes `NEW_STATE`, `GEN5`,
`MOP_PAD_LIFTING`, `MOP_PAD_LIFTING_PLUS`, `AUTO_EMPTYING`, `WETNESS_LEVEL`,
`MOPPING_SETTINGS`, `CLEANGENIUS`, `SMART_MOP_WASHING`, `SIDE_REACH`,
`AUTO_ADD_DETERGENT`, `WATER_TANK_DRAINING`, and map-format flags. These are
adapter hints; actual support and meaningful entity availability still require
the device's responses. This table cannot be applied to the L9 washer or dryer.

## Bounded initial reads

`dreamehome.observations.VACUUM_INITIAL_READ_PAIRS` selects 15 explicit
coordinates from the upstream map. They are a starting plan for known vacuum
models. Treat individual response codes as authoritative and do not repeatedly
poll unsupported coordinates.

| Coordinates | Upstream property |
| --- | --- |
| 2.1 / 2.2 | State / error |
| 3.1 / 3.2 | Battery percentage / charging status |
| 4.1 / 4.2 / 4.3 | Status / cleaning time / cleaned area |
| 4.7 | Task status |
| 4.20 | Relocation status |
| 4.25 | Self-wash base status |
| 4.35 | Warning status |
| 4.52 / 4.53 | Mop in station / mop pad installed |
| 15.3 / 15.5 | Dust collection / automatic emptying status |

The upstream routine batches at most 15 properties over Dreame cloud. Item
`did` values are correlation identifiers, while the outer RPC `did` selects
the appliance. Upstream passes local property enum numbers as those correlation
identifiers. The extracted generic client passes `siid.piid` strings. Firmware
acceptance of those generic identifiers must be established by a live read;
this review alone cannot establish it. See
[device.py:802](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/device.py#L802).

A full catalog sweep would include write-only, response-only, factory test,
streaming, remote-control, and debug coordinates that upstream deliberately
omits from its default reads. The normal discovery path should use observed
coordinates, an exact appliance schema, and a small initial vacuum plan instead
of probing every coordinate or applying a vacuum schema to laundry appliances.

## Packed and compound values

`4.23` (`CLEANING_MODE`) is a packed integer on self-wash models. The upstream
splitter derives the low one or two bits, `(value >> 8) & -769`, and
`value >> 16`. Its interpretation depends on mop lifting, wetness capabilities,
mop installation, and wash interval mode. A direct numeric-to-cleaning-mode
enum lookup would produce incorrect entities. See
[device.py:2405](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/device.py#L2405)
and
[device.py:990](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/device.py#L990).

`4.50` (`AUTO_SWITCH_SETTINGS`) is a JSON string containing a list of
`{"k": "setting-key", "v": value}` records or a single such object. Known keys
are retained in `enums.json` under `DreameVacuumAutoSwitchProperty`; examples
include `AutoDry`, `SmartHost`, `ExtrFreq`, and `SbrushExtrSwitch`. Unknown keys
must survive and semantic entity IDs should use the setting key, since list
ordering can change. Other compound values include AI configuration, DND tasks,
off-peak charging, shortcuts, and map lists. They need their own verified
semantics rather than generic numeric enum conversion. See
[device.py:1555](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/device.py#L1555).

## Standalone normalizer

`ObservationStore` has no network or device-write operations. It merges:

- `merge_properties(rows)`: read results, including per-item failures.
- `merge_cached(payload)`: `property` JSON metadata, property dictionaries such
  as `prop.2.1`, `2.1`, nested `props`/`properties`/`data`, and property rows.
- `merge_push(message)`: wrapped or unwrapped `properties_changed` messages;
  unknown methods, events, and malformed updates remain in a bounded event list.
- `snapshot()`: independent private observation data.

Snapshot `properties` maps `siid.piid` to a record with `siid`, `piid`, original
`value`, `source`, `code`, `last_code`, `last_source`, `last_item`, and
`observed_count`. Successful reads of unknown coordinates remain observable.
Failed reads preserve the previous successful value and retain the new failure
in `last_code` and `last_item`. Vacuum catalog names appear only for exact known
vacuum models; the same coordinates on the L9 washer and dryer receive no
vacuum labels.

Compound JSON objects and arrays preserve the original value and add a decoded
`compound` plus a bounded `compound_fields` scalar projection using JSON Pointer
paths. Paths describe structure only and are not a verified appliance schema.
Decoding and projection limits are explicit through `decode_error` or
`compound_truncated`. Event, property, and unknown cached-key overflow counts
are explicit in the snapshot. No source lambdas or extracted implementations
are executed.

Snapshots may contain account/device identifiers, serial numbers, signed URLs,
and private event fields. Pass them through the existing privacy redactor before
sharing diagnostics. Complete original envelopes of recognized property push
messages should be captured separately if needed; the normalizer retains those
property rows, while keeping complete envelopes for unknown methods and events.

The normalizer tests use fabricated vacuum and laundry data and verify unknown
coordinate retention, failure handling, compound values, snapshot isolation,
and bounded collections. They do not establish live property/MQTT support.

# HACS repository and releases

The published integration repository is [Ampersandman/Dreame-Home](https://github.com/Ampersandman/Dreame-Home). It contains one integration at `custom_components/dreame_home/`, including its vendored API and exact-model catalogues. The user reports successful installation through HACS, account authentication, discovery of all three appliances and updating values for each on HA OS 18.3 / Core 2026.9.4. Supplied HA diagnostics confirm complete account discovery, observed property roots and all three MQTT clients connected on Python 3.14.6; see the [HA diagnostics review](ha-diagnostics-review.md). HACS source installation works without a release; publishing one is optional. This follows the [HACS integration repository requirements](https://www.hacs.xyz/docs/publish/integration/).

## Install through HACS

1. Open HACS, select the menu in the top right, then **Custom repositories**.
2. Add `https://github.com/Ampersandman/Dreame-Home` and choose **Integration**.
3. Open **Dreame Home**, download it, and restart Home Assistant.
4. Under **Settings → Devices & services → Add integration**, select **Dreame Home**. Enter the Dreame Home account credentials and its region; choose **eu** for the validated European account.

These are the [official custom repository steps](https://www.hacs.xyz/docs/faq/custom_repositories/). Default-list submission is a separate process and is not required to add this repository. With no releases, HACS downloads the default branch. Once releases exist, its version selector also offers releases; beta releases may require enabling prereleases in HACS.

`hacs.json` uses the standard source repository layout. It does not enable `zip_release` or require a release filename. All runtime files remain committed under `custom_components/dreame_home/`, so the optional release asset never becomes a prerequisite for installation.

## What CI checks

[validate.yml](../.github/workflows/validate.yml) runs on pushes, pull requests and manual requests. Genuine GitHub offline CI passed on Python 3.12 and 3.14, together with the HACS and hassfest jobs. The test jobs install the extracted client with its MQTT dependency, check installed dependencies, verify that the committed vendored backend matches `src/dreamehome`, build the component ZIP, and run the offline unit suite. Tests use synthetic responses and source catalogues; no account credentials, device captures, APKs or research checkouts are needed.

Separate jobs run the official [HACS validation action](https://www.hacs.xyz/docs/publish/action/) with category `integration` and [Home Assistant hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest/). No HACS checks are ignored. Local brand assets are committed at `custom_components/dreame_home/brand/icon.png`, which the [current HACS brand validator](https://github.com/hacs/integration/blob/main/custom_components/hacs/validate/brands.py) accepts. Enable repository issues and set a description and topics on GitHub so those repository checks can pass.

Actions are pinned to verified source commits. The official HACS and hassfest action wrappers still pull their upstream validator container images by tag; these jobs consequently exercise the current validators. CI does not install Home Assistant. Separately, the user reports successful initial installation, authentication, discovery and updating telemetry on Core 2026.9.4. Supplied diagnostics show 27 usable washer property roots, 22 usable dryer roots among 23 recorded coordinates and 15 vacuum RPC roots, with all three devices present, reported online and MQTT connected. No metadata/read/cloud-data errors, drops or truncation were reported. These counts are property coordinates rather than HA entity totals, and this snapshot has no compound property values. Configured cloud-data keys and cached-key counts do not confirm returned cloud userdata values. Full semantic coverage, reauthentication, reload/unload, recorder and cycle behavior remain unconfirmed; controls and maps were not validated.

## Publish an optional release

1. Update `custom_components/dreame_home/manifest.json` to the intended version and commit the change. Regenerate the vendored backend when its source changes with `python tools/build_component.py`; commit the resulting `api/` files too.
2. Wait for validation to pass on the commit being released.
3. Publish a GitHub release targeting that commit, with a tag exactly equal to the manifest version or with one leading `v`, for example `v0.3.0b1`. Mark beta versions as prereleases.
4. [release.yml](../.github/workflows/release.yml) checks out that tag, rejects a version mismatch, verifies the vendored backend, builds `dist/dreame_home.zip`, and runs offline tests before uploading the asset to the existing release.

The ZIP contains integration files directly at its root (`manifest.json`, `__init__.py`, `api/`, and so on). It excludes local credentials and research assets. The workflow is triggered only when a release is published; it does not create releases or publish anything during pull request validation. Only its release job has repository write permission, and the upload step receives the GitHub token. A rerun uses [`gh release upload --clobber`](https://cli.github.com/manual/gh_release_upload) to replace an asset with the same name; it rebuilds from the same release tag.

Keep the public repository limited to integration code, source API code and catalogues, tests, required build helpers, documentation and licenses. Account captures, tokens, passwords, device identifiers, app binaries and local environments must remain outside the published files. The reusable app protocol constants and public trust certificate are part of the client; they are not account credentials.

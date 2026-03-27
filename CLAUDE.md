# CLAUDE.md

## Project

- Home Assistant **Custom Integration** (NOT an addon) for controlling blinds/rollos via a jbmedia Light Manager Air
- Repo: `uk05de/ha-lightmanager-blinds`
- Replaces fragile YAML-based config (template covers, input_numbers, timers, scripts)
- HACS compatible
- Installed in `custom_components/lightmanager_blinds/`

## Architecture

- Custom HA integration with config flow (UI-based configuration, no YAML)
- Native Cover entities with RestoreEntity for position persistence
- HTTP REST commands to Light Manager Air at `http://{host}/control`
- Position tracking via runtime calculation (no position sensor feedback from motors)
- Webhook endpoint for external control (physical remote -> LM Air -> webhook -> HA)

## Key Files

- `custom_components/lightmanager_blinds/__init__.py` -- Integration setup, webhook registration
- `custom_components/lightmanager_blinds/config_flow.py` -- Config flow (add hub) + options flow (add/remove blinds)
- `custom_components/lightmanager_blinds/cover.py` -- Cover platform with position tracking
- `custom_components/lightmanager_blinds/lm_air.py` -- HTTP client for Light Manager Air
- `custom_components/lightmanager_blinds/const.py` -- Constants
- `custom_components/lightmanager_blinds/strings.json` -- German UI strings
- `custom_components/lightmanager_blinds/manifest.json` -- Integration metadata (version here!)
- `hacs.json` -- HACS metadata

## Light Manager Air

- jbmedia Light Manager Air at 192.168.2.104
- HTTP POST to `/control` with body: `cmd=idx,{lm_air_id}`
- Each blind has 3 LM Air IDs: up, down, stop
- Example: Kueche (Küche) = 317 (up), 318 (down), 319 (stop)

## Config Flow

- Step 1: Enter LM Air IP -> tests connection -> creates integration
- Options flow: menu with "add blind" and "remove blind"
- Per blind: name, LM Air ID up/down/stop, runtime up (seconds), runtime down (seconds)
- Blinds stored in `entry.options["blinds"]` as list of dicts

## Cover Entity

- Position 0=closed, 100=open
- Position calculated from movement direction x elapsed time / total runtime
- Asymmetric runtimes (up and down can differ)
- RestoreEntity: position survives HA restarts
- Auto-stop via asyncio task after calculated duration
- IMPORTANT: `_auto_stop` must set `self._move_task = None` BEFORE calling `_stop_move` (otherwise it cancels itself)
- open/close commands always sent regardless of current position (position is calculated, not measured -- blocking would prevent manual correction)

## Webhook

- Registered at `/api/webhook/rollo_webhook`
- Called by Light Manager Air when physical remote is used
- URL format: `/api/webhook/rollo_webhook?cover=kueche&action=down`
- Matches by slug (`kueche`) or display name (Küche)
- `external=True` flag: tracks position WITHOUT sending command to LM Air (remote already did it)
- Webhook ID `rollo_webhook` matches the old YAML-based system -- no LM Air reconfiguration needed

## Slug Generation

- Name -> lowercase, spaces -> `_`, ä -> ae, ö -> oe, ü -> ue, ß -> ss
- Used for: entity unique_id, device identifier, webhook matching, covers registry key

## 8 Blinds (from old config, for reference)

- Wohnzimmer Links: 305/306/307, 20s up, 14s down
- Wohnzimmer Raffstore: 311/312/313, 20s up, 19s down
- Wohnzimmer Terrassentür: 314/315/316, 18s up, 11s down
- Küche: 317/318/319, 20s up, 15s down
- Kinderzimmer Links: 323/324/325, 20s up, 14.5s down
- Ankleide: 326/327/328, 20s up, 15s down
- Schlafzimmer Links: 329/330/331, 19s up, 14s down
- Masterbad: 332/333/334, 19s up, 14s down

## Important Notes

- This is a CUSTOM INTEGRATION, not an addon. Version is in `manifest.json`, not `config.yaml`.
- Old YAML configs are in the repo root but gitignored -- kept locally for reference only.
- HA restart required after code changes (custom integration limitation).
- Updates via HACS after adding as custom repository.
- The user prefers Klarname (e.g. Küche not kueche) for blind names.
- Position is not reliable after power loss or remote use without webhook -- commands should never be blocked based on calculated position.

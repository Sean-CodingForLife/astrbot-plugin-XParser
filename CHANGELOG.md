# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-07-08

### Added

- Initial AstrBot plugin implementation for X/Twitter tweet parsing.
- Automatic tweet URL detection for `x.com` and `twitter.com` status links.
- `/xparse <tweet-url>` command.
- X API v2 integration with Bearer Token and OAuth 1.0a support.
- Cookie GraphQL fallback for API quota or permission failures.
- Tweet text, author, timestamp, metrics, image, video, and GIF extraction.
- Image download and compression pipeline.
- OneBot `base64://` image sending for NapCat/aiocqhttp deployments.
- NapCat Stream API upload support for cross-container video transfer.
- Streamed video sending as OneBot video messages.
- File upload fallback when video message sending fails.
- Chinese configuration descriptions for AstrBot WebUI.
- Cache TTL cleanup on plugin startup/reload.
- Text and image merged sending option to reduce chat noise.

### Fixed

- Fixed invalid plugin module name in `metadata.yaml`.
- Added `repo` metadata so AstrBot can update the plugin from GitHub.
- Fixed `/xparse` command handler accidentally becoming an async generator.
- Avoided duplicate parsing when `/xparse` command messages are also seen by the auto parser.
- Added raw OneBot action fallback for adapters exposing `call_action`, `call_api`, or `api`.

### Changed

- Video transfer now prioritizes Stream API video message delivery before file fallback.
- README expanded with architecture, configuration, troubleshooting, and roadmap notes.

### Known Issues

- AstrBot local cache cleanup currently runs on plugin startup/reload, not as a background scheduled task.
- NapCat Stream temporary files are not yet actively cleaned by the plugin after successful sending.
- In `auto` mode, NapCat deployments may still try local video sending before Stream fallback.

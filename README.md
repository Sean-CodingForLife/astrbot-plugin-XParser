# astrbot-plugin-XParser

XParser is an AstrBot plugin for parsing X/Twitter tweet links and forwarding
tweet text, images, videos, and GIFs to QQ through NapCat.

The plugin is designed for deployments where AstrBot and NapCat run in separate
containers without a shared volume.  Media is downloaded inside the AstrBot
container, then transferred to NapCat through NapCat's Stream API.

## Features

- Auto-detects `x.com/.../status/...` and `twitter.com/.../status/...` links.
- Provides `/xparse <tweet-url>` for manual parsing.
- Extracts tweet text, author, timestamp, metrics, images, videos, and GIFs.
- Uses NapCat `upload_file_stream` for large video/file transfer.
- Falls back to normal AstrBot media components or source URLs when needed.

## Requirements

- AstrBot `>= 4.0.0`
- NapCat `>= v4.8.115` for Stream API support
- Python dependencies from `requirements.txt`
- X API credentials, or Twitter web cookies for the GraphQL fallback path

## Transfer Modes

- `auto`: small videos use normal message components; larger videos or failed
  sends use NapCat Stream API.
- `stream`: force Stream API for videos.
- `local`: use normal AstrBot file-system components only.

For your separate-container deployment, use `auto` or `stream`.

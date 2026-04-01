# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Zero-dependency local Markdown knowledge base viewer. A Node.js HTTP server serves static files and provides APIs to browse, search, and manage Markdown notes. The frontend is a single‑page application with real‑time search, syntax‑highlighted rendering, and a separate editor page for CRUD operations.

## Common Commands

### Start the server
```bash
# Default: serves ./notes on port 3000
node server.js

# Specify custom directory and/or port
node server.js /path/to/notes 8080

# Use platform‑specific convenience scripts
# Windows:
start.bat
# Linux/macOS:
chmod +x start.sh
./start.sh

# Scripts accept --dir and --port options
./start.sh --dir ./my-notes --port 8080
```

The server runs on `127.0.0.1` and prints the URL and notes directory on start. Stop with Ctrl+C.

### No build, lint, or test suite
This project has zero dependencies and no build step. Frontend resources (marked.js, highlight.js) are loaded from CDN. There are no unit tests, linting configuration, or CI pipelines.

## Architecture

### Server (`server.js`)
- Pure Node.js HTTP server (no Express).
- Serves static files from `public/`.
- API endpoints:
  - `GET /api/tree` – scan the notes directory, return file list with base64url IDs.
  - `GET /api/file?id=…` – read a Markdown file.
  - `PUT /api/file` – update a file (delegated to `crud-api.js`).
  - `DELETE /api/file?id=…` – delete a file (delegated to `crud-api.js`).
  - `POST /api/files` – create a new file (delegated to `crud-api.js`).
  - `POST /api/directories` – create a subdirectory (delegated to `crud-api.js`).
  - `GET /api/search?q=…` – full‑text search across note contents.
  - `GET /api/image?path=…` – serve images (path base64url‑encoded).
- Path‑traversal protection: all resolved paths must start with `NOTES_DIR`.
- CORS headers allow `*` for local development.

### CRUD module (`crud-api.js`)
- Exported handlers for create/update/delete file and create directory.
- Performs safety checks: valid filenames, path‑within‑notes‑dir, no `..` traversal.
- File IDs are base64url‑encoded relative paths.

### Frontend (`public/`)
- `index.html` – main viewer with sidebar file tree, search bar, and rendered Markdown panel.
- `editor.html` – dual‑pane Markdown editor (source + live preview) for creating/editing files.
- Vanilla JavaScript, no frameworks.
- Uses `marked` and `highlight.js` CDN for rendering and syntax highlighting.
- Communicates with server via `fetch`.

### Notes directory
- Default `./notes` (created automatically with a sample note).
- Recursively scanned for `.md`/`.mdwn` files.
- Directory structure is preserved in the UI; folders become collapsible groups.

## Key Files

- `server.js` – main server entry point.
- `crud-api.js` – CRUD operation handlers.
- `public/index.html` – primary user interface.
- `public/editor.html` – editor interface.
- `start.bat` / `start.sh` – convenience launchers that check Node.js, port availability, and auto‑open the browser.

## Security Notes
- All user‑supplied paths are validated with `isPathSafe()` (ensures they stay inside `NOTES_DIR`).
- File names are checked for illegal characters and path‑traversal sequences.
- Base64url IDs are decoded before use; invalid IDs result in 404.
- Image API only serves files with image MIME types.
- No authentication – the server is intended for local use only.

## Development Notes
- The codebase is written in Chinese (comments, UI strings) but the logic is standard JavaScript.
- Adding new API endpoints: follow the pattern in `server.js` – add a condition block before the static‑file fallback.
- Adding new frontend features: edit `index.html` and its inline `<script>`.
- The project deliberately avoids npm dependencies; keep it zero‑dependency.
- The `.agent/plan/` directory contains implementation plans for previous features (e.g., CRUD addition).
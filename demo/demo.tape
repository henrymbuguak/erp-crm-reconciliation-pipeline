# VHS tape for the project's README/docs demo GIF.
#
# Rendered on CI (see .github/workflows/demo.yml), not locally: VHS drives a
# headless browser to capture xterm.js frames, which is unreliable on native
# Windows. The workflow runs this on a Linux runner with a Postgres service
# (the same image/credentials as docker-compose.yml, just on the default
# port since there's no local Postgres to collide with in CI) and commits
# the resulting docs/assets/demo.gif back to the repo.
#
# To trigger a re-render: push a change to this file, or run the "Demo GIF"
# workflow manually from the Actions tab.

Output docs/assets/demo.gif

Require uv

Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 720
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms

# 1. Generate a fresh, deliberately messy ERP + CRM dataset.
Type "uv run datagen generate --seed 1 --customers 12 --with-ground-truth --output-dir data/demo"
Enter
Sleep 4s

# 2. Ingest, clean, resolve, and reconcile both exports.
Type "uv run reconcile data/demo"
Enter
Sleep 4s

# 3. Optional: also load the same run into Postgres.
Type "uv run reconcile data/demo --postgres-dsn postgresql://reconcile:reconcile@localhost:5432/reconcile"
Enter
Sleep 4s

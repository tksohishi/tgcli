#!/usr/bin/env bash
set -euo pipefail

echo "Installing tgcli..."

# Install uv if not present
if ! command -v uv &>/dev/null; then
    echo "uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Make uv available in current session
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install tgcli
uv tool install pytgcli

# Verify tg is on PATH
if ! command -v tg &>/dev/null; then
    echo ""
    echo "tg was installed but is not on your PATH."
    uv tool update-shell
    echo "Shell config updated. Restart your shell, then run: tg auth"
else
    echo ""
    echo "tgcli installed successfully!"
    echo ""
    echo "Get started:"
    echo "  tg auth      # set up credentials and log in"
    echo "  tg chats     # list your chats"
    echo "  tg read ...  # read messages"
fi

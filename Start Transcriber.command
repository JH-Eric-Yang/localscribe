#!/bin/bash
# LocalScribe launcher — double-click me. Everything installs into ./.managed
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"

mkdir -p "$DIR/.managed/logs"   # must exist BEFORE the tee below
exec > >(tee -a "$DIR/.managed/logs/bootstrap.log") 2>&1

echo "Starting LocalScribe — leave this window open while you transcribe."

export UV_PYTHON_INSTALL_DIR="$DIR/.managed/python"
export UV_CACHE_DIR="$DIR/.managed/uv-cache"
export HF_HOME="$DIR/.managed/hf-cache"
export HF_HUB_DISABLE_XET=1  # classic HTTP downloads: resumable + stall-recoverable

UV="$DIR/.managed/uv/uv"

fail() {
    echo ""
    echo "$1"
    echo "The universal fix: delete the .managed folder inside this folder, then double-click again."
    echo "(Technical details were saved to .managed/logs/bootstrap.log)"
    read -r -p "Press Return to close this window."
    exit 1
}

if ! "$UV" --version >/dev/null 2>&1; then
    rm -rf "$DIR/.managed/uv"
    echo "One-time setup: downloading the setup tool..."
    curl -LsSf https://astral.sh/uv/0.11.28/install.sh \
        | env UV_UNMANAGED_INSTALL="$DIR/.managed/uv" INSTALLER_NO_MODIFY_PATH=1 sh \
        || fail "Could not download the setup tool — check your internet connection (a university proxy may be blocking astral.sh), then double-click again."
    "$UV" --version >/dev/null 2>&1 \
        || fail "The setup tool did not install correctly — check your internet connection, then double-click again."
fi

"$UV" run --project "$DIR" --frozen python -m app.main \
    || fail "LocalScribe could not start."

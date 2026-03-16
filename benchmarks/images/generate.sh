#!/usr/bin/env bash
#
# Generate 4K (3840x2160) benchmark images from the HTML source files.
#
# Prerequisites: Google Chrome, macOS sips (ships with macOS).
#
# Usage:
#     ./benchmarks/images/generate.sh            # from repo root
#     ./generate.sh                              # from benchmarks/images/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$SCRIPT_DIR"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [[ ! -x "$CHROME" ]]; then
    echo "Error: Google Chrome not found at $CHROME" >&2
    exit 1
fi

JPEG_QUALITY=92
PORT=8099
PAGES=("comparison" "ranking")

cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT

python3 -m http.server "$PORT" --directory "$SCRIPT_DIR" &>/dev/null &
SERVER_PID=$!
sleep 1

for page in "${PAGES[@]}"; do
    tmp_png=$(mktemp /tmp/wybthon_img_XXXXXX.png)
    out_jpg="$OUT_DIR/wybthon_benchmark_${page}.jpg"

    echo "Rendering ${page}.html → 4K PNG …"
    "$CHROME" \
        --headless=new \
        --screenshot="$tmp_png" \
        --window-size=1920,1080 \
        --force-device-scale-factor=2 \
        --disable-gpu \
        --hide-scrollbars \
        "http://localhost:${PORT}/${page}.html" \
        2>/dev/null

    echo "Converting to JPEG (quality ${JPEG_QUALITY}) …"
    sips \
        --setProperty format jpeg \
        --setProperty formatOptions "$JPEG_QUALITY" \
        "$tmp_png" \
        --out "$out_jpg" \
        &>/dev/null

    rm -f "$tmp_png"

    dims=$(sips -g pixelWidth -g pixelHeight "$out_jpg" \
        | awk '/pixelWidth/{w=$2} /pixelHeight/{h=$2} END{print w"x"h}')
    size=$(du -h "$out_jpg" | cut -f1 | xargs)
    echo "  ✔ ${out_jpg##*/}  ${dims}  ${size}"
done

echo "Done."

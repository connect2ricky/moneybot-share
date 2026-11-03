#!/bin/zsh
# Personal install: builds the token and key from the macOS Keychain into the app, so a fresh install needs no setup.
# The result must stay on your own devices: never upload it to TestFlight or a store, or share it.
# Usage: ./install_personal.sh [ios|android]
set -euo pipefail
cd "${0:A:h}"
command -v flutter >/dev/null || export PATH="$HOME/SDKS/flutter/bin:$HOME/flutter/bin:$PATH"
command -v flutter >/dev/null || { echo "Flutter not found. Install it from https://docs.flutter.dev/get-started/install"; exit 1; }

repo=$(cd .. && uv run python -c "from moneybot.config import BACKUP_REPO; print(BACKUP_REPO)")
[[ -n "$repo" ]] || { echo "Set BACKUP_REPO in moneybot/config.py first."; exit 1; }
url="https://api.github.com/repos/$repo/contents/moneybot.mbp?ref=phone"

token=$(security find-generic-password -s moneybot-phone-token -w) || { echo "No token saved. Run: uv run moneybot phone-token"; exit 1; }
key=$(security find-generic-password -s moneybot-phone -w) || { echo "No phone key saved. Run: uv run moneybot phone-key"; exit 1; }

# A file, so the values never appear in the process list; it is removed when the script ends.
defines=$(mktemp -t moneybot)
trap 'rm -f "$defines"' EXIT
chmod 600 "$defines"
printf '{"GITHUB_TOKEN":"%s","PHONE_KEY":"%s","SNAPSHOT_URL":"%s"}' "$token" "$key" "$url" > "$defines"

case "${1:-ios}" in
  ios)
    flutter build ios --release --dart-define-from-file="$defines"
    device=$(xcrun devicectl list devices | awk '/available \(paired\)/ {for (i=1;i<=NF;i++) if ($i ~ /^[0-9A-F-]{36}$/) print $i}' | head -1)
    [[ -n "$device" ]] || { echo "No iPhone available. Unlock it and keep it on the same network as the Mac."; exit 1; }
    xcrun devicectl device install app --device "$device" build/ios/iphoneos/Runner.app
    ;;
  android)
    flutter build apk --release --dart-define-from-file="$defines"
    adb install -r build/app/outputs/flutter-apk/app-release.apk
    ;;
  *) echo "Usage: $0 [ios|android]"; exit 2 ;;
esac

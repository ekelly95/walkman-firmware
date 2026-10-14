#!/usr/bin/env bash
# Sets up a Linux copy of REA inside WSL Ubuntu, for the lanes REA only supports on Linux:
# firmware (Binwalk 3.1 / Unblob 26.6), packet captures (TShark), logic signals (sigrok-cli),
# ELF diagnostics (pwntools) and Ghidra analysis of non-Windows binaries (ARM/MIPS/ELF).
# Run as your normal WSL user: bash ~/setup-rea-linux.sh   (it asks for your sudo password)
set -euo pipefail

REA_VERSION=6.4.0                       # matches the Windows REA registration
WIN_GHIDRA=/mnt/c/Users/edmun/Tools/ghidra_12.1.4_PUBLIC
TOOLS="$HOME/tools"
SHARE="$HOME/.local/share"
BIN="$HOME/.local/bin"
mkdir -p "$TOOLS" "$SHARE" "$BIN"

step() { printf '\n==> %s\n' "$*"; }

step "System packages"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  curl ca-certificates git build-essential cmake pkg-config libssl-dev \
  libfontconfig1-dev liblzma-dev libbz2-dev \
  python3 python3-venv python3-dev pipx \
  openjdk-21-jdk-headless unzip \
  tshark sigrok-cli util-linux gdb \
  android-sdk-libsparse-utils e2fsprogs erofs-utils lz4 lziprecover lzop \
  p7zip-full partclone unar xz-utils zstd libmagic1

step "Node.js 24 (NodeSource)"
if ! node --version 2>/dev/null | grep -qE '^v(2[4-9]|[3-9][0-9])\.'; then
  curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
node --version

step "REA $REA_VERSION"
npm install --prefix "$SHARE/rea" "rea-agents@$REA_VERSION"

step "sasquatch (SquashFS extractor used by Unblob)"
if ! command -v sasquatch >/dev/null; then
  deb_url=$(curl -fsSL https://api.github.com/repos/onekey-sec/sasquatch/releases/latest \
    | grep -oE '"browser_download_url": *"[^"]*/sasquatch_[^"/]*_amd64\.deb"' | head -1 | cut -d'"' -f4 || true)
  if [ -n "$deb_url" ]; then
    tmp=$(mktemp -d); curl -fsSL -o "$tmp/sasquatch.deb" "$deb_url"
    sudo apt-get install -y "$tmp/sasquatch.deb" || echo "WARNING: sasquatch install failed; SquashFS extraction will be unavailable."; rm -rf "$tmp"
  else
    echo "WARNING: could not find a sasquatch .deb; SquashFS extraction will be reported as a missing extractor."
  fi
fi

step "Unblob 26.6"
pipx install --force 'unblob==26.6.*'

step "Rust + Binwalk 3.1"
if ! command -v cargo >/dev/null && [ ! -x "$HOME/.cargo/bin/cargo" ]; then
  curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal
fi
"$HOME/.cargo/bin/cargo" install binwalk --version '~3.1' --locked

step "pwntools environment for ELF diagnostics"
python3 -m venv "$SHARE/rea-pwntools"
"$SHARE/rea-pwntools/bin/pip" install --upgrade pip
"$SHARE/rea-pwntools/bin/pip" install pwntools==4.15.0 pyelftools==0.33 unicorn==2.1.2

step "Ghidra 12.1.4 (copied from the Windows install; it includes the Linux decompiler)"
if [ ! -d "$TOOLS/ghidra_12.1.4_PUBLIC" ]; then
  cp -r "$WIN_GHIDRA" "$TOOLS/"
fi
find "$TOOLS/ghidra_12.1.4_PUBLIC" -path '*/os/linux_x86_64/*' -type f -exec chmod +x {} +
chmod +x "$TOOLS/ghidra_12.1.4_PUBLIC/ghidraRun" "$TOOLS/ghidra_12.1.4_PUBLIC/support/"*.sh 2>/dev/null || true

step "MCP launcher $BIN/rea-mcp"
JAVA_HOME_DIR=$(dirname "$(dirname "$(readlink -f "$(command -v javac || command -v java)")")")
cat > "$BIN/rea-mcp" <<LAUNCHER
#!/usr/bin/env bash
# Starts REA's MCP server inside WSL with the Linux-only tools wired in.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
export REA_ANALYSIS_PROVIDER=ghidra
export GHIDRA_INSTALL_DIR="$TOOLS/ghidra_12.1.4_PUBLIC"
export JAVA_HOME="$JAVA_HOME_DIR"
export REA_BINWALK_COMMAND="$HOME/.cargo/bin/binwalk"
export REA_UNBLOB_COMMAND="$HOME/.local/bin/unblob"
export REA_FIRMWARE_PRLIMIT_COMMAND=/usr/bin/prlimit
export REA_TSHARK_COMMAND=/usr/bin/tshark
export REA_TSHARK_PRLIMIT_COMMAND=/usr/bin/prlimit
export REA_CAPINFOS_COMMAND=/usr/bin/capinfos
export REA_SIGROK_COMMAND=/usr/bin/sigrok-cli
export REA_SIGROK_PRLIMIT_COMMAND=/usr/bin/prlimit
export REA_PWNTOOLS_PYTHON="$SHARE/rea-pwntools/bin/python"
exec node "$SHARE/rea/node_modules/rea-agents/scripts/rea.mjs" "\${@:-mcp}"
LAUNCHER
chmod +x "$BIN/rea-mcp"

step "Versions"
"$HOME/.cargo/bin/binwalk" --version
"$HOME/.local/bin/unblob" --version
tshark --version | head -1
sigrok-cli --version | head -1

step "Unblob smoke test (checks its Landlock sandbox works under WSL)"
t=$(mktemp -d); echo "hello firmware" > "$t/a.txt"; gzip -k "$t/a.txt"
if "$HOME/.local/bin/unblob" -e "$t/out" "$t/a.txt.gz" >/dev/null 2>"$t/err"; then
  echo "unblob OK"
else
  echo "unblob FAILED:"; cat "$t/err"
fi
rm -rf "$t"

step "REA doctor"
"$BIN/rea-mcp" doctor --json || true

printf '\nDone. Tell Claude the script finished so it can register rea-linux.\n'

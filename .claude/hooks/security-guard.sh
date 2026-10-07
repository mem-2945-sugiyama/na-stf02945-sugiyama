#!/usr/bin/env bash
# PreToolUse hook — block a small set of high-severity destructive commands
# that permissions glob cannot express cleanly. Intentionally minimal per
# the "keep hooks simple" principle. Not a complete defense against
# obfuscation (eval / base64 / command substitution can bypass).
#
# Scope: team-common baseline. Framework- or project-specific rules
# (e.g. RAILS_ENV=production, Django DEBUG=True, k8s production context)
# should be added by each team to a separate guard script or to their own
# extension of this file. See "Team-specific extensions" at the bottom.
set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

block() {
  printf '%s\n' "$1" >&2
  exit 2
}

# 1. rm with recursive+force on protected paths
# Covers: -rf, -fr, -Rf, -rvf, -r -f (split), --recursive --force
if printf '%s' "$cmd" | grep -qE '\brm\b' \
   && printf '%s' "$cmd" | grep -qE '(-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)' \
   && printf '%s' "$cmd" | grep -qE '(-[a-zA-Z]*[fF][a-zA-Z]*|--force)' \
   && printf '%s' "$cmd" | grep -qE '(^|[[:space:]])(/[[:space:]]*$|/\*|~/?\**($|[[:space:]])|\$\{?HOME\}?)'; then
  block "rm with recursive+force on protected path blocked. Narrow the path."
fi

# 2. curl | bash / wget | sh piping
if printf '%s' "$cmd" | grep -qE '(curl|wget)[^|]*\|[[:space:]]*(ba)?sh([[:space:]]|$)'; then
  block "Piping curl/wget into a shell is blocked. Download the script, inspect, then run."
fi

# 3. chmod 777 / 666 / a+w (world-writable modes)
if printf '%s' "$cmd" | grep -qE 'chmod[[:space:]]+(-R[[:space:]]+)?(777|666|a\+w)'; then
  block "chmod 777/666/a+w blocked. Use a restrictive mode (e.g. 755 or 644)."
fi

# 4. dd of=/dev/*
if printf '%s' "$cmd" | grep -qE 'dd[[:space:]].*of=/dev/'; then
  block "dd of=/dev/* blocked."
fi

# 5. Protected file references
# Blocks any command that names a secret file regardless of utility. Covers
# read/copy/move/source/redirect/exec paths that the permissions glob deny
# cannot express — including embedded code (`ruby -e 'File.read(".env")'`,
# `bash -c ...`, `source .env`) and quote/order variations.
# Allowlist: `.env.sample` per CLAUDE.md (only exception to `.env*`).
safe="$(printf '%s' "$cmd" | sed -E 's#\.env\.sample([^A-Za-z0-9_]|$)#__SAFE__\1#g')"

# Prefix-style names: any suffix past the token (.env.local, master.key.bak, ...)
# still matches; the policy treats the whole family as protected.
if printf '%s' "$safe" | grep -qE '(^|[^A-Za-z0-9])(\.env|\.envrc|master\.key|\.claude\.json|\.bash_history|\.gitconfig)([^A-Za-z0-9]|$)'; then
  block "Protected file reference blocked (.env*/.envrc/master.key/.claude.json/.bash_history/.gitconfig). Only .env.sample is permitted."
fi

# Protected directories.
if printf '%s' "$safe" | grep -qE '(^|[^A-Za-z0-9])(\.ssh|\.aws|credentials|secrets)/'; then
  block "Protected directory reference blocked (.ssh/.aws/credentials/secrets/)."
fi

# .config/{gh,acli,pup}/ — auth state for gh / acli / pup.
if printf '%s' "$safe" | grep -qE '(^|[^A-Za-z0-9])\.config/(gh|acli|pup)(/|[^A-Za-z0-9]|$)'; then
  block "Protected config reference blocked (.config/{gh,acli,pup}/)."
fi

# *.pem / *.key extensions. Require a filename body and a terminal boundary
# (not alnum/_/-/.) so jq selectors (`jq .key`) and chained extensions
# (`secret.key.backup`) do not match.
if printf '%s' "$safe" | grep -qE '(^|[^A-Za-z0-9_.-])[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(pem|key)($|[^A-Za-z0-9_.-])'; then
  block "Protected file extension blocked (*.pem / *.key)."
fi

# *credentials*.json — Rails and GCP-style credential files.
if printf '%s' "$safe" | grep -qE '(^|[^A-Za-z0-9_.-])[A-Za-z0-9_.-]*credentials[A-Za-z0-9_.-]*\.json($|[^A-Za-z0-9_.-])'; then
  block "Protected credentials file blocked (*credentials*.json)."
fi

# ============================================================
# Team-specific extensions
# ------------------------------------------------------------
# Framework- or project-specific guards (e.g. RAILS_ENV=production,
# Django DEBUG flags, k8s context restrictions) are intentionally
# excluded from this team-common baseline.
#
# Each team should add its own rules either by:
#   a) Appending a guard block here in a team-managed branch, or
#   b) Registering a second hook script in .claude/settings.json:
#      "hooks": {
#        "PreToolUse": [
#          { "matcher": "Bash", "hooks": [
#              { "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/security-guard.sh" },
#              { "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/team-guard.sh" }
#          ]}
#        ]
#      }
#
# Example team-specific rules previously embedded here:
#   - Project-specific protected paths (e.g. /eiger, /DevOps, /line_ads_platform, /sherpa-)
#     → add to the rm protection regex in section 1, or guard separately
#   - RAILS_ENV=production prefix / env wrapper / Ruby ENV assignment
#   - Django: DJANGO_SETTINGS_MODULE=*.production
#   - k8s: kubectl config use-context *prod*
# ============================================================

exit 0

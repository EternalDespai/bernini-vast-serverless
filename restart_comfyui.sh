#!/usr/bin/env bash
# Restart only the ComfyUI process; API readiness is checked by the caller.
set -Eeuo pipefail
command -v supervisorctl >/dev/null || { echo "supervisorctl unavailable" >&2; exit 1; }
supervisor=(supervisorctl)
if [[ -f /etc/supervisor/supervisord.conf ]]; then
  supervisor+=(-c /etc/supervisor/supervisord.conf)
fi
service="${BERNINI_COMFY_SUPERVISOR_NAME:-}"
if [[ -z "$service" ]]; then
  # status returns nonzero when ANY process is stopped. Capture the complete
  # output before parsing, avoiding both errexit and an early-pipe SIGPIPE.
  status_rc=0
  status_output="$("${supervisor[@]}" status 2>&1)" || status_rc=$?
  mapfile -t candidates < <(printf '%s\n' "$status_output" | awk '
    tolower($1) ~ /comfyui/ && tolower($1) !~ /wrapper/ &&
    $2 ~ /^(STOPPED|STARTING|RUNNING|BACKOFF|STOPPING|EXITED|FATAL|UNKNOWN)$/ {print $1}')
  if (( ${#candidates[@]} != 1 )); then
    echo "Expected one ComfyUI supervisor service; found ${#candidates[@]} (status exit=$status_rc). Set BERNINI_COMFY_SUPERVISOR_NAME explicitly." >&2
    exit 1
  fi
  service="${candidates[0]}"
fi
[[ "$service" != -* && "$service" != *'*'* && "$service" != all && "$service" != *[[:space:]]* ]] || {
  echo "Expected a single supervisor process name" >&2; exit 1;
}
echo "BERNINI_COMFY_SUPERVISOR_SERVICE=$service"
if "${supervisor[@]}" restart "$service"; then
  exit 0
else
  rc=$?
  echo "ComfyUI restart failed (exit=$rc); inspect this service's supervisor logs." >&2
  exit "$rc"
fi

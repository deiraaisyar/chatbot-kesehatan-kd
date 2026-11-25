#!/bin/sh
# Startup health check for the deployed Kartu Risiko Pi system.
# Run on the Pi: sudo /opt/health/scripts/status_pi.sh

set -u

FAIL=0

section() {
    printf '\n=== %s ===\n' "$1"
}

check_service() {
    if systemctl is-active --quiet "$1"; then
        printf '%-12s active\n' "$1"
    else
        printf '%-12s NOT ACTIVE\n' "$1"
        FAIL=1
    fi
}

section "Services"
check_service health-api
check_service llama
systemctl is-enabled health-api llama 2>/dev/null || true

section "HTTP health"
if curl -fsS --max-time 5 http://127.0.0.1:8080/health; then
    printf '\n'
else
    printf 'llama-server health: FAILED\n'
    FAIL=1
fi

HEALTH_JSON=$(curl -fsS --max-time 5 http://127.0.0.1:8000/v1/health 2>/dev/null || true)
if [ -n "$HEALTH_JSON" ]; then
    printf '%s\n' "$HEALTH_JSON"
    STATUS=$(printf '%s' "$HEALTH_JSON" | /usr/bin/python3 -c \
        'import json,sys; print(json.load(sys.stdin).get("status","unknown"))' 2>/dev/null || echo unknown)
    if [ "$STATUS" = "down" ] || [ "$STATUS" = "unknown" ]; then
        printf 'API status: %s -> FAILED\n' "$STATUS"
        FAIL=1
    elif [ "$STATUS" = "degraded" ]; then
        printf 'API status: degraded (risk models work, chat is not ready)\n'
    else
        printf 'API status: %s\n' "$STATUS"
    fi
else
    printf 'API health: FAILED\n'
    FAIL=1
fi

section "Listening ports"
if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -E ':8000|:8080' || {
        printf 'Expected listeners on 8000 and 8080 were not found.\n'
        FAIL=1
    }
else
    printf 'ss not installed\n'
fi

section "Network"
hostname -I 2>/dev/null || true
ip -4 addr show wlan0 2>/dev/null | grep 'inet ' || true
if [ -x /usr/sbin/iw ]; then
    /usr/sbin/iw dev wlan0 get power_save 2>/dev/null || true
    /usr/sbin/iw dev wlan0 link 2>/dev/null | grep -E 'SSID|signal|bitrate' || true
fi
if command -v ufw >/dev/null 2>&1; then
    ufw status 2>/dev/null | sed -n '1,12p' || true
fi

section "System"
if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd measure_temp 2>/dev/null || true
    vcgencmd get_throttled 2>/dev/null || true
fi
free -h 2>/dev/null | sed -n '1,2p' || true
df -h / 2>/dev/null | tail -1 || true

printf '\n'
if [ "$FAIL" -ne 0 ]; then
    printf 'Result: FAILED — inspect the service logs above.\n'
    exit 1
fi
printf 'Result: OK\n'
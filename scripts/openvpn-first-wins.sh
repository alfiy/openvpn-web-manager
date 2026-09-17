#!/bin/bash
# 先连的赢：锁存在则拒绝后连者。
# 仅当 client-disconnect 释放锁，或锁已超过 90 秒且 status 中已无该 CN 时，才允许新人接管。
export PATH="/usr/bin:/bin:/usr/sbin:/sbin"

CN="${common_name:-}"
MY_IP="${untrusted_ip:-}"
MY_PORT="${untrusted_port:-}"
STYPE="${script_type:-client-connect}"
LOG="${FIRST_WINS_LOG:-/etc/openvpn/first-wins/first-wins.log}"
LOCK_DIR="${FIRST_WINS_LOCK_DIR:-/etc/openvpn/first-wins/locks}"
STATUS_FILES="/run/openvpn/server.status /var/log/openvpn/status.log /etc/openvpn/openvpn-status.log"
STALE_AFTER="${FIRST_WINS_STALE_AFTER:-90}"

log() {
    printf '%s type=%s cn=%s ip=%s port=%s %s\n' \
        "$(date '+%F %T')" "$STYPE" "${CN:--}" "${MY_IP:--}" "${MY_PORT:--}" "$*" >>"$LOG" 2>/dev/null || true
}

safe_name() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }
lock_path() { printf '%s/%s.lock' "$LOCK_DIR" "$(safe_name "$1")"; }

cn_listed() {
    local want_cn="$1"
    local me="${MY_IP}:${MY_PORT}"
    local f line addr in_list=0
    for f in $STATUS_FILES; do
        [ -r "$f" ] || continue
        in_list=0
        while IFS= read -r line; do
            case "$line" in
                "OpenVPN CLIENT LIST"*) in_list=1; continue ;;
                "ROUTING TABLE"*|"GLOBAL STATS"*) in_list=0; continue ;;
                CLIENT_LIST,"$want_cn",*)
                    addr="${line#CLIENT_LIST,$want_cn,}"
                    addr="${addr%%,*}"
                    [ "$addr" != "$me" ] && [ -n "$addr" ] && return 0
                    ;;
            esac
            if [ "$in_list" = 1 ]; then
                case "$line" in
                    "Common Name"*|"Updated"*) ;;
                    "$want_cn",*)
                        addr="${line#${want_cn},}"
                        addr="${addr%%,*}"
                        [ "$addr" != "$me" ] && [ -n "$addr" ] && return 0
                        ;;
                esac
            fi
        done < "$f"
    done
    return 1
}

mkdir -p "$LOCK_DIR" 2>/dev/null || true
log "HOOK start v5"

if [ -z "$CN" ]; then
    log "ALLOW no-common-name"
    exit 0
fi

LOCK="$(lock_path "$CN")"

if [ "$STYPE" = "client-disconnect" ]; then
    if [ -f "$LOCK" ]; then
        holder_ip="$(awk -F= '/^ip=/{print $2}' "$LOCK" 2>/dev/null || true)"
        holder_port="$(awk -F= '/^port=/{print $2}' "$LOCK" 2>/dev/null || true)"
        if [ "$holder_ip" = "$MY_IP" ] && [ "$holder_port" = "$MY_PORT" ]; then
            rm -f "$LOCK"
            log "UNLOCK released holder=$holder_ip:$holder_port"
        else
            log "UNLOCK skip rejected-or-other holder=${holder_ip:-?}:${holder_port:-?}"
        fi
    else
        log "UNLOCK no-lock"
    fi
    exit 0
fi

# 同一 CN 串行判断，避免踢人后两台同时重连都看到「无锁」
GATE="${LOCK}.gate"
touch "$GATE" 2>/dev/null || true
exec 9>"$GATE"
if ! flock -w 8 9; then
    log "DENY flock-timeout"
    exit 1
fi

if [ -f "$LOCK" ]; then
    holder_ip="$(awk -F= '/^ip=/{print $2}' "$LOCK" 2>/dev/null || true)"
    holder_port="$(awk -F= '/^port=/{print $2}' "$LOCK" 2>/dev/null || true)"
    holder_ts="$(awk -F= '/^ts=/{print $2}' "$LOCK" 2>/dev/null || true)"
    now=$(date +%s)
    age=$((now - ${holder_ts:-0}))
    if [ "$age" -lt "$STALE_AFTER" ]; then
        log "DENY holder=${holder_ip:-?}:${holder_port:-?} age=${age}s (lock-fresh)"
        exit 1
    fi
    if cn_listed "$CN"; then
        log "DENY holder=${holder_ip:-?}:${holder_port:-?} still-in-status age=${age}s"
        exit 1
    fi
    rm -f "$LOCK"
    log "STALE lock cleared age=${age}s"
fi

{
    echo "cn=$CN"
    echo "ip=$MY_IP"
    echo "port=$MY_PORT"
    echo "ts=$(date +%s)"
} >"$LOCK"
log "ALLOW take-lock"
exit 0

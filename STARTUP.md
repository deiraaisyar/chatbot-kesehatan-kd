# Startup and Operations

This document is for a Raspberry Pi where the system is **already deployed**.
It explains how to power it on, verify the services, open the dashboard, restart
components, update the deployment, and recover from common failures.

For the architecture, see [`architecture.md`](architecture.md).
For the first installation, see [`deploy/README.md`](deploy/README.md).

---

## 1. What should already be deployed

Expected layout on the Pi:

```text
/opt/health/
  app/                         FastAPI backend
  dashboard/dist/              dashboard served at /
  data/final/                  meta.json, risk_levels.json
  models/*.onnx                three risk models
  models/chat/0.5B-q4_k_m.gguf student chatbot model
  venv/                        Python environment
  bin/llama-server             llama.cpp server + shared libraries
  deploy/                      service units and deployment docs
  scripts/
/etc/health/api.env            bearer token and runtime paths
/etc/NetworkManager/dispatcher.d/90-ufw-lan
/etc/systemd/system/health-api.service
/etc/systemd/system/llama.service
```

The two systemd services must be enabled:

```bash
systemctl is-enabled health-api llama
```

Expected:

```text
enabled
enabled
```

---

## 2. Normal startup

The Pi is designed to start both services automatically at boot.

```bash
sudo shutdown -h now     # before moving or unplugging the Pi
```

At the new location:

1. Connect power and wait 30–60 seconds.
2. NetworkManager connects to the saved Wi-Fi profile.
3. `llama.service` loads the GGUF.
4. `health-api.service` loads the three ONNX models.
5. FastAPI serves the dashboard at `http://<pi-ip>:8000/`.

You do **not** normally need to start anything manually.

> Do not cut power directly. Use `sudo shutdown -h now` first, especially with
> an SD card.

---

## 3. Verify on the Pi

SSH into the Pi:

```bash
ssh omahti
```

Then run:

```bash
systemctl is-active health-api llama
systemctl is-enabled health-api llama
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8000/v1/health
ss -ltnp | grep -E ':8000|:8080'
```

Expected:

```text
active
active
enabled
enabled
{"status":"ok"}
{"status":"ok","risk":{...},"chat":{"available":true,...}}
LISTEN ... 127.0.0.1:8080
LISTEN ... 0.0.0.0:8000
```

A healthy API response looks like:

```json
{
  "status": "ok",
  "risk": {
    "hipertensi": "ok",
    "diabetes": "ok",
    "kolesterol_tinggi": "ok"
  },
  "chat": {
    "available": true,
    "backend": "llama.cpp"
  },
  "versions": {
    "risk": "catboost-2026.11",
    "chat": "chatbot-kesehatan-qwen2.5-0.5b-q4km"
  }
}
```

### Convenience script

If `scripts/status_pi.sh` is available:

```bash
sudo /opt/health/scripts/status_pi.sh
```

It prints the service states, HTTP health, ports, UFW, Wi-Fi, and temperature.

---

## 4. Verify from the laptop

Find the Pi’s current IP from the router or try:

```bash
ping <pi-ip>
ping omahti.local
```

Then:

```bash
curl http://<pi-ip>:8000/v1/health
```

Open the dashboard:

```text
http://<pi-ip>:8000/
```

The IP can change when the Pi joins a different network. The old address is not
guaranteed to work after a move.

---

## 5. Open the dashboard

1. Open `http://<pi-ip>:8000/`.
2. Go to **Pengaturan**.
3. Select **Raspberry Pi**.
4. Enter the Base URL, normally the same origin:
   ```text
   http://<pi-ip>:8000
   ```
5. Retrieve the bearer token on the Pi:
   ```bash
   sudo grep '^HEALTH_API_TOKEN=' /etc/health/api.env
   ```
6. Press **Tes koneksi**.
7. Run an assessment, then ask a question about the result.

The dashboard stores only the mode and endpoint in the browser. The token is
kept in memory, so it must be entered again after a page reload.

---

## 6. Health status meanings

| API status | Meaning | What still works |
|---|---|---|
| `ok` | Risk models and chat are ready | Assessment + chat |
| `degraded` | Risk models are ready; chat is not | Assessment only |
| `down` | Risk models are not ready | Nothing until fixed |

If the dashboard says **“Pi belum siap”**, the risk models failed to load.
If it says **“Fitur tanya jawab belum tersedia”**, only chat is unavailable.

---

## 7. Service management

### Check status

```bash
systemctl status health-api --no-pager
systemctl status llama --no-pager
```

### Restart everything

```bash
sudo systemctl restart llama
sudo systemctl restart health-api
```

### Restart only the API

```bash
sudo systemctl restart health-api
```

### Restart only the chat model

```bash
sudo systemctl restart llama
```

The API remains usable while chat is unavailable, but the dashboard will show
`degraded`.

### Stop without disabling

```bash
sudo systemctl stop health-api llama
```

Start again:

```bash
sudo systemctl start llama
sudo systemctl start health-api
```

### Logs

```bash
journalctl -u llama -n 100 --no-pager
journalctl -u health-api -n 100 --no-pager
journalctl -u llama -f
journalctl -u health-api -f
```

---

## 8. After a code update

On the laptop, commit and push first.

On the Pi:

```bash
cd /opt/health
sudo -u health git pull --ff-only
sudo -u health venv/bin/pip install -r requirements.txt
sudo systemctl restart health-api
```

If the dashboard source changed, rebuild it on the laptop and commit/push the
new `dashboard/dist/`, or build it on the Pi if Node.js is installed:

```bash
cd /opt/health/dashboard
npm run build
sudo systemctl restart health-api
```

The Pi serves `dashboard/dist/`; it does not need Node.js at runtime.

### If the API fails after an update

```bash
journalctl -u health-api -n 100 --no-pager
sudo -u health venv/bin/python -m compileall -q /opt/health/app
```

Check that `requirements.txt` was applied to the same venv used by the service.

---

## 9. After a model update

Copy the new GGUF to the Pi, verify it, and update the version label:

```bash
sudo mv /tmp/new-model.gguf /opt/health/models/chat/
sudo chown health:health /opt/health/models/chat/new-model.gguf
sha256sum /opt/health/models/chat/new-model.gguf
```

Update `ExecStart` in `/etc/systemd/system/llama.service` to the new filename,
and `CHAT_MODEL_VERSION` in `/etc/health/api.env`. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart llama
sudo systemctl restart health-api
```

Check `/v1/health` and `/v1/meta` to confirm the new version.

### If `llama-server` fails to start

```bash
journalctl -u llama -n 100 --no-pager
ls -l /opt/health/models/chat/
ls -l /opt/health/bin/llama-server
LD_LIBRARY_PATH=/opt/health/bin /opt/health/bin/llama-server --version
```

The service needs `LD_LIBRARY_PATH=/opt/health/bin` because `llama-server` is
linked against shared libraries in that directory.

---

## 10. After a network change

The Pi can store multiple NetworkManager profiles. The current deployment has
`healthnet` as the original network and `chapelure` as the new profile with
higher autoconnect priority.

Check profiles:

```bash
nmcli -f NAME,DEVICE connection show
nmcli -f NAME,DEVICE connection show --active
```

If the Pi does not connect automatically:

```bash
nmcli device wifi list
sudo nmcli connection up chapelure
ip -4 addr show wlan0
```

The `90-ufw-lan` hook automatically adds SSH/8000 rules for the new subnet.
After moving, verify:

```bash
sudo ufw status numbered
```

Old subnet rules are not removed automatically. Add the new subnet-specific
rules, then delete obsolete broad rules after confirming SSH works.

For captive portals, WPA-Enterprise, or AP/client isolation, use a travel router
or phone hotspot.

---

## 11. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Dashboard unreachable | Wrong IP, Wi-Fi down, UFW | Ping Pi; check `nmcli`, `ufw status` |
| `health` is `down` | ONNX model missing or failed | Check `journalctl -u health-api`; verify `/opt/health/models/*.onnx` |
| Chat unavailable | `llama` failed or model missing | Check `journalctl -u llama`; verify GGUF path |
| Chat very slow | Pi 4 CPU / long answer | Lower `CHAT_MAX_TOKENS`; keep one turn; benchmark |
| 401 | Missing/wrong token | Enter token from `/etc/health/api.env` |
| 404/410 | Assessment/session expired | Re-submit the form; start a new session |
| 409 | Turn limit reached | Start a new session |
| 504 | Chat timeout | Retry; check llama logs |
| Dashboard blank | `dist` missing or old | Verify `/opt/health/dashboard/dist/index.html`; rebuild/copy |
| API starts but no UI | Static mount path wrong | Check `DASHBOARD_DIR` and `app/main.py` mount |
| Pi not on Wi-Fi | Profile missing/priority | Add profile; use local console |
| Laptop cannot reach Pi | AP isolation | Use travel router/Ethernet |

### Quick DNS/IP check

```bash
hostname -I
ip -4 addr show wlan0
```

### Check UFW

```bash
sudo ufw status numbered
```

### Check temperature and throttling

```bash
vcgencmd measure_temp
vcgencmd get_throttled
```

`get_throttled` should be `0x0`. High temperature or throttling will make chat
much slower.

---

## 12. Shutdown

```bash
sudo shutdown -h now
```

Wait for the green activity LED to stop / the board to power down before
unplugging. For a Pi with an SD card, always shut down cleanly.

---

## 13. Startup checklist

Copy-paste this after a reboot:

```bash
systemctl is-active health-api llama
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8000/v1/health
ss -ltnp | grep -E ':8000|:8080'
sudo ufw status
```

From the laptop:

```bash
curl http://<pi-ip>:8000/v1/health
```

Then open:

```text
http://<pi-ip>:8000/
```

Expected final state:

- `health-api` active
- `llama` active
- `llama` listening on `127.0.0.1:8080`
- API listening on `0.0.0.0:8000`
- `/v1/health` returns `status: ok`
- dashboard loads and can connect with the bearer token

---

## 14. Related documents

- [`architecture.md`](architecture.md) — system, model, deployment, and network architecture
- [`deploy/README.md`](deploy/README.md) — first-time Pi deployment
- [`README.md`](README.md) — project overview, classifier results, and development instructions
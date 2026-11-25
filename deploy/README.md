# Raspberry Pi deployment

Target: Raspberry Pi 4 (8 GB), Raspberry Pi OS Lite 64-bit, offline demo.
The API serves the dashboard at `/` and exposes the v1 contract under `/v1`.

## 1. Copy the project

```bash
sudo adduser --disabled-password --gecos "" health
sudo mkdir -p /opt/health
sudo chown -R health:health /opt/health
# copy the repository contents into /opt/health
```

The expected layout:

```text
/opt/health/app/
/opt/health/dashboard/dist/
/opt/health/data/final/
/opt/health/models/*.onnx
/opt/health/models/chat/0.5B-q4_k_m.gguf
/opt/health/venv/
/opt/health/bin/llama-server
```

## 2. Python runtime

```bash
sudo -u health python3 -m venv /opt/health/venv
sudo -u health /opt/health/venv/bin/pip install -U pip
sudo -u health /opt/health/venv/bin/pip install -r /opt/health/requirements.txt
```

## 3. Chat model

Download on a laptop, then copy the verified GGUF to the Pi:

```powershell
.\scripts\fetch_chat_model.ps1
scp .\models\chat\0.5B-q4_k_m.gguf health@<pi-ip>:/tmp/
```

On the Pi:

```bash
sudo mv /tmp/0.5B-q4_k_m.gguf /opt/health/models/chat/
sudo chown health:health /opt/health/models/chat/0.5B-q4_k_m.gguf
sha256sum /opt/health/models/chat/0.5B-q4_k_m.gguf
```

Expected SHA-256:

```text
4117c4248a581dafcf020fd1c1b5fb84826e92236a6c12c37db2a665e0448490
```

Build llama.cpp on the Pi (or copy a matching arm64 binary):

```bash
cd /opt/health
sudo -u health git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
sudo -u health cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=OFF
sudo -u health cmake --build build --config Release -j4
sudo cp build/bin/llama-server /opt/health/bin/
```

## 4. Environment

```bash
sudo mkdir -p /etc/health
sudo cp /opt/health/deploy/api.env.example /etc/health/api.env
sudo nano /etc/health/api.env      # set HEALTH_API_TOKEN
sudo chown root:health /etc/health
sudo chmod 750 /etc/health
sudo chmod 600 /etc/health/api.env
```

`CHAT_MULTI_TURN=0` is intentional: the current student was trained on
single-turn data. Enable multi-turn only after testing the fine-tuned model.

## 5. systemd

```bash
sudo cp /opt/health/deploy/llama.service /etc/systemd/system/
sudo cp /opt/health/deploy/health-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now llama.service
sudo systemctl enable --now health-api.service
sudo systemctl status llama.service health-api.service
```

Logs:

```bash
journalctl -u llama -f
journalctl -u health-api -f
```

## 6. Network

The API binds `0.0.0.0:8000`; llama-server binds `127.0.0.1:8080`.

Connect the Pi to the demo Wi-Fi (Bookworm uses NetworkManager):

```bash
nmcli device wifi list
sudo nmcli device wifi connect "YOUR_SSID" password "YOUR_PASSWORD" name healthnet
ip -4 addr show wlan0
```

Use a DHCP reservation or a static address so the dashboard URL does not change.
Disable Wi-Fi power saving, verify client-to-client traffic, and allow only the
demo subnet through UFW:

```bash
sudo nmcli connection modify healthnet wifi.powersave 2
sudo nmcli connection up healthnet
iw dev wlan0 get power_save

# From the Pi, confirm the laptop is reachable (AP isolation test):
ping -c 4 <laptop-ip>

ip -4 addr show wlan0
sudo ufw allow from <demo-subnet>/24 to any port 22 proto tcp
sudo ufw allow from <demo-subnet>/24 to any port 8000 proto tcp
sudo ufw status
```

If the laptop and Pi can both reach the internet but cannot ping each other,
the Wi-Fi has AP/client isolation. Use a travel router or direct Ethernet.

## 7. Verify

From the demo laptop:

```bash
curl http://<pi-ip>:8000/v1/health
```

Open `http://<pi-ip>:8000/`, go to **Pengaturan**, select **Raspberry Pi**,
enter the same origin and bearer token, and press **Tes koneksi**.

Run one assessment and one chat. Confirm:

- risk levels and percentages match the card;
- red-flag cards show the emergency banner;
- chat answers contain no invented numbers;
- the fallback notice appears if the model fails the guard;
- with `CHAT_MULTI_TURN=0`, the UI offers one question per assessment.

## 8. Useful checks

```bash
curl http://127.0.0.1:8080/health
journalctl -u health-api -n 100 --no-pager
vcgencmd measure_temp
vcgencmd get_throttled
```

If `/v1/health` says `down`, the risk models failed to load. Check
`registry_error` in the logs and the ONNX files in `/opt/health/models`.
If chat is unavailable, check `llama.service` and the GGUF path.
# =========================
# GDS Vessel Dashboard
# Sensor Simulator + Firebase
# =========================

from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import threading, time, random, math, json
from datetime import datetime

# ---------- Firebase ----------
import firebase_admin
from firebase_admin import credentials, db

# ================= CONFIG =================
FIREBASE_KEY_PATH = "firebase_key.json"
FIREBASE_DB_URL = "https://gds-vessel-simulator-default-rtdb.asia-southeast1.firebasedatabase.app"



VESSEL_ID = "demo_vessel"

# =========================================

app = Flask(__name__)
CORS(app)

# ================= GLOBAL STATE =================
nav_lock = threading.Lock()

nav_current = {
    "date": "",
    "time": "",
    "latitude": 0,
    "longitude": 0,
    "speed": 0,
    "heading": 0,
    "cog": 0,
    "voltage": 0,
    "panic": 0,
    "ext_heading": 0,
    "raw_string": ""
}

nav_history = []

# ================= FIREBASE INIT =================
firebase_initialized = False

def init_firebase():
    global firebase_initialized
    if firebase_initialized:
        return
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {
        "databaseURL": FIREBASE_DB_URL
    })
    firebase_initialized = True

# ================= SENSOR SIMULATOR =================
def simulate_sensor_data():
    init_firebase()

    lat = 23.8103
    lon = 90.4125
    speed = 8.0
    heading = 45.0

    while True:
        speed += random.uniform(-0.3, 0.3)
        speed = max(3, min(15, speed))

        heading = (heading + random.uniform(-2, 2)) % 360

        distance = (speed * 1.852 / 3600) / 111
        lat += distance * math.cos(math.radians(heading))
        lon += distance * math.sin(math.radians(heading))

        voltage = random.randint(1180, 1240)
        cog = (heading + random.uniform(-2, 2)) % 360

        now = datetime.utcnow()

        packet = {
            "timestamp": now.isoformat(),
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "speed": round(speed, 1),
            "heading": round(heading, 0),
            "cog": round(cog, 0),
            "voltage": voltage,
            "panic": 0,
            "source": "SIMULATOR"
        }

        # ---- Update dashboard ----
        with nav_lock:
            nav_current.update({
                "date": now.strftime("%d/%m/%Y"),
                "time": now.strftime("%H:%M:%S"),
                "latitude": packet["latitude"],
                "longitude": packet["longitude"],
                "speed": packet["speed"],
                "heading": packet["heading"],
                "cog": packet["cog"],
                "voltage": voltage,
                "panic": 0,
                "ext_heading": packet["heading"],
                "raw_string": json.dumps(packet)
            })

            nav_history.insert(0, nav_current.copy())
            if len(nav_history) > 200:
                nav_history.pop()

        # ---- Push to Firebase ----
        try:
            ref = db.reference(f"vessels/{VESSEL_ID}/telemetry")
            ref.push(packet)
        except Exception as e:
            print("Firebase error:", e)

        time.sleep(1)

# ================= START THREAD =================
threading.Thread(target=simulate_sensor_data, daemon=True).start()

# ================= API =================
@app.route("/nav_data")
def nav_data():
    with nav_lock:
        return jsonify({
            "current": nav_current,
            "history": nav_history[:100]
        })

# ================= SIMPLE DASHBOARD =================
HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>GDS Vessel Dashboard</title>
  <style>
    body { background:#0b0b0f; color:#fff; font-family:Arial; padding:20px }
    .card { background:#14141b; padding:15px; border-radius:12px; margin-bottom:10px }
    .label { color:#aaa; font-size:12px }
    .value { font-size:22px; font-weight:bold }
  </style>
</head>
<body>

<h2>Vessel Sensor Simulator</h2>

<div class="card">
  <div class="label">Latitude</div>
  <div class="value" id="lat">--</div>
</div>

<div class="card">
  <div class="label">Longitude</div>
  <div class="value" id="lon">--</div>
</div>

<div class="card">
  <div class="label">Speed (knots)</div>
  <div class="value" id="spd">--</div>
</div>

<div class="card">
  <div class="label">Heading / COG</div>
  <div class="value" id="hdg">--</div>
</div>

<div class="card">
  <div class="label">Voltage</div>
  <div class="value" id="volt">--</div>
</div>

<script>
async function loadData(){
  const r = await fetch("/nav_data");
  const d = await r.json();
  document.getElementById("lat").innerText = d.current.latitude;
  document.getElementById("lon").innerText = d.current.longitude;
  document.getElementById("spd").innerText = d.current.speed;
  document.getElementById("hdg").innerText = d.current.heading + " / " + d.current.cog;
  document.getElementById("volt").innerText = d.current.voltage + " mV";
}
setInterval(loadData, 1000);
loadData();
</script>

</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

# ================= RUN =================
if __name__ == "__main__":
    print("GDS Sensor Simulator running...")
    app.run(host="0.0.0.0", port=5000, debug=True)

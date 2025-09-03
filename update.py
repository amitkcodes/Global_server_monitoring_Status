# ===============================
# NTP Monitoring & API using Flask
# Author: <Your Name>
# Purpose: Monitor multiple NTP servers, calculate offset, delay & response time,
#          save to SQLite DB, and provide REST APIs for realtime & history data.
# ===============================

import ntplib            # For NTP client queries
import time
from datetime import datetime
import pytz              # For timezone (IST)
from statistics import mean, stdev
import sqlite3           # Database (SQLite)
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading         # To run monitoring loop in background

# -------------------------------
# Flask app setup
# -------------------------------
app = Flask(__name__)
CORS(app)   # Enable CORS (so frontend from another origin can call APIs)

# -------------------------------
# List of NTP Servers to query
# -------------------------------
ntp_servers = [
    "157.20.66.8",
    "157.20.67.8",
    "14.139.60.103",
    "14.139.60.106",
    "14.139.60.107",
    "time.nplindia.in",
    "time.nplindia.org",
    "samay1.nic.in",
    "samay2.nic.in",
    "time.nist.gov",
    "pool.ntp.org",
    "time.windows.com",
    "time.google.com",
    "asia.pool.ntp.org",
    "uk.pool.ntp.org"
]

# -------------------------------
# Initialize SQLite Database
# -------------------------------
def init_db():
    conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
    c = conn.cursor()
    # Table schema to store NTP response details
    c.execute('''CREATE TABLE IF NOT EXISTS ntp_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,              -- When query was done
        server TEXT,                 -- NTP server name
        offset_ms REAL,              -- Time offset (ms)
        delay_ms REAL,               -- Round trip delay (ms)
        root_delay_ms REAL,          -- Root delay (server reported)
        root_dispersion_ms REAL,     -- Root dispersion (server reported)
        stratum INTEGER,             -- Server stratum
        response_time_ms REAL,       -- Server processing time (T3 - T2)
        precision_ms REAL,           -- Clock precision (server reported)
        status TEXT                  -- Online / Error
    )''')
    conn.commit()
    conn.close()

# Call once to make sure DB exists
init_db()

# -------------------------------
# NTP client setup
# -------------------------------
client = ntplib.NTPClient()
ist = pytz.timezone('Asia/Kolkata')

# -------------------------------
# Function: Query single NTP server
# -------------------------------
def query_ntp_server(server):
    try:
        # Send request to server (ntplib handles T1-T4 internally)
        response = client.request(server, version=4)
        timestamp = datetime.now(ist).isoformat()  # Current time in IST
        return {
            'server': server,
            'response': response,
            'timestamp': timestamp
        }
    except Exception as e:
        # If server unreachable, log error into DB
        print(f"Error with {server}: {e}")
        timestamp = datetime.now(ist).isoformat()
        conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
        c = conn.cursor()
        c.execute('''INSERT INTO ntp_data (timestamp, server, offset_ms, delay_ms, root_delay_ms,
                                           root_dispersion_ms, stratum, response_time_ms,
                                           precision_ms, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (timestamp, server, 0, 0, 0, 0, 0, 0, 0, "Error"))
        conn.commit()
        conn.close()
        return None

# -------------------------------
# Function: Process server response
# -------------------------------
def process_response(data):
    if data is None:
        return None

    server = data['server']
    response = data['response']
    timestamp = data['timestamp']

    # Extract NTP timestamps (from ntplib response)
    T1 = response.orig_time   # Client transmit (request sent)
    T2 = response.recv_time   # Server receive
    T3 = response.tx_time     # Server transmit
    T4 = response.dest_time   # Client receive (response received)

    # Standard NTP formulas
    offset = ((T2 - T1) + (T3 - T4)) / 2 * 1000   # ms
    delay = ((T4 - T1) - (T3 - T2)) * 1000        # ms

    # ✅ Response time = (T3 - T2)
    response_time = (T3 - T2) * 1000              # ms

    # Other values directly from NTP server
    root_delay = response.root_delay * 1000
    root_disp = response.root_dispersion * 1000
    stratum = response.stratum
    precision = (2 ** response.precision) * 1000
    status = "Online"

    # Insert into DB
    conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
    c = conn.cursor()
    c.execute('''INSERT INTO ntp_data (timestamp, server, offset_ms, delay_ms, root_delay_ms,
                                       root_dispersion_ms, stratum, response_time_ms,
                                       precision_ms, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (timestamp, server, offset, delay, root_delay, root_disp,
               stratum, response_time, precision, status))
    conn.commit()
    conn.close()

    return {'offset': offset, 'delay': delay}

# -------------------------------
# Background Thread: Monitor NTP servers in loop
# -------------------------------
def ntp_monitoring_loop():
    while True:
        cycle_start = datetime.now(ist)
        print(f"\n[{cycle_start}] Starting new cycle...")
        delays = []
        offsets = []

        # Run parallel queries to all servers
        with ThreadPoolExecutor(max_workers=len(ntp_servers)) as executor:
            future_to_server = {executor.submit(query_ntp_server, server): server for server in ntp_servers}
            for future in as_completed(future_to_server):
                data = future.result()
                result = process_response(data)
                if result:
                    delays.append(result['delay'])
                    offsets.append(result['offset'])

        # Compute jitter & mean offset
        if len(delays) > 1:
            jitter = stdev(delays)
            offset_mean = mean(offsets)
        else:
            jitter = 0
            offset_mean = offsets[0] if offsets else 0

        # Print summary
        print(f"\n---- Cycle Summary ----")
        print(f"Jitter (stddev of delay across servers): {jitter:.3f} ms")
        print(f"Average Offset (across servers): {offset_mean:.3f} ms")

        # Sleep 5 minutes before next cycle
        elapsed = (datetime.now(ist) - cycle_start).total_seconds()
        sleep_time = max(0, 300 - elapsed)
        time.sleep(sleep_time)

# Start monitoring loop in background thread
threading.Thread(target=ntp_monitoring_loop, daemon=True).start()

# -------------------------------
# Flask Routes
# -------------------------------

# Homepage (renders index.html if available)
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Error rendering index.html: {str(e)}")
        return "Error: Could not load the page. Please ensure index.html exists in the templates folder.", 500

# API: Latest realtime data (one record per server)
@app.route('/api/realtime')
def get_realtime_data():
    try:
        # Fetch latest records
        conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
        c = conn.cursor()
        c.execute('''SELECT t1.*
                     FROM ntp_data t1
                     WHERE t1.id = (SELECT MAX(t2.id)
                                    FROM ntp_data t2
                                    WHERE t2.server = t1.server)''')
        rows = c.fetchall()
        conn.close()

        # Convert to dict list
        data = []
        for row in rows:
            data.append({
                'timestamp': row[1],
                'server': row[2],
                'offset_ms': f"{row[3]:.3f}",
                'delay_ms': f"{row[4]:.3f}",
                'root_delay_ms': f"{row[5]:.3f}",
                'root_dispersion_ms': f"{row[6]:.3f}",
                'response_time_ms': f"{row[8]:.3f}",
                'precision_ms': f"{row[9]:.3f}",
                'status': row[10]
            })

        # ✅ Custom order (as you shared)
        preferred_order = [
            "14.139.60.103",
            "14.139.60.106",
            "14.139.60.107",
            "time.nplindia.in",
            "time.nplindia.org",
            "samay1.nic.in",
            "samay2.nic.in",
            "time.nist.gov",
            "pool.ntp.org",
            "time.windows.com",
            "time.google.com",
            "asia.pool.ntp.org",
            "uk.pool.ntp.org",
            "157.20.66.8",
            "157.20.67.8"
        ]

        # ✅ Sort the data based on preferred_order
        data.sort(key=lambda x: preferred_order.index(x['server']) if x['server'] in preferred_order else 999)

        return jsonify(data)

    except Exception as e:
        print(f"Error in /api/realtime: {str(e)}")
        return jsonify({'error': str(e)}), 500


# API: History (last 10 records of a given server)
@app.route('/api/history')
def get_history():
    try:
        server = request.args.get('server')
        conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
        c = conn.cursor()
        c.execute('SELECT * FROM ntp_data WHERE server = ? ORDER BY timestamp DESC LIMIT 10', (server,))
        rows = c.fetchall()
        conn.close()

        data = []
        for row in rows:
            data.append({
                'timestamp': row[1],
                'server': row[2],
                'offset_ms': f"{row[3]:.3f}",
                'delay_ms': f"{row[4]:.3f}",
                'root_delay_ms': f"{row[5]:.3f}",
                'root_dispersion_ms': f"{row[6]:.3f}",
                'response_time_ms': f"{row[8]:.3f}",   # (T3 - T2)
                'precision_ms': f"{row[9]:.3f}",
                'status': row[10]
            })
        return jsonify(data)
    except Exception as e:
        print(f"Error in /api/history: {str(e)}")
        return jsonify({'error': str(e)}), 500

# -------------------------------
# Run Flask app
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

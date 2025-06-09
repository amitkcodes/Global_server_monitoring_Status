import ntplib
import time
from datetime import datetime
import pytz
from statistics import mean, stdev
import sqlite3
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

app = Flask(__name__)
CORS(app)

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

def init_db():
    conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ntp_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        server TEXT,
        offset_ms REAL,
        delay_ms REAL,
        root_delay_ms REAL,
        root_dispersion_ms REAL,
        stratum INTEGER,
        response_time_ms REAL,
        precision_ms REAL,
        status TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

client = ntplib.NTPClient()
ist = pytz.timezone('Asia/Kolkata')

def query_ntp_server(server):
    try:
        start_time = time.time()
        response = client.request(server, version=4)
        end_time = time.time()
        timestamp = datetime.now(ist).isoformat()
        response_time = (end_time - start_time) * 1000
        return {
            'server': server,
            'response': response,
            'timestamp': timestamp,
            'response_time': response_time
        }
    except Exception as e:
        print(f"Error with {server}: {e}")
        timestamp = datetime.now(ist).isoformat()
        conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
        c = conn.cursor()
        c.execute('''INSERT INTO ntp_data (timestamp, server, offset_ms, delay_ms, root_delay_ms, root_dispersion_ms, stratum, response_time_ms, precision_ms, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (timestamp, server, 0, 0, 0, 0, 0, 0, 0, "Error"))
        conn.commit()
        conn.close()
        return None

def process_response(data):
    if data is None:
        return None
    server = data['server']
    response = data['response']
    timestamp = data['timestamp']
    response_time = data['response_time']
    
    offset = response.offset * 1000
    delay = response.delay * 1000
    root_delay = response.root_delay * 1000
    root_disp = response.root_dispersion * 1000
    stratum = response.stratum
    precision = 2 ** response.precision * 1000
    response_time = (response.tx_time - response.recv_time) * 1000  # milliseconds
    status = "Online"
    
    conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
    c = conn.cursor()
    c.execute('''INSERT INTO ntp_data (timestamp, server, offset_ms, delay_ms, root_delay_ms, root_dispersion_ms, stratum, response_time_ms, precision_ms, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (timestamp, server, offset, delay, root_delay, root_disp, stratum, response_time, precision, status))
    conn.commit()
    conn.close()
    
    return {'offset': offset, 'delay': delay}

def ntp_monitoring_loop():
    while True:
        cycle_start = datetime.now(ist)
        print(f"\n[{cycle_start}] Starting new cycle...")
        delays = []
        offsets = []
        
        with ThreadPoolExecutor(max_workers=len(ntp_servers)) as executor:
            future_to_server = {executor.submit(query_ntp_server, server): server for server in ntp_servers}
            for future in as_completed(future_to_server):
                data = future.result()
                result = process_response(data)
                if result:
                    delays.append(result['delay'])
                    offsets.append(result['offset'])
        
        if len(delays) > 1:
            jitter = stdev(delays)
            offset_mean = mean(offsets)
        else:
            jitter = 0
            offset_mean = offsets[0] if offsets else 0
        
        print(f"\n---- Cycle Summary ----")
        print(f"Jitter (stddev of delay across servers): {jitter:.3f} ms")
        print(f"Average Offset (across servers): {offset_mean:.3f} ms")
        
        elapsed = (datetime.now(ist) - cycle_start).total_seconds()
        sleep_time = max(0, 300 - elapsed)
        time.sleep(sleep_time)

threading.Thread(target=ntp_monitoring_loop, daemon=True).start()

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Error rendering index.html: {str(e)}")
        return "Error: Could not load the page. Please ensure index.html exists in the templates folder.", 500

@app.route('/api/realtime')
def get_realtime_data():
    try:
        conn = sqlite3.connect('ntp_data.db', check_same_thread=False, timeout=10)
        c = conn.cursor()
        c.execute('''SELECT t1.*
                     FROM ntp_data t1
                     WHERE t1.id = (SELECT MAX(t2.id) FROM ntp_data t2 WHERE t2.server = t1.server)''')
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
                'response_time_ms': f"{row[8]:.3f}",
                'precision_ms': f"{row[9]:.3f}",
                'status': row[10]
            })
        return jsonify(data)
    except Exception as e:
        print(f"Error in /api/realtime: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
                'response_time_ms': f"{row[8]:.3f}",
                'precision_ms': f"{row[9]:.3f}",
                'status': row[10]
            })
        return jsonify(data)
    except Exception as e:
        print(f"Error in /api/history: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

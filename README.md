# 🌐 Global Server Monitoring Status
# 🌐 https://ntp-server-monitoring.onrender.com
This project monitors multiple **NTP (Network Time Protocol) servers** worldwide, calculates offset, delay, response time, and logs results into a SQLite database.  
It also provides a **Flask-based REST API** to fetch real-time and historical monitoring data.  

Deployed on **Render Hosting** using GitHub.

---

## ✨ Features
- Monitors multiple NTP servers in parallel.
- Collects:
  - Time offset (ms)
  - Network delay (ms)
  - Root delay & dispersion
  - Stratum
  - Response time
  - Precision
  - Server status (Online/Error)
- Stores data in **SQLite database (`ntp_data.db`)**.
- Provides REST APIs for:
  - **Realtime status** of all servers
  - **Historical logs** (last 10 entries per server)
- Web interface support (`index.html` under `templates/` if added).
- Background thread for continuous monitoring (runs every 5 minutes).

---

## 🚀 APIs
### 1. History (last 10 records)
GET /api/history?server=<server_address>
eg../api/history?server=time.google.com
..../api/history?server=time.nplindia.in




### 2. Realtime Data
```http
GET /api/realtime
[
  {
    "timestamp": "2025-09-08T09:30:00+05:30",
    "server": "time.google.com",
    "offset_ms": "2.145",
    "delay_ms": "12.004",
    "root_delay_ms": "0.123",
    "root_dispersion_ms": "0.456",
    "response_time_ms": "1.200",
    "precision_ms": "0.977",
    "status": "Online"
  }
]

### 1.. History (last 10 records)
GET /api/history?server=<server_address>

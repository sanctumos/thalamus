from flask import Flask, request

app = Flask(__name__)

@app.route("/omi", methods=["POST"])
def omi_webhook():
    print(f"🔎 Incoming POST: {request.method} {request.url}")

    try:
        data = request.get_json(force=True)
        print("\n🔥 Cerebellum Input [UNRESTRICTED]:")
        print(data)
        return "OK", 200
    except Exception as e:
        print(f"💥 Failed to parse incoming data: {e}")
        return "Bad Request", 400

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
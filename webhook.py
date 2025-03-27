from flask import Flask, request, abort
import hmac
import hashlib

app = Flask(__name__)

CEREBELLUM_SIGIL = "nemean-mirror"

def verify_signature(request):
    received_signature = request.headers.get('X-Cerebellum-Sigil')
    expected_signature = hmac.new(
        CEREBELLUM_SIGIL.encode(),
        request.data,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(received_signature, expected_signature)

@app.route("/omi", methods=["POST"])
def omi_webhook():
    if not verify_signature(request):
        print("🚫 Invalid signature!")
        abort(403)

    data = request.get_json(force=True)
    print("\n🔥 Cerebellum Input [Nemean Mirror Validated]:")
    print(data)
    return "OK", 200

if __name__ == "__main__":
    app.run(port=5000)
from flask import Flask, render_template, jsonify
import datetime

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    return jsonify(
        {
            "status": "running",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)

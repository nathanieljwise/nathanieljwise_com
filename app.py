from flask import Flask, render_template, send_from_directory, abort
import time
from pathlib import Path
import hashlib

app = Flask(__name__)

STATIC_DIR = Path(app.root_path) / "static"
def read_static(name):
    return (STATIC_DIR / name).read_text(encoding="utf-8")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/publickeys')
def publickeys():
    script = (STATIC_DIR / "hybrid_encrypt.py").read_bytes()
    return render_template(
        'publickeys.html',
        rsa_pem=read_static('njwise_rsa_publicKey.pem'),
        ecc_pem=read_static('njwise_ecc_publicKey.pem'),
        script_sha256=hashlib.sha256(script).hexdigest(),
    )

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')

@app.route('/experience')
def experience():
    return render_template('experience.html')

@app.route('/nowprinting')
def printing():
    now = time.time()
    return render_template('nowprinting.html', now=now)

@app.route('/sandbox')
def sandbox():
    return render_template('sandbox.html')

WEATHER_DATA_DIR = Path(app.root_path) / "data" / "weather"
WEATHER_FILES = {"latest", "series_24h", "series_7d", "series_30d", "daily", "wind_rose"}

@app.route('/weather')
def weather():
    return render_template('weather.html')

@app.route('/api/weather/<name>.json')
def weather_data(name):
    if name not in WEATHER_FILES:
        abort(404)
    resp = send_from_directory(str(WEATHER_DATA_DIR), f"{name}.json",
                               mimetype="application/json")
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)

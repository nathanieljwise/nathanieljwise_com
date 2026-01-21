from flask import Blueprint, request, redirect, abort, jsonify
import hashlib, random, string
from .models import get_db

bp = Blueprint("shortener", __name__, url_prefix="/s")

def gen_code(n=6):
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(n))

@bp.route("/<code>")
def go(code):
    con = get_db()
    cur = con.execute("SELECT id, target FROM links WHERE code=?", (code,))
    row = cur.fetchone()
    if not row:
        abort(404)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()

    con.execute(
        "INSERT INTO clicks (link_id, ip_hash, user_agent, referrer) VALUES (?,?,?,?)",
        (row["id"], ip_hash, request.headers.get("User-Agent"), request.referrer)
    )
    con.commit()

    return redirect(row["target"], code=302)

@bp.route("/api/create", methods=["POST"])
def create():
    url = request.json.get("url")
    if not url or not url.startswith(("http://", "https://")):
        abort(400)

    code = gen_code()
    con = get_db()
    con.execute(
        "INSERT INTO links (code, target) VALUES (?,?)",
        (code, url)
    )
    con.commit()

    return jsonify(short=f"/s/{code}")

@bp.route("/api/stats/<code>")
def stats(code):
    con = get_db()
    cur = con.execute("SELECT id FROM links WHERE code=?", (code,))
    row = cur.fetchone()
    if not row:
        abort(404)

    cur = con.execute("SELECT COUNT(*) AS c FROM clicks WHERE link_id=?", (row["id"],))
    return jsonify(clicks=cur.fetchone()["c"])

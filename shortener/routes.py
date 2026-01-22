from flask import Blueprint, request, redirect, abort, jsonify, render_template_string
from flask import session, redirect, url_for, flash
import hashlib, random, string
from .models import get_db

from functools import wraps
from flask import Response

# Simple HTTP Basic Auth
ADMIN_USER = "admin"
ADMIN_PASS = "password"  # change this

def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS

def authenticate():
    return Response(
        "Authentication required", 401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

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

@bp.route("/admin", methods=["GET", "POST"])
@requires_auth
def admin():
    con = get_db()
    if request.method == "POST":
        url = request.form.get("url")
        if url and url.startswith(("http://", "https://")):
            code = gen_code()
            con.execute("INSERT INTO links (code,target) VALUES (?,?)", (code,url))
            con.commit()
    # fetch all links and click counts
    cur = con.execute("""
        SELECT l.code, l.target, COUNT(c.id) as clicks
        FROM links l LEFT JOIN clicks c ON l.id = c.link_id
        GROUP BY l.id
        ORDER BY l.id DESC
    """)
    links = cur.fetchall()

    # inline template (you can move to templates/)
    template = """
    <!doctype html>
    <html>
    <head>
        <title>Shortener Admin</title>
    </head>
    <body>
        <h1>Shortener Admin</h1>

        <h2>Create Short URL</h2>
        <form method="post">
            <input type="text" name="url" placeholder="https://example.com" required style="width:300px;">
            <button type="submit">Create</button>
        </form>

        <h2>Existing Short URLs</h2>
        <table border="1" cellpadding="5">
            <tr><th>Short</th><th>Target</th><th>Clicks</th></tr>
            {% for row in links %}
            <tr>
                <td><a href="/s/{{ row['code'] }}">/s/{{ row['code'] }}</a></td>
                <td>{{ row['target'] }}</td>
                <td>{{ row['clicks'] }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(template, links=links)

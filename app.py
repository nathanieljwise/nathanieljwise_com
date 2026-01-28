from flask import Flask, render_template
import time

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/publickeys')
def publickeys():
    return render_template('publickeys.html')

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

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)

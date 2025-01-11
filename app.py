from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/rsa')
def rsa():
    return render_template('rsa.html')

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')

@app.route('/experience')
def experience():
    return render_template('experience.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)

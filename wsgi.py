import os
import sys

virtualenv_path = '/var/www/html/nathanieljwise/venv'
activate_this = os.path.join(virtualenv_path, 'bin', 'activate_this.py')

if os.path.exists(activate_this):
    exec(open(activate_this).read(), dict(__file__=activate_this))
else:
    sys.path.insert(0, os.path.join(virtualenv_path, 'lib', 'python3.9', 'site-packages'))

sys.path.insert(0, '/var/www/html/nathanieljwise')

from app import app as application

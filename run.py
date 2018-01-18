#!/usr/bin/env python3
from flask import Flask, request, redirect, url_for, send_from_directory, abort, render_template, jsonify, session
from six.moves.urllib.parse import urlencode
from flask_oauthlib.client import OAuth
from werkzeug import secure_filename
from functools import wraps
from threading import Thread, Timer
import logging
import os
import random
import json
import time
import short_url
from random import randint

# Import our configuration
from conf import config

# Import QuadFile stuff
from QuadFile import db
from QuadFile.output import print_log, time_to_string
from QuadFile import application

app = Flask(__name__)

oauth = OAuth(app)
auth0 = oauth.remote_app(
    'auth0',
    consumer_key='zmwM9URqC2dOSdNmmu4wGVYemmx2JmHE',
    consumer_secret='DzpUSd9nLkcxN8wdC9wC0qytnW34DOG5sn-2MKhrR2vfBGOhOdQY-2o09f-5e_xt',
    request_token_params={
        'scope': 'openid profile',
        'audience': 'https://' + 'disgg.auth0.com' + '/userinfo'
    },
    base_url='https://%s' % 'disgg.auth0.com',
    access_token_method='POST',
    access_token_url='/oauth/token',
    authorize_url='/authorize',
)

# TODO: Try to turn these into functions or something I dunno
print_log('Main', 'Running in "' + os.getcwd() + '"')
print_log('Main', 'Checking for data folder')
if not os.path.exists(config['UPLOAD_FOLDER']):
  print_log('Main', 'Data folder not found, creating')
  os.makedirs(config['UPLOAD_FOLDER'])
if config["EXTENDED_DEBUG"] == False:
  log = logging.getLogger('werkzeug')
  log.setLevel(logging.ERROR)


def cleaner_thread():
  # Call itself again after the interval
  cleaner = Timer(config["CLEAN_INTERVAL"], cleaner_thread)
  cleaner.daemon = True # Daemons will attempt to exit cleanly along with the main process, which we want
  cleaner.start()

  # Actual function
  delete_old()

class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code
        
@app.errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response

@app.errorhandler(Exception)
def handle_auth_error(ex):
    response = jsonify(message=ex.message)
    return response
    
def delete_old():
  print_log('Notice', 'Cleaner running')
  targetTime = time.time() - config["TIME"]
  old = db.get_old_files(targetTime)
  for file in old:
    print_log('Notice', 'Removing old file "' + file["file"] + '"')
    try:
      os.remove(os.path.join(config["UPLOAD_FOLDER"], file["file"]))
    except Exception:
      print_log('Warning', 'Failed to delete old file "' + file["file"] + '"')
    db.delete_entry(file["file"])

def error_page(error, code):
  return render_template('error.html', page=config["SITE_DATA"], error=error, code=code)

def requires_auth(f):
  @wraps(f)
  def decorated(*args, **kwargs):
    if 'profile' not in session:
      return redirect('/login')
    return f(*args, **kwargs)
  return decorated

def allowed_file(filename):
  if config["ALLOW_ALL_FILES"]:
    return True
  else:
    if config["BLACKLIST"]:
      return '.' in filename and filename.rsplit('.', 1)[1] not in config["BANNED_EXTENSIONS"]      
    else:
      return '.' in filename and filename.rsplit('.', 1)[1] in config["ALLOWED_EXTENSIONS"]   

#def donor_allowed_file(filename):
#  if config["DONOR_ALLOW_ALL_FILES"]:
#    return True
#  else:
#    if config["DONOR_BLACKLIST"]:
#      return '.' in filename and filename.rsplit('.', 1)[1] not in config["DONOR_BANNED_EXTENSIONS"]      
#    else:
#      return '.' in filename and filename.rsplit('.', 1)[1] in config["DONOR_ALLOWED_EXTENSIONS"]

@app.route('/', methods=['GET', 'POST'])
def upload_file():
  if request.method == 'POST':
    print_log('Web', 'New file received')
    if not application.basicauth(request.headers.get('X-Hyozan-Auth'), config["KEY"]):
      abort(403)
    data = dict()
    file = request.files['file']

    # Only continue if a file that's allowed gets submitted.
    if file and allowed_file(file.filename):
      filename = secure_filename(short_url.encode_url(int(time.time()), 5) + '.' + file.filename.rsplit('.',1)[1])
      while os.path.exists(os.path.join(config["UPLOAD_FOLDER"], filename)):
        filename = str(randint(1000,8999)) + '-' + secure_filename(filename)

      thread1 = Thread(target = db.add_file, args = (filename,))
      thread1.start()
      print_log('Thread', 'Adding to DB')
      file.save(os.path.join(config['UPLOAD_FOLDER'], filename))
      thread1.join()

      data["file"] = filename
      data["url"] = config["DOMAIN"] + "/" + filename
      print_log('Main', 'New file processed "' + filename + '"')

      try:
        if request.form["source"] == "web":
          return render_template('link.html', data=data, page=config["SITE_DATA"])
      except Exception:
        return json.dumps(data)
    else:
      print_log('Notice', 'Forbidden file received')
      return error_page(error="This file isn't allowed, sorry!", code=403)

  # Return Web UI if we have a GET request
  elif request.method == 'GET':
    return render_template('upload.html', page=config["SITE_DATA"])

@app.route('/custom', methods=['GET', 'POST'])
@requires_auth
def donor_upload_file():
  if request.method == 'POST':
    print_log('Web', 'New premium file received')
    if not application.basicauth(request.headers.get('X-Hyozan-Auth'), config["KEY"]):
      abort(403)
    data = dict()
    file = request.files['file']

    # Only continue if a file that's allowed gets submitted.
    if file and allowed_file(file.filename):
      filename = secure_filename(file.filename)
      while os.path.exists(os.path.join(config["UPLOAD_FOLDER"], filename)):
        filename = str(randint(1000,8999)) + '-' + secure_filename(filename)

      thread1 = Thread(target = db.add_file, args = (filename,))
      thread1.start()
      print_log('Thread', 'Adding to DB')
      file.save(os.path.join(config['UPLOAD_FOLDER'], filename))
      thread1.join()

      data["file"] = filename
      data["url"] = config["DOMAIN"] + "/" + filename
      print_log('Main', 'New premium file processed "' + filename + '"')

      try:
        if request.form["source"] == "web":
          return render_template('link.html', data=data, page=config["SITE_DATA"])
      except Exception:
        return json.dumps(data)
    else:
      print_log('Notice', 'Forbidden file received')
      return error_page(error="This file isn't allowed, sorry!", code=403)

  # Return Web UI if we have a GET request
  elif request.method == 'GET':
    return render_template('upload.html', page=config["SITE_DATA"])

@app.route('/morelogin')
def more_login_now():
    return 'test'

@app.route('/otherlogin')
def other_login_now():
    return auth0.authorize(callback='https://i.dis.gg/callback')

@app.route('/login')
def login_now():
    return auth0.authorize(callback='https://i.dis.gg/callback')
  
@app.route('/callback')
def callback_handling():
    resp = auth0.authorized_response()
    if resp is None:
        raise AuthError({'code': request.args['error'],
                         'description': request.args['error_description']}, 401)

    url = 'https://' + AUTH0_DOMAIN + '/userinfo'
    headers = {'authorization': 'Bearer ' + resp['access_token']}
    resp = requests.get(url, headers=headers)
    userinfo = resp.json()

    session[constants.JWT_PAYLOAD] = userinfo

    session[constants.PROFILE_KEY] = {
        'user_id': userinfo['sub'],
        'name': userinfo['name'],
        'picture': userinfo['picture']
    }

    return redirect('/custom')
  
@app.route('/logout')
def logout():
    session.clear()
    params = {'returnTo': url_for('home', _external=True), 'client_id': 'zmwM9URqC2dOSdNmmu4wGVYemmx2JmHE'}
    return redirect(auth0.base_url + '/v2/logout?' + urlencode(params))

# Def all the static pages
@app.route('/about')
def about():
  return render_template('about.html', page=config["SITE_DATA"])
@app.route('/terms')
def terms():
  return render_template('terms.html', page=config["SITE_DATA"])
@app.route('/privacy')
def privacy():
  return render_template('privacy.html', page=config["SITE_DATA"])
@app.route('/faq')
def faq():
  return render_template('faq.html', page=config["SITE_DATA"])
@app.route('/dmca')
def dmca():
  video = random.choice(os.listdir("static/dmca/"))
  return render_template('dmca.html', page=config["SITE_DATA"], video=video)

# Static resources that browsers spam for
@app.route('/favicon.ico')
def favicon():
  return send_from_directory('static', 'favicon.ico')
@app.route('/apple-touch-icon.png')
def appleTouch():
  return send_from_directory('static', 'logo/152px.png')
@app.route('/robots.txt')
def robotsTxt():
  return send_from_directory('static', 'robots.txt')

# Custom 404
@app.errorhandler(404)
def page_not_found(e):
    return error_page(error="We couldn't find that. Are you sure you know what you're looking for?", code=404), 404
#@app.errorhandler(500)
#def internal_error(e):
#    return error_page(error="Oops, this is an unknown error, not good.", code=500), 500
@app.errorhandler(403)
def no_permission(e):
    return error_page(error="Check your privilege yo", code=403), 403


@app.route('/<filename>', methods=['GET'])
def get_file(filename):
  print_log('Web', 'Hit "' + filename + '" - ' + time_to_string(time.time()))
  try:
    db.update_file(filename)
  except Exception:
    print_log('Warning', 'Unable to update access time. Is the file in the database?')
  return send_from_directory(config['UPLOAD_FOLDER'], filename)


# Configure nginx to use these urls as custom error pages
@app.route('/error/<int:error>')
def nginx_error(error):
  if error == 413:
    return error_page(error="O-o-onii-chan, noo it's too big ~~", code=413), 413
  elif error == 403: # Block IPs with your web server and return /error/403 for this page
    return error_page(error="Sorry, the IP you're using has been blocked due to excessive abuse", code=403), 403
  else:
    return error_page(error="We literally have no idea what just happened", code="Unknown")


if config["DELETE_FILES"]:
  cleaner_thread()
  
if __name__ == '__main__':
  app.run(
    port=config["PORT"],
    host=config["HOST"],
    debug=config["DEBUG"]
  )

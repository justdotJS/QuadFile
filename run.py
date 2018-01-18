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
import requests
import json
import time
import short_url
from random import randint
import constants

AUTH0_CALLBACK_URL = constants.AUTH0_CALLBACK_URL
AUTH0_CLIENT_ID = constants.AUTH0_CLIENT_ID
AUTH0_CLIENT_SECRET = constants.AUTH0_CLIENT_SECRET
AUTH0_DOMAIN = constants.AUTH0_DOMAIN
AUTH0_AUDIENCE = constants.AUTH0_AUDIENCE
if AUTH0_AUDIENCE is '':
    AUTH0_AUDIENCE = 'https://' + AUTH0_DOMAIN + '/userinfo'
    
# Import our configuration
from conf import config

# Import QuadFile stuff
from QuadFile import db
from QuadFile.output import print_log, time_to_string
from QuadFile import application

app = Flask(__name__)
app.secret_key = constants.SECRET_KEY

oauth = OAuth(app)
auth0 = oauth.remote_app(
    'auth0',
    consumer_key=AUTH0_CLIENT_ID,
    consumer_secret=AUTH0_CLIENT_SECRET,
    request_token_params={
        'scope': 'openid profile',
        'audience': AUTH0_AUDIENCE
    },
    base_url='https://%s' % AUTH0_DOMAIN,
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
        if constants.PROFILE_KEY not in session:
            return redirect('/login')
        if notallowed_id(session[constants.PROFILE_KEY]):
            return (error_page(error='Please donate to access this page.', code=403), 403)
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

def allowed_id(id):  
  return id in config["DONOR_ID_LIST"]
              
def allowed_id(id):  
  return id not in config["DONOR_ID_LIST"]

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

@app.route('/test')
def tester():
    return 'test'

@app.route('/login')
def login():
    return auth0.authorize(callback=AUTH0_CALLBACK_URL)
  
@app.route('/callback')
def callback():
    resp = auth0.authorized_response()
    
    if resp is None:
        return error_page(error=request.args['error_reason'] + request.args['error_description'], code=500), 500
    
    url = 'https://' + AUTH0_DOMAIN + '/userinfo'
    headers = {'authorization': 'Bearer ' + resp['access_token']}
    resp = requests.get(url, headers=headers)
    userinfo = resp.json()
    
    session[constants.JWT_PAYLOAD] = userinfo
    
    session[constants.PROFILE_KEY] = {
        'user_id': userinfo['sub'],
        'name': userinfo['name']
    }
    
    session[constants.PROFILE_KEY] = userinfo['sub'].split('|')[-1]
    
    #return session[constants.PROFILE_KEY]
    if allowed_id(session[constants.PROFILE_KEY]):
        return redirect('/custom')
    else:
        return error_page(error="Please donate to access this page.", code=403), 403
  
@app.route('/logout')
def logout():
    session.clear()
    params = {'returnTo': 'https://i.dis.gg', 'client_id': AUTH0_CLIENT_ID}
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
@app.errorhandler(500)
def internal_error(e):
    return error_page(error="Oops, this is an unknown error, not good.", code=500), 500
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

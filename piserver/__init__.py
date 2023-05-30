from flask import Flask, send_from_directory
import os
from picamera2 import Picamera2
import time

scratch_fp = '~/'

def create_app():

    app = Flask(__name__)

    camera = Picamera2()

    @app.route('/image')
    def image():
        """
        Take an image and return it over the function
        """
        time.sleep(2)
        camera.start_and_capture_file(scratch_fp + 'capture.jpg')

        return send_from_directory(scratch_fp + 'capture.jpg')
    








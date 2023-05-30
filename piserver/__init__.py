from flask import Flask, send_from_directory
import os
from picamera import PiCamera
import time

scratch_fp = '~/'

def create_app():

    app = Flask(__name__)

    camera = PiCamera()

    @app.route('/image')
    def image():
        """
        Take an image and return it over the function
        """
        time.sleep(2)
        camera.capture(scratch_fp + 'capture.jpg')

        return send_from_directory(scratch_fp + 'capture.jpg')
    








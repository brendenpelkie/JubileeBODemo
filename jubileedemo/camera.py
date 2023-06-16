import requests
import webbrowser

class Camera():
    """
    raspberry pi camera server client
    """
    def __init__(self, config):
        self.address = config['ip_address']
        self.port = config['port']

        self.video_endpoint = config['url_videoendpoint']
        self.still_endpoint = config['url_stillendpoint']

        self.still_url = f'http://{self.address}:{self.port}/{self.still_endpoint}'
        self.video_url = f'http://{self.address}:{self.port}/{self.video_endpoint}'
    def capture_image(self, timeout = 10):
        """
        Capture image from raspberry pi and write to file
        """
        try:
            response = requests.get(self.still_url, timeout = 10)
        except [ConnectionError, ConnectionRefusedError]:
            raise AssertionError
        
        assert response.status_code == 200

        return response.content

    def video_feed(self):
        webbrowser.open(self.video_url)

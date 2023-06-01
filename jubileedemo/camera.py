import requests

class Camera():
    """
    raspberry pi camera server client
    """
    def __init__(self, config):
        self.address = config['camera_address']
        self.port = config['camera_port']

        self.endpoint = config['url_endpoint']

        self.url = f'http://{self.address}:{self.port}/{self.endpoint}'

    def capture_image(self, fp, timeout = 10):
        """
        Capture image from raspberry pi and write to file
        """
        try:
            response = requests.get(self.url, timeout = 10)
        except [ConnectionError, ConnectionRefusedError]:
            raise AssertionError
        
        assert response.status_code == 200

        with open(fp, 'wb') as f:
            f.write(response.content)

        return True
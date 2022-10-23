import requests

def discover_wifi_devices():
    response = requests.post("https://app.divoom-gz.com/Device/ReturnSameLANDevice")
    data = response.json()
    if data['ReturnCode'] != 0:
        print(data)
    return data

def url_image_handle(url):
    """
    Returns a handle to directly open pictures from an url.
    """
    return requests.get(url, stream=True).raw
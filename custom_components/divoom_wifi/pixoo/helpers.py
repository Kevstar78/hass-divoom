import requests
import json

def discover_wifi_devices():
    return __get_request('https://app.divoom-gz.com/Device/ReturnSameLANDevice')

def get_font_list():
    return __get_request('https://app.divoom-gz.com/Device/GetTimeDialFontList')

def get_dial_type():
    return __get_request('https://app.divoom-gz.com/Channel/GetDialType')

def get_dial_list(dial_type='Social', page=1):
    # for dial_type see get_dial_type
    return __get_request(
        'https://app.divoom-gz.com/Channel/GetDialList',
        {
            'DialType': dial_type,
            'Page': page
        })

def get_img_upload_list(device_id, device_mac, page=1):
    # device_id and device_mac can be determined by discover_wifi_devices
    return __get_request(
        'https://app.divoom-gz.com/Device/GetImgUploadList',
        {
            'DeviceId': device_id,
            'DeviceMac': device_mac,
            'Page': page
        })

def get_img_like_list(device_id, device_mac, page=1):
    # device_id and device_mac can be determined by discover_wifi_devices
    return __get_request(
        'https://app.divoom-gz.com/Device/GetImgLikeList',
        {
            'DeviceId': device_id,
            'DeviceMac': device_mac,
            'Page': page
        })

def url_image_handle(url):
    """
    Returns a handle to directly open pictures from an url.
    """
    return requests.get(url, stream=True).raw

def __get_request(url, request_dict={}):
    if request_dict:
        response = requests.post(url, json.dumps(request_dict))
    else:
        response = requests.post(url)
    data = response.json()
    if data['ReturnCode'] != 0:
        print(data)
    return data
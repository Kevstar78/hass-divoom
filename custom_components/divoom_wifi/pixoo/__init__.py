import base64
import json
from enum import IntEnum
from PIL import Image, ImageOps
import requests

from ._colors import Palette
from ._font import retrieve_glyph


def clamp(value, minimum=0, maximum=255):
    if value > maximum:
        return maximum
    if value < minimum:
        return minimum

    return value


def clamp_color(rgb):
    return clamp(rgb[0]), clamp(rgb[1]), clamp(rgb[2])


def lerp(start, end, interpolant):
    return start + interpolant * (end - start)


def lerp_location(xy1, xy2, interpolant):
    return lerp(xy1[0], xy2[0], interpolant), lerp(xy1[1], xy2[1], interpolant)


def minimum_amount_of_steps(xy1, xy2):
    return max(abs(xy1[0] - xy2[0]), abs(xy1[1] - xy2[1]))


def rgb_to_hex_color(rgb):
    return f'#{rgb[0]:0>2X}{rgb[1]:0>2X}{rgb[2]:0>2X}'


def round_location(xy):
    return round(xy[0]), round(xy[1])
    
    
def discover_wifi_devices():
    response = requests.post("https://app.divoom-gz.com/Device/ReturnSameLANDevice")
    data = response.json()
    if data['ReturnCode'] != 0:
        print(data)
    return data


class Channel(IntEnum):
    FACES = 0
    CLOUD = 1
    VISUALIZER = 2
    CUSTOM = 3


class ImageResampleMode(IntEnum):
    PIXEL_ART = Image.NEAREST
    SMOOTH = Image.ANTIALIAS


class TextScrollDirection(IntEnum):
    LEFT = 0
    RIGHT = 1


class Pixoo:
    __buffer = []
    __buffers_send = 0
    __counter = 0
    __display_list = []

    def __init__(self, address, size=64, debug=False):
        assert size in [16, 32, 64], 'Invalid screen size in pixels given. Valid options are 16, 32, and 64'

        self.address = address
        self.debug = debug
        self.size = size

        # Total number of pixels
        self.pixel_count = self.size * self.size

        # Generate URL
        self.__url = 'http://{0}/post'.format(address)

        # Prefill the buffer
        self.fill()

        # Retrieve the counter
        self.__load_counter()
        
        # Retrieve current device configuration
        self.device_config = self.__get_config()
        
        # Default values for Scoreboard
        self.blue_score = 0
        self.red_score = 0

    def add_display_item(self, text='', xy=(0, 0), color=Palette.WHITE, identifier=1, font=2, width=64,
                         movement_speed=0, direction=TextScrollDirection.LEFT, align=1,
                         height=16, display_type=22, url_time=None):

        identifier = clamp(identifier, 0, 39)

        text_properties = {
            'TextId': identifier,
            'type': display_type,
            'x': xy[0],
            'y': xy[1],
            'dir': direction,
            'font': font,
            'TextWidth': width,
            'TextHeight': height,
            'speed': movement_speed,
            'color': rgb_to_hex_color(color),
            'align': align
            }

        if text != '':
            text_properties['TextString'] = text
        if url_time != None:
            text_properties['UrlTime'] = url_time

        self.__display_list.append(text_properties)

    def clear(self, rgb=Palette.BLACK):
        self.fill(rgb)

    def clear_display_list(self):
        self.__display_list = []

    def clear_rgb(self, r, g, b):
        self.fill_rgb(r, g, b)

    def clear_text(self):
        self.__send_request({
            'Command' : 'Draw/ClearHttpText'
        })

    def draw_character(self, character, xy=(0, 0), rgb=Palette.WHITE):
        matrix = retrieve_glyph(character)
        if matrix is not None:
            for index, bit in enumerate(matrix):
                if bit == 1:
                    local_x = index % 3
                    local_y = int(index / 3)
                    self.draw_pixel((xy[0] + local_x, xy[1] + local_y), rgb)

    def draw_character_at_location_rgb(self, character, x=0, y=0, r=255, g=255, b=255):
        self.draw_character(character, (x, y), (r, g, b))

    def draw_filled_rectangle(self, top_left_xy=(0, 0), bottom_right_xy=(1, 1), rgb=Palette.BLACK):
        for y in range(top_left_xy[1], bottom_right_xy[1] + 1):
            for x in range(top_left_xy[0], bottom_right_xy[0] + 1):
                self.draw_pixel((x, y), rgb)

    def draw_filled_rectangle_from_top_left_to_bottom_right_rgb(self, top_left_x=0, top_left_y=0, bottom_right_x=1,
                                                                bottom_right_y=1, r=0, g=0, b=0):
        self.draw_filled_rectangle((top_left_x, top_left_y), (bottom_right_x, bottom_right_y), (r, g, b))

    def draw_image(self, image_path_or_object, xy=(0, 0), image_resample_mode=ImageResampleMode.PIXEL_ART, pad_resample=False):
        image = image_path_or_object if isinstance(image_path_or_object, Image.Image) else Image.open(image_path_or_object)
        size = image.size
        width = size[0]
        height = size[1]

        # See if it needs to be scaled/resized to fit the display
        if width > self.size or height > self.size:
            if pad_resample:
                image = ImageOps.pad(image, (self.size, self.size), image_resample_mode)
            else:
                image.thumbnail((self.size, self.size), image_resample_mode)

            if self.debug:
                print(
                    f'[.] Resized image to fit on screen (saving aspect ratio): "{image_path_or_object}" ({width}, {height}) '
                    f'-> ({image.size[0]}, {image.size[1]})')

        # Convert the loaded image to RGB
        rgb_image = image.convert('RGB')

        # Iterate over all pixels in the image that are left and buffer them
        for y in range(image.size[1]):
            for x in range(image.size[0]):
                location = (x, y)
                placed_x = x + xy[0]
                if self.size - 1 < placed_x or placed_x < 0:
                    continue

                placed_y = y + xy[1]
                if self.size - 1 < placed_y or placed_y < 0:
                    continue

                self.draw_pixel((placed_x, placed_y), rgb_image.getpixel(location))

    def draw_image_at_location(self, image_path_or_object, x, y, image_resample_mode=ImageResampleMode.PIXEL_ART):
        self.draw_image(image_path_or_object, (x, y), image_resample_mode)

    def draw_line(self, start_xy, stop_xy, rgb=Palette.WHITE):
        line = set()

        # Calculate the amount of steps needed between the points to draw a nice line
        amount_of_steps = minimum_amount_of_steps(start_xy, stop_xy)

        # Iterate over them and create a nice set of pixels
        for step in range(amount_of_steps):
            if amount_of_steps == 0:
                interpolant = 0
            else:
                interpolant = step / amount_of_steps

            # Add a pixel as a rounded location
            line.add(round_location(lerp_location(start_xy, stop_xy, interpolant)))

        # Draw the actual pixel line
        for pixel in line:
            self.draw_pixel(pixel, rgb)

    def draw_line_from_start_to_stop_rgb(self, start_x, start_y, stop_x, stop_y, r=255, g=255, b=255):
        self.draw_line((start_x, start_y), (stop_x, stop_y), (r, g, b))

    def draw_pixel(self, xy, rgb):
        # If it's not on the screen, we're not going to bother
        if xy[0] < 0 or xy[0] >= self.size or xy[1] < 0 or xy[1] >= self.size:
            if self.debug:
                limit = self.size - 1
                print(f'[!] Invalid coordinates given: ({xy[0]}, {xy[1]}) (maximum coordinates are ({limit}, {limit})')
            return

        # Calculate the index
        index = xy[0] + (xy[1] * self.size)

        # Color it
        self.draw_pixel_at_index(index, rgb)

    def draw_pixel_at_index(self, index, rgb):
        # Validate the index
        if index < 0 or index >= self.pixel_count:
            if self.debug:
                print(f'[!] Invalid index given: {index} (maximum index is {self.pixel_count - 1})')
            return

        # Clamp the color, just to be safe
        rgb = clamp_color(rgb)

        # Move to place in array
        index = index * 3

        self.__buffer[index] = rgb[0]
        self.__buffer[index + 1] = rgb[1]
        self.__buffer[index + 2] = rgb[2]

    def draw_pixel_at_index_rgb(self, index, r, g, b):
        self.draw_pixel_at_index(index, (r, g, b))

    def draw_pixel_at_location_rgb(self, x, y, r, g, b):
        self.draw_pixel((x, y), (r, g, b))

    def draw_text(self, text, xy=(0, 0), rgb=Palette.WHITE):
        for index, character in enumerate(text):
            self.draw_character(character, (index * 4 + xy[0], xy[1]), rgb)

    def draw_text_at_location_rgb(self, text, x, y, r, g, b):
        self.draw_text(text, (x, y), (r, g, b))

    def fill(self, rgb=Palette.BLACK):
        self.__buffer = []
        rgb = clamp_color(rgb)
        for index in range(self.pixel_count):
            self.__buffer.extend(rgb)

    def fill_rgb(self, r, g, b):
        self.fill((r, g, b))

    def get_current_channel(self):
        response = requests.post(self.__url, json.dumps({
            'Command': 'Channel/GetIndex'
            }))
        return response.json()

    def push(self, reload_counter=False):
        if reload_counter:
            self.reload_counter()
        self.__send_buffer()

    def reload_counter(self):
        self.__load_counter()

    def reset_counter(self):
        response = requests.post(self.__url, '{"Command": "Draw/ResetHttpGifId"}')
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)
        else:
            self.__counter = 1
            if self.debug:
                print('[.] Counter reset and stored: ' + str(self.__counter))

    def send_animation(self, pic_list, pic_speed=1000, reload_counter=False):
        if reload_counter:
            self.reload_counter()
        pic_num = len(pic_list)
        update_counter = True
        for pic_offset, pic in enumerate(pic_list):
            self.draw_image(pic)
            self.__send_buffer(pic_num, pic_offset, pic_speed, update_counter)
            update_counter = False

    def send_display_list(self):
        request = {
            'Command' : 'Draw/SendHttpItemList',
            'ItemList' : self.__display_list
        }
        self.__send_request(request)

    def send_text(self, text, xy=(0, 0), color=Palette.WHITE, identifier=1, font=2, width=64,
                  movement_speed=0,
                  direction=TextScrollDirection.LEFT, align=1):

        # Make sure the identifier is valid
        identifier = clamp(identifier, 0, 19)

        response = requests.post(self.__url, json.dumps({
            'Command': 'Draw/SendHttpText',
            'TextId': identifier,
            'x': xy[0],
            'y': xy[1],
            'dir': direction,
            'font': font,
            'TextWidth': width,
            'speed': movement_speed,
            'TextString': text,
            'color': rgb_to_hex_color(color),
            'align': align
        }))

        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)

    def set_brightness(self, brightness):
        brightness = clamp(brightness, 0, 100)
        response = requests.post(self.__url, json.dumps({
            'Command': 'Channel/SetBrightness',
            'Brightness': brightness
        }))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)

    def set_channel(self, channel):
        response = requests.post(self.__url, json.dumps({
            'Command': 'Channel/SetIndex',
            'SelectIndex': int(channel)
        }))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)

    def set_clock(self, clock_id):
        response = requests.post(self.__url, json.dumps({
            'Command': 'Channel/SetClockSelectId',
            'ClockId': clock_id
        }))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)

    def set_countdown(self, status=1, minutes=1, seconds=1):
        self.__send_request({
            'Command': 'Tools/SetTimer',
            'Minute' : minutes,
            'Second' : seconds,
            'Status' : status
        })

    def set_face(self, face_id):
        self.set_clock(face_id)

    def set_screen_switch(self, onoff):
        self.__send_request({
            'Command': 'Channel/OnOffScreen',
            'OnOff': onoff
        })

    def set_scoreboard(self, blue_score=0, red_score=0):
        self.blue_score = blue_score
        self.red_score = red_score
        self.__send_request({
            'Command': 'Tools/SetScoreBoard',
            'BlueScore': blue_score,
            'RedScore': red_score
        })

    def set_stopwatch(self, status):
        self.__send_request({
            'Command' : 'Tools/SetStopWatch',
            'Status' : status
        })

    def set_visualizer(self, equalizer_position):
        response = requests.post(self.__url, json.dumps({
            'Command': 'Channel/SetEqPosition',
            'EqPosition': equalizer_position
        }))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)

    def show_image(self, image_path_or_object, **kwargs):
        self.draw_image(image_path_or_object, **kwargs)
        self.push()

    def show_image_from_url(self, image_url, **kwargs):
        image_object = requests.get(image_url, stream=True).raw
#        if isinstance(image_object, Image.Image):
        if not "pad_resample" in kwargs:
            kwargs["pad_resample"] = True
        self.show_image(image_object, **kwargs)

    def turn_on(self):
        self.set_screen_switch(1)
        
    def turn_off(self):
        self.set_screen_switch(0)

    def update_config(self):
        self.device_config = self.__get_config()
        
    def update_score(self):
        self.set_scoreboard(self.blue_score, self.red_score)

    def __clamp_location(self, xy):
        return clamp(xy[0], 0, self.size - 1), clamp(xy[1], 0, self.size - 1)

    def __error(self, error):
        if self.debug:
            print('[x] Error on request ' + str(self.__counter))
            print(error)

    def __get_config(self):
        response = requests.post(self.__url, json.dumps({
            'Command': 'Channel/GetAllConf'
        }))
        return response.json()
 
    def __load_counter(self):
        response = requests.post(self.__url, '{"Command": "Draw/GetHttpGifId"}')
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)
        else:
            self.__counter = int(data['PicId'])
            if self.debug:
                print('[.] Counter loaded and stored: ' + str(self.__counter))

    def __send_buffer(self, pic_num=1, pic_offset=0, pic_speed=1000, update_counter=True):
        # Encode the buffer to base64 encoding
        base64_bytes = base64.b64encode(bytearray(self.__buffer))

        # Add to the internal counter
        if update_counter:
            self.__counter = self.__counter + 1

        if self.debug:
            print(f'[.] Counter set to {self.__counter}')

        response = requests.post(self.__url, json.dumps({
            'Command': 'Draw/SendHttpGif',
            'PicNum': pic_num,
            'PicWidth': self.size,
            'PicOffset': pic_offset,
            'PicID': self.__counter,
            'PicSpeed': pic_speed,
            'PicData': str(base64_bytes.decode())
        }))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)
        else:
            self.__buffers_send = self.__buffers_send + 1

            if self.debug:
                print(f'[.] Pushed {self.__buffers_send} buffers')

    def __send_request(self, request_dict):
        response = requests.post(self.__url, json.dumps(request_dict))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)


__all__ = (Channel, ImageResampleMode, Pixoo, TextScrollDirection)

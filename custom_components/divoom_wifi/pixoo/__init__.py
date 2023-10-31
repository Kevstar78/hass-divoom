import base64
import json
from enum import IntEnum

import requests
import time
from PIL import Image, ImageOps, ImageDraw, UnidentifiedImageError

from ._colors import Palette
from ._font import retrieve_glyph
from .helpers import url_image_handle
from .simulator import Simulator, SimulatorConfig


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


class Channel(IntEnum):
    FACES = 0
    CLOUD = 1
    VISUALIZER = 2
    CUSTOM = 3
    BLACK_SCREEN = 4


class ImageResampleMode(IntEnum):
    PIXEL_ART = Image.NEAREST
    SMOOTH = Image.LANCZOS


class TextScrollDirection(IntEnum):
    LEFT = 0
    RIGHT = 1


class Pixoo:
    __buffer = []
    __buffers_send = 0
    __counter = 0
    __display_list = []
    __refresh_counter_limit = 32
    __simulator = None
    __command_list = []

    def __init__(self, address, size=64, debug=False, refresh_connection_automatically=True, simulated=False,
                 simulation_config=SimulatorConfig()):
        assert size in [16, 32, 64], \
            'Invalid screen size in pixels given. ' \
            'Valid options are 16, 32, and 64'

        self.refresh_connection_automatically = refresh_connection_automatically
        self.address = address
        self.debug = debug
        self.size = size
        self.simulated = simulated

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

        # Resetting if needed
        if self.refresh_connection_automatically and self.__counter > self.__refresh_counter_limit:
            self.__reset_counter()

        # We're going to need a simulator
        if self.simulated:
            self.__simulator = Simulator(self, simulation_config)

    def add_command(self, command):
        self.__command_list.append(command)

    def add_display_item(self, text='', xy=(0, 0), color=Palette.WHITE, identifier=1, font=2, width=64,
                         movement_speed=0, direction=TextScrollDirection.LEFT, align=1,
                         height=16, display_type=22, url_time=None):
        # for values and meaning of display_type see: http://doc.divoom-gz.com/web/#/12?page_id=234
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

    def clear_command_list(self):
        self.__command_list = []

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

    def draw_character_at_location_rgb(self, character, x=0, y=0, r=255, g=255,
                                       b=255):
        self.draw_character(character, (x, y), (r, g, b))

    def draw_filled_rectangle(self, top_left_xy=(0, 0), bottom_right_xy=(1, 1),
                              rgb=Palette.BLACK):
        for y in range(top_left_xy[1], bottom_right_xy[1] + 1):
            for x in range(top_left_xy[0], bottom_right_xy[0] + 1):
                self.draw_pixel((x, y), rgb)

    def draw_filled_rectangle_from_top_left_to_bottom_right_rgb(self,
                                                                top_left_x=0,
                                                                top_left_y=0,
                                                                bottom_right_x=1,
                                                                bottom_right_y=1,
                                                                r=0, g=0, b=0):
        self.draw_filled_rectangle((top_left_x, top_left_y),
                                   (bottom_right_x, bottom_right_y), (r, g, b))

    def draw_image(self, image_path_or_object, xy=(0, 0),
                   image_resample_mode=ImageResampleMode.PIXEL_ART,
                   pad_resample=False):
        image = image_path_or_object if isinstance(image_path_or_object,
                                                   Image.Image) else Image.open(
            image_path_or_object)
        size = image.size
        width = size[0]
        height = size[1]

        # See if it needs to be scaled/resized to fit the display
        if width > self.size or height > self.size:
            if pad_resample:
                image = ImageOps.pad(image, (self.size, self.size),
                                     image_resample_mode)
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

                self.draw_pixel((placed_x, placed_y),
                                rgb_image.getpixel(location))

    def draw_image_at_location(self, image_path_or_object, x, y,
                               image_resample_mode=ImageResampleMode.PIXEL_ART):
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
            line.add(
                round_location(lerp_location(start_xy, stop_xy, interpolant)))

        # Draw the actual pixel line
        for pixel in line:
            self.draw_pixel(pixel, rgb)

    def draw_line_from_start_to_stop_rgb(self, start_x, start_y, stop_x, stop_y,
                                         r=255, g=255, b=255):
        self.draw_line((start_x, start_y), (stop_x, stop_y), (r, g, b))

    def draw_pixel(self, xy, rgb):
        # If it's not on the screen, we're not going to bother
        if xy[0] < 0 or xy[0] >= self.size or xy[1] < 0 or xy[1] >= self.size:
            if self.debug:
                limit = self.size - 1
                print(
                    f'[!] Invalid coordinates given: ({xy[0]}, {xy[1]}) (maximum coordinates are ({limit}, {limit})')
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

    def get_device_time(self):
        response = requests.post(self.__url, json.dumps({
            'Command': 'Device/GetDeviceTime'
            }))
        return response.json()

    def get_face_id(self):
        response = requests.post(self.__url, json.dumps({
            'Command': 'Channel/GetClockInfo'
            }))
        return response.json()

    def get_weather_info(self):
        response = requests.post(self.__url, json.dumps({
            'Command': 'Device/GetWeatherInfo'
            }))
        return response.json()

    def play_buzzer(self, active_time, off_time, total_time):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Device/PlayBuzzer',
            'ActiveTimeInCycle': active_time,
            'OffTimeInCycle': off_time,
            'PlayTotalTime': total_time
        })

    def play_divoom_gif(self, file_id=''):
        # file_id needs to be determined from img upload list (see helpers.py)
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Draw/SendRemote',
            'FileId': file_id
        })

    def play_gif(self, file_type=0, file_name=''):
        # file_type: 2:play net file; 1:play tf’s folder; 0:play tf’s file
        # file_name (depending on file_type): 2:http address; 1:the folder path; 0:the file path
        self.__send_request({
            'Command': 'Device/PlayTFGif',
            'FileType': file_type,
            'FileName': file_name
        })

    def push(self, reload_counter=False):
        if reload_counter:
            self.__load_counter()
        self.__send_buffer()

    def send_animation(self, pic_list, pic_speed=1000, reload_counter=False):
        if reload_counter:
            self.__load_counter()
        pic_num = len(pic_list)
        update_counter = True
        for pic_offset, pic in enumerate(pic_list):
            self.draw_image(pic)
            self.__send_buffer(pic_num, pic_offset, pic_speed, update_counter)
            update_counter = False

    def send_command_list(self, clear_list=True):
        request = {
            'Command' : 'Draw/CommandList',
            'CommandList' : self.__command_list
        }
        self.__send_request(request)

        if clear_list:
            self.clear_command_list()

    def send_command_file_list(self, file_url):
        self.__send_request({
            'Command': 'Draw/UseHTTPCommandSource',
            'CommandUrl': file_url
        })

    def send_display_list(self, clear_list=True):
        request = {
            'Command' : 'Draw/SendHttpItemList',
            'ItemList' : self.__display_list
        }
        self.__send_request(request)

        if clear_list:
            self.clear_display_list()

    def send_text(self, text, xy=(0, 0), color=Palette.WHITE, identifier=1, font=2, width=64,
                  movement_speed=0, direction=TextScrollDirection.LEFT, align=1,
                  gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        # Make sure the identifier is valid
        identifier = clamp(identifier, 0, 19)

        self.__send_request({
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
        }, gather_command)

    def set_brightness(self, brightness, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        brightness = clamp(brightness, 0, 100)
        self.__send_request({
            'Command': 'Channel/SetBrightness',
            'Brightness': brightness
        }, gather_command)

    def set_channel(self, channel, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Channel/SetIndex',
            'SelectIndex': int(channel)
        }, gather_command)
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)
        
    def set_clock(self, clock_id, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Channel/SetClockSelectId',
            'ClockId': clock_id
        }, gather_command)

    def set_cloud(self, cloud_id, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Channel/CloudIndex',
            'Index': cloud_id
        }, gather_command)

    def set_countdown(self, status=1, minutes=1, seconds=1, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Tools/SetTimer',
            'Minute' : minutes,
            'Second' : seconds,
            'Status' : status
        }, gather_command)

    def set_custom_page(self, index, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Channel/SetCustomPageIndex',
            'CustomPageIndex': index
        }, gather_command)

    def set_custom_channel(self, index, gather_command=False)):
        self.set_custom_page(index)
        self.set_channel(3)
        
    def set_face(self, face_id, gather_command=False):
        self.set_clock(face_id, gather_command)

    def set_high_light_mode(self, high_light_mode=0, gather_command=False):
        # 0:close; 1:open
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Device/SetHighLightMode',
            'Mode': high_light_mode
        }, gather_command)

    def set_hour_mode(self, time_flag=0, gather_command=False):
        # 1:24-hour; 0:12-hour
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Device/SetTime24Flag',
            'Mode': time_flag
        }, gather_command)

    def set_noise_status(self, noise_status, gather_command=False):
        # noise_status: 1:start; 0:stop
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Tools/SetNoiseStatus',
            'NoiseStatus': noise_status
        }, gather_command)

    def set_mirror_mode(self, mirror_mode=0, gather_command=False):
        # mirror_mode: 0:disable; 1:enalbe
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Device/SetMirrorMode',
            'Mode': mirror_mode
        }, gather_command)

    def set_scoreboard(self, blue_score=0, red_score=0, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.blue_score = blue_score
        self.red_score = red_score
        self.__send_request({
            'Command': 'Tools/SetScoreBoard',
            'BlueScore': blue_score,
            'RedScore': red_score
        }, gather_command)

    def set_stopwatch(self, status, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command' : 'Tools/SetStopWatch',
            'Status' : status
        }, gather_command)

    def set_screen(self, on=True, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Channel/OnOffScreen',
            'OnOff': 1 if on else 0
        }, gather_command)

    def set_screen_rotation(self, rotation=0, gather_command=False):
        # rotation_angle: 0:normal, 1:90; 2:180; 3:270 (degree)
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Device/SetScreenRotationAngle',
            'Mode': rotation
        }, gather_command)

    def set_screen_off(self, gather_command=False):
        self.set_screen(False, gather_command)

    def set_screen_on(self, gather_command=False):
        self.set_screen(True, gather_command)

    def set_system_time(self, system_time, gather_command=False):
        # This will set the system time in unix format (seconds since January 1st 1970)
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Device/SetUTC',
            'Utc': system_time
        }, gather_command)

    def set_temperature_mode(self, temperature_mode=0, gather_command=False):
        # temperature_mode: 0:Celsius; 1:Fahrenheit
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Device/SetDisTempMode',
            'Mode': temperature_mode
        }, gather_command)

    def set_time_zone(self, time_zone='GMT+1', gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Sys/TimeZone',
            'TimeZoneValue': time_zone
        }, gather_command)

    def set_visualizer(self, equalizer_position, gather_command=False):
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Channel/SetEqPosition',
            'EqPosition': equalizer_position
        }, gather_command)

    def set_weather_location(self, longitude=0.0, latitude=0.0, gather_command=False):
        # longitude and latitude in degree decimal
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Sys/LogAndLat',
            'Longitude': longitude,
            'Latitude': latitude
        }, gather_command)

    def set_white_balance(self, r, g, b, gather_command=False):
        # Range for r, g, b: 0:100
        # This won't be possible
        if self.simulated:
            return

        self.__send_request({
            'Command': 'Device/SetWhiteBalance',
            'RValue': r,
            'GValue': g,
            'BValue': b
        }, gather_command)

    def show_image(self, image_path_or_object, **kwargs):
        self.draw_image(image_path_or_object, **kwargs)
        self.push()

    def show_image_from_url(self, image_url, **kwargs):
        image = url_image_handle(image_url)
        self.show_image(image, **kwargs)

    def show_albumart(self, image):
        """
        Display album art of currently played album on pixoo device.
        """
        self.show_image(image, pad_resample=True)

    def show_albumart_from_url(self, image):
        self.show_image_from_url(image, pad_resample=True)

    def show_album_and_artist(self, image_path, artist, album, track):
        """
        Displays album art and artist information.
        """
        try:
            org_image = Image.open(image_path)
        except UnidentifiedImageError:
            if self.debug:
                print("No image found")
            return

        image = ImageOps.pad(org_image, (64, 64), Image.NEAREST)
        overlay = Image.new(image.mode, image.size)
        mask = Image.new('L', image.size, 255)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((0,32,64,64), fill=128)
        image = Image.composite(image, overlay, mask)
        self.show_albumart(image)
        time.sleep(.5)
        self.show_artist_info(artist, album, track)
        time.sleep(30)
        self.show_albumart(org_image)

    def show_album_and_artist_from_url(self, image_path, artist, album, track):
        self.show_album_and_artist(url_image_handle(image_path), artist, album, track)

    def show_artist_info(self, artist, album, track):
        """
        Displays information on song, artist, and album.
        """
        self.add_display_item(
            text='{0} - {1}'.format(artist, album), movement_speed=100, xy=(1,32), width=62)
        self.add_display_item(
            text='{0}'.format(track), movement_speed=100, xy=(1,48), width=62, identifier=2)
        self.send_display_list()

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
        # Just assume it's starting at the beginning if we're simulating
        if self.simulated:
            self.__counter = 1
            return

        response = requests.post(self.__url, '{"Command": "Draw/GetHttpGifId"}')
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)
        else:
            self.__counter = int(data['PicId'])
            if self.debug:
                print('[.] Counter loaded and stored: ' + str(self.__counter))

    def __send_buffer(self, pic_num=1, pic_offset=0, pic_speed=1000, update_counter=True):
        # Add to the internal counter
        if update_counter:
            self.__counter = self.__counter + 1

        # Check if we've passed the limit and reset the counter for the animation remotely
        if self.refresh_connection_automatically and self.__counter >= self.__refresh_counter_limit:
            self.__reset_counter()
            self.__counter = 1

        if self.debug:
            print(f'[.] Counter set to {self.__counter}')

        # If it's simulated, we don't need to actually push it to the divoom
        if self.simulated:
            self.__simulator.display(self.__buffer, self.__counter)

            # Simulate this too I suppose
            self.__buffers_send = self.__buffers_send + 1
            return

        # Encode the buffer to base64 encoding
        response = requests.post(self.__url, json.dumps({
            'Command': 'Draw/SendHttpGif',
            'PicNum': pic_num,
            'PicWidth': self.size,
            'PicOffset': pic_offset,
            'PicID': self.__counter,
            'PicSpeed': pic_speed,
            'PicData': str(base64.b64encode(bytearray(self.__buffer)).decode())
        }))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)
        else:
            self.__buffers_send = self.__buffers_send + 1

            if self.debug:
                print(f'[.] Pushed {self.__buffers_send} buffers')

    def __send_request(self, request_dict, gather_command=False):
        if gather_command:
            self.add_command(request_dict)
            return

        response = requests.post(self.__url, json.dumps(request_dict))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)

    def __reset_counter(self):
        if self.debug:
            print(f'[.] Resetting counter remotely')

        # This won't be possible
        if self.simulated:
            return

        response = requests.post(self.__url, json.dumps({
            'Command': 'Draw/ResetHttpGifId'
        }))
        data = response.json()
        if data['error_code'] != 0:
            self.__error(data)


__all__ = (Channel, ImageResampleMode, Pixoo, TextScrollDirection)

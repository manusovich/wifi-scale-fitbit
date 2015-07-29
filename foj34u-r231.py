#!/usr/bin/env python

import logging
import time
import time as time_
import collections
import pygame, sys, os
import bluetooth
import RPi.GPIO as GPIO

from datetime import datetime
from pygame.locals import *
import fitbit as fitbit
from weightprocessor import WeightProcessor, WeightRecord, WeightProcessorConfiguration


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

HOME = "/home/pi"

# initial user's list with their weights and fitbit user keys.
# this map we are using only if we don't have weight history, otherwise last morning
# values will be used to define user
USERS = {"Alex": {'weight': 77,
                  'fitbit_user': os.environ.get('FITBIT_ALEX_ID'),
                  'fitbit_secret': os.environ.get('FITBIT_ALEX_SECRET')},
         "Olya": {'weight': 57},
         "Platon": {'weight': 16}}

# Fitbit client information
FITBIT_CLIENT_ID = os.environ.get('FITBIT_CLIENT_ID')
FITBIT_CLIENT_SECRET = os.environ.get('FITBIT_CLIENT_SECRET')

# initial possible diff in weights for users to define them based on USERS map
# for example if you have here 2 and 77 for alex in the map, we will consider that
# user is alex if we will have 77 - 2 < value < 77 + 2
USERS_MAX_W_DIFF = 2

# after this time we won't anymore check correlation with last morning weight
MAX_PAUSE_BETWEEN_MORNING_CHECKS_IN_DAYS = 5

# difference between two morning weights should not be greater than this value
# if it more, we will consider this value as regular (not morning)
MAX_WEIGHT_DIFF_BETWEEN_MORNING_CHECKS = 2

# time limits for morning values (24 hours period). None if check should not be performed
MORNING_HOURS = None

# path for database file
DB_PATH = HOME + "/weight_db"

CONTINUOUS_REPORTING = "04"  # Easier as string with leading zero

COMMAND_LIGHT = 11
COMMAND_REPORTING = 12
COMMAND_REQUEST_STATUS = 15
COMMAND_REGISTER = 16
COMMAND_READ_REGISTER = 17

# input is Wii device to host
INPUT_STATUS = 20
INPUT_READ_DATA = 21

EXTENSION_8BYTES = 32
# end "hex" values

BUTTON_DOWN_MASK = 8

TOP_RIGHT = 0
BOTTOM_RIGHT = 1
TOP_LEFT = 2
BOTTOM_LEFT = 3

BLUETOOTH_NAME = "Nintendo RVL-WBC-01"

os.environ["SDL_FBDEV"] = "/dev/fb1"

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

WEIGHT_FONT_PATH = HOME + "/OpenSans-Bold.ttf"
WEIGHT_FONT_SIZE = 100

LOG_FILE = HOME + "/scale.log"

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

display = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), 0, 32)
display.fill(BLACK)

pygame.font.init()
font = pygame.font.Font(WEIGHT_FONT_PATH, WEIGHT_FONT_SIZE)

pygame.display.update()

logging.basicConfig(filename=LOG_FILE,
                    format='%(asctime)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    level=logging.DEBUG)


def render_weight(weight, color):
    display.fill(BLACK)
    score_text = font.render(weight, 1, color)
    display.blit(score_text, (60, 30))
    pygame.display.update()


class UserProvider:
    def __init__(self, users_map):
        self.users = users_map

    def all(self):
        return self.users

    def by_name(self, name):
        return USERS[name]

    def weight(self, name):
        return USERS[name]['weight']

    def fitbit_user_id(self, name):
        return USERS[name]['fitbit_user']

    def fitbit_user_secret(self, name):
        return USERS[name]['fitbit_secret']

    def update_weight(self, name, weight):
        USERS[name]['weight'] = weight


class FitbitConnector:
    def __init__(self, client_id, client_key, user_provider):
        self.client_id = client_id
        self.client_key = client_key
        self.user_provider = user_provider

    def log_weight(self, user, weight):
        fitbit_user_id = self.user_provider.fitbit_user_id(user)
        fitbit_user_secret = self.user_provider.fitbit_user_secret(user)

        if fitbit_user_id is None or fitbit_user_secret is None:
            logging.warning("{} doesn't have fitbit keys. Weight will not be saved in fitbit cloud".format(user))
        else:
            logging.debug("Fitbit - saving {} for {}".format(weight, user))
            authd_client = fitbit.Fitbit(self.client_id, self.client_key, resource_owner_key=fitbit_user_id,
                                         resource_owner_secret=fitbit_user_secret)
            # making conversion to pounds
            fitbit_data = {'weight': weight * 2.2046, 'date': datetime.today().strftime("%Y-%m-%d")}
            authd_client._COLLECTION_RESOURCE('body', data=fitbit_data)


class EventProcessor:
    def __init__(self):
        self.measured = False
        self.done = False
        self.events = []
        self.board = None
        self.last_render = 0

    def init_board(self, board):
        self.board = board

    def reset(self):
        self.measured = False
        self.done = False
        self.events = []
        self.last_render = 0

    def mass(self, event):
        if event.totalWeight > 10:
            tnow = int(round(time_.time() * 1000))
            if (tnow - self.last_render) > 500:
                render_weight(str(self.weight + 2), WHITE)
                self.last_render = int(round(time_.time() * 1000))
            self.events.append(event.totalWeight)
            if not self.measured:
                self.board.set_light(True)
                logging.debug("Starting measurement.")
                self.measured = True
        elif self.measured:
            self.done = True

    @property
    def weight(self):
        if not self.events:
            return 0
        histogram = collections.Counter(round(num, 1) for num in self.events)
        return histogram.most_common(1)[0][0]


class BoardEvent:
    def __init__(self, top_left, top_right, bottom_left, bottom_right,
                 button_pressed, button_released):
        self.topLeft = top_left
        self.topRight = top_right
        self.bottomLeft = bottom_left
        self.bottomRight = bottom_right
        self.buttonPressed = button_pressed
        self.buttonReleased = button_released
        # convenience value
        self.totalWeight = top_left + top_right + bottom_left + bottom_right


class Wiiboard:
    def __init__(self, events_processor):
        # Sockets and status
        self.receive_socket = None
        self.control_socket = None

        events_processor.init_board(self)

        self.processor = events_processor
        self.calibration = []
        self.calibrationRequested = False
        self.LED = False
        self.address = None
        self.buttonDown = False
        for i in xrange(3):
            self.calibration.append([])
            for j in xrange(4):
                # high dummy value so events with it don't register
                self.calibration[i].append(10000)

        self.status = "Disconnected"
        self.lastEvent = BoardEvent(0, 0, 0, 0, False, False)

        try:
            self.receive_socket = bluetooth.BluetoothSocket(bluetooth.L2CAP)
            self.control_socket = bluetooth.BluetoothSocket(bluetooth.L2CAP)
        except ValueError:
            raise Exception("Error: Bluetooth not found")

    def is_connected(self):
        return self.status == "Connected"

    # Connect to the Wiiboard at bluetooth address <address>
    def connect(self, address):
        if address is None:
            logging.debug("Non existent address")
            return
        self.receive_socket.connect((address, 0x13))
        self.control_socket.connect((address, 0x11))
        if self.receive_socket and self.control_socket:
            logging.debug("Connected to Wiiboard at address " + address)
            self.status = "Connected"
            self.address = address
            self.calibrate()
            use_ext = ["00", COMMAND_REGISTER, "04", "A4", "00", "40", "00"]
            self.send(use_ext)
            self.set_reporting_type()
            logging.debug("Wiiboard connected")
        else:
            logging.debug(
                "Could not connect to Wiiboard at address " + address)

    def receive(self):
        while self.status == "Connected" and not self.processor.done:
            data = self.receive_socket.recv(25)
            in_type = int(data.encode("hex")[2:4])
            if in_type == INPUT_STATUS:
                self.set_reporting_type()
            elif in_type == INPUT_READ_DATA:
                if self.calibrationRequested:
                    packet_length = (
                        int(str(data[4]).encode("hex"), 16) / 16 + 1)
                    self.parse_calibration_response(data[7:(7 + packet_length)])

                    if packet_length < 16:
                        self.calibrationRequested = False
            elif in_type == EXTENSION_8BYTES:
                self.processor.mass(self.create_board_event(data[2:12]))
            else:
                logging.debug("ACK to data write received")

    def disconnect(self):
        if self.status == "Connected":
            self.status = "Disconnecting"
            while self.status == "Disconnecting":
                self.wait(100)

        try:
            self.receive_socket.close()
        except:
            pass

        try:
            self.control_socket.close()
        except:
            pass

        logging.debug("WiiBoard disconnected")

    # Try to discover a Wiiboard
    def discover(self):
        logging.debug("Press the red sync button on the board now")
        address = None
        bluetooth_devices = bluetooth.discover_devices(
            duration=6, lookup_names=True)
        for bluetooth_device in bluetooth_devices:
            if bluetooth_device[1] == BLUETOOTH_NAME:
                address = bluetooth_device[0]
                logging.debug("Found Wiiboard at address " + address)
        if address is None:
            logging.debug("No Wiiboards discovered.")
        return address

    def create_board_event(self, data):
        button_bytes = data[0:2]
        data = data[2:12]
        button_pressed = False
        button_released = False

        state = (int(button_bytes[0].encode("hex"), 16) << 8) | int(
            button_bytes[1].encode("hex"), 16)
        if state == BUTTON_DOWN_MASK:
            button_pressed = True
            if not self.buttonDown:
                logging.debug("Button pressed")
                self.buttonDown = True

        if not button_pressed:
            if self.lastEvent.buttonPressed:
                button_released = True
                self.buttonDown = False
                logging.debug("Button released")

        raw_tr = (int(data[0].encode("hex"), 16) << 8) + \
                 int(data[1].encode("hex"), 16)
        raw_br = (int(data[2].encode("hex"), 16) << 8) + \
                 int(data[3].encode("hex"), 16)
        raw_tl = (int(data[4].encode("hex"), 16) << 8) + \
                 int(data[5].encode("hex"), 16)
        raw_bl = (int(data[6].encode("hex"), 16) << 8) + \
                 int(data[7].encode("hex"), 16)

        return BoardEvent(self.calc_mass(raw_tl, TOP_LEFT),
                          self.calc_mass(raw_tr, TOP_RIGHT),
                          self.calc_mass(raw_bl, BOTTOM_LEFT),
                          self.calc_mass(raw_br, BOTTOM_RIGHT),
                          button_pressed, button_released)

    def calc_mass(self, raw, pos):
        val = 0.0
        # calibration[0] is calibration values for 0kg
        # calibration[1] is calibration values for 17kg
        # calibration[2] is calibration values for 34kg
        if raw < self.calibration[0][pos]:
            return val
        elif raw < self.calibration[1][pos]:
            val = 17 * \
                  ((raw - self.calibration[0][pos]) /
                   float((self.calibration[1][pos] - self.calibration[0][pos])))
        elif raw > self.calibration[1][pos]:
            val = 17 + 17 * \
                       ((raw - self.calibration[1][pos]) /
                        float((self.calibration[2][pos] - self.calibration[1][pos])))

        return val

    def get_last_event(self):
        return self.lastEvent

    def get_led(self):
        return self.LED

    def parse_calibration_response(self, data):
        index = 0
        if len(data) == 16:
            for i in xrange(2):
                for j in xrange(4):
                    self.calibration[i][j] = (int(data[index].encode("hex"), 16) << 8) + int(
                        data[index + 1].encode("hex"), 16)
                    index += 2
        elif len(data) < 16:
            for i in xrange(4):
                self.calibration[2][i] = (int(data[index].encode("hex"), 16) << 8) + int(
                    data[index + 1].encode("hex"), 16)
                index += 2

    # Send <data> to the Wiiboard
    # <data> should be an array of strings, each string representing a single hex byte
    def send(self, data):
        if self.status != "Connected":
            return
        data[0] = "52"

        send_data = ""
        for byte in data:
            byte = str(byte)
            send_data += byte.decode("hex")

        self.control_socket.send(send_data)

    # Turns the power button LED on if light is True, off if False
    # The board must be connected in order to set the light
    def set_light(self, light):
        if light:
            val = "10"
        else:
            val = "00"

        message = ["00", COMMAND_LIGHT, val]
        self.send(message)
        self.LED = light

    def calibrate(self):
        message = ["00", COMMAND_READ_REGISTER,
                   "04", "A4", "00", "24", "00", "18"]
        self.send(message)
        self.calibrationRequested = True

    def set_reporting_type(self):
        data = ["00", COMMAND_REPORTING, CONTINUOUS_REPORTING, EXTENSION_8BYTES]
        self.send(data)

    def wait(self, millis):
        time.sleep(millis / 1000.0)


def main():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(4, GPIO.OUT)
    GPIO.output(4, GPIO.LOW)
    time.sleep(3)
    GPIO.cleanup()

    events_processor = EventProcessor()
    board = Wiiboard(events_processor)

    if len(sys.argv) == 1:
        logging.debug("Discovering board...")
        address = board.discover()
    else:
        address = sys.argv[1]

    logging.debug("Trying to connect...")
    board.connect(address)  # The wii board must be in sync mode at this time
    board.set_light(False)

    WeightProcessor.db_path = DB_PATH
    configuration = WeightProcessorConfiguration(MAX_PAUSE_BETWEEN_MORNING_CHECKS_IN_DAYS,
                                                 MAX_WEIGHT_DIFF_BETWEEN_MORNING_CHECKS,
                                                 USERS_MAX_W_DIFF,
                                                 MORNING_HOURS)

    user_provider = UserProvider(USERS)
    weight_processor = WeightProcessor(configuration,
                                       user_provider,
                                       FitbitConnector(FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET, user_provider))

    while 1 == 1:
        events_processor.reset()
        board.receive()

        weight = events_processor.weight + 2
        render_weight(str(weight), GREEN)

        weight_record = WeightRecord({'year': datetime.today().year,
                                      'month': datetime.today().month,
                                      'day': datetime.today().day,
                                      'w': weight})

        weight_processor.process(weight_record)

        time.sleep(2)

        board.set_light(False)

        display.fill(BLACK)
        pygame.display.update()

        logging.debug('Ready for next job')


if __name__ == "__main__":
    main()

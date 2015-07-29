from datetime import datetime
import logging

from weightprocessor import WeightProcessor, WeightRecord, WeightProcessorConfiguration


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# initial user's list with their weights and fitbit user keys.
# this map we are using only if we don't have weight history, otherwise last morning
# values will be used to define user
USERS = {"Alex": {'weight': 77, 'fitbit_user': "userId", 'fitbit_key': "userKey"},
         "Olya": {'weight': 57},
         "Platon": {'weight': 16}}

# Fitbit client information
FITBIT_CLIENT_ID = None
FITBIT_CLIENT_SECRET = None

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
MORNING_HOURS = (5,12)

# path for database file
DB_PATH = "./weight_db"

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #



logging.basicConfig(format='%(asctime)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    level=logging.DEBUG)

class UserProvider:
    def __init__(self, users_map):
        self.users = users_map

    def all(self):
        return self.users

    def by_name(self, name):
        return USERS[name]

    def weight(self, name):
        return USERS[name]['weight']

    def update_weight(self, name, weight):
        USERS[name]['weight'] = weight


class FitbitConnector:
    def __init__(self, client_id, client_key):
        self.client_id = client_id
        self.client_key = client_key

    def log_weight(self, user, weight):
        logging.debug("Fitbit - saving {} for {}".format(weight, user))


WeightProcessor.db_path = DB_PATH
configuration = WeightProcessorConfiguration(MAX_PAUSE_BETWEEN_MORNING_CHECKS_IN_DAYS,
                                             MAX_WEIGHT_DIFF_BETWEEN_MORNING_CHECKS,
                                             USERS_MAX_W_DIFF,
                                             MORNING_HOURS)

processor = WeightProcessor(configuration,
                            UserProvider(USERS),
                            FitbitConnector(FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET))

record = WeightRecord({'year': datetime.today().year,
                       'month': datetime.today().month,
                       'day': datetime.today().day,
                       'w': 76.3})

processor.process(record)

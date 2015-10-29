import logging
import json

from datetime import date, datetime


def get_first_func(iterable, default=None):
    if iterable:
        for i in iterable:
            return i
    return default


def diff_dates_func(date1, date2):
    return abs(date2 - date1).days


class WeightProcessorConfiguration:
    def __init__(self, max_pause_for_morning_checks_days, max_morning_weight_diff,
                 max_weight_diff_to_define_user, morning_hours):
        self._max_pause_for_morning_checks_days = max_pause_for_morning_checks_days
        self._max_morning_weight_diff = max_morning_weight_diff
        self._max_weight_diff_to_define_user = max_weight_diff_to_define_user
        self._morning_hours = morning_hours

    def max_pause_for_morning_checks_days(self):
        return self._max_pause_for_morning_checks_days

    def max_morning_weight_diff(self):
        return self._max_morning_weight_diff

    def max_weight_diff_to_define_user(self):
        return self._max_weight_diff_to_define_user

    def morning_hours(self):
        return self._morning_hours


class WeightProcessor:
    def __init__(self, data, configuration, users_provider, fitbit=None):
        self.data = data
        self.configuration = configuration
        self.users_provider = users_provider
        self.fitbit = fitbit
        self.update_users_map()

    # update user's weights in USER structure
    def update_users_map(self):
        for user in self.users_provider.all():
            last_user_record = self.data.last(user)
            if last_user_record is not None:
                self.users_provider.update_weight(user, last_user_record.w)

    def process_new_morning_record(self, today_morning, last_morning=None):
        logging.debug("Saving as morning value")

        if last_morning is not None:
            last_morning.last = False
            self.data.save(last_morning)

        today_morning.last = True
        today_morning.morning = True
        self.data.save(today_morning)

        if self.fitbit is not None:
            self.fitbit.log_weight(today_morning.user, today_morning.w)

    def process_new_regular_record(self, data):
        logging.debug("Saving as regular value")

        data.morning = False
        data.last = False
        self.data.save(data)

    def check_for_morning_value(self, data, last_morning):
        d1 = date(data.year, data.month, data.day)
        d2 = date(last_morning.year, last_morning.month, last_morning.day)
        diff_date = diff_dates_func(d1, d2)
        diff_w = data.w - last_morning.w

        logging.debug(
            "Compare with last: Date diff {} Weight diff {}".format(diff_date, diff_w))

        return diff_date < self.configuration.max_pause_for_morning_checks_days() \
               and diff_w > self.configuration.max_morning_weight_diff()

    def get_user_by_weight(self, w):
        diff_to_define_user = self.configuration.max_weight_diff_to_define_user()

        for user in self.users_provider.all():
            map_weight = self.users_provider.weight(user)
            if map_weight - diff_to_define_user <= w <= map_weight + diff_to_define_user:
                return user

        return None

    def process(self, data):
        user = self.get_user_by_weight(data.w)
        morning_flow = True

        if user is not None:
            logging.debug("User {} matching to {} kg".format(user, data.w))
            data.user = user
        else:
            # in case if we can't define user, we are saving weight for generic user and not
            # doing any other flows
            logging.warn("Nobody is matching to {} kg".format(data.w))
            data.user = 'User'
            morning_flow = False

        hour = datetime.today().hour
        if self.configuration.morning_hours() is None or not (
                        self.configuration.morning_hours()[0] <= hour <= self.configuration.morning_hours()[1]):
            logging.debug("Morning flow will not be executed because of hours limit")
            morning_flow = False

        if morning_flow:
            logging.info("MF {}".format(json.dumps(data)))
            today_morning = self.data.today_morning(data)
            last_morning = self.data.last_morning(data)

            if today_morning is None and last_morning is None:
                # if we don't have any records for this day and none for previous, just record this value as
                # first morning
                logging.info("Wow, your first value in db! Saving that")
                self.process_new_morning_record(data)

            elif today_morning is None and last_morning is not None:
                # if we don't have morning record for today but we have for last_morning 5 days, we should check the diff
                # between last_morning morning and today morning. We should not accept diff in w greater than 2
                if self.check_for_morning_value(data, last_morning):
                    logging.warn(
                        "Weight diff is too significant to be consider as morning weight. "
                        "Will be recorded as regular")
                    data.morning = False
                    self.data.save(data)
                else:
                    logging.info("Saving as morning weight for today")
                    self.process_new_morning_record(data, last_morning)

            elif today_morning is not None and last_morning is not None:
                # in situation when we already log morning value, when we have new data, we just saving that as
                # regular data

                logging.info("We already have morning value. Saving new one as regular")
                self.process_new_regular_record(data)
        else:
            self.process_new_regular_record(data)

        self.data.commit()

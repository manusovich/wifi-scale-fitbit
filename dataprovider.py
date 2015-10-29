from blitzdb import FileBackend, Document
import logging

def get_first_func(iterable, default=None):
    if iterable:
        for i in iterable:
            return i
    return default


class WeightRecord(Document):
    pass


class DataProvider:
    def __init__(self, db_path):
        self.db = FileBackend(db_path)

    def last(self, user):
        get_first_func(self.db.filter(WeightRecord, {'user': user, 'last': True}))

    def all_mornings(self, user):
        db_filter = self.db.filter(WeightRecord, {'user': user, 'morning': True})
        return db_filter

    def last_morning(self, data):
        db_filter2 = self.db.filter(WeightRecord, {'last': True, 'morning': True, 'user': data.user})

        if db_filter2:
            count = sum(1 for r in db_filter2)
            logging.debug("LMDB 0 '{}'".format(count))

        logging.debug("LMDB1 '{}'".format(db_filter2))
        logging.debug("LMDB2 '{}'".format(data.user))

        get_first_func(db_filter2)

    def today_morning(self, data):
        logging.debug("TMDB {}".format({
            'year': data.year, 'month': data.month, 'day': data.day, 'user': data.user, 'morning': True}))

        get_first_func(self.db.filter(WeightRecord, {
            'year': data.year, 'month': data.month, 'day': data.day, 'user': data.user, 'morning': True}))

    def save(self, record):
        record.save(self.db)

    def commit(self):
        self.db.commit()

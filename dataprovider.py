from blitzdb import FileBackend, Document


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
        return get_first_func(self.db.filter(WeightRecord, {'user': user, 'last': True}))

    def all_mornings(self, user):
        db_filter = self.db.filter(WeightRecord, {'user': user, 'morning': True})
        #if db_filter:
        #    for i in db_filter:
        #        logging.debug("T0 {}".format(i.time))
        sor = sorted(db_filter, key=lambda x: x.time, reverse=False)
        #if sor:
        #    for i in sor:
        #       logging.debug("T1 {}".format(i.time))
        return sor

    def last_morning(self, data):
        return get_first_func(self.db.filter(WeightRecord, {
            'last': True, 'morning': True, 'user': data.user}))

    def today_morning(self, data):
        return get_first_func(self.db.filter(WeightRecord, {
            'year': data.year, 'month': data.month, 'day': data.day, 'user': data.user, 'morning': True}))

    def save(self, record):
        record.save(self.db)

    def commit(self):
        self.db.commit()

from blitzdb import FileBackend, Document


def get_first_func(iterable, default=None):
    if iterable:
        for i in iterable:
            return i
    return default


class WeightRecord(Document):
    pass


class DataProvider:
    db_path = "./db"

    def __init__(self):
        self.db = FileBackend(self.db_path)

    def last(self, user):
        get_first_func(self.db.filter(WeightRecord, {'user': user, 'last': True}))

    def all(self, user):
        self.db.get(WeightRecord, {'user': user})

    def last_morning(self, data):
        get_first_func(self.db.filter(WeightRecord, {
            'last': True, 'morning': True, 'user': data.user}))

    def today_morning(self, data):
        get_first_func(self.db.filter(WeightRecord, {
            'year': data.year, 'month': data.month, 'day': data.day, 'user': data.user, 'morning': True}))

    def save(self, record):
        record.save(self.db)

    def commit(self):
        self.db.commit()

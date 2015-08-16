#!/usr/bin/env python

from pygame.locals import *
from dataprovider import WeightRecord, DataProvider

data = DataProvider()
all_records = data.get_db().filter(WeightRecord, {'last': True, 'morning': True, 'user': 'Alex'})
print all_records

count = sum(1 for r in all_records)
print count

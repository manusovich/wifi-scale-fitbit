#!/usr/bin/env python

from pygame.locals import *
from dataprovider import WeightRecord, DataProvider

DataProvider.db_path = "/home/pi/weight_db"

data = DataProvider()
all_records = data.all("Alex")
print all_records

count = sum(1 for r in all_records)
print count

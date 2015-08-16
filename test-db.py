#!/usr/bin/env python

from pygame.locals import *
from dataprovider import WeightRecord, DataProvider

data = DataProvider("/home/pi/weight_db")
all_records = data.all("Alex")
print all_records

count = sum(1 for r in all_records)
print count

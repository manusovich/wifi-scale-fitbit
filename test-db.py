#!/usr/bin/env python

from pygame.locals import *
from dataprovider import WeightRecord, DataProvider

data = DataProvider()
all_records = data.last("Alex")
print all_records

count = sum(1 for r in all_records)
print count

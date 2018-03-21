import os
import sys 
sys.stdout.flush()
import glob
import json
import gc
import numpy as np
import utm

from math import isnan

from datetime import datetime, timedelta

## CONFIG ##
file_path = '/tmp/sam_kol.dat'
output_path = 'oceancirculatin_tide_visualisation.data'
date = datetime(day=1, month=1, year=2018) # GMT
timestep = timedelta(days=0, hours=2, minutes=0)
UTM_ZONE = 45 
NODE_COUNT = 68604
ELEMENT_COUNT = 134659
## CONFIG ##

NODES = [[] for i in range(0, NODE_COUNT+1)]

START = datetime.now()

def visualisation():
	global date
	global START
	global NODES

	with open(output_path, 'a') as o:
		with open(file_path, 'r') as f:
			print 'PROCESSING: '+str(file_path)

			node = 0
			element = 0
			for line in f:
				line = line.strip().split(' ')
				if len(line)==11: # NODE
					try:
						line = [float(i) for i in line]
						node += 1
						lng, lat = utm.to_latlon(line[0], line[1], UTM_ZONE, 'U')
						depth = line[2]
						NODES[node] = [lng, lat, depth]
					except Exception, e:
						print e
				elif len(line)==3: # ELEMENT
					try:
						line = [int(i) for i in line]
						element += 1
						polygon = {'type': 'Polygon', 'coordinates': [[NODES[n][:-1] for n in line]]}
						polygon['coordinates'][0] += [polygon['coordinates'][0][0]]   
						depth = np.mean([NODES[n][-1] for n in line])
						output_line = json.dumps(polygon)+'$$'+str(depth)
						o.write(output_line+'\n')
					except Exception, e:
						print e

				if node and node%NODE_COUNT==0:
					node = 0
				if element and element%ELEMENT_COUNT==0:
					element = 0
					NODES = []
					date += timestep
					break

if __name__ == '__main__':
	visualisation()
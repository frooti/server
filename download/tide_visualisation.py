import sys 
sys.path.append('/home/dataraft/projects/oceandb')
sys.stdout.flush()

import scipy.io
from shapely.geometry import asShape, mapping
from statistics import mean
from download.models import zone, tide, tide_visualisation
from datetime import datetime, timedelta

## CONFIG ##
grid_file = '/rawdata/tide/jan/water_level_Jan_1.mat'
## CONFIG ##

MAT = scipy.io.loadmat(grid_file)
LNG = MAT['data']['X'][0][0]
LAT = MAT['data']['Y'][0][0]
GRID = MAT['data']['X'][0][0].shape

def visualisation():
	elements = []
	for i in range(0, GRID[0]):
		for j in range(0, GRID[1]):
			if i!=GRID[0]-1 and j!=GRID[1]-1:
				p1 = [round(float(LNG[i][j]), 3), round(float(LAT[i][j]), 3)]
				p2 = [round(float(LNG[i][j+1]), 3), round(float(LAT[i][j+1]), 3)]
				p3 = [round(float(LNG[i+1][j+1]), 3), round(float(LAT[i+1][j+1]), 3)]
				p4 = [round(float(LNG[i+1][j]), 3), round(float(LAT[i+1][j]), 3)]
				try:
					polygon = asShape({'type': 'Polygon', 'coordinates': [[p1, p2, p3, p4, p1]]})
					if polygon.is_valid:
						elements.append(polygon)
				except:
					pass

	for z in zone.objects(ztype='zone'):
		print 'PROCESSING: '+str(z.zid)+' '+str(z.name)
		zpolygon = asShape(z.polygon)
		for e in elements:
			if zpolygon.intersects(e):
				print mapping(e)
				points = [t['values'] for t in tide.objects(loc__geo_intersects=mapping(e))]
				
				if points:
					data = []
					for i in range(1,366):
						if data:
							tide_visualisation.objects.insert(data)
							data = []
						values = []
						for p in points:
							try:
								values.append(p[str(i)]['0'])
							except:
								pass

						if values:
							tv = tide_visualisation(zid=z.zid)
							tv.date = datetime(year=2018, month=1, day=1)+timedelta(days=i-1)
							tv.polygon = mapping(e)
							tv.depth = mean(values)
							data.append(tv)
					else:
						if data:
							tide_visualisation.objects.insert(data)
							data = []

if __name__ == '__main__':
	START = datetime.now()
	visualisation()
	print 'TIME: '+str(datetime.now()-START)
	print 'completed!'
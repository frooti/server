import scipy.io
import shapely.geometry import asShape, mapping
from statistics import mean
from download.models import zone, tide, tide_visualisation
from datetime import datetime, timedelta

## CONFIG ##
grid_file = 'current/uv/1.5_jan_current.mat'
## CONFIG ##

MAT = scipy.io.loadmat(grid_file)
LNG = MAT['data']['X'][0][0]
LAT = MAT['data']['Y'][0][0]
GRID = MAT['data']['X'][0][0].shape

def visualisation():
	elements = []
	for i in GRID[0]:
		for j in GRID[1]:
			if i!=GRID[0]-1 and j!=GRID[1]-1:
				p1 = [round(float(LNG[i][j]), 3), round(float(LAT[i][j]), 3)]
				p2 = [round(float(LNG[i][j+1]), 3), round(float(LAT[i][j+1]), 3)]
				p3 = [round(float(LNG[i+1][j+1]), 3), round(float(LAT[i+1][j+1]]), 3)]
				p4 = [round(float(LNG[i+1][j]), 3), round(float(LAT[i+1][j]]), 3)]
				elements.append(asShape({'type': 'Polygon', 'coordinates': [[p1, p2, p3, p4, p1]]}))

	for z in zone.objects(zid='b951a954-f3f7-44f6-80a6-0194cbee50a1'):
		zpolygon = shape(z.polygon)
		for e in elements:
			if e.intersects(zpolygon):
				points = [t for t in tide.objects(loc__geo_intersects=mapping(e))]
				for i in range(1,366):
					values = []
					for p in points:
						values.append(p['values'][str(i)]['0'])

					tv = tide_visualisation(zid=z.zid)
					tv.date = datetime(year=2018, month=1, day=i)
					tv.polygon = mapping(e)
					tv.depth = mean(values)
					tv.save()

if __name__ == '__main__':
	visualisation()
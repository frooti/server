from datetime import datetime, timedelta
from models import bathymetry 

connect('ocean', host='mongodb://localhost:27017/ocean')

## CONFIG ##
file_path = '/tmp/bathy_data'
## CONFIG ##

with open(file_path, 'r') as f:
	for i, r in enumerate(f):
		print i
		values = r.split(',')
		longitute = float(values[0])
		latitude = float(values[1])
		depth = float(values[2])

		loc = {'type': 'Point', 'coordinates': [longitute, latitude]}
		data['set_depth'] = depth
		data['upsert'] = True
		bathymetry.objects(loc=loc).update_one(**data)

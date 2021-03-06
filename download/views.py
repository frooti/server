# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render
from models import zone, zonedata, userzone, order, wave, wavedirection, waveperiod, bathymetry, userbathymetry, shoreline, usershoreline, tide, current, currentdirection, sediment
import boto3
from django.core.mail import EmailMultiAlternatives
from django.views.decorators.csrf import csrf_exempt
from oceandb.auth import User

# Create your views here.
DEFAULT_RESPONSE = '{"status":false, "msg": "bad request."}'

from django.http import HttpResponse, HttpResponseRedirect
import django.contrib.auth as auth
import json, geojson
import uuid
import time
from datetime import datetime, timedelta
import calendar
import dateutil.parser
from decimal import Decimal
import csv
from scipy.spatial import ConvexHull
from math import isnan

ses = boto3.client('ses', region_name='us-east-1')

### CACHE ###
import redis
pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
REDIS = redis.Redis(connection_pool=pool)
### CACHE ###

# utilities
def default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def monthToDate(month):
	from_date = datetime(day=1, month=int(month), year=2015)
	to_date = datetime(day=calendar.monthrange(2015, int(month))[1], month=int(month), year=2015)
	return from_date, to_date

MIN_PRICE = 1000
WAVE_DATAPOINT_PRICE = 1
BATHY_DATAPOINT_PRICE = 1

def login(request):
	res = json.loads(DEFAULT_RESPONSE)
	
	## session check ##
	if request.user:
		res['msg'] = 'session active.'
		res['status'] = True
		res['data'] = {'email': request.user.email, 'subscription_type': request.user.subscription_type, 'subscription_zones': request.user.subscription_zones, 'is_active': request.user.is_active}
		# userzones
		res['data']['userzones'] = [[uz.uzid, uz.polygon] for uz in userzone.objects(email=request.user.email)]
		# projects
		res['data']['projects'] = [[z.zid, z.polygon] for z in zone.objects(ztype='project')]
		return HttpResponse(json.dumps(res, default=default))

	## jugaad ##
	if '_auth_user_id' in request.session:
		request.session.pop('_auth_user_id')

	email = request.GET.get('email', '')
	password = request.GET.get('password', '')

	user = auth.authenticate(request=request, username=email, password=password)
	if user:
		auth.login(request, user)
		res['msg'] = 'login successful.'
		res['status'] = True
		res['data'] = {'email': email, 'subscription_type': user.subscription_type, 'subscription_zones': user.subscription_zones, 'is_active':user.is_active}
		# userzones
		res['data']['userzones'] = [[uz.uzid, uz.polygon] for uz in userzone.objects(email=request.user.email)]
		# projects
		res['data']['projects'] = [[z.zid, z.polygon] for z in zone.objects(ztype='project')]
	else:
		res['msg'] = 'email/password does not match.'
		res['status'] = False
	return HttpResponse(json.dumps(res, default=default))

def logout(request):
	res = json.loads(DEFAULT_RESPONSE)
	auth.logout(request)
	res['msg'] = 'logout successful'
	res['status'] = True
	return HttpResponse(json.dumps(res, default=default))

def signup(request):
	res = json.loads(DEFAULT_RESPONSE)
	email = request.GET.get('email', None)
	password = request.GET.get('password', None)
	organization = request.GET.get('organization', None)
	phone = request.GET.get('phone', None)
	name = request.GET.get('name', None)
	subscription_zones = request.GET.get('subscription_zones', '[]')
	subscription_type = request.GET.get('subscription_type', None)

	if email and password and organization and phone and name and subscription_type:
		try:
			if User.objects(email=email).first():
				res['status'] = False
				res['msg'] = 'email already exists.'
			else:
				if subscription_zones:
					subscription_zones = json.loads(subscription_zones)
				if subscription_type not in ['A', 'B']:
					subscription_type = 'A'
				user = User().create_user(email=email, password=password, organization=organization, phone=phone, name=name, subscription_zones=subscription_zones, subscription_type=subscription_type, subscription_date=datetime.now())
				res['status'] = True
				res['msg'] = 'user registered.'
		except Exception, e:
			print e
			res['status'] = False
			res['msg'] = 'someting went wrong.'
	else:
		res['status'] = False
		res['msg'] = 'Please fill all the form fields.'

	return HttpResponse(json.dumps(res, default=default))

def getZone(request):
	res = json.loads(DEFAULT_RESPONSE)
	try:
		zones = []
		bathymetry = []
		shorelines = []

		for z in zone.objects().exclude('triangles'):
			if z.ztype == 'zone':
				#zones.append({'type':'Feature', 'properties':{'zid':z.zid, 'name':z.name}, 'geometry':z.polygon})
				zones.append({'zid':z.zid, 'name':z.name, 'polygon':z.polygon})
			elif z.ztype == 'bathymetry':
				#bathymetry.append({'type':'Feature', 'properties':{'zid':z.zid, 'name':z.name}, 'geometry':z.polygon})
				bathymetry.append({'zid':z.zid, 'name':z.name, 'polygon':z.polygon})

		for s in shoreline.objects():
			shorelines.append({'lid':s.lid, 'name':s.name, 'line':s.line, 'date':s.date.strftime('%Y-%m-%d')})

		res['zones'] = zones
		res['bathymetry'] = bathymetry
		res['shoreline'] = []
		res['status'] = True
		res['msg'] = 'success' 
	except Exception,e:
		print e
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, separators=(',', ':'), default=default))

def getZoneData(request):
	res = json.loads(DEFAULT_RESPONSE)
	zid = request.GET.get('zid', None)
	month = request.GET.get('month', None)
	day = request.GET.get('day', None)
	try:
		if zid and month and day: # zone
			tri = REDIS.get(zid+'_'+month)
			if tri:
				ztype, tri = tri.split('$')
				tri = json.loads(tri)
			else:
				z = zonedata.objects(zid=zid, month=month).first()
				tri = z.triangles
				ztype = z.ztype
				if ztype=='zone':
					REDIS.set(zid+'_'+month, '{}${}'.format(z.ztype, json.dumps(tri)))
			
			if ztype=='zone':
				for i in range(len(tri)):
					for j in range(len(tri[i])):
						if isinstance(tri[i][j], dict):
							if day in tri[i][j]:
								tri[i][j] = tri[i][j][day]
							else:
								tri[i][j] = None
			if tri:
				res['triangles'] = tri
				res['status'] = True
				res['msg'] = 'success'
		elif zid: # bathymetry
			z = zone.objects(zid=zid).first()
			tri = z.triangles

			if tri:
				res['triangles'] = tri
				res['status'] = True
				res['msg'] = 'success'
	except Exception,e:
		print e
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, separators=(',', ':'), default=default))

def getSedimentData(request):
	res = json.loads(DEFAULT_RESPONSE)
	zid = request.GET.get('zid', None)
	month = request.GET.get('month', None)
	try:
		if zid and month: # zone
			data = {}
			for s in sediment.objects(zid=zid):
				key = json.dumps(s.loc['coordinates'])+'$'+str(s.angle)
				if key in data:
					data[key][int(s.month)] = round(s.value, 2)
				else:
					data[key] = [None] * 13
					data[key][int(s.month)] = round(s.value, 2)

			values = []
			for key in data:
				point = json.loads(key.split('$')[0])
				angle = round(float(key.split('$')[1]), 2)
				value = data[key]
				values.append([point, angle, value])

			res['data'] = values
			res['status'] = True
			res['msg'] = 'success'
	except Exception,e:
		print e
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, default=default))

def getShoreLine(request):
	res = json.loads(DEFAULT_RESPONSE)
	res['shoreline'] = []
	year = int(request.GET.get('year', datetime.now().year))
	try:
		if request.user and year:
			data = []
			from_date = datetime(year=year, month=1, day=1)
			to_date = datetime(year=year, month=12, day=31)
			for usl in usershoreline.objects(email=request.user.email, created_at__gte=from_date, created_at__lte=to_date):
				line = json.loads(json.dumps(usl.line))
				line['properties'] = {}
				line['properties']['lid'] = usl.lid
				line['properties']['name'] = usl.name
				line['properties']['created_at'] = usl.created_at.strftime('%Y-%m-%d')
				data.append(line)
			res['shoreline'] = data
			res['status'] = True
			res['msg'] = 'success'
	except Exception, e:
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, default=default))

def monthToDate(month):
	from_date = datetime(day=1, month=int(month), year=2015)
	to_date = datetime(day=calendar.monthrange(2015, int(month))[1], month=int(month), year=2015)
	return from_date, to_date

def getPrice(data, polygon, month=None):
	datapoints = 0
	if data=='bathymetry':
		month = 1
	if data and polygon and month:
		from_date, to_date = monthToDate(month)
		try:
			if data in ['waveheight', 'waveperiod', 'wavedirection']:
				if data=='waveheight':
					model = wave
				elif data=='wavedirection':
					model = wavedirection
				elif data=='waveperiod':
					model = waveperiod
				
				spatialpoints = model.objects(__raw__={'l':{'$geoWithin':{'$geometry': polygon}}}).count()
				available_days = 0
				sample = model.objects(__raw__={'l':{'$geoWithin':{'$geometry': polygon}}})[0]
				
				while from_date<=to_date:
					day = str(from_date.timetuple().tm_yday)
					try:
						sample.values[day]
						available_days += 1
					except:
						pass
					from_date += timedelta(days=1)

				datapoints = spatialpoints*available_days*4
				price = 0

				if datapoints:
					price = round(MIN_PRICE+(datapoints*WAVE_DATAPOINT_PRICE), 0)
				else:
					price = 0
				return price, datapoints
			elif data == 'bathymetry':
				datapoints = bathymetry.objects(__raw__={'l':{'$geoWithin':{'$geometry': polygon}}}).count()
				price = 0

				if datapoints:
					price = round(MIN_PRICE+(datapoints*BATHY_DATAPOINT_PRICE), 0)
				else:
					price = 0
				return price, datapoints
			elif data in ['tide', 'current', 'currentdirection']:
				if data=='tide':
					model = tide
				elif data=='current':
					model = current
				elif data=='currentdirection':
					model = currentdirection

				spatialpoints = model.objects(__raw__={'l':{'$geoWithin':{'$geometry': polygon}}}).count()
				available_days = 0
				sample = model.objects(__raw__={'l':{'$geoWithin':{'$geometry': polygon}}})[0]

				while from_date<=to_date:
					day = str(from_date.timetuple().tm_yday)
					try:
						sample.values[day]
						available_days += 1
					except:
						pass
					from_date += timedelta(days=1)

				datapoints = spatialpoints*available_days*72
				price = 0

				if datapoints:
					price = round(MIN_PRICE+(datapoints*WAVE_DATAPOINT_PRICE), 0)
				else:
					price = 0
				return price, datapoints			
		except:
			pass
	return -1, 0

def fetchPrice(request):
	res = json.loads(DEFAULT_RESPONSE)
	polygon = request.GET.get('polygon', None)
	data =  request.GET.get('data', None)
	month = request.GET.get('month', None)
	from_date, to_date = monthToDate(month)
	# from_date = request.GET.get('from_date', None)
	# to_date = request.GET.get('to_date', None)
	# try:
	# 	from_date = dateutil.parser.parse(from_date)
	# 	to_date = dateutil.parser.parse(to_date)
	# except:
	# 	from_date = dateutil.parser.parse((datetime.now()-timedelta(days=7)).isoformat())
	# 	to_date = dateutil.parser.parse((datetime.now()+timedelta(days=7)).isoformat())
	user = request.user
	datapoints = 0
	try:
		polygon = json.loads(polygon)
		
		if polygon and data in ['waveheight', 'wavedirection', 'waveperiod', 'bathymetry', 'tide', 'current', 'currentdirection']:
			price, datapoints = getPrice(data, polygon, month)

			res['status'] = True
			res['msg'] = 'success'
			res['datapoints'] = datapoints
			if price>=0:
				res['price'] = '$'+str(price)
			else:
				res['price'] = '$0'
			res['size'] = str(datapoints*34/1024)+' KB'
			if request.user:
				res['email'] = request.user.email
	except Exception, e:
		print e
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, default=default))

def orderData(request):
	res = json.loads(DEFAULT_RESPONSE)
	polygon = request.GET.get('polygon', None)
	data =  request.GET.get('data', None)
	month = request.GET.get('month', None)
	# from_date = request.GET.get('from_date', (datetime(day=1, month=9, year=2017)-timedelta(days=7)).isoformat())
	# to_date = request.GET.get('to_date', (datetime(day=1, month=9, year=2017)+timedelta(days=7)).isoformat())
	
	user = request.user
	email = user.email if user else None
	#organization = request.GET.get('organization', None)

	try:
		polygon = json.loads(polygon)
		# from_date = dateutil.parser.parse(from_date)
		# to_date = dateutil.parser.parse(to_date)

		if email and polygon and data in ['waveheight', 'wavedirection', 'waveperiod', 'bathymetry', 'tide', 'current', 'currentdirection']:
			o = order(oid=str(uuid.uuid4()))
			o.email = user.email
			o.data = data
			o.polygon = polygon
			o.month = month
			# o.from_date = from_date
			# o.to_date = to_date
			price, datapoints = getPrice(data, polygon, month)
			if datapoints>0:
				o.price = price
				o.datapoints = datapoints
				o.save()

				res['status'] = True
				res['msg'] = 'order placed.'

				# email
				# if 'test' not in o.email:
				# 	sub = 'Received Order #'+str(o.oid)
				# 	email_msg = 'Hi, \n We are processing your download request. You will receive the download link within 1 hr. \n\nThank You,\nSamudra Team.'
				# 	from_email = 'ravi@dataraft.in'
				# 	to_email = [o.email]
				# 	cc = ['ravi@dataraft.in']
				# 	msg = EmailMultiAlternatives(sub, email_msg, from_email, to_email, cc=cc)
				# 	msg.send()
				if 'test' not in o.email:
					email_msg = 'Hi, \n We are processing your download request. You will receive the download link within 1 hr. \n\nThank You,\nSamudra Team.'
					email = {
						'Source': 'order@dataraft.in',
						'Destination': {'ToAddresses': [o.email], 'BccAddresses': ['ravi@dataraft.in']},
						'Message': {
							'Subject': {'Data': 'Received Order #'+str(o.oid)},
							'Body': {'Text': {'Data': email_msg}},
						},					
					}
					ses.send_email(**email)
	except Exception, e:
		print e
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, default=default))

def heatMap(request):
	res = json.loads(DEFAULT_RESPONSE)
	timestep = request.GET.get('timestep', '1')

	try:
		f = open('/home/ubuntu/projects/oceandb/download/timestep/timestep'+timestep+'.json')
		res['data'] = f.read()
		res['status'] = True
		res['msg'] = 'success' 
	except Exception,e:
		print e
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, default=default))

@csrf_exempt
def uploadData(request):
	res = json.loads(DEFAULT_RESPONSE)
	if request.user:
		data = request.POST.get('data-type', None)
		f = request.FILES.get('csv-file')
		name = request.POST.get('name', None)
		date = request.POST.get('date', None) # iso format
		if data and f and name and date:
			try:
				if data == 'bathymetry':
					date = dateutil.parser.parse(date)
					if userzone.objects(email=request.user.email, name=name).first(): # unique name check
						res['msg'] = name+' '+'already exists. Please provide a unique zone name.'
						res['status'] = False
						return HttpResponse(json.dumps(res, default=default))
					
					points = []
					points_geojson = []
					for row in csv.reader(f.read().splitlines()):
						try:
							# remove empty cells
							for i, r in enumerate(row):
								row[i] = r.strip()
							for i in range(len(row)):
								if '' in row:
									row.remove('')
							if len(row)!=3:
								continue

							longitude = float(row[1])
							latitude = float(row[0])
							value = float(row[2])
							point = [longitude, latitude]
							points.append(point)
							points_geojson.append([{'type': 'Point', 'coordinates': point}, value])
						except Exception, e:
							res['msg'] = 'There is problem with your data. Please correct it and try again.'
							res['status'] = False
							return HttpResponse(json.dumps(res, default=default))
						
					chull = []
					try: # chull check
						hull = ConvexHull(points)
						for i in hull.vertices:
							chull.append(points[i])
						chull = chull+[chull[0]]
						if not chull:
							res['msg'] = 'Your data does not have a polygon boundary. Please correct it and try again.'
							res['status'] = False
							return HttpResponse(json.dumps(res, default=default))
					except Exception, e:
						res['msg'] = 'Your data does not have a polygon boundary. Please correct it and try again.'
						res['status'] = False
						return HttpResponse(json.dumps(res, default=default))

					# subscribed zone check
					intersection_zones = [z.zid for z in zone.objects(polygon__geo_intersects=[chull], ztype='zone').exclude('triangles')]
					subscribed_zones = request.user.subscription_zones
					if not intersection_zones or list(set(intersection_zones)-set(subscribed_zones)):
						res['msg'] = 'Some of your data is outside your subscribed zone. Please correct it and try again.'
						res['status'] = False
						return HttpResponse(json.dumps(res, default=default))

					# add to database
					uz = userzone(uzid=str(uuid.uuid4()))
					uz.email = request.user.email
					uz.name = name
					uz.ztype = 'bathymetry'
					uz.polygon = {'type':'Polygon', 'coordinates': [chull]}
					uz.date = date
					uz.save()

					data = []
					for p in points_geojson:
						data.append(userbathymetry(loc=p[0], depth=p[1], email=request.user.email, uzid=uz.uzid))
					if data:
						userbathymetry.objects.insert(data)
					
					res['msg'] = 'Data uploaded successfully.'
					res['status'] = True
					return HttpResponse(json.dumps(res, default=default))

				elif data == 'shoreline':
					date = dateutil.parser.parse(from_date)
					if usershoreline.objects(email=request.user.email, name=name).first(): # unique name check
						res['msg'] = name+' '+'already exists. Please provide a unique shoreline name. eg: marina_beach_12/10/2017.'
						res['status'] = False
						return HttpResponse(json.dumps(res, default=default))

					points = []
					for row in csv.reader(f.read().splitlines()):
						try:
							# remove empty cells
							for i, r in enumerate(row):
								row[i] = r.strip()
							for i in range(len(row)):
								if '' in row:
									row.remove('')
							if len(row)!=2:
								continue

							longitude = float(row[1])
							latitude = float(row[0])
							point = (longitude, latitude)
							points.append(point)
						except Exception, e:
							res['msg'] = 'There is problem with your data. Please correct it and try again.'
							res['status'] = False
							return HttpResponse(json.dumps(res, default=default))

					# validate linestring
					try:
						line = geojson.LineString(points)
						if not line.is_valid:
							res['msg'] = 'Your data does not form a line string. Please correct it and try again.'
							res['status'] = False
							return HttpResponse(json.dumps(res, default=default))
					except Exception, e:
						res['msg'] = 'Your data does not form a line string. Please correct it and try again.'
						res['status'] = False
						return HttpResponse(json.dumps(res, default=default))

					# subscribed zone check
					intersection_zones = [z.zid for z in zone.objects(polygon__geo_intersects=json.loads(geojson.dumps(line)), ztype='zone').exclude('triangles')]
					subscribed_zones = request.user.subscription_zones
					if not intersection_zones or list(set(intersection_zones)-set(subscribed_zones)):
						res['msg'] = 'Some of your data is outside your subscribed zone. Please correct it and try again.'
						res['status'] = False
						return HttpResponse(json.dumps(res, default=default))

					# add to database
					usl = usershoreline(lid=str(uuid.uuid4()))
					usl.email = request.user.email
					usl.name = name
					usl.line = json.loads(geojson.dumps(line))
					usl.date = date 
					usl.save()

					res['msg'] = 'Data uploaded successfully.'
					res['status'] = True
					return HttpResponse(json.dumps(res, default=default))

			except Exception, e:
				print e
				res['msg'] = 'Something went wrong.'
				res['status'] = False
	return HttpResponse(json.dumps(res, default=default))

def pointData(request):
	res = json.loads(DEFAULT_RESPONSE)
	point = request.GET.get('point', None)
	data =  request.GET.get('data', None)
	if request.GET.get('warmup', None):
		request.user = User.objects(email='ravi@dataraft.in').first()
	month = request.GET.get('month', '5')
	from_date, to_date = monthToDate(month)

	try:
		point = json.loads(point)

		if request.user and point and data in ['waveheight', 'wavedirection', 'waveperiod', 'bathymetry', 'tide', 'current', 'currentdirection']:
			intersection_zones = [z.zid for z in zone.objects(polygon__geo_intersects=point, ztype__in=['zone', 'project']).exclude('triangles')]
			subscribed_zones = request.user.subscription_zones+request.user.projects
			
			if intersection_zones and not list(set(intersection_zones)-set(subscribed_zones)): # subscribed zone check
				if data in ['waveheight', 'wavedirection', 'waveperiod', 'tide', 'current', 'currentdirection']:
					datapoints = []
					model = wave
					if data=='wavedirection':
						model = wavedirection
					elif data=='waveperiod':
						model = waveperiod
					elif data=='tide':
						model = tide
					elif data=='current':
						model = current
					elif data=='currentdirection':
						model = currentdirection

					p = model.objects(loc__near=point).first()
					if p:
						values = p.values
						while from_date<=to_date:
							day = str(from_date.timetuple().tm_yday)
							try:
								for h in sorted([int(i) for i in values.get(day, {}).keys()]):
									if data=='current' or data=='currentdirection':
										h = int(h)
										hour = str(h/60)
										mins = str(h%60)
										v = values[day][str(h)]
										if not isnan(v) and not v==-99:
											datapoints.append({'d': from_date.strftime('%Y-%m-%d')+'-'+hour+'-'+mins, 'v': v})
									elif data=='tide':
										h = int(h)
										hour = str(h/60)
										mins = str(h%60)
										v = values[day][str(h)]
										if not isnan(v) and not v==-99:
											datapoints.append({'d': from_date.strftime('%Y-%m-%d')+'-'+hour+'-'+mins, 'v': v})
									else:
										h = str(h)
										datapoints.append({'d': from_date.strftime('%Y-%m-%d')+'-'+h+'-0', 'v': values[day][h]})
							except:
								pass
							from_date += timedelta(days=1)
						res['lat'] = p.loc['coordinates'][1]
						res['lng'] = p.loc['coordinates'][0]
					res['status'] = True
					res['msg'] = 'success'
					res['data'] = datapoints
				elif data=='bathymetry':
					data = []
					p = bathymetry.objects(loc__near=point).first()
					if p:
						try:
							data = p.depth
						except:
							pass
						res['lat'] = p.loc['coordinates'][1]
						res['lng'] = p.loc['coordinates'][0]
					res['status'] = True
					res['msg'] = 'success'
					res['data'] = data					
			else:
				res['status'] = False
				res['msg'] = 'Please click inside your subscribed zone.'
	except Exception, e:
		print e
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, default=default))

def visualisation(request):
	res = json.loads(DEFAULT_RESPONSE)
	data = request.GET.get('data', 'waveheight')

	try:
		data = []
		for z in zone.objects():
			data.append([z.zid, z.triangles])
		res['data'] = data
		res['status'] = True
		res['msg'] = 'success'
	except Exception,e:
		print e
		res['status'] = False
		res['msg'] = 'Someting went wrong.'

	return HttpResponse(json.dumps(res, default=default))



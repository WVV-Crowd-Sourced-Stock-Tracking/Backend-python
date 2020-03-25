import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import googlemaps
from math import sin, cos, sqrt, atan2, radians
import time
import datetime as dt
import pygeohash as pgh
import boto3
from decimal import Decimal
import json


app = FastAPI()
app.query_cache = []
app.cache_max_size = 1000


def distance(lat1, lon1, lat2, lon2):
    # approximate radius of earth in km
    R = 6373.0

    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    # we discussed to have all distances in meters
    distance = R * c * 1000

    return distance


def find_query(
        latitude: float, longitude: float, radius: float,
        max_dist: float = 1000, max_age: float = 24):
    """Returns a cached request if it exists otherwise None.

    :param latitude: A latitude value.
    :type latitude: float
    :param latitude: A longitude value.
    :type latitude: float
    :param radius: The radius surrounding the coordinates used in the search.
    :type latitude: float
    :param max_dist: The maximum distance a cached coordinate can be away from the query coordinates.
    :type latitude: float
    :param max_age: A cached result may not be any older than today minus this value measured in hours.
    :type latitude: float
    """
    t0 = time.time()

    # remove all elements too old
    max_age_dt = dt.datetime.now() - dt.timedelta(hours=max_age)
    app.query_cache = [entry for entry in app.query_cache if entry['ts'] > max_age_dt]

    min_dist = float('inf')
    print("Searching %d cached queries" % len(app.query_cache))
    for q in app.query_cache:
        dist = distance(latitude, longitude, q["lat"], q['lng'])
        print(q["lat"], q['lng'], q['radius'], dist)
        if dist < min_dist and radius == q['radius']:
            min_dist = dist
            min_result = q['result']
    print("find_query took %.2f secs" % (time.time() - t0))
    if min_dist < max_dist:
        return min_result
    return None


def add_query_to_cache(latitude, longitude, radius, result):
    app.query_cache.append({
        "lat": latitude,
        "lng": longitude,
        "radius": radius,
        "result": result,
        "ts": dt.datetime.now()
    })



@app.get("/markets")
def read_markets(
        zip_code: str = None, latitude: float = None, longitude: float = None,
        radius: float = 1000):
    print(zip_code, latitude, longitude, radius)

    gmaps = None
    if zip_code is not None:
        #TODO we should verify that it is a valid German zip code
        # we first need to use the Geocoding API to map a German zip to latitude/longitude coordinates
        gmaps = googlemaps.Client(key=os.environ['GOOGLE_MAPS_KEY'])
        results = gmaps.geocode(address='%s+Deutschland' % zip_code)
        if len(results) > 0:
            latitude = results[0]['geometry']['location']['lat']
            longitude = results[0]['geometry']['location']['lng']
        else:
            print("ERROR: could not map ZIP code to coordinates.")
            raise HTTPException(status_code=404, detail="Could not map ZIP code to coordinates.")

    cached_query = find_query(latitude, longitude, radius)

    if cached_query is None:
        if gmaps is None:
            gmaps = googlemaps.Client(key=os.environ['GOOGLE_MAPS_KEY'])
        result = gmaps.places_nearby((latitude, longitude), radius=radius, keyword='supermarkt')
        add_query_to_cache(latitude, longitude, radius, result)

        tbl = boto3.session.Session().resource('dynamodb').Table("supermarket")
        if 'results' in result:
            for market in result['results']:
                item = {
                    'place_id': market["place_id"],
                    'geohash': pgh.encode(
                        market['geometry']['location']['lat'],
                        market['geometry']['location']['lng'], precision=6),
                    # quick and dirty solution to replace all floats bx Decimal objects
                    'result': json.loads(json.dumps(market), parse_float=Decimal)
                }
                tbl.put_item(Item=item)
    else:
        result = cached_query

    markets = []
    if 'results' in result:
        for market in result['results']:

            markets.append({
                "name": market["name"],
                "latitude": market['geometry']['location']['lat'],
                "longitude": market['geometry']['location']['lng'],
                "vicinity": market['vicinity'],
                "id": market["place_id"],
                "distance": distance(latitude, longitude, market['geometry']['location']['lat'], market['geometry']['location']['lng'])
            })
            if 'opening_hours' in market:
                if 'open_now' in market['opening_hours']:
                    markets[-1]['open_now'] = market['opening_hours']['open_now']
                else:
                    print("Did not find open_now in %s" % market['opening_hours'])
    return markets


@app.get("/market")
def read_market(place_id: str):
    print(place_id)
    gmaps = googlemaps.Client(key=os.environ['GOOGLE_MAPS_KEY'])
    response = gmaps.place(place_id=place_id)
    market = {}
    if 'result' in response:
        if 'address_components' in response['result']:
            details = response['result']['address_components']
            for component in details:
                if 'street_number' in component['types']:
                    market['street_number'] = component['short_name']
                elif 'route' in  component['types']:
                    market['route'] = component['short_name']
                elif 'locality' in  component['types']:
                    market['locality'] = component['short_name']
                elif 'postal_code' in  component['types']:
                    market['postal_code'] = component['short_name']
        if 'opening_hours' in response['result'] and 'periods' in response['result']['opening_hours']:
            market['opening_hours'] = {
                'periods': response['result']['opening_hours']['periods']
            }
        if 'icon' in response['result']:
            market['icon'] = response['result']['icon']

    return market


@app.get("/cache/markets/", include_in_schema=False)
def read_cache_markets():
    return app.query_cache

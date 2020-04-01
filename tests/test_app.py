import os
os.environ['GOOGLE_MAPS_KEY'] = 'test'
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import json
import datetime as dt

from app.main import app


client = TestClient(app)


@patch('boto3.session.Session')
@patch('googlemaps.Client')
def test_read_markets_zip_code(patched_client, patched_boto3):
    with open('tests/resources/response_geocode.json') as fp:
        patched_client.return_value.geocode.return_value = json.load(fp)
        with open('tests/resources/response_place_nearbysearch.json') as fp:
            patched_client.return_value.places_nearby.return_value = json.load(fp)

    response = client.get("/markets?zip_code=50933")
    assert response.status_code == 200
    markets = response.json()
    assert len(markets) == 20


@patch('boto3.session.Session')
def test_read_markets_lat_lng(patched_boto3):

    with patch('googlemaps.Client') as patched_client:
        with open('tests/resources/response_place_nearbysearch.json') as fp:
            patched_client.return_value.places_nearby.return_value = json.load(fp)
        response = client.get("/markets?latitude=50.935173&longitude=6.953101")
        assert response.status_code == 200
        markets = response.json()
        assert len(markets) == 20
        assert markets[0]['name'] == 'REWE'
        assert markets[0]['latitude'] == 50.9356314
        assert markets[0]['longitude'] == 6.9565733
        # verify address
        assert markets[0]['vicinity'] == 'Hohe Str. 30, Köln'
        # verify opening hours
        assert markets[0]['open_now'] is True
        # verify id
        assert markets[0]['id'] == "ChIJqQrWBrIlv0cRJJd5f3qooWM"
        # verify distance
        assert abs(markets[0]['distance'] - 248.6) < 1e-1


@patch('boto3.session.Session')
def test_read_markets_radius(patched_boto3):
    client.app.query_cache = []
    with patch('googlemaps.Client') as patched_client:
        response = client.get("/markets?latitude=50.935173&longitude=6.953101")
        assert patched_client.mock_calls[1][2]['radius'] == 1000

    client.app.query_cache = []
    with patch('googlemaps.Client') as patched_client:
        response = client.get("/markets?latitude=50.935173&longitude=6.953101&radius=2000")
        assert patched_client.mock_calls[1][2]['radius'] == 2000


@patch('boto3.session.Session')
def test_read_markets_cached_radius(patched_boto3):
    client.app.query_cache = []
    with patch('googlemaps.Client') as patched_client:
        response = client.get("/markets?latitude=50.935173&longitude=6.953101")
        response = client.get("/markets?latitude=50.935173&longitude=6.953101&radius=2000")
    assert len(client.app.query_cache) == 2


@patch('boto3.session.Session')
def test_cache(patched_boto3):
    client.app.query_cache = []
    with patch('googlemaps.Client') as patched_client:
        response = client.get("/markets?latitude=50.73438&longitude=7.09549")
        # create client, places_nearby, 2x .__contains__
        assert len(patched_client.mock_calls) == 4
        response = client.get("/cache/markets").json()
        assert len(response) == 1

    with patch('googlemaps.Client') as patched_client:
        response = client.get("/markets?latitude=50.73438&longitude=7.10000")
        assert len(patched_client.mock_calls) == 0
        response = client.get("/cache/markets").json()
        assert len(response) == 1


@patch('boto3.session.Session')
def test_cache_max_age(patched_boto3):
    client.app.query_cache = [{
        "lat": 50.73438,
        "lng": 7.09549,
        "radius": 1000,
        "result": [],
        "ts": dt.datetime.now() - dt.timedelta(hours=30)
    }]
    with patch('googlemaps.Client') as patched_client:
        response = client.get("/markets?latitude=50.73438&longitude=7.09549")
        # create client, places_nearby, 2x .__contains__
        assert len(patched_client.mock_calls) == 4
        response = client.get("/cache/markets").json()
        assert len(response) == 1


def test_read_market():
    with patch('googlemaps.Client') as patched_client:
        with open('tests/resources/response_place.json') as fp:
            patched_client.return_value.place.return_value = json.load(fp)
        response = client.get("/market?place_id=ChIJqQrWBrIlv0cRJJd5f3qooWM")
        assert response.status_code == 200
        market = response.json()
        assert market['street_number'] == '30'
        assert market['route'] == 'Hohe Str.'
        assert market['locality'] == 'Köln'
        assert market['postal_code'] == '50667'
        assert type(market['opening_hours']) == dict
        assert 'periods' in market['opening_hours']
        assert market['icon'] == "https://maps.gstatic.com/mapfiles/place_api/icons/shopping-71.png"
        assert market['latitude'] == 50.9356314
        assert market['longitude'] == 6.956573299999999


def test_read_market_zero_periode():
    with patch('googlemaps.Client') as patched_client:
        with open('tests/resources/response_place-zero_periode.json') as fp:
            patched_client.return_value.place.return_value = json.load(fp)
        response = client.get("/market?place_id=ChIJqQrWBrIlv0cRJJd5f3qooWM")
        assert response.status_code == 200
        market = response.json()
        assert len(market['opening_hours']['periods']) == 1

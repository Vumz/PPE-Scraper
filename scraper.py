latitude = 40.8417
longitude = -73.9394
searchRadius = 3200 
locationTypes = ['hardware_store', 'car_repair', 'beauty_salon', 'painter', 'plumber', 'roofing_contractor']
keywords = []
apiKey = 'insert your API key here' 

import pandas as pd
import requests
import json
import time
import numpy as np

finalData = []
urlNearby = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json?'
urlDetails = 'https://maps.googleapis.com/maps/api/place/details/json?'

# latitude longitude offset conversion, dx/dy in meters
def offsetConversion(latitude, longitude, dx, dy):
  earthRadius = 6378137
  latOffset  = latitude + (dy/earthRadius)*(180/np.pi)
  longOffset = longitude + (dx/(earthRadius*np.cos(np.pi*latitude/180)))*(180/np.pi)
  return (latOffset, longOffset)

# get coordinate list for grid searching
def gridCoordinates(latitude, longitude, radius, maxRad):
  if radius <= maxRad:
    return [(latitude, longitude)]
  # width/height of grid search in terms of number of inner circles
  length = int(np.ceil(radius/maxRad))
  # number of total inner circles for grid search + 4 outer corners
  count = np.square(length + 1) + np.square(length)
  coordinates = [(latitude, longitude)]
  # get coordinate list in clockwise order from inner most circle to outer circle layer
  for layer in range(1, length + 1):
    startCoord = coordinates[-1]
    curCoord = offsetConversion(startCoord[0], startCoord[1], -maxRad, maxRad)
    for offset in [(2*maxRad, 0), (0, -2*maxRad), (-2*maxRad, 0), (0, 2*maxRad)]:
      for innerCount in range(layer):
        coordinates.append(offsetConversion(curCoord[0], curCoord[1], offset[0], offset[1]))
        curCoord = coordinates[-1]
  # delete four outer corners
  for corner in range(4):
    del coordinates[(count - 1) - length*corner] 
  return coordinates

# exports data to a csv with the specified name
def export(data, name):
  print('writing to ' + name)
  labels = ['name', 'address', 'phone', 'website', 'search term']
  exportDataframe = pd.DataFrame.from_records(data, columns=labels)
  exportDataframe.to_csv(name)

# determine inner circle search radius
def calcRadius(latitude, longitude, searchRadius, queries, apiKey):
  candidate = {}
  for query in queries:
    candidate[query] = 0
  prevCount = 0
  searchRange = (0, searchRadius)
  radius = searchRadius
  # binary search for radius size where the highest density is between 20 and 50 locations
  while prevCount < 20 or prevCount > 50:
    prevCount = 0
    for query in candidate:
      count = countQuery(query[0], query[1], latitude, longitude, radius, apiKey)
      time.sleep(1)
      if count < 0:
        return -1
      if count >= prevCount:
        candidate[query] = count
        prevCount = count
    for key, value in list(candidate.items()):
      if value < prevCount:
        del candidate[key]
    if prevCount == 0 and radius == searchRadius:
      return 0 
    elif prevCount <= 50 and radius == searchRadius:
      return searchRadius
    elif radius < 100:
      return radius
    elif prevCount < 20:
      searchRange = (radius, searchRange[1])
    elif prevCount > 50:
      searchRange = (searchRange[0], radius)
    else:
      return radius
    radius = searchRange[0] + (searchRange[1] - searchRange[0]) // 2

# count the number of locations in a query
def countQuery(query, term, latitude, longitude, radius, apiKey):
  url = urlNearby+'location='+str(latitude)+','+str(longitude)+'&radius='+str(radius)+'&'+query+'='+term+'&key='+apiKey
  nextPage = True
  count = 0
  # initial API requests to grab top level info
  while nextPage:
    response = requests.get(url)
    jsonObj = json.loads(response.text)
    status = jsonObj['status']
    # API request error handling
    if status != 'OK' and status != 'ZERO_RESULTS':
      print('error: ' + status)
      if status == 'REQUEST_DENIED':
        print('your API key may not be valid')
      return -1
    results = jsonObj['results']
    for result in results:
      count += 1
    # wait time to avoid query limits with google API
    time.sleep(2)
    if 'next_page_token' in jsonObj:
      nextPageToken = jsonObj['next_page_token']
      url = urlNearby+'key='+apiKey+'&pagetoken='+nextPageToken
    else:
      nextPage = False
  return count

# makes API requests and logs contact information
def getContactInfo(query, term, searchRadius, visited, coordinate, radius, apiKey):
  url = urlNearby+'location='+str(coordinate[0])+','+str(coordinate[1])+'&radius='+str(radius)+'&'+query+'='+term+'&key='+apiKey
  nextPage = True
  # initial API requests to grab top level info
  while nextPage:
    response = requests.get(url)
    jsonObj = json.loads(response.text)
    status = jsonObj['status']
    # API request error handling
    if status != 'OK' and status != 'ZERO_RESULTS':
      print('error: ' + status)
      export(finalData, term + str(searchRadius) + 'm_error.csv')
      return False
    results = jsonObj['results']
    for result in results:
      name = result['name']
      place_id = result ['place_id']
      # secondary API requests to grab contact info
      if place_id not in visited:
        visited.add(place_id)
        urlDetail = urlDetails+'place_id='+place_id+'&fields=formatted_address,formatted_phone_number,website&key='+apiKey
        responseDetail = requests.get(urlDetail)
        jsonObjDetail = json.loads(responseDetail.text)
        result = jsonObjDetail['result']
        data = [name]
        for attr in ['formatted_address', 'formatted_phone_number', 'website']:
          if attr in result:
            data.append(result[attr])
          else:
            data.append('n/a')
        data.append(term)
        finalData.append(data)
        # wait time to avoid query limits with google API
        time.sleep(1)
    if 'next_page_token' in jsonObj:
      nextPageToken = jsonObj['next_page_token']
      url = urlNearby+'key='+apiKey+'&pagetoken='+nextPageToken
    else:
      nextPage = False
  return True

# main function to scrape google maps for locations matching search criteria and writing to a csv file
def dataExtract(latitude, longitude, searchRadius, locationTypes, keywords, apiKey):
  # input error handling
  if type(locationTypes) != list:
    print('error: please enter location types in a list')
    return
  if type(keywords) != list:
    print('error: please enter keywords in a list')
    return
  elif type(latitude) != float or type(longitude) != float:
    print('error: please enter a float value for latitude and longitude')
    return
  elif type(searchRadius) != int or searchRadius < 0:
    print('error: please enter a positive integer for the search radius')
    return
  elif type(apiKey) != str or apiKey == '':
    print('error: please enter a valid API key')
    return
  # determine all search parameters for inner query zones
  visited = set()
  queries = []
  for t in locationTypes:
    queries.append(('type', t))
  for keyword in keywords:
    queries.append(('keyword', keyword))
  radius = calcRadius(latitude, longitude, searchRadius, queries, apiKey)
  if radius < 0:
    return 
  if radius == 0:
    print('no locations found, try with a bigger search radius')
    return
  coordinates = gridCoordinates(latitude, longitude, searchRadius, radius)
  print('collecting search results...')
  progress = 0
  # get contact information for all locations matching specified critera
  for coordinate in coordinates:
    for query in queries:
      if getContactInfo(query[0], query[1], searchRadius, visited, coordinate, radius, apiKey) == False:
        return 
      time.sleep(1)
    progress += 1
    print(str(progress) + '/' + str(len(coordinates)) + ' zones')
  #export collected data to a csv
  if locationTypes:
    export(finalData, locationTypes[-1] + str(searchRadius) + 'm.csv')
  elif keywords:
    export(finalData, keywords[-1] + str(searchRadius) + 'm.csv')
  print('search complete!')

dataExtract(latitude, longitude, searchRadius, locationTypes, keywords, apiKey)
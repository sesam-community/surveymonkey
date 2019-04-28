# surveymonkey
Sesam connector for surveymonkey API

[![Build Status](https://travis-ci.org/sesam-community/surveymonkey.svg?branch=master)](https://travis-ci.org/sesam-community/surveymonkey)

### Features

* **Rate-limit handling** : delays or rejects requests depending on the comparison of remaining limit ratio and configured thresholds  
* **Implicit paging** : pages implicitly and returns all pages in 1 response (optionally by streaming)
* **Sesamification of entities** : able to add _id or _updated ot entities
* **Fetching via http transform** : implements http transform to traverse within entity hierarchy. Any field in the input to the transform can be refered to by {{_filed_name_}} in the url. See example below.
* **Streaming option** : optional streams the fetched content. Notice that streaming will prevent pipe runs to swallow errors as it always returns HTTP-200 in the response header but will eliminate memory problems and enable continuity in fetches.

* **minimalreportingdata** : a special url path _minimalreportingdata_ will return the minimal reporting data in one request. In the response there will be survey details, collectors, and response data. It supports


#### Environment Variables

| NAME       | Description       | Is Mandatory   | Default value   |
|:-----------|:-----------------|---------------:|----------------:|
| SURVEYMONKEY_ACCESS_TOKEN_LIST / SURVEYMONKEY_ACCESS_TOKEN | list of access tokens one for each account / a string of single account token, respectively. |Y| N/A|
| SURVEYMONKEY_URL | surveymonkey base url up to API call path |Y| N/A|
| LOGLEVEL | loglevel for the service |N| Info|
| PER_PAGE | page size for the paged API calls |N| 1000|
| THRESHOLD_FOR_REQUEST_REJECTION_MINUTE | ratio of "remaining/minute-limit". Once reached requests will be rejected |N| 0.1|
| THRESHOLD_FOR_REQUEST_REJECTION_DAY | ratio of "remaining/day-limit". Once reached requests will be rejected |N| 0.1|
| THRESHOLD_FOR_DELAYED_RESPONSE_MINUTE | ratio of "remaining/minute-limit". Once reached requests will be delayed by remaining/time_to_reset |N| 0.3|
| THRESHOLD_FOR_DELAYED_RESPONSE_DAY | ratio of "remaining/day-limit". Once reached requests will be delayed by remaining/time_to_reset |N| 0.3|



#### query parameters

Query parameters defined by [surveymonkey API](https://developer.surveymonkey.com/api/v3/) are passed over.
Additionaly, following parameters are defined by this microservice:

| NAME       | Description       | Is Mandatory   | Default value   |
|:-----------|:-----------------|---------------:|----------------:|
| _id_src | source field for _id |N| N/A|
| _updated_src | source field for _updated |N| N/A|
| _do_stream | flag to enable/disable streaming. Set to _1_ for enabling, any other value otherwise|N| 0|
| since | sesam pull protocol's since value. Gets renamed to _start_modified_at_ |N| N/A|
| limit | accepted but ignored. use _page_size_ and _page_ instead |N| N/A|


### Examples

##### system
```{
    "_id": "surveymonkey-proxy-service",
    "type": "system:microservice",
    "connect_timeout": 60,
    "docker": {
        "environment": {
            "LOGLEVEL": "DEBUG",
            "SURVEYMONKEY_ACCESS_TOKEN_LIST": ["$SECRET(surveymonkey_access_token1)", "$SECRET(surveymonkey_access_token2)"],
            "SURVEYMONKEY_URL": "$ENV(surveymonkey_baseurl)"
        },
        "image": "sesamcommunity/surveymonkey:v1.0",
        "port": 5000
    },
    "read_timeout": 7200
}
```
##### pipe source examples
```
...
{
  "type": "json",
  "system": "surveymonkey-proxy-service",
  "is_chronological": true,
  "is_since_comparable": true,
  "supports_since": true,
  "url": "minimalreportingdata"
}
...
```
```
...
{
  "type": "json",t
  "system": "surveymonkey-proxy-service",
  "is_chronological": false,
  "is_since_comparable": true,
  "supports_since": true,
  "url": "surveys/1/responses/bulk?since=2019-01-01T00:00:00&sort_by=date_modified"
}
...
```
##### pipe http_transform example
```
{
  "_id": "surveymonkey-survey-details",
  "type": "pipe",
  "source": {
    "type": "dataset",
    "dataset": "surveymonkey-survey"
  },
  "transform": [{
      "type": "http",
      "system": "surveymonkey-proxy-service",
      "batch_size": 1,
      "url": "transform/surveys/{{surveymonkey-survey:id}}/details"
    },
    {
      "type": "dtl",
      "rules": {
        "default": [
        ...
        ]
      }
    }
  ]
}
```

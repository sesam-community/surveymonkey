
from flask import Flask, request, Response, abort, redirect
import requests
import os
import json
import re
import logger as l
from datetime import datetime, timedelta
from time import sleep
import cherrypy

app = Flask(__name__)

logger = l.Logger('surveymonkey', os.environ.get('LOGLEVEL', 'INFO'))

BASE_URL = os.environ.get('SURVEYMONKEY_URL')
ACCESS_TOKEN_LIST = json.loads(os.environ.get('SURVEYMONKEY_ACCESS_TOKEN_LIST', '{}'))
if not ACCESS_TOKEN_LIST:
    ACCESS_TOKEN_LIST = [os.environ.get('SURVEYMONKEY_ACCESS_TOKEN')]
PER_PAGE = int(os.environ.get('PER_PAGE', '1000'))
RATE_LIMIT_THRESHOLDS = [{
    'policy_name': 'REQUEST_REJECTION',
    'Minute': float(os.environ.get('THRESHOLD_FOR_REQUEST_REJECTION_MINUTE', '0.1')),
    'Day': float(os.environ.get('THRESHOLD_FOR_REQUEST_REJECTION_DAY', '0.1'))
}, {
    'policy_name': 'DELAYED_RESPONSE',
    'Minute': float(os.environ.get('THRESHOLD_FOR_DELAYED_RESPONSE_MINUTE', '0.3')),
    'Day': float(os.environ.get('THRESHOLD_FOR_DELAYED_RESPONSE_DAY', '0.3'))
}]

SURVEY_BLACKLIST = os.environ.get('SURVEY_BLACKLIST')
SURVEY_BLACKLIST = SURVEY_BLACKLIST.replace(
    ' ', '').split(',') if SURVEY_BLACKLIST else []


logger.info(
    'started up with LOG_LEVEL=%s, BASE_URL=%s, PER_PAGE=%d, RATE_LIMIT_THRESHOLDS=%s, SURVEY_BLACKLIST=%s, NUMBER_OF_SM_ACCOUNTS=%d' %
    (l.getLevel(logger), BASE_URL, PER_PAGE, RATE_LIMIT_THRESHOLDS, SURVEY_BLACKLIST, len(ACCESS_TOKEN_LIST)))

API_ENDPOINTS_TO_READ_FROM_DATA_FIELD = [
    'minimalreportingdata',
    'users/{id}/workgroups', 'users/{id}/shared', 'groups',
    'groups/{id}/members', 'surveys', 'survey_categories', 'survey_templates',
    'survey_languages', 'surveys/{id}/pages', 'surveys/{id}/questions',
    'surveys/{id}/responses/bulk', 'question_bank/questions', 'survey_folders',
    'surveys/{id}/languages', 'contact_lists', 'contact_lists/{id}/contacts',
    'surveys/{id}/collectors', 'collectors/{id}/messages',
    'collectors/{id}/recipients', 'collectors/{id}/recipients',
    'collectors/{id}/responses', 'collectors/{id}/responses/bulk', 'webhooks',
    'benchmark_bundles', 'workgroups', 'workgroups/{id}/members',
    'workgroups/{id}/shares', 'roles', 'errors', 'contacts', 'contacts/bulk',
    '/contact_lists/{id}/contacts/bulk', 'contact_fields'
]
SERVICE_PARAMETERS = [
    '_id_src', '_updated_src',
    '_do_stream', 'since', 'limit']
RESPONSE_CONTENT_TYPE = 'application/json; charset=utf-8'

g_reject_requests_policy_expires_at = None


def rate_limit_check_pre_apicall():
    global g_reject_requests_policy_expires_at
    if g_reject_requests_policy_expires_at:
        if g_reject_requests_policy_expires_at > datetime.now():
            raise Exception({
                'error': True,
                'message': 'Rejected due to active REQUEST_REJECTION policy.Ends at ' +
                g_reject_requests_policy_expires_at.isoformat()
            })
        else:
            logger.warning('REQUEST_REJECTION policy is deactivated')
            g_reject_requests_policy_expires_at = None


def rate_limit_check_post_apicall(api_response):
    def activate_reject_requests_policy(seconds_to_reset):
        global g_reject_requests_policy_expires_at
        g_reject_requests_policy_expires_at = datetime.now() + timedelta(0,
                                                                         seconds_to_reset)
        logger.warning(
            'REQUEST_REJECTION policy is activated with expiry time %s' %
            g_reject_requests_policy_expires_at)

    try:
        for period in ['Minute', 'Day']:
            limit = int(api_response.headers['X-Ratelimit-App-Global-' +
                                             period + '-Limit'])
            remaining = int(
                api_response.headers.get('X-Ratelimit-App-Global-' +
                                         period + '-Remaining'))
            seconds_to_reset = int(api_response.headers.get(
                'X-Ratelimit-App-Global-' + period + '-Reset'))

            if api_response.status_code == 429 and remaining == 0:
                activate_reject_requests_policy(seconds_to_reset)
                raise StopIteration
            else:
                for threshold in RATE_LIMIT_THRESHOLDS:
                    ratio = float(remaining / limit)
                    if ratio <= threshold[period]:
                        logger.warning('%s policy activation conditions met '
                                       '(period=%s, ratio=%f, threshold=%f, seconds=%d, remaining=%d)' %
                                       (threshold['policy_name'], period, ratio,
                                        threshold[period], seconds_to_reset, remaining))
                        if threshold['policy_name'] == 'REQUEST_REJECTION':
                            activate_reject_requests_policy(seconds_to_reset)
                        elif threshold['policy_name'] == 'DELAYED_RESPONSE':
                            sleep_duration = int(seconds_to_reset / remaining)
                            sleep(sleep_duration)
    except KeyError:
        None


def sesamify(entity, service_args):
    def remove_tz_offset(value):
        return value[:-6] if re.search('\+\d\d:\d\d$', value) else value
    if service_args.get('_id_src'):
        entity['_id'] = str(entity.get(service_args.get('_id_src')))
    if service_args.get('_updated_src'):
        entity['_updated'] = remove_tz_offset(
            str(entity.get(service_args.get('_updated_src'))))
    elif entity.get('date_modified'):
        if service_args.get('latest_date_modified', '') > entity.get('date_modified', ''):
            entity['_updated'] = remove_tz_offset(
                str(service_args.get('latest_date_modified')))
        else:
            entity['_updated'] = remove_tz_offset(
                str(entity.get('date_modified')))
            service_args['latest_date_modified'] = entity['_updated']
    return entity


def generate_entities(session, url, service_args, api_args):
    def do_read_from_data_field(url):
        api_endpoint = re.sub(r'/\d+', r'/{id}', url.replace(BASE_URL, ''))
        return api_endpoint in API_ENDPOINTS_TO_READ_FROM_DATA_FIELD
    do_page = True
    is_first_yield = True
    while do_page and not g_reject_requests_policy_expires_at:
        logger.debug('issuing a call to url=%s with args=%s' % (url, api_args))
        api_response = session.get(url, params=api_args)
        api_response_json = api_response.json()
        rate_limit_check_post_apicall(api_response)
        if api_response.status_code != 200:
            raise Exception(api_response_json.get('error'))

        data = api_response_json.get('data') if do_read_from_data_field(url) else [
            api_response.json()]
        for entity in data:
            yield entity
        do_page = service_args.get(
            'is_paging_on') and api_response_json.get(
            'links') and api_response_json.get('links', {}).get('next')
        if do_page:
            api_args['page'] = api_response_json.get('page') + 1


def fetch_data(session, path, service_args, api_args):
    global g_reject_requests_policy_expires_at
    is_first_yield = True
    url = None
    try:
        yield '['
        for access_token in ACCESS_TOKEN_LIST:
            session.headers.update({
            'Authorization': 'Bearer %s' % access_token,
            'Content-Type': 'application/json'
            })
            if path == 'minimalreportingdata':
                surveys = generate_entities(
                    session, BASE_URL + 'surveys', service_args, api_args={})
                for survey in surveys:
                    if survey.get('id') in SURVEY_BLACKLIST:
                        continue
                    for extension in [{'path': '/details',
                                       'api_args': {'include': 'date_modified'}},
                                      {'path': '/collectors',
                                       'api_args': {'include': 'status,date_modified'}},
                                      {'path': '/responses/bulk', 'api_args': api_args}]:
                        extension_entities = generate_entities(
                            session, survey['href'] + extension['path'], service_args, extension['api_args'])
                        for entity in extension_entities:
                            if is_first_yield:
                                is_first_yield = False
                            else:
                                yield ','
                            yield json.dumps(sesamify(entity, service_args))

            else:
                entity_list = generate_entities(
                    session, BASE_URL + path, service_args, api_args)
                for entity in entity_list:
                    if is_first_yield:
                        is_first_yield = False
                    else:
                        yield ','
                    yield json.dumps(sesamify(entity, service_args))
    except StopIteration:
        None
    except Exception as err:
        logger.exception(err)
        yield str(err)
        if not service_args.get('do_stream'):
            raise
    finally:
        yield ']\n'


def get_session():
    session = requests.Session()
    return session


def get_args(path, args):
    service_args = {
        'is_paging_on': ('page'
                         not in args),
        'do_stream': (args.get('_do_stream', '0') == '1')
    }
    if 'since' in args:
        args['start_modified_at'] = args.get('since')
    for param in SERVICE_PARAMETERS:
        if param in args:
            service_args[param] = args[param]
            del args[param]
    logger.debug('service_args=%s, args=%s ' % (service_args, args))
    return service_args, args


def get_data(path, request_args):
    response_data = []
    try:
        rate_limit_check_pre_apicall()
        with get_session() as session:
            service_args, api_args = get_args(path, request_args)
            fetched_data = fetch_data(session, path, service_args, api_args)

            if service_args.get('do_stream'):
                response_data = fetched_data
            else:
                for entity in fetched_data:
                    response_data.append(entity)
            return Response(
                response=response_data, content_type=RESPONSE_CONTENT_TYPE)
    except Exception as err:
        err_arg = err.args[0]
        status_code = err_arg.get('http_status_code', 500) if type(
            err_arg) == dict else 500
        return Response(
            response=json.dumps(err_arg),
            status=status_code,
            content_type=RESPONSE_CONTENT_TYPE)


@app.route('/<path:path>', methods=['GET'])
def get(path):
    return get_data(path, request.args.to_dict(True))


@app.route('/transform/<path:path>', methods=['POST'])
def transform(path):
    incoming_json = request.get_json()[0]
    generated_path = path
    logger.debug('%s' % (incoming_json))
    try:
        for replacement in re.findall('{{.*?}}', path):
            generated_path = generated_path.replace(
                replacement, str(incoming_json[replacement[2:-2]]))
        return get_data(generated_path, request.args.to_dict(True))
    except Exception as err:
        logger.exception(err)
        err_arg = {'message': str(err)}
        return Response(
            response=json.dumps(err_arg),
            status=err_arg.get('http_status_code', 500),
            content_type=RESPONSE_CONTENT_TYPE)


if __name__ == '__main__':
    if os.environ.get('WEBFRAMEWORK','').lower() == 'flask':
        app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    else:
        cherrypy.tree.graft(app, '/')

        # Set the configuration of the web server to production mode
        cherrypy.config.update({
            'environment': 'production',
            'engine.autoreload_on': False,
            'log.screen': True,
            'server.socket_port': int(os.environ.get('PORT', 5000)),
            'server.socket_host': '0.0.0.0'
        })

        # Start the CherryPy WSGI web server
        cherrypy.engine.start()
        cherrypy.engine.block()

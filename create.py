import argparse
import os
import yaml
import simplejson as json
import elasticsearch
from elasticsearch import helpers
import certifi
import datetime
import uuid
import random
import faker
import pytz
import collections

events_index = 'events_index'
metrics_index = 'metrics_index'


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', action='store', help='configuration file')
    return parser.parse_args()


def put_template(es, template_name, index_patterns):
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(cur_dir, template_name)
    with open(template_path, 'r') as t:
        template = json.load(t)

    template['index_patterns'] = index_patterns
    filename = os.path.splitext(template_name)[0]
    es.indices.put_template(name='dashboard_template_{}'.format(filename), body=template, create=False)


def create_template(config, es):
    print('Creating templates')
    if 'events_template' in config:
        put_template(es, config['events_template'], config['events_index_patterns'])
    if 'metrics_template' in config:
        put_template(es, config['metrics_template'], config['metrics_index_patterns'])


def gen_semver():
    return '{}.{}.{}'.format(random.randint(1, 10), random.randint(1, 10), random.randint(1, 10))


windows = 'Windows'
mac = 'macOS'
linux = 'Linux'
oses = [windows, mac, linux]


def gen_host_info():

    fake = faker.Faker()
    host = {
        'agent': {
            'id': str(uuid.uuid4()),
            'type': 'endpoint',
            'version': gen_semver()
        },
        'host': {
            'name': fake.hostname(),
            'os': {
                'name': random.choice(oses)
            },
            'ip': [fake.ipv4_public(network=False, address_class=None)]
        }
    }
    return host


gb = 1073741824


def gen_metrics(os_info, event_info):
    if os_info == windows:
        drive = 'c:\\'
    else:
        drive = '/var/'

    system_uptime = random.randint(1, 365 * 24 * 60 * 60)
    timestamp = random_date()
    data = {
        '@timestamp': timestamp.isoformat() + 'Z',
        'event': {
            'category': ['host'],
            'id': uuid.uuid4(),
            'kind': 'metrics',
        },
        'endpoint': {
            'system': {
                'uptime': {
                    # seconds in a year
                    'endpoint': random.randint(1, system_uptime),
                    'system': system_uptime
                },
                'cpu': {
                    'endpoint': {
                        'mean': random.uniform(1.0, 99.0),
                        'latest': random.uniform(1.0, 99.0),
                        'histogram': [random.randint(0, 60 * 5) for i in range(20)]
                    }
                },
                'memory': {
                    'endpoint': {
                        'private': {
                            'mean': random.randint(1, gb),
                            'latest': random.randint(1, gb)
                        }
                    }
                },
                'disks': [
                    {
                        'mount': drive,
                        'free': random.randint(gb*50, gb*300),
                        'total': gb*500
                    }
                ],
                'events': {
                    'since_start': event_info,
                    'backlog_size': random.randint(0, 200000)
                }
            }
        }
    }
    return data


def random_date(days_prior=9):
    delta = datetime.timedelta(days=days_prior)
    start = datetime.datetime.now(pytz.timezone('EST')) - delta
    int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
    random_second = random.randint(0, int_delta)
    rand_date = start + datetime.timedelta(seconds=random_second)
    return rand_date


def gen_event():
    categories = {
        'event': ['network', 'file', 'driver', 'process', 'registry'],
        'alert': ['malware']
    }
    cat_key = random.choices(list(categories.keys()), [.60, .40])[0]
    #datetime.datetime.now(pytz.timezone('EST')).isoformat() + 'Z',
    timestamp = random_date()
    return {
        '@timestamp': timestamp.isoformat() + 'Z',
        'event': {
            'category': [random.choice(categories[cat_key])],
            'id': uuid.uuid4(),
            'kind': cat_key,
        }
    }


def gen_locations(num_locations):
    locs = []
    fake = faker.Faker()
    for i in range(num_locations):
        fake_loc = fake.location_on_land(coords_only=True)
        locs.append({
            'geo': {
                'location': {
                    "lon": fake_loc[1],
                    "lat": fake_loc[0],
                }
            }
        })
    return locs


def generate_events(config):
    num_hosts = random.randint(35, 60)
    event_info = collections.defaultdict(int)
    #num_locations = random.randint(3, 10)
    #num_locations = 3
    #locations = gen_locations(num_locations)
    for i in range(num_hosts):
        num_events = random.randint(1, 100)
        host = gen_host_info()
        #loc = random.choice(locations)
        #host['host'].update(loc)
        for j in range(num_events):
            event = gen_event()
            event_kind = event['event']['kind']
            event_info[event_kind] += 1
            event.update(host)

            bulk_request = {
                '_index': config[events_index],
            }
            bulk_request.update(event)
            yield bulk_request

        num_metrics = random.randint(1, 500)
        for j in range(num_metrics):
            metrics = gen_metrics(host['host']['os']['name'], event_info)
            metrics.update(host)
            bulk_request = {
                '_index': config[metrics_index],
            }
            bulk_request.update(metrics)
            yield bulk_request

def insert_events(config, es):
    helpers.bulk(es, generate_events(config))


def del_previous_index(config, es):
    if not config['del_previous']:
        return

    print('Deleting previous index {}'.format(config[events_index]))
    es.indices.delete(index=config[events_index], ignore=[404])
    print('Deleting previous index {}'.format(config[metrics_index]))
    es.indices.delete(index=config[metrics_index], ignore=[404])


def main():
    args = parse_args()
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f.read())

    print('config:\n' + json.dumps(config, indent=4))
    es = elasticsearch.Elasticsearch(config['es'], ca_certs=certifi.where())
    del_previous_index(config, es)
    create_template(config, es)

    print('Generating events')
    insert_events(config, es)


if __name__ == '__main__':
    main()

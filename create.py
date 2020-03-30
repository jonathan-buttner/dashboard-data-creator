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
import geopy


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', action='store', help='configuration file')
    return parser.parse_args()


def create_template(config, es):
    if 'template' not in config:
        return

    print('Creating template')
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(cur_dir, config['template'])
    with open(template_path, 'r') as t:
        template = json.load(t)

    template['index_patterns'] = config['index_patterns']
    es.indices.put_template(name='dashboard_template', body=template, create=False)


def gen_semver():
    return '{}.{}.{}'.format(random.randint(1, 10), random.randint(1, 10), random.randint(1, 10))


def gen_host_info():

    fake = faker.Faker()
    oses = ['Windows', 'macOS', 'Linux']
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


def random_date(days_prior=3):
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
    cat_key = random.choices(list(categories.keys()), [.99, .01])[0]
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
    num_locations = random.randint(3, 10)
    #num_locations = 3
    locations = gen_locations(num_locations)
    for i in range(num_hosts):
        num_events = random.randint(1, 500)
        host = gen_host_info()
        loc = random.choice(locations)
        host['host'].update(loc)
        for j in range(num_events):
            event = gen_event()
            event.update(host)

            bulk_request = {
                '_index': config['index'],
            }
            bulk_request.update(event)
            yield bulk_request


def insert_events(config, es):
    helpers.bulk(es, generate_events(config))


def del_previous_index(config, es):
    if not config['del_previous']:
        return

    print('Deleting previous index {}'.format(config['index']))
    es.indices.delete(index=config['index'], ignore=[404])


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

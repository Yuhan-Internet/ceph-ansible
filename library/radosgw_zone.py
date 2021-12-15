# Copyright 2020, Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule
try:
    from ansible.module_utils.ca_common import fatal
except ImportError:
    from module_utils.ca_common import fatal
import datetime
import json
import os


ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: radosgw_zone

short_description: Manage RADOS Gateway Zone

version_added: "2.8"

description:
    - Manage RADOS Gateway zone(s) creation, deletion and updates.
options:
    cluster:
        description:
            - The ceph cluster name.
        required: false
        default: ceph
    name:
        description:
            - name of the RADOS Gateway zone.
        required: true
    state:
        description:
            If 'present' is used, the module creates a zone if it doesn't
            exist or update it if it already exists.
            If 'absent' is used, the module will simply delete the zone.
            If 'info' is used, the module will return all details about the
            existing zone (json formatted).
        required: false
        choices: ['present', 'absent', 'info']
        default: present
    realm:
        description:
            - name of the RADOS Gateway realm.
        required: true
    zonegroup:
        description:
            - name of the RADOS Gateway zonegroup.
        required: true
    endpoints:
        description:
            - endpoints of the RADOS Gateway zone.
        required: false
        default: []
    access_key:
        description:
            - set the S3 access key of the user.
        required: false
        default: None
    secret_key:
        description:
            - set the S3 secret key of the user.
        required: false
        default: None
    default:
        description:
            - set the default flag on the zone.
        required: false
        default: false
    master:
        description:
            - set the master flag on the zone.
        required: false
        default: false
    tier_type:
        description:
            - The zone tier type.
        required: false
        default: None
    es_tier_conf_endpoint:
        description:
            - Specifies the Elasticsearch server endpoint to access.
        required: false
        default: None
    es_tier_conf_username:
        description:
            - Elasticsearch username.
        required: false
        default: None
    es_tier_conf_password:
        description:
            - Elasticsearch password.
        required: false
        default: None
    es_tier_conf_num_shards:
        description:
            - The number of shards that Elasticsearch will be configured with on data sync initialization.
              Note that this cannot be changed after init.
        required: false
        default: None
    es_tier_conf_num_replicas:
        description:
            - The number of the replicas that Elasticsearch will be configured with on data sync initialization.
        required: false
        default: None
    es_tier_conf_explicit_custom_meta:
        description:
            - Specifies whether all user custom metadata will be indexed.
        required: false
        default: None
    es_tier_conf_index_buckets_list:
        description:
            - If empty, all buckets will be indexed. Otherwise, only buckets specified here will be indexed.
              It is possible to provide bucket prefixes (e.g., foo*), or bucket suffixes (e.g., *bar).
        required: false
        default: None
    es_tier_conf_approved_owners_list:
        description:
            - If empty, buckets of all owners will be indexed (subject to other restrictions),
              otherwise, only buckets owned by specified owners will be indexed.
              Suffixes and prefixes can also be provided.
        required: false
        default: None
    es_tier_conf_override_index_path:
        description:
            - if not empty, this string will be used as the elasticsearch index path.
              Otherwise the index path will be determined and generated on sync initialization.
        required: false
        default: None
author:
    - Dimitri Savineau <dsavinea@redhat.com>
'''

EXAMPLES = '''
- name: create a RADOS Gateway default zone
  radosgw_zone:
    name: z1
    realm: foo
    zonegroup: bar
    endpoints:
      - http://192.168.1.10:8080
      - http://192.168.1.11:8080
    default: true

- name: get a RADOS Gateway zone information
  radosgw_zone:
    name: z1
    state: info

- name: delete a RADOS Gateway zone
  radosgw_zone:
    name: z1
    state: absent
'''

RETURN = '''#  '''


def container_exec(binary, container_image):
    '''
    Build the docker CLI to run a command inside a container
    '''

    container_binary = os.getenv('CEPH_CONTAINER_BINARY')
    command_exec = [container_binary,
                    'run',
                    '--rm',
                    '--net=host',
                    '-v', '/etc/ceph:/etc/ceph:z',
                    '-v', '/var/lib/ceph/:/var/lib/ceph/:z',
                    '-v', '/var/log/ceph/:/var/log/ceph/:z',
                    '--entrypoint=' + binary, container_image]
    return command_exec


def is_containerized():
    '''
    Check if we are running on a containerized cluster
    '''

    if 'CEPH_CONTAINER_IMAGE' in os.environ:
        container_image = os.getenv('CEPH_CONTAINER_IMAGE')
    else:
        container_image = None

    return container_image


def pre_generate_radosgw_cmd(container_image=None):
    '''
    Generate radosgw-admin prefix comaand
    '''
    if container_image:
        cmd = container_exec('radosgw-admin', container_image)
    else:
        cmd = ['radosgw-admin']

    return cmd


def generate_radosgw_cmd(cluster, args, container_image=None):
    '''
    Generate 'radosgw' command line to execute
    '''

    cmd = pre_generate_radosgw_cmd(container_image=container_image)

    base_cmd = [
        '--cluster',
        cluster,
        'zone'
    ]

    cmd.extend(base_cmd + args)

    return cmd


def exec_commands(module, cmd):
    '''
    Execute command(s)
    '''

    rc, out, err = module.run_command(cmd)

    return rc, cmd, out, err


def create_zone(module, container_image=None):
    '''
    Create a new zone
    '''

    cluster = module.params.get('cluster')
    name = module.params.get('name')
    realm = module.params.get('realm')
    zonegroup = module.params.get('zonegroup')
    endpoints = module.params.get('endpoints')
    access_key = module.params.get('access_key')
    secret_key = module.params.get('secret_key')
    default = module.params.get('default')
    master = module.params.get('master')
    tier_type = module.params.get('tier_type')
    es_tier_conf_endpoint = module.params.get('es_tier_conf_endpoint')
    es_tier_conf_username = module.params.get('es_tier_conf_username')
    es_tier_conf_password = module.params.get('es_tier_conf_password')
    es_tier_conf_num_shards = module.params.get('es_tier_conf_num_shards')
    es_tier_conf_num_replicas = module.params.get('es_tier_conf_num_replicas')
    es_tier_conf_explicit_custom_meta = module.params.get('es_tier_conf_explicit_custom_meta')
    es_tier_conf_index_buckets_list = module.params.get('es_tier_conf_index_buckets_list')
    es_tier_conf_approved_owners_list = module.params.get('es_tier_conf_approved_owners_list')
    es_tier_conf_override_index_path = module.params.get('es_tier_conf_override_index_path')

    args = [
        'create',
        '--rgw-realm=' + realm,
        '--rgw-zonegroup=' + zonegroup,
        '--rgw-zone=' + name
    ]

    if endpoints:
        args.extend(['--endpoints=' + ','.join(endpoints)])

    if access_key:
        args.extend(['--access-key=' + access_key])

    if secret_key:
        args.extend(['--secret-key=' + secret_key])

    if default:
        args.append('--default')

    if master:
        args.append('--master')

    if tier_type == 'elasticsearch':
        args.append(f'--tier-type={tier_type}')

        tier_conf_list = []

        if es_tier_conf_endpoint:
            tier_conf_list.append(f'endpoint={es_tier_conf_endpoint}')

        if es_tier_conf_username:
            tier_conf_list.append(f'username={es_tier_conf_username}')

        if es_tier_conf_password:
            tier_conf_list.append(f'password={es_tier_conf_password}')

        if es_tier_conf_num_shards:
            tier_conf_list.append(f'num_shards={es_tier_conf_num_shards}')

        if es_tier_conf_num_replicas:
            tier_conf_list.append(f'num_replicas={es_tier_conf_num_replicas}')

        if es_tier_conf_explicit_custom_meta:
            tier_conf_list.append(f'explicit_custom_meta={es_tier_conf_explicit_custom_meta}')

        if es_tier_conf_index_buckets_list:
            tier_conf_list.append(f'index_buckets_list={es_tier_conf_index_buckets_list}')

        if es_tier_conf_approved_owners_list:
            tier_conf_list.append(f'approved_owners_list={es_tier_conf_approved_owners_list}')

        if es_tier_conf_override_index_path:
            tier_conf_list.append(f'override_index_path={es_tier_conf_override_index_path}')

        tier_conf_str = ','.join(tier_conf_list)

        if tier_conf_str:
            # tier_conf_str not empty
            args.append(f'--tier-config={tier_conf_str}')

    cmd = generate_radosgw_cmd(cluster=cluster,
                               args=args,
                               container_image=container_image)

    return cmd


def modify_zone(module, container_image=None):
    '''
    Modify a new zone
    '''

    cluster = module.params.get('cluster')
    name = module.params.get('name')
    realm = module.params.get('realm')
    zonegroup = module.params.get('zonegroup')
    endpoints = module.params.get('endpoints')
    access_key = module.params.get('access_key')
    secret_key = module.params.get('secret_key')
    default = module.params.get('default')
    master = module.params.get('master')
    tier_type = module.params.get('tier_type')
    es_tier_conf_endpoint = module.params.get('es_tier_conf_endpoint')
    es_tier_conf_username = module.params.get('es_tier_conf_username')
    es_tier_conf_password = module.params.get('es_tier_conf_password')
    es_tier_conf_num_shards = module.params.get('es_tier_conf_num_shards')
    es_tier_conf_num_replicas = module.params.get('es_tier_conf_num_replicas')
    es_tier_conf_explicit_custom_meta = module.params.get('es_tier_conf_explicit_custom_meta')
    es_tier_conf_index_buckets_list = module.params.get('es_tier_conf_index_buckets_list')
    es_tier_conf_approved_owners_list = module.params.get('es_tier_conf_approved_owners_list')
    es_tier_conf_override_index_path = module.params.get('es_tier_conf_override_index_path')

    args = [
        'modify',
        '--rgw-realm=' + realm,
        '--rgw-zonegroup=' + zonegroup,
        '--rgw-zone=' + name
    ]

    if endpoints:
        args.extend(['--endpoints=' + ','.join(endpoints)])

    if access_key:
        args.extend(['--access-key=' + access_key])

    if secret_key:
        args.extend(['--secret-key=' + secret_key])

    if default:
        args.append('--default')

    if master:
        args.append('--master')

    if tier_type == 'elasticsearch':
        args.append(f'--tier-type={tier_type}')

        tier_conf_list = []

        if es_tier_conf_endpoint:
            tier_conf_list.append(f'endpoint={es_tier_conf_endpoint}')

        if es_tier_conf_username:
            tier_conf_list.append(f'username={es_tier_conf_username}')

        if es_tier_conf_password:
            tier_conf_list.append(f'password={es_tier_conf_password}')

        if es_tier_conf_num_shards:
            tier_conf_list.append(f'num_shards={es_tier_conf_num_shards}')

        if es_tier_conf_num_replicas:
            tier_conf_list.append(f'num_replicas={es_tier_conf_num_replicas}')

        if es_tier_conf_explicit_custom_meta:
            tier_conf_list.append(f'explicit_custom_meta={es_tier_conf_explicit_custom_meta}')

        if es_tier_conf_index_buckets_list:
            tier_conf_list.append(f'index_buckets_list={es_tier_conf_index_buckets_list}')

        if es_tier_conf_approved_owners_list:
            tier_conf_list.append(f'approved_owners_list={es_tier_conf_approved_owners_list}')

        if es_tier_conf_override_index_path:
            tier_conf_list.append(f'override_index_path={es_tier_conf_override_index_path}')

        tier_conf_str = ','.join(tier_conf_list)

        if tier_conf_str:
            # tier_conf_str not empty
            args.append(f'--tier-config={tier_conf_str}')

    cmd = generate_radosgw_cmd(cluster=cluster,
                               args=args,
                               container_image=container_image)

    return cmd


def get_zone(module, container_image=None):
    '''
    Get existing zone
    '''

    cluster = module.params.get('cluster')
    name = module.params.get('name')
    realm = module.params.get('realm')
    zonegroup = module.params.get('zonegroup')

    args = [
        'get',
        '--rgw-realm=' + realm,
        '--rgw-zonegroup=' + zonegroup,
        '--rgw-zone=' + name,
        '--format=json'
    ]

    cmd = generate_radosgw_cmd(cluster=cluster,
                               args=args,
                               container_image=container_image)

    return cmd


def get_zonegroup(module, container_image=None):
    '''
    Get existing zonegroup
    '''

    cluster = module.params.get('cluster')
    realm = module.params.get('realm')
    zonegroup = module.params.get('zonegroup')

    cmd = pre_generate_radosgw_cmd(container_image=container_image)

    args = [
        '--cluster',
        cluster,
        'zonegroup',
        'get',
        '--rgw-realm=' + realm,
        '--rgw-zonegroup=' + zonegroup,
        '--format=json'
    ]

    cmd.extend(args)

    return cmd


def get_realm(module, container_image=None):
    '''
    Get existing realm
    '''

    cluster = module.params.get('cluster')
    realm = module.params.get('realm')

    cmd = pre_generate_radosgw_cmd(container_image=container_image)

    args = [
        '--cluster',
        cluster,
        'realm',
        'get',
        '--rgw-realm=' + realm,
        '--format=json'
    ]

    cmd.extend(args)

    return cmd


def remove_zone(module, container_image=None):
    '''
    Remove a zone
    '''

    cluster = module.params.get('cluster')
    name = module.params.get('name')
    realm = module.params.get('realm')
    zonegroup = module.params.get('zonegroup')

    args = [
        'delete',
        '--rgw-realm=' + realm,
        '--rgw-zonegroup=' + zonegroup,
        '--rgw-zone=' + name
    ]

    cmd = generate_radosgw_cmd(cluster=cluster,
                               args=args,
                               container_image=container_image)

    return cmd


def exit_module(module, out, rc, cmd, err, startd, changed=False):
    endd = datetime.datetime.now()
    delta = endd - startd

    result = dict(
        cmd=cmd,
        start=str(startd),
        end=str(endd),
        delta=str(delta),
        rc=rc,
        stdout=out.rstrip("\r\n"),
        stderr=err.rstrip("\r\n"),
        changed=changed,
    )
    module.exit_json(**result)


def run_module():
    module_args = dict(
        cluster=dict(type='str', required=False, default='ceph'),
        name=dict(type='str', required=True),
        state=dict(type='str', required=False, choices=['present', 'absent', 'info'], default='present'),  # noqa: E501
        realm=dict(type='str', require=True),
        zonegroup=dict(type='str', require=True),
        endpoints=dict(type='list', require=False, default=[]),
        access_key=dict(type='str', required=False, no_log=True),
        secret_key=dict(type='str', required=False, no_log=True),
        default=dict(type='bool', required=False, default=False),
        master=dict(type='bool', required=False, default=False),
        tier_type=dict(type='str', required=False, choices=['elasticsearch', None], default=None),
        es_tier_conf_endpoint=dict(type='str', required=False, default=None),
        es_tier_conf_username=dict(type='str', required=False, default=None, no_log=True),
        es_tier_conf_password=dict(type='str', required=False, default=None, no_log=True),
        es_tier_conf_num_shards=dict(type='int', required=False, default=None),
        es_tier_conf_num_replicas=dict(type='int', required=False, default=None),
        es_tier_conf_explicit_custom_meta=dict(type='str', required=False, default=None),
        es_tier_conf_index_buckets_list=dict(type='str', required=False, default=None),
        es_tier_conf_approved_owners_list=dict(type='str', required=False, default=None),
        es_tier_conf_override_index_path=dict(type='str', required=False, default=None)
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    # Gather module parameters in variables
    name = module.params.get('name')
    state = module.params.get('state')
    endpoints = module.params.get('endpoints')
    access_key = module.params.get('access_key')
    secret_key = module.params.get('secret_key')
    tier_type = module.params.get('tier_type')
    es_tier_conf_endpoint = module.params.get('es_tier_conf_endpoint')
    es_tier_conf_username = module.params.get('es_tier_conf_username')
    es_tier_conf_password = module.params.get('es_tier_conf_password')
    es_tier_conf_num_shards = module.params.get('es_tier_conf_num_shards')
    es_tier_conf_num_replicas = module.params.get('es_tier_conf_num_replicas')
    es_tier_conf_explicit_custom_meta = module.params.get('es_tier_conf_explicit_custom_meta')
    es_tier_conf_index_buckets_list = module.params.get('es_tier_conf_index_buckets_list')
    es_tier_conf_approved_owners_list = module.params.get('es_tier_conf_approved_owners_list')
    es_tier_conf_override_index_path = module.params.get('es_tier_conf_override_index_path')

    if module.check_mode:
        module.exit_json(
            changed=False,
            stdout='',
            stderr='',
            rc=0,
            start='',
            end='',
            delta='',
        )

    startd = datetime.datetime.now()
    changed = False

    # will return either the image name or None
    container_image = is_containerized()

    if state == "present":
        rc, cmd, out, err = exec_commands(module, get_zone(module, container_image=container_image))  # noqa: E501
        if rc == 0:
            zone = json.loads(out)
            _rc, _cmd, _out, _err = exec_commands(module, get_realm(module, container_image=container_image))  # noqa: E501
            if _rc != 0:
                fatal(_err, module)
            realm = json.loads(_out)
            _rc, _cmd, _out, _err = exec_commands(module, get_zonegroup(module, container_image=container_image))  # noqa: E501
            if _rc != 0:
                fatal(_err, module)
            zonegroup = json.loads(_out)
            if not access_key:
                access_key = ''
            if not secret_key:
                secret_key = ''
            if not tier_type:
                tier_type = ''
            if zone.get('tier_config'):
                # zone has tier_config; check if tier_config changed
                for a_zone in zonegroup['zones']:
                    if a_zone['name'] == name:
                        if a_zone['tier_type'] == 'elasticsearch':
                            # elasticsearch sync zone
                            current_tier_config = {
                                'endpoint': zone['tier_config'].get('endpoint'),
                                'username': zone['tier_config'].get('username'),
                                'password': zone['tier_config'].get('password'),
                                'num_shards': zone['tier_config'].get('num_shards'),
                                'num_replicas': zone['tier_config'].get('num_replicas'),
                                'explicit_custom_meta': zone['tier_config'].get('explicit_custom_meta'),
                                'index_buckets_list': zone['tier_config'].get('index_buckets_list'),
                                'approved_owners_list': zone['tier_config'].get('approved_owners_list'),
                                'override_index_path': zone['tier_config'].get('override_index_path')
                            }
            else:
                current_tier_config = None

            if es_tier_conf_endpoint or \
               es_tier_conf_username or \
               es_tier_conf_password or \
               es_tier_conf_num_shards or \
               es_tier_conf_num_replicas or \
               es_tier_conf_explicit_custom_meta or \
               es_tier_conf_index_buckets_list or \
               es_tier_conf_approved_owners_list or \
               es_tier_conf_override_index_path:
                if tier_type != 'elasticsearch':
                    fatal('tier_type is not "elasticsearch" but elasticsearch config provided.', module)
                asked_tier_config = {
                    'endpoint': es_tier_conf_endpoint,
                    'username': es_tier_conf_username,
                    'password': es_tier_conf_password,
                    'num_shards': es_tier_conf_num_shards,
                    'num_replicas': es_tier_conf_num_replicas,
                    'explicit_custom_meta': es_tier_conf_explicit_custom_meta,
                    'index_buckets_list': es_tier_conf_index_buckets_list,
                    'approved_owners_list': es_tier_conf_approved_owners_list,
                    'override_index_path': es_tier_conf_override_index_path
                }
            else:
                asked_tier_config = None

            if asked_tier_config:
                if current_tier_config == asked_tier_config:
                    tier_config_changed = False
                else:
                    tier_config_changed = True
            else:
                tier_config_changed = False

            current = {
                'endpoints': next(zone['endpoints'] for zone in zonegroup['zones'] if zone['name'] == name),  # noqa: E501
                'access_key': zone['system_key']['access_key'],
                'secret_key': zone['system_key']['secret_key'],
                'realm_id': zone['realm_id']
            }
            asked = {
                'endpoints': endpoints,
                'access_key': access_key,
                'secret_key': secret_key,
                'realm_id': realm['id']
            }
            if asked['endpoints'] == []:
                current['endpoints'] = []
            if current != asked or tier_config_changed:
                if tier_type == 'elasticsearch':
                    if current_tier_config and asked_tier_config:
                        if current_tier_config['num_shards'] != asked_tier_config['num_shards']:
                            fatal('num_shards cannot be changed', module)
                rc, cmd, out, err = exec_commands(module, modify_zone(module, container_image=container_image))  # noqa: E501
                changed = True
        else:
            rc, cmd, out, err = exec_commands(module, create_zone(module, container_image=container_image))  # noqa: E501
            changed = True

    elif state == "absent":
        rc, cmd, out, err = exec_commands(module, get_zone(module, container_image=container_image))  # noqa: E501
        if rc == 0:
            rc, cmd, out, err = exec_commands(module, remove_zone(module, container_image=container_image))  # noqa: E501
            changed = True
        else:
            rc = 0
            out = "Zone {} doesn't exist".format(name)

    elif state == "info":
        rc, cmd, out, err = exec_commands(module, get_zone(module, container_image=container_image))  # noqa: E501

    exit_module(module=module, out=out, rc=rc, cmd=cmd, err=err, startd=startd, changed=changed)  # noqa: E501


def main():
    run_module()


if __name__ == '__main__':
    main()

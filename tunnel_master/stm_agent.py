import os
import re
import sys
import time
import json
import socket 
import logging
import subprocess
import logging.handlers
from string import ascii_lowercase as ascii

from config import APP_DIR, LOG_FILENAME, HOSTS_FILENAME, SSH_FILENAME, ALIASES_FILENAME, SSH_TUNNEL_MASTER_ALIASES

log = logging.getLogger('stm')

SSH_PORT_RX = re.compile('^\[localhost\]\:(\d+)')
ALIASES_RX = re.compile('^alias\s(\w+)\=')
SERVICE_DEFAULT_PORTS = {
    'mysql': 3309,
    'psql': 5432,
    'mssql': 1433,
}


class StmAgent(object):
    
    def __init__(self):
        self._hosts = {}
        self._ports = set()
        self._users = {}
        self._aliases = {}
        self._services = {}
        self._config = None
        self._parent_objs = []
        self._stm_type = None
        self._last_auto_port = 10000
        self._parent_tunnel_alias = None

        self._load_config()

    def start_agent(self, stm_type):
        self._stm_type = stm_type

        if stm_type == 'client':            
            if not self._prompt_parent_input():
                return

            if not self._prompt_port():
                return

            if not self._prompt_user():
                log.error('User info missing, aborting...')
                return
        elif stm_type == 'service':
            if not self._prompt_remote_tunnel_alias_input():
                return

            if not self._prompt_alias():
                return False

            if not self._prompt_port():
                return False

            if not self._prompt_service_host():
                return False

            if not self._prompt_service_type():
                return False

            if not self._prompt_service_port():
                return False

            if not self._prompt_sql_service_username():
                return False

            if not self._prompt_sql_service_password():
                return False

            if not self._prompt_sql_service_database():
                log.error('SQL DB name missing, aborting...')
                return False

            self._services[self._alias] = {
                'port': self._port,
                'remote_tunnel': self._remote_tunnel,
                'service_host': self._service_host,
                'service_port': self._service_port,
                'service_type': self._service_type,
                'sql_username': self._sql_service_username,
                'sql_password': self._sql_service_password,
                'sql_database': self._sql_service_database,
            }

        else:
            return

        self._write_changes()

    def _load_config(self):
        self._config = {
            'hosts': {},
            'misc': {},
        }
        try:
            with open(HOSTS_FILENAME, 'r') as f_obj:
                self._config = json.loads(f_obj.read())
        except IOError as e:
            log.error('Creating new conf file, reason: %s', e)
        except ValueError as e:
            log.error('Creating new conf, reason: %s', e)

        for host_alias, conf in self._config['hosts'].items():
            self._hosts[host_alias] = conf['host']
            self._ports.add(conf['port'])
            self._users[host_alias] = conf['users']
            for username, alias in conf['users'].items():
                self._aliases[alias] = {
                    'host': conf['host'],
                    'port': conf['port'],
                }

        for service_alias, conf in self._config['hosts'].items():
            self._ports.add(conf['port'])

        self._services = self._config.get('services', {})

        if self._hosts:
            k, v = zip(*self._hosts.items())
            self._parent_objs = k + v

        if 'last_auto_port' in self._config['misc']:
            self._last_auto_port = self._config['misc']['last_auto_port'] + 5

    def _write_changes(self):
        self._config['misc']['last_auto_port'] = self._last_auto_port

        if self._stm_type == 'client':
            if self._parent_tunnel_alias not in self._config['hosts']:
                self._config['hosts'][self._parent_tunnel_alias] = {
                    'host': self._parent_tunnel,
                    'port': self._port,
                    'users': self._users[self._parent_tunnel_alias],
                }
        elif self._stm_type == 'service':
            self._config['services'] = self._services

        with open(HOSTS_FILENAME, 'w') as f_obj:
            f_obj.write(json.dumps(self._config))

        with open(SSH_TUNNEL_MASTER_ALIASES, 'a') as f_obj:
            try:
                file_info = f_obj.read()
            except Exception as err:
                f_obj.write('#/bin/bash\n\n')

            f_obj.write('alias %s="stm ssh -s $KONSOLE_DBUS_SERVICE -a %s -c $1"\n' % (self._alias, self._alias,))

    def _prompt_parent_input(self):
        try:
            parent_input = input('Enter parent host (use "list" for listing existing parents): ')
        except KeyboardInterrupt:
            print()
            return False

        if not parent_input:
            print('Empty host is not allowed!')
            return self._prompt_parent_input()
        elif parent_input == 'list':
            if self._list_parent_tunnels():
                return True
            return self._prompt_parent_input()
        else:
            ip_address = parent_input
            fqdn = parent_input

            if re.match('((\d{1,3}\.)+\d+)', parent_input):
                fqdn = socket.getfqdn(parent_input)
            else:
                try:
                    ip_address = socket.gethostbyname(parent_input)
                except:
                    print('Hostname not found')
                    return self._prompt_parent_input()

            parent = fqdn

            try:
                alias = ''.join(ascii[int(x)] if x.isalnum() else '-' for x in ip_address)
            except ValueError:
                alias = parent.split('.')[0]

            self._parent_tunnel_alias = alias
            self._parent_tunnel = parent

            if alias in self._parent_objs:
                existing_port = self._config['hosts'][alias]['port']
                print('Using existing host: "%s" with port: %s' % (parent, existing_port,))
                return True
       
        return True

    def _list_parent_tunnels(self):
        selections = []
        for idx, (alias, host) in enumerate(self._hosts.items()):
            print('#%-2s - %-20s: %s' % (idx, alias, host,))
            selections.append((alias, host,))

        try:
            select_from_list_input = int(input('Select from list: '))
        except ValueError:
            print('Only integers are allowed!')
            return self._list_parent_tunnels()
        except KeyboardInterrupt:
            print()
            return

        if select_from_list_input >= len(selections):
            print('Selection is greater than available list')
            return self._list_parent_tunnels()

        self._parent_tunnel_alias = selections[select_from_list_input][0]
        self._parent_tunnel = selections[select_from_list_input][1]
        return True

    def _prompt_port(self):
        try:
            port_input = input('Enter port (use "list" for listing existing ports) [%s]: ' % self._last_auto_port)
        except KeyboardInterrupt:
            print()
            return False

        if not port_input:
            while 1:
                if self._last_auto_port in self._ports:
                    self._last_auto_port += 5
                    continue

                self._port = self._last_auto_port
                break
            if not self._check_known_hosts():
                return self._prompt_port()

            return True
        elif port_input == 'list':
            self._list_ports()
            return self._prompt_port()
        else:
            try:
                self._port = int(port_input)
            except ValueError:
                print('Only integers are allowed')
                return self._prompt_port()

            if self._port in self._ports:
                print('Port already assigned, choose different one!')
                return self._prompt_port()

            if not self._check_known_hosts():
                return self._prompt_port()

            return True

    def _list_ports(self):
        if self._parent_tunnel_alias in self._config['hosts']:
            print('Assign port for given host', self._config['hosts'][self._parent_tunnel_alias]['port'])
        print('Assigned ports:', self._ports)

    def _check_known_hosts(self):
        if not os.access(SSH_FILENAME, os.F_OK):
            return True

        ssh_ports = []
        f_obj = open(SSH_FILENAME, 'r')
        hosts = f_obj.readlines()
        f_obj.close()
        for host in hosts:
            port_match = SSH_PORT_RX.match(host)
            if not port_match:
                continue
            ssh_ports.append(int(port_match.group(1)))

        if self._port in ssh_ports:
            print('Port exists in ssh known_hosts...')
            choice = input('Do you want to (d)elete existing host, (s)elect new port?: ')
            if choice == 's':
                return False
            elif choice == 'd':
                f_obj = open(SSH_FILENAME, 'w')
                for host in hosts:
                    port_match = SSH_PORT_RX.match(host)
                    if port_match and int(port_match.group(1)) == self._port:
                        continue

                    f_obj.write(host)

                f_obj.close()

        return True

    def _prompt_user(self):
        try:
            user_input = input('Enter username: ')
        except KeyboardInterrupt:
            print()
            return False

        if not user_input:
            print('User must be assigned!')
            return self._prompt_user()
        else:            
            users = {}
            if self._parent_tunnel_alias in self._users:
                users = self._users[self._parent_tunnel_alias]

            existing_users = users.keys()

            if user_input in existing_users:
                print('User already exists!')
                return self._prompt_user()

            alias = self._prompt_alias()
            if not alias:
                return False

            users[user_input] = alias

        self._users[self._parent_tunnel_alias] = users
        return True

    def _prompt_alias(self):
        try:
            alias_input = input('Enter alias for bash usage: ')
        except KeyboardInterrupt:
            print()
            return False

        if not alias_input:
            print('Alias must be assigned!')
            return self._prompt_alias()
        else:
            alias = alias_input

        if not self._check_known_aliases(alias):
            return self._prompt_alias()

        self._alias = alias
        return alias

    def _check_known_aliases(self, alias):
        if not os.access(ALIASES_FILENAME, os.F_OK):
            return True

        with open(ALIASES_FILENAME, 'r') as f_obj:
            for line in f_obj:
                alias_match = ALIASES_RX.match(line)
                if alias_match and alias_match.group(1) == alias:
                    print('Alias already assigned')
                    return False

        if not os.path.exists(SSH_TUNNEL_MASTER_ALIASES):
            return True

        with open(SSH_TUNNEL_MASTER_ALIASES, 'r') as f_obj:
            for line in f_obj:
                alias_match = ALIASES_RX.match(line)
                if alias_match and alias_match.group(1) == alias:
                    print('Alias already assigned')
                    return False
        
        return True

    def _prompt_remote_tunnel_alias_input(self):
        try:
            rta_input = input('Enter remote tunnel alias (use "list" for listing existing aliases): ')
        except KeyboardInterrupt:
            print()
            return False

        if not rta_input:
            print('Empty remote tunnel is not allowed')
            return self._prompt_remote_tunnel_alias_input()
        elif rta_input == 'list':
            if self._list_remote_tunnels():
                return True
            return self._prompt_remote_tunnel_alias_input()
        elif rta_input not in self._aliases:
            print('Remote tunnel alias not found')
            return self._prompt_remote_tunnel_alias_input()

        self._remote_tunnel = rta_input

        return True

    def _list_remote_tunnels(self):
        selections = []
        for idx, (alias, alias_obj) in enumerate(self._aliases.items()):
            print('#%-2s - %-20s: %s' % (idx, alias, alias_obj['host'],))
            selections.append(alias)

        try:
            select_from_list_input = int(input('Select from list: '))
        except ValueError:
            print('Only integers are allowed!')
            return self._list_remote_tunnels()
        except KeyboardInterrupt:
            print()
            return

        if select_from_list_input >= len(selections):
            print('Selection is greater than available list')
            return self._list_remote_tunnels()
    
        self._remote_tunnel = selections[select_from_list_input]
        return True

    def _prompt_service_host(self):
        try:
            service_host_input = input('Enter service host: ')
        except KeyboardInterrupt:
            print()
            return False

        if not service_host_input:
            print('Empty host is not allowed!')
            return self._prompt_service_host()
        else:
            fqdn = service_host_input

            if re.match('((\d{1,3}\.)+\d+)', service_host_input):
                fqdn = socket.getfqdn(service_host_input)
            else:
                try:
                    ip_address = socket.gethostbyname(service_host_input)
                except:
                    print('Hostname not found')
                    return self._prompt_service_host()

            self._service_host = fqdn

        return True

    def _prompt_service_port(self):
        known_service_type_port = SERVICE_DEFAULT_PORTS.get(self._service_type)
        if known_service_type_port:
            known_service_port_str = ' [%s]' % (known_service_type_port)
        else:
            known_service_port_str = ''

        try:
            service_port_input = input('Enter service port%s:' % (known_service_port_str))
        except KeyboardInterrupt:
            print()
            return False

        if not service_port_input and not known_service_type_port:
            return self._prompt_service_port()
        elif not service_port_input and known_service_type_port:
            self._service_port = known_service_type_port
        else:
            self._service_port = int(service_port_input)

        return True

    def _prompt_service_type(self):
        try:
            service_type_input = input('Enter service type: ')
        except KeyboardInterrupt:
            print()
            return False

        if not service_type_input:
            print('Empty service type is not allowed!')
            return self._prompt_service_type()
        else:
            self._service_type = service_type_input

        return True

    def _prompt_sql_service_username(self):
        try:
            sql_username_input = input('Enter SQL username: ')
        except KeyboardInterrupt:
            print()
            return False

        if not sql_username_input:
            print('Empty SQL username is not allowed!')
            return self._prompt_sql_service_username()
        else:
            self._sql_service_username = sql_username_input

        return True

    def _prompt_sql_service_password(self):
        try:
            sql_password_input = input('Enter SQL password: ')
        except KeyboardInterrupt:
            print()
            return False

        if not sql_password_input:
            print('Empty SQL password is not allowed!')
            return self._prompt_sql_service_password()
        else:
            self._sql_service_password = sql_password_input

        return True

    def _prompt_sql_service_database(self):
        try:
            sql_database_input = input('Enter SQL database name: ')
        except KeyboardInterrupt:
            print()
            return False

        if not sql_database_input:
            print('Empty SQL database name is not allowed!')
            return self._prompt_sql_service_database()
        else:
            self._sql_service_database = sql_database_input

        return True



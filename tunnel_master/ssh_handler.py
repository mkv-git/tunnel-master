import os
import json
import time
import logging
import subprocess
import logging.handlers
from dbus import SessionBus, Interface, String

from config import HOSTS_FILENAME, YBER_TUNNEL

KONSOLE_SESSION_PATH = 'org.kde.konsole.Session'

log = logging.getLogger('stm')


class SshTunnelHandler(object):
    @classmethod
    def __init__(cls, service, alias, launch):
        cls._window_id = os.environ['KONSOLE_DBUS_WINDOW']
        cls._service = service
        cls._alias = alias
        cls._launch = launch
        cls._parent_host = None
        cls._parent_port = None
        cls._user = None
        cls._sql_username = None
        cls._sql_password = None
        cls._sql_database = None
        cls._tunnel_type = 'ssh'

        cls.launch()

    @classmethod
    def launch(cls):
        found = False

        try:
            with open(HOSTS_FILENAME, 'r') as f_obj:
                cls._config = json.loads(f_obj.read())
        except IOError as e:
            log.error('Hosts file is missing...')
            return
        except Exception as e:
            log.exception('Got unexpected exception @ loading conf')
            return

        remote_tunnel_alias = cls._alias

        for service, conf in cls._config.get('services', {}).items():
            if cls._alias in service:
                cls._tunnel_type = 'service'
                remote_tunnel_alias = conf['remote_tunnel']
                cls._remote_port = conf['port']
                cls._service_host = conf['service_host']
                cls._service_port = conf['service_port']
                cls._service_type = conf['service_type']
                cls._sql_username = conf['sql_username']
                cls._sql_password = conf['sql_password']
                cls._sql_database = conf['sql_database']
                break

        for host_alias, conf in cls._config['hosts'].items():
            if remote_tunnel_alias in conf['users'].values():
                reversed_users_conf = {v: k for k, v in conf['users'].items()}
                cls._parent_host = conf['host']
                cls._parent_port = conf['port']
                cls._user = reversed_users_conf[remote_tunnel_alias]
                found = True
                break       

        if not found:
            log.error('Alias not found')
            return 

        if not cls._is_main_tunnel_active():
            status = cls._construct_main_tunnel()
            if not status:
                log.error('Failed to build parent tunnel for %s', (cls._alias))
                return

        if cls._launch and cls._tunnel_type == 'ssh':
            cls._construct_sub_tunnel()
        elif cls._launch and cls._tunnel_type == 'service':
            cls._construct_service_tunnel()
            if cls._launch == 1:
                cls._launch_service_client()
        elif not cls._launch and cls._tunnel_type == 'service':
            cls._construct_service_tunnel()

    @classmethod
    def _is_main_tunnel_active(cls):
        try:
            tunnel_uri = '%s:%s' % (cls._parent_port, cls._parent_host)
            subprocess.check_output(['pgrep', '-f', tunnel_uri])
        except Exception as e:
            #exception expected here, hence no logging        
            return False

        return True

    @classmethod
    def _construct_main_tunnel(cls):
        main_ssh_tunnel_cmd = 'autossh -M 0 -f -N -L %s:%s:%s %s' % (
            cls._parent_port, cls._parent_host, 22, YBER_TUNNEL)

        try:
            subprocess.call(main_ssh_tunnel_cmd, shell=True)
            time.sleep(0.5)
            log.info('Created main tunnel for %s [%s]' % 
                    (cls._alias, main_ssh_tunnel_cmd))
        except:
            log.exception('Failed to build main tunnel for %s [%s]' % 
                    (cls._alias, main_ssh_tunnel_cmd))
            return False

        return True

    @classmethod
    def _construct_sub_tunnel(cls):
        if not cls._window_id:
            log.error('Missing window_id')
            return False

        try:
            session_bus = SessionBus()
            new_session = session_bus.get_object(cls._service, cls._window_id).newSession()
            sess = session_bus.get_object(cls._service, '/Sessions/' + str(new_session))
            bus_intf = Interface(sess, KONSOLE_SESSION_PATH)
            env = bus_intf.environment()
            env.append(String('KONSOLE_DBUS_WINDOW=' + cls._window_id))
            bus_intf.setEnvironment(env)
            destination = '%s@localhost' % cls._user
            bus_intf.runCommand('ssh ' + destination + ' -p ' + str(cls._parent_port))
        except:
            log.exception('Failed to build tunnel for %s' % (cls._alias))
            return False

        return True

    @classmethod
    def _construct_service_tunnel(cls):
        try:
            service_uri = '%s:%s' % (cls._remote_port, cls._service_host)
            subprocess.check_output(['pgrep', '-f', service_uri])
            return True
        except Exception as e:
            #exception expected here, hence no logging just continue
            pass


        service_tunnel_cmd = 'autossh -M 0 -f -N -L %s:%s:%s %s@localhost -p %s' % (
            cls._remote_port, cls._service_host, cls._service_port, cls._user, cls._parent_port,
        )

        try:
            subprocess.call(service_tunnel_cmd, shell=True)
            time.sleep(1)
            log.info('Created service tunnel for %s [%s]' % (
                cls._alias, service_tunnel_cmd)
            )
        except:
            log.exception('Failed to build service tunnel for %s [%s]' % (
                cls._alias, service_tunnel_cmd)
            )
            return False

        return True

    @classmethod
    def _launch_service_client(cls):
        if not cls._window_id:
            log.error('Missing window_id')
            return False

        try:
            session_bus = SessionBus()
            new_session = session_bus.get_object(cls._service, cls._window_id).newSession()
            sess = session_bus.get_object(cls._service, '/Sessions/' + str(new_session))
            bus_intf = Interface(sess, KONSOLE_SESSION_PATH)
            env = bus_intf.environment()
            env.append(String('KONSOLE_DBUS_WINDOW=' + cls._window_id))
            bus_intf.setEnvironment(env)
            destination = '%s@localhost' % cls._user
            tab_name = None

            if cls._service_type == 'mysql':
                service_client_cmd = 'mysql -h 127.0.0.1 -P %s -u %s -p%s %s' % (
                    cls._remote_port, cls._sql_username, cls._sql_password, cls._sql_database,
                )
                tab_name = 'MySQL :: ' + cls._alias
            elif cls._service_type == 'psql':
                service_client_cmd = 'psql -h 127.0.0.1 -p %s -U %s %s' % (
                    cls._remote_port, cls._sql_username, cls._sql_database,
                )
                tab_name = 'PSQL :: ' + cls._alias
            else:
                print('Service type unknown')
                return

            bus_intf.runCommand(service_client_cmd)
            bus_intf.setTitle(1, tab_name)
        except:
            log.exception('Failed to build tunnel for %s' % (cls._alias))
            return False

        return True       

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


class ScpHandler(object):
    @classmethod
    def __init__(cls, alias, direction, files_from, files_to):
        cls._alias = alias
        cls._direction = direction
        cls._files_from = files_from
        cls._files_to = files_to

        cls._start_sending()
        cls._send_files()

    @classmethod
    def _start_sending(cls):
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

        for host_alias, conf in cls._config['hosts'].items():
            if cls._alias in conf['users'].values():
                reversed_users_conf = {v: k for k, v in conf['users'].items()}
                cls._parent_host = conf['host']
                cls._parent_port = conf['port']
                cls._user = reversed_users_conf[cls._alias]
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
    def _send_files(cls):
        if cls._direction == 'down':
            files_uri = '%s %s@localhost:%s' % (cls._files_from, cls._user, cls._files_to)
        elif cls._direction == 'up':
            files_uri = '%s@localhost:%s %s' % (cls._user, cls._files_from, cls._files_to)
        else:
            print('Unknown direction')
            return

        scp_cmd = 'scp -P %s -r %s' % (cls._parent_port, files_uri)
        try:
            subprocess.call(scp_cmd, shell=True)
        except:
            log.excption('Failed to send files with %s [%s]' % (
                cls._alias, scp_cmd)
            )
            return False

        return True



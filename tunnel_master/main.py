#! /usr/bin/python3

import json
import logging
import argparse
import logging.handlers

from stm_agent import StmAgent
from scp_handler import ScpHandler
from ssh_handler import SshTunnelHandler
from config import DEFAULT_SSH_PORT, APP_DIR, LOG_FILENAME, YBER_TUNNEL, HOSTS_FILENAME

log = logging.getLogger('stm')
log.setLevel(logging.DEBUG)
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=10*1024*1024, backupCount=5)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
log.addHandler(handler)

KONSOLE_SESSION_PATH = 'org.kde.konsole.Session'


def create_args_parser():
    parent_parser = argparse.ArgumentParser(prog='stm', description='SSH tunnel master', add_help=False)
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest='operation')
    
    # agent
    stm_agent_parser = subparsers.add_parser('agent', parents=[parent_parser])
    stm_agent_parser.add_argument('-type', default='client', required=True, choices=('client', 'service',))

    # ssh
    ssh_handler_parser = subparsers.add_parser('ssh', parents=[parent_parser])
    ssh_handler_parser.add_argument('-service', required=True)
    ssh_handler_parser.add_argument('-alias', required=True)
    ssh_handler_parser.add_argument('-count', default=1, const=1, nargs='?', type=int)
    ssh_handler_parser.add_argument('-launch', default=1, type=int)

    # scp
    scp_handler_parser = subparsers.add_parser('scp', parents=[parent_parser])
    scp_handler_parser.add_argument('-alias', required=True)
    scp_handler_parser.add_argument('-direction', choices=('down', 'up',), required=True)
    scp_handler_parser.add_argument('-from_files', required=True)
    scp_handler_parser.add_argument('-to_files', required=True)

    # info
    info_parser = subparsers.add_parser('info', parents=[parent_parser])
    info_parser.add_argument('-aliases', const='all', nargs='?')

    args = parser.parse_args()

    return args

def main():
    res = create_args_parser()

    if res.operation == 'agent':
        stm_agent = StmAgent()
        stm_agent.start_agent(res.type)
    elif res.operation == 'info':
        if res.aliases:
            try:
                with open(HOSTS_FILENAME, 'r') as f_obj:
                    config = json.loads(f_obj.read())
            except IOError as e:
                log.error('Creating new conf file, reason: %s', e)
            except ValueError as e:
                log.error('Creating new conf, reason: %s', e)

            for host_alias, conf in config['hosts'].items():
                for username, alias in conf['users'].items():
                    print('%-30s - %s:%s' % (alias, conf['host'], conf['port']))
    elif res.operation == 'ssh':
        for i in range(res.count):
            SshTunnelHandler(res.service, res.alias, res.launch)
    elif res.operation == 'scp':
        ScpHandler(res.alias, res.direction, res.from_files, res.to_files)


if __name__ == '__main__':
    main()

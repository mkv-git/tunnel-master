import os

DEFAULT_SSH_PORT = 22
APP_NAME = 'ssh_tunnel_master'
APP_DIR = os.path.join(os.getenv('HOME'), '.local/share/' + APP_NAME)
LOG_DIR = os.path.join(APP_DIR, 'logs')
LOG_FILENAME = os.path.join(LOG_DIR, APP_NAME + '.log')
SSH_FILENAME = os.path.join(os.getenv('HOME'), '.ssh', 'known_hosts')
BASHRC_FILENAME = os.path.join(os.getenv('HOME'), '.bashrc')
ALIASES_FILENAME = os.path.join(os.getenv('HOME'), '.bash_aliases')
SSH_TUNNEL_MASTER_ALIASES = os.path.join(os.getenv('HOME'), '.bash_stm_aliases')
HOSTS_FILENAME = os.path.join(APP_DIR, 'hosts.conf')
YBER_TUNNEL = 'maksko@ybershell.estpak.ee'

if not os.access(APP_DIR, os.F_OK):
    os.mkdir(APP_DIR)

if not os.access(LOG_DIR, os.F_OK):
    os.mkdir(LOG_DIR)

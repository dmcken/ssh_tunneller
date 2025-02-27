'''
Primary entrypoint for Docker container

SSHTunneller is a simple docker image which allows you to establish SSH tunnels
by just deploying a container with some enviroment variables by password or
publickey authentication. The SSH Tunnels are pure python implemented with the
SSHTunnel library. This little tool uses the magic of Docker to restart the
tunnel if the tunnel dies for any reason.
'''

# System imports
import ast
import io
import logging
import os
import pprint
import sys
import time

# from contextlib import redirect_stdout

# External imports
import sshtunnel

logger = logging.getLogger(__name__)

def check_log_level(level: str, default_level: str = 'INFO') -> int:
    '''
    Vet the logging level sent in, based on info from:
    https://stackoverflow.com/questions/18846024/get-list-of-named-loglevels

    Until a public / formal method exists for this the protected member access
    will have to continue.
    '''
    # pylint: disable=protected-access
    if level in logging._nameToLevel:
        return logging._nameToLevel[level]

    return logging._nameToLevel[default_level]

def setup_logging() -> None:
    '''
    Setup logging for this script
    '''
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S' # ISO format
    log_level_default = 'INFO'

    log_level = os.environ.get("log_level", log_level_default)
    log_level_value = check_log_level(log_level, default_level=log_level_default)

    #TODO: allow the user to set any underlying modules / packages logging levels.
    # Current thoughts on the matter, allow the definition of variable:
    # log_level_<module name> = ERROR
    # for example log_level_paramiko would then translate to:
    # logging.getLogger('paramiko').setLevel(logging.ERROR)
    logging.getLogger('paramiko.transport').setLevel(logging.ERROR)

    logging.basicConfig(
        format=log_format,
        datefmt=date_format,
        level=log_level_value,
    )

def parse_config() -> dict[str,str]:
    '''
    Parse config data.

    Scan and parse environment and produce argument dictionary to pass to
    sshtunnel's open_tunnel function.
    '''
    tunnel_params = {}

    # Mandatory items
    ssh_host = os.environ.get("ssh_host")
    ssh_port = int(os.environ.get("ssh_port"))
    ssh_username = os.environ.get("ssh_username")

    tunnel_params['ssh_address_or_host'] = tuple([ssh_host, ssh_port])
    tunnel_params['ssh_username'] = ssh_username
    tunnel_params['set_keepalive'] = 30.0

    private_key_file = "/private.key"
    if os.path.exists(private_key_file):
        logging.debug("Private key present - using public key authentication")
        tunnel_params['ssh_pkey'] = private_key_file

        ssh_private_key_password = os.environ.get("ssh_private_key_password")
        if ssh_private_key_password in [None, 'None']:
            pass # No key password
        else:
            tunnel_params['ssh_private_key_password'] = ssh_private_key_password
    else:
        ssh_password = os.environ.get("ssh_password")
        if ssh_password is None:
            logging.error("SSH Password not provided, quitting...")
            sys.exit(-1)
        else:
            tunnel_params['ssh_password'] = ssh_password

    # Tunnel forwards
    remote_bind_addresses = os.environ.get("remote_bind_addresses")
    local_bind_addresses = os.environ.get("local_bind_addresses")
    tunnel_params['remote_bind_addresses'] = ast.literal_eval(remote_bind_addresses)
    tunnel_params['local_bind_addresses']  = ast.literal_eval(local_bind_addresses)

    return tunnel_params

def start_tunnel() -> None:
    '''
    Start tunnel with logging
    '''
    setup_logging()

    ### Setup the console handler with a StringIO object
    log_capture_string = io.StringIO()
    handler_ch = logging.StreamHandler(log_capture_string)
    handler_ch.setLevel(logging.ERROR)

    ### Add the console handler to the logger
    logger.addHandler(handler_ch)

    tunnel_config = parse_config()

    logging.info("SSH Tunnel starting...")
    # Potentally dangerous statement as passwords will be included
    logging.debug("SSH Tunnel parameters:\n%s", pprint.pformat(tunnel_config))

    try:
        with sshtunnel.open_tunnel(
            **tunnel_config
        ) as server:
            logging.info("SSH Tunnels established on %s@%s:%d\nbinds: '%s' => '%s'",
                tunnel_config['ssh_username'],
                tunnel_config['ssh_address_or_host'][0],
                tunnel_config['ssh_address_or_host'][1],
                tunnel_config['remote_bind_addresses'],
                tunnel_config['local_bind_addresses'],
            )
            while True:
                check_tunnel(server, log_capture_string)
    except Exception as exc:
        logging.error("SSH Tunnel Failed %s", exc)
    finally:
        logging.warning("SSH Tunnel ended")

def check_tunnel(server, stdout):
    '''
    Check status of tunnel
    '''
    #Check for remote side error from internal modules of Paramiko/SSHTunnel
    out = stdout.getvalue()

    if 'to remote side of the tunnel' in out:
        logging.error("Problem with remote side, maybe the other side is unavailable, "
            "restarting...")

        sys.exit(-2)

    server.check_tunnels()

    for ret in server.tunnel_is_up.values():
        if ret is False:
            logging.error("Tunnel is dead, restarting...")
            sys.exit(-1)

    time.sleep(1)

if __name__== "__main__":
    start_tunnel()

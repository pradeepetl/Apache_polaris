#!/usr/bin/env python3
import json
import os
import re
import socket
import subprocess
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PRINCIPALS_FILE = '/data/principals.json'
ICEBERG_PROPS = '/catalog/iceberg.properties'
DOCKER_SOCKET = '/var/run/docker.sock'
TRINO_CONTAINER = os.environ.get('TRINO_CONTAINER', 'trino')
CREDENTIAL_KEY = 'iceberg.rest-catalog.oauth2.credential='
ALLOWED_CONTAINERS = {'polaris', 'trino', 'localstack', 'spark-jupyter', 'marimo'}
COMPOSE_FILE = '/compose/docker-compose.yml'
POLARIS_CONTAINER = 'polaris'


def dechunk(body):
    decoded = b''
    pos = 0
    while pos < len(body):
        nl = body.find(b'\r\n', pos)
        if nl == -1:
            break
        size_str = body[pos:nl].decode('ascii', errors='replace').strip()
        try:
            chunk_size = int(size_str, 16)
        except ValueError:
            break
        if chunk_size == 0:
            break
        start = nl + 2
        decoded += body[start:start + chunk_size]
        pos = start + chunk_size + 2
    return decoded


def docker_logs(container, tail=50, grep_pattern=None):
    if container not in ALLOWED_CONTAINERS:
        return f'Container "{container}" not allowed'
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(3)
    sock.connect(DOCKER_SOCKET)
    path = f'/v1.41/containers/{container}/logs?stdout=true&stderr=true&tail={tail}'
    request = f'GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'
    sock.sendall(request.encode())
    chunks = []
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        except socket.timeout:
            break
    sock.close()
    raw = b''.join(chunks)
    parts = raw.split(b'\r\n\r\n', 1)
    body = parts[1] if len(parts) > 1 else b''
    header = parts[0].decode('utf-8', errors='replace') if parts else ''
    if 'chunked' in header.lower():
        body = dechunk(body)
    lines = []
    i = 0
    while i < len(body):
        if i + 8 <= len(body):
            size = int.from_bytes(body[i+4:i+8], 'big')
            if size > 0 and i + 8 + size <= len(body):
                lines.append(body[i+8:i+8+size].decode('utf-8', errors='replace'))
                i += 8 + size
                continue
        lines.append(body[i:].decode('utf-8', errors='replace'))
        break
    text = ''.join(lines)
    if grep_pattern:
        text = '\n'.join(l for l in text.split('\n') if grep_pattern in l)
    return text


def docker_env(container):
    if container not in ALLOWED_CONTAINERS:
        return f'Container "{container}" not allowed'
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(DOCKER_SOCKET)
        path = f'/v1.41/containers/{container}/json'
        request = f'GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n'
        sock.sendall(request.encode())
        chunks = []
        while True:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            except socket.timeout:
                break
        sock.close()
        raw = b''.join(chunks)
        parts = raw.split(b'\r\n\r\n', 1)
        body = parts[1] if len(parts) > 1 else b''
        data = json.loads(body.decode('utf-8', errors='replace'))
        env_list = data.get('Config', {}).get('Env', [])
        return '\n'.join(env_list)
    except Exception as e:
        return f'Error: {e}'


def get_polaris_realms():
    env_text = docker_env(POLARIS_CONTAINER)
    realms = []
    creds = {}
    for line in env_text.split('\n'):
        if line.startswith('POLARIS_REALM_CONTEXT_REALMS='):
            realms = [r.strip() for r in line.split('=', 1)[1].split(',') if r.strip()]
        elif line.startswith('POLARIS_BOOTSTRAP_CREDENTIALS='):
            raw = line.split('=', 1)[1]
            for entry in raw.split(';'):
                parts = entry.strip().split(',')
                if len(parts) >= 3:
                    creds[parts[0].strip()] = {
                        'clientId': parts[1].strip(),
                        'clientSecret': parts[2].strip()
                    }
    return realms, creds


def read_compose_env_var(key):
    with open(COMPOSE_FILE, 'r') as f:
        content = f.read()
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith(f'{key}:'):
            val = stripped.split(':', 1)[1].strip().strip('"').strip("'")
            return val
    return ''


def update_compose_env_var(key, new_value):
    with open(COMPOSE_FILE, 'r') as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f'{key}:'):
            indent = line[:len(line) - len(line.lstrip())]
            needs_quote = ';' in new_value or ',' in new_value
            if needs_quote:
                new_lines.append(f'{indent}{key}: "{new_value}"\n')
            else:
                new_lines.append(f'{indent}{key}: {new_value}\n')
        else:
            new_lines.append(line)
    with open(COMPOSE_FILE, 'w') as f:
        f.writelines(new_lines)


def current_realm_env():
    # The running container is the source of truth; the compose file may be a different copy (e.g. devcontainer).
    realms, creds = get_polaris_realms()
    if not realms:
        realms = [r.strip() for r in read_compose_env_var('POLARIS_REALM_CONTEXT_REALMS').split(',') if r.strip()]
    entries = [f'{r},{c["clientId"]},{c["clientSecret"]}' for r, c in creds.items()]
    if not entries:
        entries = [e.strip() for e in read_compose_env_var('POLARIS_BOOTSTRAP_CREDENTIALS').split(';') if e.strip()]
    return realms, entries


def save_realm_env(realm_list, cred_entries):
    env = {
        'POLARIS_REALM_CONTEXT_REALMS': ','.join(realm_list),
        'POLARIS_BOOTSTRAP_CREDENTIALS': ';'.join(cred_entries),
    }
    # Best effort: keeps the realm after `docker compose up` recreates the container.
    try:
        for key, value in env.items():
            update_compose_env_var(key, value)
    except OSError:
        pass
    return env


def add_realm_to_compose(realm_name, client_id, client_secret):
    realm_list, cred_entries = current_realm_env()
    if realm_name in realm_list:
        return False, f'Realm "{realm_name}" already exists'
    for value in (client_id, client_secret):
        if any(ch in value for ch in ',;=" '):
            return False, 'Client ID and secret must not contain commas, semicolons, quotes, "=" or spaces'
    realm_list.append(realm_name)
    cred_entries = [e for e in cred_entries if not e.startswith(f'{realm_name},')]
    cred_entries.append(f'{realm_name},{client_id},{client_secret}')
    return True, save_realm_env(realm_list, cred_entries)


def remove_realm_from_compose(realm_name):
    realm_list, cred_entries = current_realm_env()
    if realm_name not in realm_list:
        return False, f'Realm "{realm_name}" not found'
    if len(realm_list) <= 1:
        return False, 'Cannot remove the last realm'
    realm_list.remove(realm_name)
    cred_entries = [e for e in cred_entries if not e.startswith(f'{realm_name},')]
    return True, save_realm_env(realm_list, cred_entries)


def docker_api(method, path, body=None):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(60)
    sock.connect(DOCKER_SOCKET)
    headers = f'{method} {path} HTTP/1.0\r\nHost: localhost\r\n'
    if body:
        headers += f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n'
    headers += '\r\n'
    sock.sendall(headers.encode())
    if body:
        sock.sendall(body.encode() if isinstance(body, str) else body)
    chunks = []
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        except socket.timeout:
            break
    sock.close()
    raw = b''.join(chunks)
    parts = raw.split(b'\r\n\r\n', 1)
    status_line = parts[0].decode('utf-8', errors='replace').split('\r\n')[0] if parts else ''
    status_code = int(status_line.split(' ')[1]) if len(status_line.split(' ')) > 1 else 0
    resp_body = parts[1] if len(parts) > 1 else b''
    return status_code, resp_body


def inspect_container(name):
    status, body = docker_api('GET', f'/v1.41/containers/{name}/json')
    if status != 200:
        return None
    if body[:1] not in (b'{', b'['):
        body = dechunk(body)
    return json.loads(body.decode('utf-8', errors='replace'))


def create_and_start(name, config, host_config, networks):
    # Create attaches one network; the rest are connected afterwards.
    net_items = list(networks.items())
    networking = {}
    if net_items:
        first_name, first_cfg = net_items[0]
        networking = {'EndpointsConfig': {first_name: first_cfg}}
    body = json.dumps({**config, 'HostConfig': host_config, 'NetworkingConfig': networking})
    status, resp = docker_api('POST', f'/v1.41/containers/create?name={name}', body)
    if status != 201:
        return False, f'create failed (HTTP {status}): {resp.decode("utf-8", errors="replace")[:300]}'
    for net_name, net_cfg in net_items[1:]:
        docker_api('POST', f'/v1.41/networks/{net_name}/connect',
                   json.dumps({'Container': name, 'EndpointConfig': net_cfg}))
    status, _ = docker_api('POST', f'/v1.41/containers/{name}/start')
    if status not in (200, 204, 304):
        return False, f'start failed (HTTP {status})'
    return True, 'OK'


def recreate_polaris(env_updates):
    # Clone the running container so network, aliases, image, ports, volumes and compose labels survive.
    info = inspect_container(POLARIS_CONTAINER)
    if not info:
        return False, f'Container "{POLARIS_CONTAINER}" not found'

    old = info.get('Config', {})
    env = [e for e in (old.get('Env') or []) if e.split('=', 1)[0] not in env_updates]
    env += [f'{k}={v}' for k, v in env_updates.items()]

    keep = ('Image', 'Cmd', 'Entrypoint', 'WorkingDir', 'User', 'Labels', 'ExposedPorts', 'Healthcheck', 'Volumes')
    config = {k: old[k] for k in keep if old.get(k) is not None}
    config['Env'] = env
    # Copy only portable settings; inspect output also has runtime-only fields that make create/start fail.
    old_host = info.get('HostConfig', {})
    host_keys = ('Binds', 'PortBindings', 'RestartPolicy', 'ExtraHosts', 'Mounts', 'LogConfig')
    host_config = {k: old_host[k] for k in host_keys if old_host.get(k)}

    networks = {}
    for net_name, net in (info.get('NetworkSettings', {}).get('Networks') or {}).items():
        aliases = [a for a in (net.get('Aliases') or []) if a != info.get('Id', '')[:12]]
        if POLARIS_CONTAINER not in aliases:
            aliases.append(POLARIS_CONTAINER)
        networks[net_name] = {'Aliases': aliases}
    if networks:
        host_config['NetworkMode'] = next(iter(networks))

    old_name = f'{POLARIS_CONTAINER}-old'
    docker_api('DELETE', f'/v1.41/containers/{old_name}?force=true')
    status, _ = docker_api('POST', f'/v1.41/containers/{POLARIS_CONTAINER}/stop?t=10')
    if status not in (204, 304):
        return False, f'Failed to stop polaris (HTTP {status})'
    # Keep the old container (renamed) until the new one is up, so a failed create can be rolled back.
    status, _ = docker_api('POST', f'/v1.41/containers/{POLARIS_CONTAINER}/rename?name={old_name}')
    if status not in (200, 204):
        docker_api('POST', f'/v1.41/containers/{POLARIS_CONTAINER}/start')
        return False, f'Failed to rename polaris (HTTP {status})'

    ok, msg = create_and_start(POLARIS_CONTAINER, config, host_config, networks)
    if not ok:
        docker_api('DELETE', f'/v1.41/containers/{POLARIS_CONTAINER}?force=true')
        docker_api('POST', f'/v1.41/containers/{old_name}/rename?name={POLARIS_CONTAINER}')
        docker_api('POST', f'/v1.41/containers/{POLARIS_CONTAINER}/start')
        return False, f'{msg}; previous Polaris container restored'

    docker_api('DELETE', f'/v1.41/containers/{old_name}?force=true')
    return True, 'Polaris container recreated and starting'


def load_principals():
    if not os.path.exists(PRINCIPALS_FILE):
        return []
    with open(PRINCIPALS_FILE, 'r') as f:
        data = json.load(f)
    return data.get('principals', [])


def get_trino_realm():
    if os.path.exists(ICEBERG_PROPS):
        with open(ICEBERG_PROPS, 'r') as f:
            for line in f:
                m = re.search(r'Polaris-Realm:\s*([^,\s]+)', line)
                if line.strip().startswith('iceberg.rest-catalog.http-headers=') and m:
                    return m.group(1)
    return None


def get_bootstrap_root():
    creds = {}
    try:
        _, creds = get_polaris_realms()
    except Exception:
        pass
    if not creds:
        try:
            raw = read_compose_env_var('POLARIS_BOOTSTRAP_CREDENTIALS')
            for entry in raw.split(';'):
                parts = [p.strip() for p in entry.split(',')]
                if len(parts) >= 3:
                    creds[parts[0]] = {'clientId': parts[1], 'clientSecret': parts[2]}
        except Exception:
            pass
    if not creds:
        return None
    realm = get_trino_realm()
    c = creds.get(realm) or next(iter(creds.values()))
    return {'name': c['clientId'], 'clientId': c['clientId'], 'clientSecret': c['clientSecret'], 'builtin': True}


def list_principals():
    """Saved principals plus the bootstrap root (a saved entry with the same clientId wins, e.g. after rotation)."""
    principals = load_principals()
    root = get_bootstrap_root()
    if root and not any(p.get('clientId') == root['clientId'] for p in principals):
        principals = [root] + principals
    return principals


def save_principals(principals):
    os.makedirs(os.path.dirname(PRINCIPALS_FILE), exist_ok=True)
    with open(PRINCIPALS_FILE, 'w') as f:
        json.dump({'principals': principals}, f, indent=2)


def get_active_credential():
    if not os.path.exists(ICEBERG_PROPS):
        return None, None
    with open(ICEBERG_PROPS, 'r') as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith(CREDENTIAL_KEY):
                cred = stripped[len(CREDENTIAL_KEY):]
                parts = cred.split(':', 1)
                client_id = parts[0] if parts else cred
                return client_id, cred
    return None, None


def update_credential(client_id, client_secret):
    # Every Polaris-backed Trino catalog (iceberg, global_sales, ...) uses the same principal.
    catalog_dir = os.path.dirname(ICEBERG_PROPS)
    for name in sorted(os.listdir(catalog_dir)):
        if not name.endswith('.properties'):
            continue
        path = os.path.join(catalog_dir, name)
        with open(path, 'r') as f:
            lines = f.readlines()
        if not any(l.strip().startswith(CREDENTIAL_KEY) for l in lines):
            continue
        new_lines = [
            f'{CREDENTIAL_KEY}{client_id}:{client_secret}\n' if l.strip().startswith(CREDENTIAL_KEY) else l
            for l in lines
        ]
        with open(path, 'w') as f:
            f.writelines(new_lines)


def restart_trino():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect(DOCKER_SOCKET)
    request = (
        f'POST /v1.41/containers/{TRINO_CONTAINER}/restart?t=10 HTTP/1.1\r\n'
        f'Host: localhost\r\n'
        f'Content-Length: 0\r\n'
        f'\r\n'
    )
    sock.sendall(request.encode())
    response = sock.recv(4096).decode()
    sock.close()
    status_line = response.split('\r\n')[0]
    status_code = int(status_line.split(' ')[1])
    return status_code in (200, 204, 304)


class ManagerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f'[{datetime.now().strftime("%H:%M:%S")}] {format % args}')

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        path = urlparse(self.path).path.rstrip('/')

        if path == '/health':
            self.send_json(200, {'status': 'ok'})

        elif path == '/principals':
            self.send_json(200, {'principals': list_principals()})

        elif path == '/active':
            client_id, _ = get_active_credential()
            principals = list_principals()
            name = None
            for p in principals:
                if p.get('clientId') == client_id:
                    name = p['name']
                    break
            self.send_json(200, {'clientId': client_id, 'name': name})

        elif path == '/realms':
            try:
                realms, creds = get_polaris_realms()
                realm_list = []
                for r in realms:
                    info = {'name': r}
                    if r in creds:
                        info['clientId'] = creds[r]['clientId']
                    realm_list.append(info)
                self.send_json(200, {'realms': realm_list})
            except Exception as e:
                self.send_json(500, {'error': f'Failed to read realms: {e}'})

        elif path == '/realms/status':
            try:
                status_code, body = docker_api('GET', f'/v1.41/containers/{POLARIS_CONTAINER}/json')
                if status_code == 200:
                    data = json.loads(body.decode('utf-8', errors='replace'))
                    state = data.get('State', {})
                    health = state.get('Health', {}).get('Status', 'unknown')
                    running = state.get('Running', False)
                    self.send_json(200, {'running': running, 'health': health})
                else:
                    self.send_json(200, {'running': False, 'health': 'not found'})
            except Exception as e:
                self.send_json(200, {'running': False, 'health': f'error: {e}'})

        else:
            self.send_json(404, {'error': 'Not found'})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip('/')

        if path == '/principals':
            body = self.read_body()
            name = body.get('name', '').strip()
            client_id = body.get('clientId', '').strip()
            client_secret = body.get('clientSecret', '').strip()
            if not name or not client_id or not client_secret:
                self.send_json(400, {'error': 'name, clientId, and clientSecret are required'})
                return
            principals = load_principals()
            principals = [p for p in principals if p['name'] != name]
            principals.append({
                'name': name,
                'clientId': client_id,
                'clientSecret': client_secret,
                'savedAt': datetime.now(timezone.utc).isoformat()
            })
            save_principals(principals)
            self.send_json(201, {'ok': True, 'message': f'Principal "{name}" saved'})

        elif path == '/switch':
            body = self.read_body()
            name = body.get('name', '').strip()
            client_id = body.get('clientId', '').strip()
            client_secret = body.get('clientSecret', '').strip()

            if name and (not client_id or not client_secret):
                principals = list_principals()
                match = next((p for p in principals if p['name'] == name), None)
                if not match:
                    self.send_json(404, {'error': f'Principal "{name}" not found in saved principals'})
                    return
                client_id = match['clientId']
                client_secret = match['clientSecret']

            if not client_id or not client_secret:
                self.send_json(400, {'error': 'Provide name (of saved principal) or clientId + clientSecret'})
                return

            try:
                update_credential(client_id, client_secret)
            except Exception as e:
                self.send_json(500, {'error': f'Failed to update config: {e}'})
                return

            try:
                ok = restart_trino()
                if not ok:
                    self.send_json(500, {'error': 'Docker restart returned unexpected status'})
                    return
            except Exception as e:
                self.send_json(500, {'error': f'Failed to restart Trino: {e}'})
                return

            self.send_json(200, {
                'ok': True,
                'message': f'Credential updated to {client_id}, Trino restarting',
                'clientId': client_id
            })

        elif path == '/realms':
            body = self.read_body()
            name = body.get('name', '').strip().upper()
            client_id = body.get('clientId', '').strip()
            client_secret = body.get('clientSecret', '').strip()
            if not name or not client_id or not client_secret:
                self.send_json(400, {'error': 'name, clientId, and clientSecret are required'})
                return
            if not name.replace('_', '').replace('-', '').isalnum():
                self.send_json(400, {'error': 'Realm name must be alphanumeric (underscores and dashes allowed)'})
                return
            try:
                ok, result = add_realm_to_compose(name, client_id, client_secret)
                if not ok:
                    self.send_json(409 if 'already exists' in result else 400, {'error': result})
                    return
                ok, msg = recreate_polaris(result)
                if not ok:
                    self.send_json(500, {'error': f'Container recreation failed: {msg}'})
                    return
                self.send_json(201, {
                    'ok': True,
                    'message': f'Realm "{name}" added. Polaris is restarting (~15s).',
                    'realm': name
                })
            except Exception as e:
                self.send_json(500, {'error': f'Failed to add realm: {e}'})

        elif path == '/restart-proxy':
            self.send_json(200, {'ok': True, 'message': 'Restarting proxy in 1s'})
            def _restart():
                import time
                time.sleep(1)
                try:
                    docker_api('POST', '/v1.41/containers/polaris-admin/restart?t=2')
                except Exception:
                    pass
            threading.Thread(target=_restart, daemon=True).start()

        elif path == '/exec':
            body = self.read_body()
            cmd = body.get('cmd', '').strip()
            if not cmd:
                self.send_json(400, {'error': 'cmd is required'})
                return
            try:
                if cmd.startswith('docker logs '):
                    parts = cmd.split()
                    container = 'polaris'
                    tail = 50
                    grep = None
                    i = 2
                    while i < len(parts):
                        if parts[i] == '--tail' and i + 1 < len(parts):
                            tail = int(parts[i+1]); i += 2
                        elif parts[i] == '2>&1':
                            i += 1
                        elif parts[i] == '|':
                            rest = ' '.join(parts[i+1:])
                            if 'grep' in rest:
                                for p in parts[i+1:]:
                                    if p not in ('grep', '|', 'tail', '-30', '-20', '-10', '-5', '2>&1', '-i'):
                                        grep = p.strip('"').strip("'")
                                        break
                            break
                        else:
                            container = parts[i]; i += 1
                    output = docker_logs(container, tail, grep)
                    if grep and 'tail' in cmd:
                        lines = output.strip().split('\n')
                        try:
                            n = int([p for p in parts if p.startswith('-') and p[1:].isdigit()][-1][1:])
                            output = '\n'.join(lines[-n:])
                        except:
                            pass
                    self.send_json(200, {'output': output, 'exitCode': 0})
                elif cmd.startswith('docker exec '):
                    parts = cmd.split(None, 3)
                    container = parts[2] if len(parts) > 2 else 'polaris'
                    subcmd = parts[3] if len(parts) > 3 else ''
                    if 'env' in subcmd and 'otel' in subcmd.lower():
                        output = docker_env(container)
                        if 'otel' in subcmd.lower() or 'OTEL' in subcmd:
                            output = '\n'.join(l for l in output.split('\n') if 'otel' in l.lower() or 'OTEL' in l)
                        if not output.strip():
                            output = 'No OTEL env vars found'
                        self.send_json(200, {'output': output, 'exitCode': 0})
                    else:
                        self.send_json(200, {'output': docker_env(container), 'exitCode': 0})
                else:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                    output = result.stdout
                    if result.stderr and not result.stdout:
                        output = result.stderr
                    elif result.stderr:
                        output = result.stdout + '\n' + result.stderr
                    self.send_json(200, {'output': output, 'exitCode': result.returncode})
            except subprocess.TimeoutExpired:
                self.send_json(200, {'output': '(command timed out after 30s)', 'exitCode': -1})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        else:
            self.send_json(404, {'error': 'Not found'})

    def do_DELETE(self):
        path = urlparse(self.path).path.rstrip('/')
        parts = path.split('/')
        if len(parts) == 3 and parts[1] == 'principals':
            name = parts[2]
            principals = load_principals()
            before = len(principals)
            principals = [p for p in principals if p['name'] != name]
            if len(principals) == before:
                self.send_json(404, {'error': f'Principal "{name}" not found'})
                return
            save_principals(principals)
            self.send_json(200, {'ok': True, 'message': f'Principal "{name}" deleted'})
        elif len(parts) == 3 and parts[1] == 'realms':
            name = parts[2].upper()
            try:
                ok, result = remove_realm_from_compose(name)
                if not ok:
                    self.send_json(400 if 'last realm' in result else 404, {'error': result})
                    return
                ok, msg = recreate_polaris(result)
                if not ok:
                    self.send_json(500, {'error': f'Container recreation failed: {msg}'})
                    return
                self.send_json(200, {
                    'ok': True,
                    'message': f'Realm "{name}" removed. Polaris is restarting (~15s).',
                })
            except Exception as e:
                self.send_json(500, {'error': f'Failed to remove realm: {e}'})
        else:
            self.send_json(404, {'error': 'Not found'})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), ManagerHandler)
    print(f'Polaris Manager API listening on port {port}')
    server.serve_forever()

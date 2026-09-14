"""Run inside a disposable Linux control harness with Docker socket access.
Never run against your application's broker state or workspace. See README.
"""
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
import uuid

from backend.app.sandbox_broker import Broker, Config, DockerError


def main():
    os.environ['CODEZZN_SANDBOX_TOKEN'] = secrets.token_hex(32)
    os.environ['CODEZZN_SANDBOX_INSTANCE'] = 'verification-' + uuid.uuid4().hex[:12]
    os.environ['CODEZZN_SANDBOX_WORKSPACE_CONTAINER'] = 'codezzn-sandbox-verification'
    # /workspace is a dedicated scratch volume, never the user's working tree.
    os.chmod('/workspace', 0o777)
    with tempfile.TemporaryDirectory() as temp:
        os.environ['CODEZZN_SANDBOX_STATE'] = str(Path(temp) / 'tasks.db')
        config = Config()
        broker = Broker(config)
        results = []

        def submit(command, mode='read-only'):
            return broker.submit({'id': uuid.uuid4().hex, 'command': command, 'mode': mode})['id']

        def finish(task):
            end = time.monotonic() + 90
            while time.monotonic() < end:
                with broker.lock:
                    active = broker.running.get(task)
                if active is None:
                    row = broker.get(task)
                    assert not row['cleanup_pending'], row
                    try:
                        broker.docker.request('GET', '/containers/' + row['name'] + '/json')
                        raise AssertionError('container still exists')
                    except DockerError as exc:
                        assert exc.status == 404
                    return row
                active[0].join(timeout=0.2)
            raise AssertionError('task did not terminate')

        try:
            command = '''python - <<'PY'
import os, pathlib, socket
assert os.getuid() == 10001
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not pathlib.Path('/app/data').exists()
assert 'CODEZZN_SANDBOX_TOKEN' not in os.environ
try:
    pathlib.Path('/workspace/forbidden').write_text('no')
    raise AssertionError('read-only mount writable')
except OSError:
    pass
try:
    pathlib.Path('/etc/forbidden').write_text('no')
    raise AssertionError('root filesystem writable')
except OSError:
    pass
s = socket.socket(); s.settimeout(1)
try:
    s.connect(('1.1.1.1', 443))
    raise AssertionError('network reachable')
except OSError:
    pass
print('isolation assertions passed')
PY'''
            row = finish(submit(command))
            assert row['status'] == 'completed' and row['exit_code'] == 0, row
            results.append('non-root/read-only/no-socket/no-data/no-secret/network denied')
            row = finish(submit("python -c \"from pathlib import Path; Path('/workspace/result.txt').write_text('ok')\"", 'workspace-write'))
            assert row['exit_code'] == 0, row
            assert Path('/workspace/result.txt').read_text() == 'ok'
            results.append('workspace-write persists only in scratch volume')
            task = submit('sleep 30')
            end = time.monotonic() + 20
            while broker.get(task)['status'] != 'running' and time.monotonic() < end:
                time.sleep(0.1)
            row = broker.get(task)
            info = broker.docker.request('GET', '/containers/' + row['name'] + '/json')
            host = info['HostConfig']
            assert host['NetworkMode'] == 'none'
            assert host['Memory'] == config.memory and host['MemorySwap'] == config.memory
            assert host['NanoCpus'] == int(config.cpus * 1e9) and host['PidsLimit'] == config.pids
            assert info['Config']['User'] == '10001:10001'
            assert len(info['Mounts']) == 1 and info['Mounts'][0]['Destination'] == '/workspace'
            broker.cancel(task)
            assert finish(task)['status'] == 'cancelled'
            results.append('Docker inspect CPU/memory/PID caps + cancellation removes container')
            config.timeout = 2
            task = submit("python -c \"import subprocess,time; subprocess.Popen(['sleep','99']); time.sleep(99)\"")
            assert finish(task)['status'] == 'timed_out'
            results.append('timeout destroys container including child processes')
            config.timeout = 60
            row = finish(submit("python -c \"x=bytearray(1024*1024*1024)\""))
            assert row['status'] == 'failed' and 'Memory limit' in row['error'], row
            results.append('memory exhaustion is OOM-killed within 512 MiB limit')
            command = '''python - <<'PY'
import subprocess
children=[]
limited=False
try:
    for _ in range(100):
        try:
            children.append(subprocess.Popen(['sleep', '20']))
        except OSError:
            limited=True
            break
    assert limited, 'PID cap not enforced'
    print('PID cap enforced')
finally:
    for child in children:
        child.terminate()
    for child in children:
        child.wait()
PY'''
            row = finish(submit(command))
            assert row['exit_code'] == 0, row
            results.append('PID exhaustion is blocked at configured process cap')
            # Independent PID-1 watchdog must work with no broker worker/reaper.
            from backend.app.sandbox_broker import container_spec
            watchdog = uuid.uuid4().hex
            watchdog_name = 'codezzn-' + config.instance + '-' + watchdog
            spec = container_spec(config, watchdog, 'sleep 99', 'read-only', broker.workspace(), time.time()+1, broker.image())
            broker.docker.request('POST', '/containers/create?name=' + watchdog_name, spec)
            broker.docker.request('POST', '/containers/' + watchdog_name + '/start')
            time.sleep(2)
            info = broker.docker.request('GET', '/containers/' + watchdog_name + '/json')
            assert not info['State']['Running'] and info['State']['ExitCode'] == 124, info['State']
            broker.remove(watchdog_name)
            results.append('independent container watchdog expires without broker worker')
            # Simulate a broker crash by creating an orphan directly without a worker.
            from backend.app.sandbox_broker import container_spec
            orphan = uuid.uuid4().hex
            name = 'codezzn-' + config.instance + '-' + orphan
            spec = container_spec(config, orphan, 'sleep 99', 'read-only', broker.workspace(), time.time()+60, broker.image())
            broker.docker.request('POST', '/containers/create?name=' + name, spec)
            broker.docker.request('POST', '/containers/' + name + '/start')
            with broker.db() as db:
                db.execute('INSERT INTO tasks(id,name,status,mode,created,deadline) VALUES(?,?,?,?,?,?)',
                           (orphan,name,'running','read-only',time.time(),time.time()+60))
            restored = Broker(config)
            restored.recover()
            assert restored.get(orphan)['status'] == 'interrupted'
            assert not restored.get(orphan)['cleanup_pending']
            results.append('startup orphan reconciliation and durable interrupted state')
            print(json.dumps({'passed': results, 'count': len(results)}, indent=2))
        finally:
            broker.close()


if __name__ == '__main__':
    main()

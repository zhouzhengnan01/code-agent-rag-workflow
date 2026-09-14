"""Offline tests: python -m unittest discover -s tests -p test_sandbox.py -v"""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.app.sandbox_broker import Broker, Config, DockerError, container_spec, decode_logs


class FakeDocker:
    def __init__(self):
        self.containers = {}
        self.specs = []
        self.forever = False
        self.fail_start = False
        self.fail_delete = False
        self.warnings = []

    def request(self, method, path, body=None, **kwargs):
        if path.startswith('/images/'):
            return {'Id': 'sha256:test', 'Os': 'linux', 'Config': {}}
        if path == '/containers/codezzn/json':
            return {'Mounts': [{'Destination': '/workspace', 'Source': '/host/project/workspace', 'Type': 'bind'}]}
        if path.startswith('/containers/json?'):
            return [{'Id': name, 'Labels': spec['Labels']} for name, spec in list(self.containers.items())]
        if path.startswith('/containers/create?'):
            from urllib.parse import parse_qs, urlparse
            name = parse_qs(urlparse(path).query)['name'][0]
            self.containers[name] = body
            self.specs.append(body)
            return {'Id': name, 'Warnings': self.warnings}
        name = path.split('/')[2].split('?')[0]
        if method == 'DELETE':
            if self.fail_delete:
                raise DockerError(500, 'unavailable')
            if name not in self.containers:
                raise DockerError(404, 'absent')
            self.containers.pop(name)
            return {}
        if path.endswith('/start'):
            if self.fail_start:
                raise DockerError(500, 'start failed')
            return {}
        if path.endswith('/json'):
            if name not in self.containers:
                raise DockerError(404, 'absent')
            return {'Config': self.containers[name], 'State': {'Running': self.forever, 'ExitCode': 0}}
        if '/logs?' in path:
            text = b'uid=10001 sandbox result\n'
            return bytes([1, 0, 0, 0]) + len(text).to_bytes(4, 'big') + text
        raise AssertionError((method, path))


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEZZN_SANDBOX_TOKEN': 't' * 40,
                              'CODEZZN_SANDBOX_STATE': str(Path(self.temp.name) / 'tasks.db'),
                              'CODEZZN_SANDBOX_TIMEOUT': '2'}, clear=False)
        self.env.start()
        self.config = Config()
        self.docker = FakeDocker()
        self.broker = Broker(self.config, self.docker)

    def tearDown(self):
        self.docker.fail_delete = False
        self.broker.close()
        self.env.stop()
        self.temp.cleanup()

    def submit(self, **kwargs):
        import uuid
        payload = {'id': uuid.uuid4().hex, 'command': 'id', 'mode': 'read-only', **kwargs}
        row = self.broker.submit(payload)
        return row['id']

    def finish(self, task):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self.broker.lock:
                pair = self.broker.running.get(task)
            if pair is None:
                return self.broker.get(task)
            pair[0].join(timeout=0.05)
        self.fail('task did not terminate')

    def test_policy_nonroot_single_mount_no_network_and_limits(self):
        task = self.submit()
        row = self.finish(task)
        self.assertEqual(row['status'], 'completed')
        self.assertFalse(row['cleanup_pending'])
        self.assertFalse(self.docker.containers)
        spec = self.docker.specs[0]
        host = spec['HostConfig']
        self.assertEqual(spec['User'], '10001:10001')
        self.assertEqual(host['NetworkMode'], 'none')
        self.assertEqual(len(host['Mounts']), 1)
        self.assertTrue(host['Mounts'][0]['ReadOnly'])
        self.assertTrue(host['Mounts'][0]['BindOptions']['NonRecursive'])
        self.assertEqual(host['CapDrop'], ['ALL'])
        self.assertTrue(host['ReadonlyRootfs'])
        self.assertEqual(host['MemorySwap'], host['Memory'])
        self.assertGreater(host['NanoCpus'], 0)
        self.assertEqual(host['PidsLimit'], 64)
        self.assertNotIn('CODEZZN_SANDBOX_TOKEN', str(spec))

    def test_workspace_write_and_fresh_containers(self):
        a = self.submit(mode='workspace-write')
        b = self.submit()
        self.finish(a)
        self.finish(b)
        self.assertNotEqual(a, b)
        self.assertEqual(len(self.docker.specs), 2)
        self.assertTrue(any(not s['HostConfig']['Mounts'][0]['ReadOnly'] for s in self.docker.specs))

    def test_timeout_kills_container(self):
        self.docker.forever = True
        self.config.timeout = 0.15
        row = self.finish(self.submit())
        self.assertEqual(row['status'], 'timed_out')
        self.assertFalse(self.docker.containers)

    def test_cancel_kills_container(self):
        self.docker.forever = True
        task = self.submit()
        self.broker.cancel(task)
        self.assertEqual(self.finish(task)['status'], 'cancelled')
        self.assertFalse(self.docker.containers)

    def test_start_failure_cleanup(self):
        self.docker.fail_start = True
        row = self.finish(self.submit())
        self.assertEqual(row['status'], 'failed')
        self.assertFalse(row['cleanup_pending'])
        self.assertFalse(self.docker.containers)

    def test_unsupported_limits_fail_closed(self):
        self.docker.warnings = ['Your kernel does not support pids limit capabilities']
        row = self.finish(self.submit())
        self.assertEqual(row['status'], 'failed')
        self.assertIn('policy enforcement', row['error'])
        self.assertFalse(self.docker.containers)

    def test_cleanup_failure_retried_and_state_persists(self):
        self.docker.fail_delete = True
        task = self.submit()
        row = self.finish(task)
        self.assertTrue(row['cleanup_pending'])
        self.docker.fail_delete = False
        restored = Broker(self.config, self.docker)
        restored.recover()
        self.assertFalse(restored.get(task)['cleanup_pending'])
        self.assertFalse(self.docker.containers)

    def test_restart_marks_orphan_interrupted(self):
        task = 'a' * 32
        name = 'codezzn-' + self.config.instance + '-' + task
        with self.broker.db() as db:
            db.execute('INSERT INTO tasks(id,name,status,mode,created,deadline) VALUES(?,?,?,?,?,?)',
                       (task, name, 'running', 'read-only', time.time(), time.time() + 60))
        self.docker.containers[name] = container_spec(self.config, task, 'sleep 99', 'read-only',
            {'Type': 'bind', 'Source': '/workspace'}, time.time() + 60, 'sha256:test')
        self.broker.recover()
        self.assertEqual(self.broker.get(task)['status'], 'interrupted')
        self.assertFalse(self.docker.containers)

    def test_reaper_ignores_other_instance(self):
        other = container_spec(self.config, 'b' * 32, 'id', 'read-only', {}, 0, 'sha256:test')
        other['Labels']['io.codezzn.sandbox.instance'] = 'another-app'
        self.docker.containers['foreign'] = other
        self.broker.recover()
        self.assertIn('foreign', self.docker.containers)

    def test_no_client_policy_override(self):
        with self.assertRaises(ValueError):
            self.submit(image='evil')
        with self.assertRaises(ValueError):
            self.submit(mode='danger-full-access')
        with self.assertRaises(ValueError):
            self.submit(command='id\x00')
        self.assertFalse(self.docker.specs)

    def test_log_frames_are_bounded(self):
        raw = b'\x01\x00\x00\x00' + (8).to_bytes(4, 'big') + b'abcdefgh'
        self.assertEqual(decode_logs(raw, 3), 'abc')

    def test_broker_auth_http(self):
        import http.client
        from http.server import ThreadingHTTPServer
        from backend.app.sandbox_broker import handler_for
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.broker))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
            conn.request('GET', '/health')
            self.assertEqual(conn.getresponse().status, 401)
            conn.close()
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
            conn.request('GET', '/health', headers={'Authorization': 'Bearer ' + self.config.token})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['policy']['network'], 'none')
            conn.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == '__main__':
    unittest.main()

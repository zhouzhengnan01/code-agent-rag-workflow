"""Client-to-broker integration, using real HTTP and a fake Docker engine."""
import asyncio
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

from backend.app import sandbox
from backend.app.sandbox_broker import Broker, Config, handler_for
from test_sandbox import FakeDocker


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEZZN_SANDBOX_TOKEN': 'x' * 40,
            'CODEZZN_SANDBOX_STATE': str(Path(self.temp.name) / 'tasks.db')})
        self.env.start()
        self.docker = FakeDocker()
        self.broker = Broker(Config(), self.docker)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.broker))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = patch.dict(os.environ, {'CODEZZN_SANDBOX_URL': f'http://127.0.0.1:{self.server.server_port}'})
        self.url.start()

    async def asyncTearDown(self):
        self.broker.close()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.url.stop()
        self.env.stop()
        self.temp.cleanup()

    async def test_round_trip(self):
        result = await sandbox.run_command('id', 'read-only')
        self.assertEqual(result['exit_code'], 0)
        self.assertIn('uid=10001', result['output'])
        self.assertFalse(result['cleanup_pending'])
        self.assertTrue((await sandbox.sandbox_status())['ready'])

    async def test_client_cancellation_stops_remote_task(self):
        self.docker.forever = True
        task = asyncio.create_task(sandbox.run_command('sleep 99'))
        for _ in range(100):
            if self.broker.tasks():
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        for _ in range(100):
            if not self.broker.running:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(self.broker.tasks()[0]['status'], 'cancelled')
        self.assertFalse(self.docker.containers)

    async def test_missing_config_fails_closed(self):
        with patch.dict(os.environ, {'CODEZZN_SANDBOX_URL': ''}):
            with self.assertRaises(RuntimeError):
                await sandbox.run_command('id')
        self.assertFalse(self.docker.specs)

    async def test_shell_agent_calls_broker_not_local_process(self):
        from backend.app import agent
        with patch.object(agent, 'run_command', new_callable=AsyncMock) as run:
            run.return_value = {'exit_code': 0, 'output': 'ok'}
            result = await agent.execute_tool('run_shell', {'command': 'id'},
                {'allow_shell': True, 'auto_approve': True, 'sandbox_mode': 'read-only'},
                {'run_shell': ('builtin', None)})
            self.assertEqual(result['output'], 'ok')
            run.assert_awaited_once_with('id', 'read-only')
            with self.assertRaises(PermissionError):
                await agent.execute_tool('run_shell', {'command': 'id'},
                    {'allow_shell': True, 'auto_approve': True, 'sandbox_mode': 'danger-full-access'},
                    {'run_shell': ('builtin', None)})

    async def test_git_executes_in_readonly_container(self):
        from backend.app import agent
        with patch.object(agent, 'run_command', new_callable=AsyncMock) as run:
            run.return_value = {'exit_code': 0, 'output': ''}
            await agent._run_git(['diff'])
            command, mode = run.call_args.args
            self.assertEqual(mode, 'read-only')
            self.assertIn('--no-ext-diff', command)
            self.assertIn('--no-textconv', command)
            self.assertIn('core.hooksPath=/dev/null', command)
            with self.assertRaises(ValueError):
                agent._git_revision('--output=/etc/x')


if __name__ == '__main__':
    unittest.main()

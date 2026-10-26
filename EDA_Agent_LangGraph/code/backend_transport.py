"""Bound the whole SSH operation, including Paramiko's request acknowledgement."""
from contextlib import contextmanager
from threading import Event, Timer

from eda_remote_v8 import RemoteError, exec_checked


@contextmanager
def connection_deadline(ssh, seconds, operation):
    expired = Event()

    def close_expired():
        expired.set()
        ssh.close()

    timer = Timer(seconds, close_expired)
    timer.daemon = True
    timer.start()
    try:
        yield
        if expired.is_set():
            raise TimeoutError(operation)
    except Exception as exc:
        if expired.is_set():
            raise RemoteError(
                f'{operation}超过 {seconds} 秒，已关闭连接。远端工具是否停止仍需单独确认。'
            ) from exc
        raise
    finally:
        timer.cancel()


def open_sftp_bounded(ssh, seconds=12):
    with connection_deadline(ssh, seconds, 'SFTP 启动'):
        sftp = ssh.open_sftp()
        sftp.get_channel().settimeout(seconds)
        return sftp


def exec_bounded(ssh, command, timeout_seconds=30):
    # exec_checked alone starts its clock after exec_command returns. A server
    # that never acknowledges the exec request would otherwise block forever.
    with connection_deadline(ssh, timeout_seconds, '远程命令（含启动握手）'):
        return exec_checked(ssh, command, timeout_seconds=timeout_seconds)

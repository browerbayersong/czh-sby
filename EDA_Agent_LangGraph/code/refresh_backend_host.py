"""Trust a VM's new DHCP address only when its public host key matches the old address."""
import argparse
import ipaddress
import subprocess
from pathlib import Path

import paramiko


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--previous', required=True)
    args = parser.parse_args()
    ipaddress.ip_address(args.host)
    ipaddress.ip_address(args.previous)
    known = Path.home() / '.ssh/known_hosts'
    keys = paramiko.HostKeys(str(known))
    previous = keys.lookup(args.previous)
    if not previous or 'ssh-rsa' not in previous:
        raise ValueError('No previously verified RSA host key; do not trust a new host automatically')
    scanned = subprocess.run(['ssh-keyscan', '-T', '5', '-t', 'rsa', args.host],
                             capture_output=True, text=True, timeout=12, check=True)
    lines = [line for line in scanned.stdout.splitlines() if not line.startswith('#') and line.strip()]
    approved = []
    for line in lines:
        entry = paramiko.hostkeys.HostKeyEntry.from_line(line)
        if entry and entry.key.get_name() == 'ssh-rsa' and entry.key == previous['ssh-rsa']:
            approved.append(f'{args.host} ssh-rsa {entry.key.get_base64()}\n')
    if len(approved) != 1:
        raise ValueError('New address does not match the previously verified VM key')
    existing = keys.lookup(args.host)
    if existing and 'ssh-rsa' in existing and existing['ssh-rsa'] != previous['ssh-rsa']:
        raise ValueError('Conflicting key already recorded for the new address')
    if not existing or 'ssh-rsa' not in existing:
        with known.open('a', encoding='utf-8') as handle:
            handle.write('\n' + approved[0])
    print('New address matches the previously verified VM public key; SSH alias is ready.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Lookup LDAP group members and print basic user details."""

from __future__ import annotations

import argparse
import sys

from ldap3 import ALL, Connection, Server


LDAP_HOST = "localhost"
LDAP_PORT = 3389
BIND_DN = "cn=admin,dc=dewcis,dc=com"
BIND_PASSWORD = "adminpass"
GROUPS_BASE = "ou=groups,dc=dewcis,dc=com"
USERS_BASE = "ou=users,dc=dewcis,dc=com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query LDAP group members.")
    parser.add_argument("group", help="LDAP group common name")
    return parser.parse_args()


def connect() -> Connection:
    server = Server(LDAP_HOST, port=LDAP_PORT, get_info=ALL)
    connection = Connection(server, user=BIND_DN, password=BIND_PASSWORD, auto_bind=True)
    return connection


def main() -> int:
    args = parse_args()

    try:
        conn = connect()
    except Exception as exc:
        print(f"Error: unable to connect to LDAP: {exc}", file=sys.stderr)
        return 1

    try:
        group_filter = f"(&(objectClass=posixGroup)(cn={args.group}))"
        conn.search(
            search_base=GROUPS_BASE,
            search_filter=group_filter,
            attributes=["cn", "gidNumber", "memberUid"],
        )

        if not conn.entries:
            print(f"Error: group '{args.group}' not found in directory.", file=sys.stderr)
            return 1

        group_entry = conn.entries[0]
        members = list(group_entry.memberUid.values) if "memberUid" in group_entry else []

        print(f"Group: {group_entry.cn.value} (gidNumber: {group_entry.gidNumber.value})")
        print("Members:")

        for uid in members:
            user_filter = f"(&(objectClass=posixAccount)(uid={uid}))"
            conn.search(
                search_base=USERS_BASE,
                search_filter=user_filter,
                attributes=["uid", "cn", "homeDirectory"],
            )
            if not conn.entries:
                print(f"{uid} | <missing user entry> | -")
                continue

            user = conn.entries[0]
            print(f"{user.uid.value} | {user.cn.value} | {user.homeDirectory.value}")

        return 0
    finally:
        conn.unbind()


if __name__ == "__main__":
    raise SystemExit(main())

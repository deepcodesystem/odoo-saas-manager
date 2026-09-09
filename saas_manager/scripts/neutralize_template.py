#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Neutralisation native Odoo 18 pour les bases SaaS templates.

Exécute `odoo.modules.neutralize.neutralize_database` sur une ou plusieurs
bases (désactive les mails sortants, les crons, les webhooks, les providers,
et pose le flag `database.is_neutralized`). À lancer UNE FOIS par template :
les instances clonées hériteront d'une base propre.

Usage:
    # Base unique
    python3 scripts/neutralize_template.py template_blank

    # Toutes les bases commençant par 'template_'
    python3 scripts/neutralize_template.py --pattern 'template_%'

    # Avec credentials PostgreSQL custom
    python3 scripts/neutralize_template.py template_blank \
        --host localhost --port 5432 --user odoo --password secret
"""

import argparse
import sys

import psycopg2


def get_conn(args, dbname):
    return psycopg2.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        dbname=dbname,
        connect_timeout=30,
    )


def list_databases(args, pattern):
    conn = get_conn(args, 'postgres')
    try:
        with conn.cursor() as cr:
            cr.execute(
                "SELECT datname FROM pg_database "
                "WHERE datname LIKE %s AND datistemplate = false ORDER BY datname",
                [pattern],
            )
            return [row[0] for row in cr.fetchall()]
    finally:
        conn.close()


def neutralize_db(args, dbname):
    """Neutralise une base : le code natif Odoo doit être importable."""
    from odoo.modules.neutralize import neutralize_database

    conn = get_conn(args, dbname)
    try:
        # Neutralisation native (SQL par module : mails, crons, webhooks, ...)
        with conn.cursor() as cr:
            neutralize_database(cr)
        conn.commit()
        print(f"[OK] {dbname} neutralized (native)")
    except Exception as exc:
        conn.rollback()
        print(f"[FAIL] {dbname}: {exc}", file=sys.stderr)
        return False
    finally:
        conn.close()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('databases', nargs='*', help='Database names to neutralize')
    parser.add_argument('--pattern', help='SQL LIKE pattern to select databases (e.g. template_%%)')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', default=5432, type=int)
    parser.add_argument('--user', default='odoo')
    parser.add_argument('--password', default='')
    args = parser.parse_args()

    dbnames = list(args.databases)
    if args.pattern:
        dbnames += list_databases(args, args.pattern)

    if not dbnames:
        parser.error('No database given (pass names or --pattern)')

    failures = 0
    for dbname in dbnames:
        if not neutralize_db(args, dbname):
            failures += 1

    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()

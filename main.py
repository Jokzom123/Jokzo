"""
Entry point for the SEC GAAP data fetcher.

Usage
-----
    python main.py [--limit N] [--log-level LEVEL]

Options
-------
--limit N       Process only the first N companies (useful for testing).
--log-level     Python logging level: DEBUG, INFO, WARNING, ERROR (default: INFO).
--db-path       Path to the SQLite database file (default: sec_gaap.db).
--reset         Clear the checkpoint file and start over (does NOT wipe the DB).
"""

import argparse
import logging
import os
import sys

import config
from src import database, fetcher


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch SEC EDGAR GAAP data for all US-listed companies."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after processing N companies (default: all).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=f"SQLite database file path (default: {config.DB_PATH}).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the checkpoint file so the run starts from the beginning.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Override DB path if supplied on the command line
    if args.db_path:
        config.DB_PATH = args.db_path

    # Optionally clear checkpoint
    if args.reset and os.path.exists(config.CHECKPOINT_FILE):
        os.remove(config.CHECKPOINT_FILE)
        logging.info("Checkpoint cleared – starting from the beginning.")

    # Validate user-agent (SEC EDGAR requirement)
    if config.SEC_USER_AGENT == "YourName yourname@example.com":
        print(
            "\nWARNING: Please set your SEC_USER_AGENT in config.py or via the\n"
            "  SEC_USER_AGENT environment variable before running in production.\n"
            "  SEC EDGAR requires a valid name and email address.\n"
            "  Example:  export SEC_USER_AGENT='Jane Doe jane@example.com'\n"
        )

    # Open / initialise the database
    conn = database.get_connection(config.DB_PATH)
    database.init_db(conn)

    # Step 1: populate the companies table
    fetcher.load_tickers(conn)

    # Step 2: fetch GAAP facts for all pending companies
    fetcher.fetch_all_gaap(conn, limit=args.limit)

    conn.close()
    print("\nAll done!  Database saved to:", config.DB_PATH)


if __name__ == "__main__":
    main()

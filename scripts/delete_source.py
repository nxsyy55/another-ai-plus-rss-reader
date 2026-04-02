import sys
import argparse
from pathlib import Path

# Ensure src is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aiNewReader.db import get_db, init_db, delete_feeds_batch

def main():
    parser = argparse.ArgumentParser(description="Delete all records from a specific source (feed).")
    parser.add_argument("source", help="The URL or name of the feed to delete.")
    parser.add_argument("--by-name", action="store_true", help="Search by name instead of URL.")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually delete anything.")
    
    args = parser.parse_args()
    
    print("Initializing database connection...")
    init_db()
    
    with get_db() as conn:
        if args.by_name:
            rows = conn.execute("SELECT id, url, name FROM feeds WHERE name = ?", (args.source,)).fetchall()
        else:
            rows = conn.execute("SELECT id, url, name FROM feeds WHERE url = ? OR name = ?", (args.source, args.source)).fetchall()
            
        if not rows:
            print(f"Error: No feed found matching '{args.source}'")
            sys.exit(1)
            
        if len(rows) > 1 and not args.by_name:
            print(f"Multiple feeds found for '{args.source}':")
            for row in rows:
                print(f"  - {row['name']} ({row['url']})")
            print("Please provide the exact URL or use --by-name if you are sure.")
            sys.exit(1)
            
        print(f"Found {len(rows)} feed(s) to delete:")
        for row in rows:
            article_count = conn.execute("SELECT COUNT(*) FROM articles WHERE feed_id = ?", (row['id'],)).fetchone()[0]
            print(f"  - {row['name']} ({row['url']}) with {article_count} articles")
            
        if args.dry_run:
            print("\nDry run: No changes made.")
            return
            
        confirm = input(f"\nAre you sure you want to delete these {len(rows)} source(s) and ALL their articles? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return
            
        urls = [row['url'] for row in rows]
        
        print("\nDeleting records...")
        # delete_feeds_batch handles feedback, tags, articles, and feeds
        delete_feeds_batch(conn, urls)
        print("   Done!")

    print("\nVacuuming database to reclaim disk space...")
    with get_db() as conn:
        conn.isolation_level = None  # Disable auto-transaction
        conn.execute("VACUUM")
    print("   Done!")

if __name__ == "__main__":
    main()

import sys
import yaml
from pathlib import Path

# Ensure src is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aiNewReader.db import get_db, init_db

def main():
    print("Initializing database connection...")
    init_db()
    
    # 1. Load current feeds from feeds.yaml
    feeds_yaml_path = Path(__file__).parent.parent / "feeds.yaml"
    if not feeds_yaml_path.exists():
        print(f"Error: {feeds_yaml_path} not found.")
        sys.exit(1)
        
    with open(feeds_yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    current_urls = {f['url'] for f in config.get('feeds', [])}
    print(f"Loaded {len(current_urls)} URLs from feeds.yaml")
    
    with get_db() as conn:
        # 2. Find feeds in DB that are not in feeds.yaml
        db_feeds = conn.execute("SELECT id, url, name FROM feeds").fetchall()
        feeds_to_remove = [f for f in db_feeds if f['url'] not in current_urls]
        
        if not feeds_to_remove:
            print("No feeds in database are missing from feeds.yaml. Nothing to clean.")
            return
            
        print(f"\nFound {len(feeds_to_remove)} feeds in database that are NOT in feeds.yaml:")
        total_articles_to_remove = 0
        for f in feeds_to_remove:
            count = conn.execute("SELECT COUNT(*) FROM articles WHERE feed_id = ?", (f['id'],)).fetchone()[0]
            print(f"  - {f['name']} ({f['url']}) : {count} articles")
            total_articles_to_remove += count
            
        print(f"\nTotal articles to be removed: {total_articles_to_remove}")
        
        confirm = input("\nProceed with deletion of these articles and their related data? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return
            
        feed_ids = [f['id'] for f in feeds_to_remove]
        id_placeholders = ", ".join("?" for _ in feed_ids)
        
        print("\nDeleting records...")
        
        # 1. Delete feedback for these articles (since it doesn't have CASCADE)
        conn.execute(f"""
            DELETE FROM feedback 
            WHERE article_id IN (SELECT id FROM articles WHERE feed_id IN ({id_placeholders}))
        """, feed_ids)
        
        # 2. Delete article_tags (has CASCADE, but good to be explicit or let CASCADE work)
        # 3. Delete articles
        # Since articles has ON DELETE CASCADE for feeds, we could just delete the feeds.
        # But the user asked to delete articles if source is not in list. 
        # Should we delete the feeds themselves too? Probably yes, to keep DB in sync with feeds.yaml.
        
        cur = conn.execute(f"DELETE FROM articles WHERE feed_id IN ({id_placeholders})", feed_ids)
        articles_deleted = cur.rowcount
        
        cur = conn.execute(f"DELETE FROM feeds WHERE id IN ({id_placeholders})", feed_ids)
        feeds_deleted = cur.rowcount
        
        print(f"   Removed {articles_deleted} articles.")
        print(f"   Removed {feeds_deleted} orphaned feeds from database.")
        print("   Done!")

    print("\nVacuuming database to reclaim disk space...")
    with get_db() as conn:
        conn.isolation_level = None
        conn.execute("VACUUM")
    print("   Done!")

if __name__ == "__main__":
    main()

import sqlite3

# Connect to the database
conn = sqlite3.connect('users.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 60)
print("DATABASE VERIFICATION SCRIPT")
print("=" * 60)

# Check if reviews table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'")
reviews_table = cursor.fetchone()

# Check if download_history table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='download_history'")
download_history_table = cursor.fetchone()

if reviews_table:
    print("\n✓ Reviews table EXISTS in database")
    
    # Get table schema
    cursor.execute("PRAGMA table_info(reviews)")
    columns = cursor.fetchall()
    
    print("\nReviews Table Schema:")
    print("-" * 60)
    for col in columns:
        print(f"  {col['name']:15} {col['type']:10} {'NOT NULL' if col['notnull'] else 'NULL'}")
    
    # Count reviews
    cursor.execute("SELECT COUNT(*) as count FROM reviews")
    count = cursor.fetchone()['count']
    print(f"\nTotal Reviews in Database: {count}")
    
    # Show sample reviews if any exist
    if count > 0:
        cursor.execute("""
            SELECT r.id, r.rating, r.review_text, r.created_at, 
                   u.name as user_name, res.title as resource_title
            FROM reviews r
            JOIN users u ON r.user_id = u.id
            JOIN resources res ON r.resource_id = res.id
            LIMIT 5
        """)
        reviews = cursor.fetchall()
        
        print("\nSample Reviews:")
        print("-" * 60)
        for review in reviews:
            print(f"\nReview ID: {review['id']}")
            print(f"  Resource: {review['resource_title']}")
            print(f"  User: {review['user_name']}")
            print(f"  Rating: {'★' * review['rating']}{'☆' * (5 - review['rating'])} ({review['rating']}/5)")
            print(f"  Review: {review['review_text'][:100] if review['review_text'] else 'No text review'}")
            print(f"  Date: {review['created_at']}")
    
    # Show average ratings per resource
    cursor.execute("""
        SELECT res.title, 
               COUNT(r.id) as review_count,
               ROUND(AVG(r.rating), 1) as avg_rating
        FROM resources res
        LEFT JOIN reviews r ON res.id = r.resource_id
        GROUP BY res.id
        HAVING review_count > 0
        ORDER BY avg_rating DESC
        LIMIT 10
    """)
    ratings = cursor.fetchall()
    
    if ratings:
        print("\n\nResource Ratings Summary:")
        print("-" * 60)
        for rating in ratings:
            print(f"{rating['title'][:40]:40} | {rating['avg_rating']}/5 ★ | {rating['review_count']} reviews")
    
else:
    print("\n✗ Reviews table DOES NOT EXIST")
    print("  The table should be created automatically when the app runs.")

if download_history_table:
    print("\n✓ Download History table EXISTS in database")
    
    # Get table schema
    cursor.execute("PRAGMA table_info(download_history)")
    columns = cursor.fetchall()
    
    print("\nDownload History Table Schema:")
    print("-" * 60)
    for col in columns:
        print(f"  {col['name']:15} {col['type']:10} {'NOT NULL' if col['notnull'] else 'NULL'}")
    
    # Count downloads
    cursor.execute("SELECT COUNT(*) as count FROM download_history")
    count = cursor.fetchone()['count']
    print(f"\nTotal Downloads in Database: {count}")
    
    # Show sample downloads if any exist
    if count > 0:
        cursor.execute("""
            SELECT dh.id, dh.download_date,
                   u.name as user_name, res.title as resource_title
            FROM download_history dh
            JOIN users u ON dh.user_id = u.id
            JOIN resources res ON dh.resource_id = res.id
            ORDER BY dh.download_date DESC
            LIMIT 10
        """)
        downloads = cursor.fetchall()
        
        print("\nRecent Downloads:")
        print("-" * 60)
        for download in downloads:
            print(f"\nDownload ID: {download['id']}")
            print(f"  Resource: {download['resource_title']}")
            print(f"  User: {download['user_name']}")
            print(f"  Date: {download['download_date']}")
    
    # Show download statistics per user
    cursor.execute("""
        SELECT u.name, 
               COUNT(dh.id) as download_count,
               COUNT(DISTINCT dh.resource_id) as unique_resources
        FROM users u
        LEFT JOIN download_history dh ON u.id = dh.user_id
        GROUP BY u.id
        HAVING download_count > 0
        ORDER BY download_count DESC
        LIMIT 10
    """)
    user_stats = cursor.fetchall()
    
    if user_stats:
        print("\n\nUser Download Statistics:")
        print("-" * 60)
        for stat in user_stats:
            print(f"{stat['name'][:30]:30} | {stat['download_count']} downloads | {stat['unique_resources']} unique resources")
else:
    print("\n✗ Download History table DOES NOT EXIST")
    print("  The table should be created automatically when the app runs.")

# Check resources table
cursor.execute("SELECT COUNT(*) as count FROM resources")
resource_count = cursor.fetchone()['count']
print(f"\n\nTotal Resources in Database: {resource_count}")

# Check users table
cursor.execute("SELECT COUNT(*) as count FROM users")
user_count = cursor.fetchone()['count']
print(f"Total Users in Database: {user_count}")

print("\n" + "=" * 60)
print("DATABASE VERIFICATION COMPLETE")
print("=" * 60)

conn.close()

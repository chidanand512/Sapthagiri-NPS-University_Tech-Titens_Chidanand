from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# File upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'ppt', 'pptx', 'jpg', 'jpeg', 'png', 'txt', 'zip'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# configure a simple admin email (change via env if desired)
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@example.com')

# Database setup
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT NOT NULL,
            college TEXT NOT NULL,
            branch TEXT NOT NULL,
            semester TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            semester TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            year_batch TEXT NOT NULL,
            description TEXT,
            tags TEXT,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_size INTEGER,
            privacy TEXT DEFAULT 'Public',
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Add privacy column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE resources ADD COLUMN privacy TEXT DEFAULT 'Public'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Create reviews table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (resource_id) REFERENCES resources (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(resource_id, user_id)
        )
    ''')
    
    # Create download history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS download_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (resource_id) REFERENCES resources (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_resource_rating(resource_id):
    """Get average rating and review count for a resource"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            COALESCE(AVG(rating), 0) as avg_rating,
            COUNT(*) as review_count
        FROM reviews
        WHERE resource_id = ?
    ''', (resource_id,))
    result = cursor.fetchone()
    conn.close()
    return {
        'avg_rating': round(result['avg_rating'], 1) if result['avg_rating'] else 0,
        'review_count': result['review_count']
    }

def get_user_review(resource_id, user_id):
    """Get user's review for a specific resource"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM reviews
        WHERE resource_id = ? AND user_id = ?
    ''', (resource_id, user_id))
    review = cursor.fetchone()
    conn.close()
    return dict(review) if review else None

# Initialize database
init_db()

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        college = request.form.get('college')
        branch = request.form.get('branch')
        semester = request.form.get('semester')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            flash('Email already exists!', 'error')
            return redirect(url_for('signup'))
        
        # Insert new user
        hashed_password = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (name, email, password, phone, college, branch, semester)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, email, hashed_password, phone, college, branch, semester))
        
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user'] = email
            # store user id for later API calls
            session['student_id'] = user['id']
            # simple role: treat ADMIN_EMAIL as admin
            session['user_type'] = 'admin' if email == ADMIN_EMAIL else 'student'
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password!', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect(url_for('login'))
    
    # Get user's uploaded resources
    cursor.execute('''
        SELECT * FROM resources 
        WHERE user_id = ? 
        ORDER BY upload_date DESC
    ''', (user['id'],))
    resources = [dict(row) for row in cursor.fetchall()]
    
    # Get download count
    cursor.execute('SELECT COUNT(*) as count FROM download_history WHERE user_id = ?', (user['id'],))
    download_count = cursor.fetchone()['count']
    
    conn.close()
    
    user_data = {
        'name': user['name'],
        'phone': user['phone'],
        'college': user['college'],
        'branch': user['branch'],
        'semester': user['semester'],
        'download_count': download_count
    }
    
    return render_template('dashboard.html', user=user_data, resources=resources)

@app.route('/upload_page')
def upload_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect(url_for('login'))
    
    # Get user's uploaded resources
    cursor.execute('''
        SELECT * FROM resources 
        WHERE user_id = ? 
        ORDER BY upload_date DESC
    ''', (user['id'],))
    resources = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template('upload_page.html', resources=resources)

@app.route('/upload_resource', methods=['POST'])
def upload_resource():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Get form data
    title = request.form.get('title')
    subject = request.form.get('subject')
    semester = request.form.get('semester')
    resource_type = request.form.get('resource_type')
    year_batch = request.form.get('year_batch')
    description = request.form.get('description', '')
    tags = request.form.get('tags', '')
    privacy = request.form.get('privacy', 'Public')
    
    # Check if file is present
    if 'file' not in request.files:
        flash('No file selected!', 'error')
        return redirect(url_for('dashboard'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected!', 'error')
        return redirect(url_for('dashboard'))
    
    if file and allowed_file(file.filename):
        # Secure the filename and add timestamp
        original_filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{original_filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save file
        file.save(filepath)
        file_size = os.path.getsize(filepath)
        
        # Get user ID
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user'],))
        user = cursor.fetchone()
        
        # Insert resource into database
        cursor.execute('''
            INSERT INTO resources 
            (user_id, title, subject, semester, resource_type, year_batch, description, tags, filename, original_filename, file_size, privacy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user['id'], title, subject, semester, resource_type, year_batch, description, tags, filename, original_filename, file_size, privacy))
        
        conn.commit()
        conn.close()
        
        flash('Resource uploaded successfully!', 'success')
    else:
        flash('Invalid file type! Allowed types: PDF, DOCX, PPT, Images, TXT, ZIP', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/edit_resource/<int:resource_id>', methods=['POST'])
def edit_resource(resource_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user ID
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    # Check if resource belongs to user
    cursor.execute('SELECT * FROM resources WHERE id = ? AND user_id = ?', (resource_id, user['id']))
    resource = cursor.fetchone()
    
    if not resource:
        flash('Resource not found or unauthorized!', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    
    # Update resource
    title = request.form.get('title')
    subject = request.form.get('subject')
    semester = request.form.get('semester')
    resource_type = request.form.get('resource_type')
    year_batch = request.form.get('year_batch')
    description = request.form.get('description', '')
    tags = request.form.get('tags', '')
    privacy = request.form.get('privacy', 'Public')
    
    cursor.execute('''
        UPDATE resources 
        SET title = ?, subject = ?, semester = ?, resource_type = ?, year_batch = ?, description = ?, tags = ?, privacy = ?
        WHERE id = ?
    ''', (title, subject, semester, resource_type, year_batch, description, tags, privacy, resource_id))
    
    conn.commit()
    conn.close()
    
    flash('Resource updated successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete_resource/<int:resource_id>')
def delete_resource(resource_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user ID
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    # Check if resource belongs to user
    cursor.execute('SELECT * FROM resources WHERE id = ? AND user_id = ?', (resource_id, user['id']))
    resource = cursor.fetchone()
    
    if not resource:
        flash('Resource not found or unauthorized!', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    
    # Delete file from filesystem
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], resource['filename'])
    if os.path.exists(filepath):
        os.remove(filepath)
    
    # Delete from database
    cursor.execute('DELETE FROM resources WHERE id = ?', (resource_id,))
    conn.commit()
    conn.close()
    
    flash('Resource deleted successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/download/<int:resource_id>')
def download_resource(resource_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current user info
    cursor.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    current_user = cursor.fetchone()
    
    # Get resource with uploader info
    cursor.execute('''
        SELECT r.*, u.college as uploader_college 
        FROM resources r
        JOIN users u ON r.user_id = u.id
        WHERE r.id = ?
    ''', (resource_id,))
    resource = cursor.fetchone()
    
    if not resource:
        conn.close()
        flash('Resource not found!', 'error')
        return redirect(url_for('dashboard'))
    
    # Check privacy access
    if resource['privacy'] == 'Private':
        if current_user['college'] != resource['uploader_college']:
            conn.close()
            flash('Access denied! This resource is private and only available to students from ' + resource['uploader_college'], 'error')
            return redirect(url_for('access_resources'))
    
    # Record download in history
    try:
        cursor.execute('''
            INSERT INTO download_history (resource_id, user_id)
            VALUES (?, ?)
        ''', (resource_id, current_user['id']))
        conn.commit()
    except Exception as e:
        print(f"Error recording download: {e}")
    
    conn.close()
    
    return send_from_directory(app.config['UPLOAD_FOLDER'], resource['filename'], as_attachment=True, download_name=resource['original_filename'])


@app.route('/my_resources')
def my_resources():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect(url_for('login'))
    
    # Get user's uploaded resources with ratings
    cursor.execute('''
        SELECT * FROM resources 
        WHERE user_id = ? 
        ORDER BY upload_date DESC
    ''', (user['id'],))
    resources = []
    for row in cursor.fetchall():
        resource_dict = dict(row)
        rating_info = get_resource_rating(row['id'])
        resource_dict['avg_rating'] = rating_info['avg_rating']
        resource_dict['review_count'] = rating_info['review_count']
        resources.append(resource_dict)
    
    conn.close()
    
    return render_template('my_resources.html', resources=resources, user=user)


@app.route('/download_history')
def download_history():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect(url_for('login'))
    
    # Get download history with resource details
    cursor.execute('''
        SELECT 
            dh.id,
            dh.download_date,
            r.id as resource_id,
            r.title,
            r.subject,
            r.resource_type,
            r.semester,
            r.year_batch,
            r.privacy,
            u.name as uploader_name,
            u.college as uploader_college
        FROM download_history dh
        JOIN resources r ON dh.resource_id = r.id
        JOIN users u ON r.user_id = u.id
        WHERE dh.user_id = ?
        ORDER BY dh.download_date DESC
    ''', (user['id'],))
    
    downloads = [dict(row) for row in cursor.fetchall()]
    
    # Add rating info for each resource
    for download in downloads:
        rating_info = get_resource_rating(download['resource_id'])
        download['avg_rating'] = rating_info['avg_rating']
        download['review_count'] = rating_info['review_count']
    
    # Get statistics
    cursor.execute('SELECT COUNT(*) as count FROM download_history WHERE user_id = ?', (user['id'],))
    total_downloads = cursor.fetchone()['count']
    
    cursor.execute('''
        SELECT COUNT(DISTINCT resource_id) as count 
        FROM download_history 
        WHERE user_id = ?
    ''', (user['id'],))
    unique_resources = cursor.fetchone()['count']
    
    conn.close()
    
    stats = {
        'total_downloads': total_downloads,
        'unique_resources': unique_resources
    }
    
    return render_template('download_history.html', user=user, downloads=downloads, stats=stats)


@app.route('/my_profile')
def my_profile():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect(url_for('login'))
    
    # Get user statistics
    cursor.execute('SELECT COUNT(*) as count FROM resources WHERE user_id = ?', (user['id'],))
    upload_count = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM reviews WHERE user_id = ?', (user['id'],))
    review_count = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM download_history WHERE user_id = ?', (user['id'],))
    download_count = cursor.fetchone()['count']
    
    conn.close()
    
    user_data = {
        'name': user['name'],
        'email': user['email'],
        'phone': user['phone'],
        'college': user['college'],
        'branch': user['branch'],
        'semester': user['semester'],
        'upload_count': upload_count,
        'review_count': review_count,
        'download_count': download_count
    }
    
    return render_template('my_profile.html', user=user_data)


@app.route('/access_resources')
def access_resources():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current user info
    cursor.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect(url_for('login'))
    
    # Get all resources with uploader info
    cursor.execute('''
        SELECT r.*, u.name as uploader_name, u.college as uploader_college, u.branch as uploader_branch
        FROM resources r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.upload_date DESC
    ''')
    all_resources = cursor.fetchall()
    conn.close()
    
    # Filter resources based on privacy
    accessible_resources = []
    for resource in all_resources:
        resource_dict = dict(resource)
        if resource['privacy'] == 'Public':
            resource_dict['accessible'] = True
        elif resource['privacy'] == 'Private' and resource['uploader_college'] == user['college']:
            resource_dict['accessible'] = True
        else:
            resource_dict['accessible'] = False
        
        # Add rating information
        rating_info = get_resource_rating(resource['id'])
        resource_dict['avg_rating'] = rating_info['avg_rating']
        resource_dict['review_count'] = rating_info['review_count']
        
        accessible_resources.append(resource_dict)
    
    user_data = {
        'name': user['name'],
        'college': user['college'],
        'branch': user['branch'],
        'semester': user['semester']
    }
    
    return render_template('access_resources.html', user=user_data, resources=accessible_resources)


@app.route('/resource/<int:resource_id>')
def resource_detail(resource_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current user info
    cursor.execute('SELECT * FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    # Get resource with uploader info
    cursor.execute('''
        SELECT r.*, u.name as uploader_name, u.college as uploader_college, u.branch as uploader_branch
        FROM resources r
        JOIN users u ON r.user_id = u.id
        WHERE r.id = ?
    ''', (resource_id,))
    resource = cursor.fetchone()
    
    if not resource:
        conn.close()
        flash('Resource not found!', 'error')
        return redirect(url_for('access_resources'))
    
    resource_dict = dict(resource)
    
    # Check accessibility
    if resource['privacy'] == 'Public':
        resource_dict['accessible'] = True
    elif resource['privacy'] == 'Private' and resource['uploader_college'] == user['college']:
        resource_dict['accessible'] = True
    else:
        resource_dict['accessible'] = False
    
    # Get rating information
    rating_info = get_resource_rating(resource_id)
    resource_dict['avg_rating'] = rating_info['avg_rating']
    resource_dict['review_count'] = rating_info['review_count']
    
    # Get all reviews with user info
    cursor.execute('''
        SELECT r.*, u.name as reviewer_name
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.resource_id = ?
        ORDER BY r.created_at DESC
    ''', (resource_id,))
    reviews = [dict(row) for row in cursor.fetchall()]
    
    # Get current user's review if exists
    user_review = get_user_review(resource_id, user['id'])
    
    conn.close()
    
    return render_template('resource_detail.html', 
                         resource=resource_dict, 
                         reviews=reviews, 
                         user_review=user_review,
                         user=user)


@app.route('/submit_review/<int:resource_id>', methods=['POST'])
def submit_review(resource_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    rating = request.form.get('rating', type=int)
    review_text = request.form.get('review_text', '').strip()
    
    if not rating or rating < 1 or rating > 5:
        flash('Please provide a valid rating (1-5 stars)', 'error')
        return redirect(url_for('resource_detail', resource_id=resource_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user ID
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    # Check if user already reviewed this resource
    existing_review = get_user_review(resource_id, user['id'])
    
    try:
        if existing_review:
            # Update existing review
            cursor.execute('''
                UPDATE reviews 
                SET rating = ?, review_text = ?, updated_at = CURRENT_TIMESTAMP
                WHERE resource_id = ? AND user_id = ?
            ''', (rating, review_text, resource_id, user['id']))
            flash('Your review has been updated!', 'success')
        else:
            # Insert new review
            cursor.execute('''
                INSERT INTO reviews (resource_id, user_id, rating, review_text)
                VALUES (?, ?, ?, ?)
            ''', (resource_id, user['id'], rating, review_text))
            flash('Your review has been submitted!', 'success')
        
        conn.commit()
    except sqlite3.IntegrityError:
        flash('Error submitting review. Please try again.', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('resource_detail', resource_id=resource_id))


@app.route('/delete_review/<int:resource_id>')
def delete_review(resource_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user ID
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user'],))
    user = cursor.fetchone()
    
    # Delete review
    cursor.execute('''
        DELETE FROM reviews 
        WHERE resource_id = ? AND user_id = ?
    ''', (resource_id, user['id']))
    
    conn.commit()
    conn.close()
    
    flash('Your review has been deleted!', 'success')
    return redirect(url_for('resource_detail', resource_id=resource_id))


@app.route('/get_student_info', methods=['GET'])
def get_student_info():
    if session.get('user_type') != 'student' and session.get('user_type') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    # prefer student_id if present
    sid = session.get('student_id')
    if sid:
        cursor.execute('SELECT * FROM users WHERE id = ?', (sid,))
    else:
        cursor.execute('SELECT * FROM users WHERE email = ?', (session.get('user'),))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return jsonify({'success': False, 'message': 'Student not found'}), 404

    # we don't have a USN column in the current schema; synthesize one using id
    usn = f"U{user['id']:04d}"

    return jsonify({
        'success': True,
        'student': {
            'name': user['name'],
            'usn': usn,
            'email': user['email'],
            'department': user['branch'],
            'semester': user['semester']
        }
    })

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

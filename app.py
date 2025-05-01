import logging
from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_bcrypt import Bcrypt
from datetime import date
from db_config import mysql, init_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
app.secret_key = 'your_secret_key'
bcrypt = Bcrypt(app)
init_app(app)


# Item Model
class Item:
    def __init__(self, id, name, category, stock, expiration_date, description):
        self.id = id
        self.name = name
        self.category = category
        self.stock = stock
        self.expiration_date = expiration_date
        self.description = description

    @classmethod
    def add(cls, name, category, stock, expiration_date, description):
        logging.info(f"Adding item: {name}, Category: {category}, Stock: {stock}")
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO items (name, category, stock, expiration_date, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, category, stock, expiration_date, description))
        mysql.connection.commit()
        cur.close()

    @classmethod
    def update(cls, item_id, name, category, stock, expiration_date, description):
        logging.info(f"Updating item ID {item_id}: {name}, Category: {category}, Stock: {stock}")
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE items 
            SET name=%s, category=%s, stock=%s, expiration_date=%s, description=%s 
            WHERE id=%s
        """, (name, category, stock, expiration_date, description, item_id))
        mysql.connection.commit()
        cur.close()

    @classmethod
    def delete(cls, item_id):
        logging.info(f"Deleting item ID {item_id}")
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM items WHERE id=%s", (item_id,))
        mysql.connection.commit()
        cur.close()

    @classmethod
    def get(cls, item_id):
        logging.info(f"Fetching item ID {item_id}")
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM items WHERE id=%s", (item_id,))
        item = cur.fetchone()
        cur.close()
        return cls(*item) if item else None


# ActivityLog Model
class ActivityLog:
    def __init__(self, user_id, action, item_name):
        self.user_id = user_id
        self.action = action
        self.item_name = item_name

    @classmethod
    def log(cls, user_id, action, item_name):
        logging.info(f"Logging activity: User ID {user_id}, Action: {action}, Item: {item_name}")
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO activity_log (user_id, action, item_name)
            VALUES (%s, %s, %s)
        """, (user_id, action, item_name))
        mysql.connection.commit()
        cur.close()


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        logging.info(f"Login attempt for username: {username}")

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        cur.close()

        if user:
            try:
                if bcrypt.check_password_hash(user[3], password):
                    logging.info(f"Login successful for username: {username}")
                    session['id'] = user[0]
                    session['username'] = user[1]
                    return redirect('/dashboard')
            except ValueError:
                logging.warning(f"Password hash mismatch for username: {username}")
                hashed = bcrypt.generate_password_hash(password).decode('utf-8')
                cur = mysql.connection.cursor()
                cur.execute("UPDATE users SET password=%s WHERE id=%s", (hashed, user[0]))
                mysql.connection.commit()
                cur.close()
                session['id'] = user[0]
                session['username'] = user[1]
                return redirect('/dashboard')

        logging.warning(f"Invalid login credentials for username: {username}")
        flash("Invalid login credentials")

    return render_template("login.html")


@app.route('/logout')
def logout():
    logging.info(f"User {session.get('username')} logged out")
    session.clear()
    return redirect('/')


@app.route('/dashboard', methods=['GET'])
def dashboard():
    if 'id' not in session:
        logging.warning("Unauthorized access to dashboard")
        return redirect('/')

    category = request.args.get('category', '')
    search = request.args.get('search', '')
    show_expiring = request.args.get('expiring', 'false') == 'true'

    logging.info(f"Dashboard accessed by user {session['username']}, Filters - Category: {category}, Search: {search}, Expiring: {show_expiring}")

    cur = mysql.connection.cursor()
    query = "SELECT * FROM items WHERE 1=1"
    params = []

    if category:
        query += " AND category = %s"
        params.append(category)

    if search:
        query += " AND name LIKE %s"
        params.append('%' + search + '%')

    if show_expiring:
        query += " AND expiration_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)"

    query += " ORDER BY expiration_date ASC"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    cur.close()

    items = [Item(*row) for row in rows]  # Convert tuples to Item objects

    return render_template('dashboard.html', items=items, today=date.today())



@app.route('/add', methods=['GET', 'POST'])
def add_item():
    if 'id' not in session:
        logging.warning("Unauthorized access to add item")
        return redirect('/')

    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        stock = request.form['stock']
        expiration_date = request.form['expiration_date'] or None
        description = request.form['description']

        logging.info(f"User {session['username']} adding item: {name}")
        Item.add(name, category, stock, expiration_date, description)

        ActivityLog.log(session['id'], 'Added item', name)

        return redirect('/dashboard')

    return render_template('add_item.html')


@app.route('/edit/<int:item_id>/<string:item_name>', methods=['GET', 'POST'])
def edit_item(item_id, item_name):
    if 'id' not in session:
        logging.warning("Unauthorized access to edit item")
        return redirect('/')

    item = Item.get(item_id)
    if not item:
        logging.error(f"Item ID {item_id} not found for editing")
        flash("Item not found")
        return redirect('/dashboard')

    if request.method == 'POST':
        try:
            name = request.form['name']
            category = request.form['category']
            stock = int(request.form['stock'])
            expiration_date = request.form['expiration_date'] or None
            description = request.form['description']

            logging.info(f"User {session['username']} editing item ID {item_id}: {name}")
            Item.update(item_id, name, category, stock, expiration_date, description)

            ActivityLog.log(session['id'], 'Edited item', name)
            flash("Item updated successfully")
            return redirect('/dashboard')
        except ValueError as e:
            logging.error(f"Error updating item ID {item_id}: {e}")
            flash("Invalid input. Please check your data and try again.")

    return render_template("edit_item.html", item=item, item_name=item_name)


@app.route('/delete/<int:item_id>')
def delete_item(item_id):
    if 'id' not in session:
        logging.warning("Unauthorized access to delete item")
        return redirect('/')

    item = Item.get(item_id)

    if item:
        item_name = item.name
        logging.info(f"User {session['username']} deleting item ID {item_id}: {item_name}")
        Item.delete(item_id)

        ActivityLog.log(session['id'], 'Deleted item', item_name)

    return redirect('/dashboard')


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'id' not in session:
        logging.warning("Unauthorized access to settings")
        return redirect('/')

    cur = mysql.connection.cursor()

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')

        logging.info(f"User {session['username']} updating settings: Username: {username}, Email: {email}")
        cur.execute("""
            UPDATE users 
            SET username=%s, email=%s, password=%s 
            WHERE id=%s
        """, (username, email, hashed, session['id']))
        mysql.connection.commit()
        session['username'] = username
        return redirect('/dashboard')

    cur.execute("SELECT username, email FROM users WHERE id=%s", (session['id'],))
    user = cur.fetchone()
    cur.close()

    return render_template("settings.html", user=user)


@app.route('/history')
def history():
    if 'id' not in session:
        logging.warning("Unauthorized access to history")
        return redirect('/')
    logging.info(f"User {session['username']} accessing history")
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT a.action, a.item_name, a.timestamp, u.username
        FROM activity_log a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.timestamp DESC
    """)
    logs = cur.fetchall()
    cur.close()
    return render_template('history.html', logs=logs)


if __name__ == '__main__':
    logging.info("Starting the application")
    app.run(debug=True)

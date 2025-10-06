from flask import Flask, render_template, request, redirect, flash, session, jsonify, send_file
import mysql.connector
import math
import csv
import io
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='Btsdeepa@24',
        database='sims_db'
    )

# Activity log helper
def log_activity(action, item_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO activity_log (action, item_name) VALUES (%s, %s)", (action, item_name))
    conn.commit()
    conn.close()

# Home
@app.route('/')
def home():
    return redirect('/view-inventory')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Replace with your actual user check logic
        if username == 'admin' and password == '1234':
            session['user'] = username
            flash('Login successful!', 'success')
            return redirect('/view-inventory')
        else:
            flash('Invalid credentials. Try again.', 'danger')
            return redirect('/login')

    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect('/')

# View inventory
@app.route('/view-inventory')
def view_inventory():
    query = request.args.get('q', '')
    supplier = request.args.get('supplier', '')
    quantity_threshold = request.args.get('quantity_threshold', '')
    page = int(request.args.get('page', 1))
    per_page = 5
    offset = (page - 1) * per_page

    filters = []
    values = []

    if query:
        filters.append("(name LIKE %s OR supplier LIKE %s)")
        values.extend([f"%{query}%", f"%{query}%"])
    if supplier:
        filters.append("supplier = %s")
        values.append(supplier)
    if quantity_threshold:
       if quantity_threshold == '5+':
           filters.append("quantity >= 5")
       elif quantity_threshold == '10+':
           filters.append("quantity >= 10")
       elif quantity_threshold == '50+':
           filters.append("quantity >= 50")
       elif quantity_threshold == '100+':
           filters.append("quantity >= 100")

    where_clause = " AND ".join(filters)
    if where_clause:
        where_clause = "WHERE " + where_clause

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM inventory {where_clause}", tuple(values))
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT * FROM inventory
        {where_clause}
        ORDER BY last_updated DESC
        LIMIT %s OFFSET %s
    """, tuple(values + [per_page, offset]))
    items = cursor.fetchall()

    cursor.execute("SELECT DISTINCT supplier FROM inventory")
    suppliers = [row[0] for row in cursor.fetchall()]
    conn.close()

    total_pages = math.ceil(total / per_page)

    return render_template('view_inventory.html',
        items=items,
        page=page,
        total_pages=total_pages,
        query=query,
        suppliers=suppliers,
        selected_supplier=supplier,
        quantity_threshold=quantity_threshold
    )

# Add item
@app.route('/add-item', methods=['GET', 'POST'])
def add_item():
    if 'user' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect('/login')
    if request.method == 'POST':
        name = request.form['name']
        quantity = int(request.form['quantity'])
        supplier = request.form['supplier']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO inventory (name, quantity, supplier, last_updated)
            VALUES (%s, %s, %s, NOW())
        """, (name, quantity, supplier))
        conn.commit()
        conn.close()

        log_activity("Added", name)
        flash('Item added successfully!', 'success')
        return redirect('/view-inventory')

    return render_template('add_item.html')

# Edit item
@app.route('/edit-item/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'user' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect('/login')

    if request.method == 'POST':
        name = request.form['name']
        quantity = int(request.form['quantity'])
        supplier = request.form['supplier']

        cursor.execute("""
            UPDATE inventory
            SET name = %s, quantity = %s, supplier = %s, last_updated = NOW()
            WHERE id = %s
        """, (name, quantity, supplier, item_id))
        conn.commit()
        conn.close()

        log_activity("Edited", name)
        flash('Item updated successfully!', 'success')
        return redirect('/view-inventory')

    cursor.execute("SELECT * FROM inventory WHERE id = %s", (item_id,))
    item = cursor.fetchone()
    conn.close()
    return render_template('edit_item.html', item=item)

# Delete item
@app.route('/delete-item/<int:item_id>')
def delete_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if 'user' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect('/login')
    cursor.execute("SELECT name FROM inventory WHERE id = %s", (item_id,))
    item_name = cursor.fetchone()[0]

    cursor.execute("DELETE FROM inventory WHERE id = %s", (item_id,))
    conn.commit()
    conn.close()

    log_activity("Deleted", item_name)
    flash('Item deleted successfully!', 'danger')
    return redirect('/view-inventory')

# Export CSV

@app.route('/export-csv')
def export_csv():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, quantity, supplier, last_updated FROM inventory ORDER BY last_updated DESC")
    items = cursor.fetchall()
    conn.close()

    # Use StringIO for csv.writer
    string_buffer = io.StringIO()
    writer = csv.writer(string_buffer)
    writer.writerow(['Name', 'Quantity', 'Supplier', 'Last Updated'])

    for item in items:
        writer.writerow([
            item[0],
            item[1],
            item[2],
            item[3].strftime('%Y-%m-%d') if item[3] else ''
        ])

    # Convert string to bytes
    byte_buffer = BytesIO(string_buffer.getvalue().encode('utf-8'))
    return send_file(byte_buffer, mimetype='text/csv', as_attachment=True, download_name='inventory.csv')

# Export PDF
@app.route('/export-pdf')
def export_pdf():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, quantity, supplier, last_updated FROM inventory ORDER BY last_updated DESC")
    items = cursor.fetchall()
    conn.close()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Inventory Report")

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(200, 750, "Inventory Report")

    pdf.setFont("Helvetica", 12)
    y = 720
    for item in items:
        line = f"Name: {item[0]} | Qty: {item[1]} | Supplier: {item[2]} | Updated: {item[3].strftime('%Y-%m-%d')}"
        pdf.drawString(50, y, line)
        y -= 20
        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="inventory_report.pdf", mimetype='application/pdf')

# Charts
@app.route('/charts')
def charts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, quantity FROM inventory ORDER BY last_updated DESC")
    items = cursor.fetchall()
    conn.close()

    labels = [item[0] for item in items]
    quantities = [item[1] for item in items]

    return render_template('charts.html', labels=labels, quantities=quantities)

# Activity log
@app.route('/logs')
def view_logs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT action, item_name, timestamp FROM activity_log ORDER BY timestamp DESC")
    logs = cursor.fetchall()
    conn.close()
    return render_template('logs.html', logs=logs)

# RESTful API
@app.route('/api/items', methods=['GET'])
def api_get_items():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory ORDER BY last_updated DESC")
    items = cursor.fetchall()
    conn.close()

    result = []
    for item in items:
        result.append({
            'id': item[0],
            'name': item[1],
            'quantity': item[2],
            'supplier': item[3],
            'last_updated': item[4].isoformat() if item[4] else None
        })
    return jsonify(result)

@app.route('/api/items', methods=['POST'])
def api_add_item():
    data = request.get_json()
    name = data.get('name')
    quantity = data.get('quantity')
    supplier = data.get('supplier')

    if not name or quantity is None or not supplier:
        return jsonify({'error': 'Missing fields'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inventory (name, quantity, supplier, last_updated)
        VALUES (%s, %s, %s, NOW())
    """, (name, quantity, supplier))
    conn.commit()
    conn.close()

    log_activity("Added (API)", name)
    return jsonify({'message': 'Item added successfully'}), 201

@app.route('/api/items/<int:item_id>', methods=['PUT'])
def api_update_item(item_id):
    data = request.get_json()
    name = data.get('name')
    quantity = data.get('quantity')
    supplier = data.get('supplier')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE inventory
        SET name = %s, quantity = %s, supplier = %s, last_updated = NOW()
        WHERE id = %s
    """, (name, quantity, supplier, item_id))
    conn.commit()
    conn.close()

    log_activity("Edited (API)", name)
    return jsonify({'message': 'Item updated successfully'})

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def api_delete_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM inventory WHERE id = %s", (item_id,))
    item = cursor.fetchone()
    if not item:
        conn.close()
        return jsonify({'error': 'Item not found'}), 404

    item_name = item[0]

    cursor.execute("DELETE FROM inventory WHERE id = %s", (item_id,))
    conn.commit()
    conn.close()

    log_activity("Deleted (API)", item_name)
    return jsonify({'message': 'Item deleted successfully'})

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
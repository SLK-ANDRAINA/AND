from flask import Flask, render_template, send_file
import sqlite3
import os
import csv

# --- Configuration ---
DB_PATH = "ebay.db"

app = Flask(
    __name__,
    template_folder=os.path.join("dashboard", "templates"),
    static_folder=os.path.join("dashboard", "static")
)

# --- Connexion DB ---
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- Routes Dashboard ---
@app.route('/')
def dashboard_home():
    conn = get_db_connection()
    sellers = conn.execute("SELECT seller_id FROM sellers").fetchall()
    conn.close()
    return render_template('home.html', sellers=sellers)

@app.route('/seller/<seller_id>/active')
def active_listings(seller_id):
    conn = get_db_connection()
    items = conn.execute(
        "SELECT * FROM listings WHERE status='ACTIVE' AND seller=?", 
        (seller_id,)
    ).fetchall()
    conn.close()
    return render_template('listings.html', title=f"ACTIVES - {seller_id}", items=items)

@app.route('/seller/<seller_id>/ended')
def ended_listings(seller_id):
    conn = get_db_connection()
    items = conn.execute(
        "SELECT * FROM listings WHERE status='ENDED' AND seller=?", 
        (seller_id,)
    ).fetchall()
    conn.close()
    return render_template('listings.html', title=f"ENDED - {seller_id}", items=items)

@app.route('/seller/<seller_id>/kpis')
def kpis(seller_id):
    conn = get_db_connection()
    
    # Totals
    total_active = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE status='ACTIVE' AND seller=?", 
        (seller_id,)
    ).fetchone()[0]
    total_ended = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE status='ENDED' AND seller=?", 
        (seller_id,)
    ).fetchone()[0]

    # Average price, nettoyage symboles
    rows = conn.execute(
        "SELECT price FROM listings WHERE price IS NOT NULL AND seller=?", 
        (seller_id,)
    ).fetchall()

    prices = []
    for row in rows:
        try:
            cleaned = ''.join(c for c in row['price'] if c.isdigit() or c == '.')
            prices.append(float(cleaned))
        except:
            pass

    avg_price = round(sum(prices)/len(prices), 2) if prices else 0

    conn.close()
    return render_template(
        'kpis.html',
        seller_id=seller_id,
        total_active=total_active,
        total_ended=total_ended,
        avg_price=avg_price
    )

# --- Export CSV ---
@app.route('/seller/<seller_id>/export')
def export_csv(seller_id):
    conn = get_db_connection()
    items = conn.execute("SELECT * FROM listings WHERE seller=?", (seller_id,)).fetchall()
    conn.close()

    if not items:
        return f"Aucun listing pour {seller_id}", 404

    filename = f"{seller_id}_export.csv"

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(items[0].keys())  # header
        for item in items:
            writer.writerow(item)

    return send_file(filename, as_attachment=True)

# --- Lancer l'application ---
if __name__ == '__main__':
    app.run(debug=True)

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import datetime
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# PostgreSQL configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin@localhost/analytics_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Define the Customer model
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    subscription_start = db.Column(db.Date, nullable=False)
    subscription_end = db.Column(db.Date, nullable=True)  # Nullable if the subscription is still active
    monthly_spend = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f'<Customer {self.name}>'

# Basic route to display homepage
@app.route('/')
def home():
    customers = Customer.query.all()  # Fetch all customers
    return render_template('index.html', customers=customers)

# Route to add a new customer
@app.route('/add', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        start = datetime.datetime.strptime(request.form['start'], '%Y-%m-%d').date()
        end = request.form['end'] or None  # If the subscription is still active
        monthly_spend = float(request.form['monthly_spend'])

        new_customer = Customer(name=name, subscription_start=start, subscription_end=end, monthly_spend=monthly_spend)
        db.session.add(new_customer)
        db.session.commit()

        return redirect(url_for('home'))

    return render_template('add_customer.html')

if __name__ == '__main__':
    app.run(debug=True)
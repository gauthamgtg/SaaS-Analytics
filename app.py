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
    customers = Customer.query.all()

    # Calculate the number of active customers (those without a subscription_end)
    active_customers = Customer.query.filter(Customer.subscription_end == None).count()

    # Calculate the total monthly spend
    total_spend = db.session.query(db.func.sum(Customer.monthly_spend)).scalar()

    # Calculate churn rate: churned customers / total customers
    total_customers = Customer.query.count()
    churned_customers = Customer.query.filter(Customer.subscription_end != None).count()
    churn_rate = (churned_customers / total_customers) * 100 if total_customers > 0 else 0

    return render_template('index.html', 
                           customers=customers, 
                           active_customers=active_customers, 
                           total_spend=total_spend, 
                           churn_rate=churn_rate)


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

@app.route('/delete/<int:id>')
def delete_customer(id):
    customer = Customer.query.get_or_404(id)  # Fetch customer by ID or return 404
    db.session.delete(customer)  # Delete the customer
    db.session.commit()  # Commit the change
    return redirect(url_for('home'))  # Redirect back to the homepage


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_customer(id):
    customer = Customer.query.get_or_404(id)
    
    if request.method == 'POST':
        # Update customer details from form input
        customer.name = request.form['name']
        customer.subscription_start = request.form['subscription_start']
        customer.subscription_end = request.form['subscription_end'] or None  # Handle empty input for active customers
        customer.monthly_spend = request.form['monthly_spend']

        db.session.commit()  # Save changes
        return redirect(url_for('home'))  # Redirect back to homepage after update

    # GET request: render edit form with existing customer data
    return render_template('edit.html', customer=customer)

if __name__ == '__main__':
    app.run(debug=True)
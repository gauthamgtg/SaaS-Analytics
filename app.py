from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import datetime
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for
import plotly.express as px
import csv
from io import StringIO
from flask import Response


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
    subscription_end = db.Column(db.Date, nullable=False)  # End date is now mandatory
    monthly_spend = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f'<Customer {self.name}>'

# Basic route to display homepage
@app.route('/')
def home():
    customers = Customer.query.all()

    # Get today's date
    today = datetime.today().date()

    # Prepare a list of customers with their active status
    customer_data = []
    for customer in customers:
        # Check if today's date is before or on the subscription end date
        is_active = today <= customer.subscription_end

        customer_data.append({
            'id': customer.id,
            'name': customer.name,
            'subscription_start': customer.subscription_start,
            'subscription_end': customer.subscription_end,
            'monthly_spend': customer.monthly_spend,
            'is_active': is_active
        })

    # Calculate active customers, churn rate, etc.
    active_customers = sum(1 for customer in customer_data if customer['is_active'])
    total_spend = sum(customer['monthly_spend'] for customer in customer_data)
    
    last_month = today - timedelta(days=30)
    churned_customers_last_month = Customer.query.filter(
        Customer.subscription_end < today, 
        Customer.subscription_end >= last_month
    ).count()
    
    total_customers_last_month = Customer.query.filter(
        Customer.subscription_start <= last_month, 
        Customer.subscription_end >= last_month
    ).count()

    churn_rate = (churned_customers_last_month / total_customers_last_month) * 100 if total_customers_last_month > 0 else 0

    return render_template('index.html', 
                           customers=customer_data, 
                           active_customers=active_customers, 
                           total_spend=total_spend, 
                           churn_rate=churn_rate)


# Route to add a new customer
@app.route('/add', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        start = datetime.strptime(request.form['start'], '%Y-%m-%d').date()
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


@app.route('/dashboard')
def dashboard():
    # Fetch data from the database
    data = Customer.query.all()

    # Convert data to a suitable format for Plotly
    if not data:
        return render_template('dashboard.html', graph_html='No data available')

    names = [customer.name for customer in data]
    spends = [customer.monthly_spend for customer in data]

    # Create a DataFrame for Plotly
    import pandas as pd
    df = pd.DataFrame({'Name': names, 'Monthly Spend': spends})

    # Create the bar chart
    fig = px.bar(df, x='Name', y='Monthly Spend', title='Monthly Spend by Customer')
    graph_html = fig.to_html(full_html=False)

    return render_template('dashboard.html', graph_html=graph_html)


@app.route('/export')
def export():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Subscription Start', 'Subscription End', 'Monthly Spend'])
    for customer in Customer.query.all():
        writer.writerow([customer.name, customer.subscription_start, customer.subscription_end, customer.monthly_spend])
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=customers.csv"
    return response

def generate_churn_rate_chart():
    # Query data for churn rate over time (example: monthly churn rate for the past year)
    today = datetime.today()
    churn_rate_data = []
    dates = []

    for i in range(12):
        start_date = today - timedelta(days=(i + 1) * 30)
        end_date = today - timedelta(days=i * 30)
        churned_customers = Customer.query.filter(
            Customer.subscription_end != None,
            Customer.subscription_end >= start_date,
            Customer.subscription_end < end_date
        ).count()
        total_customers = Customer.query.filter(Customer.subscription_start < start_date).count()
        churn_rate = (churned_customers / total_customers) * 100 if total_customers > 0 else 0
        churn_rate_data.append(churn_rate)
        dates.append(start_date.strftime('%Y-%m'))

    churn_rate_data.reverse()
    dates.reverse()

    churn_rate_chart = go.Figure(data=[
        go.Scatter(x=dates, y=churn_rate_data, mode='lines+markers', name='Churn Rate')
    ])
    churn_rate_chart.update_layout(title='Monthly Churn Rate', xaxis_title='Month', yaxis_title='Churn Rate (%)')

    return pio.to_html(churn_rate_chart, full_html=False)

def generate_monthly_spend_chart():
    # Query data for total monthly spend (example: for the past year)
    today = datetime.today()
    monthly_spend_data = []
    dates = []

    for i in range(12):
        start_date = today - timedelta(days=(i + 1) * 30)
        end_date = today - timedelta(days=i * 30)
        total_spend = db.session.query(db.func.sum(Customer.monthly_spend)).filter(
            Customer.subscription_start < end_date,
            (Customer.subscription_end == None) | (Customer.subscription_end >= start_date)
        ).scalar() or 0
        monthly_spend_data.append(total_spend)
        dates.append(start_date.strftime('%Y-%m'))

    monthly_spend_data.reverse()
    dates.reverse()

    monthly_spend_chart = go.Figure(data=[
        go.Bar(x=dates, y=monthly_spend_data, name='Total Monthly Spend')
    ])
    monthly_spend_chart.update_layout(title='Total Monthly Spend', xaxis_title='Month', yaxis_title='Total Spend')

    return pio.to_html(monthly_spend_chart, full_html=False)

if __name__ == '__main__':
    app.run(debug=True)
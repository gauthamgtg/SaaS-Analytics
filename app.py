from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import datetime
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for
import plotly.express as px
import csv
from io import StringIO
from flask import Response
import plotly.graph_objs as go
import plotly.io as pio
from sqlalchemy import func

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
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Customer {self.name}>'
    

@app.route('/')
def home():
    customers = Customer.query.all()
    today = datetime.today().date()
    customer_data = []
    
        # Fetch all customers from the database
    customers = Customer.query.all()

    # Update is_active for each customer
    for customer in customers:
        customer.is_active = customer.subscription_start <= date.today() <= customer.subscription_end

    # Commit the updates to the database
    db.session.commit()

    for customer in customers:
        is_active = today <= customer.subscription_end
        customer_data.append({
            'id': customer.id,
            'name': customer.name,
            'subscription_start': customer.subscription_start,
            'subscription_end': customer.subscription_end,
            'monthly_spend': customer.monthly_spend,
            'is_active': is_active
        })

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

@app.route('/charts')
def charts():
    customers = Customer.query.all()

    today = datetime.today().date()
    dates = []
    active_counts = []

    for i in range(30):
        date = today - timedelta(days=i)
        active_count = sum(1 for customer in customers if customer.subscription_start <= date <= customer.subscription_end)
        dates.append(date)
        active_counts.append(active_count)

    # Create plot
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=active_counts, mode='lines+markers', name='Active Customers'))
    fig.update_layout(title='Active Customers Over Time', xaxis_title='Date', yaxis_title='Number of Active Customers')

    # Convert plot to HTML
    plot_html = pio.to_html(fig, full_html=False)

    return render_template('charts.html', plot_html=plot_html)

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

# Add ARPU route
@app.route('/metrics')
def metrics():
    total_revenue = db.session.query(func.sum(Customer.monthly_spend)).scalar() or 0
    active_customers = db.session.query(Customer).filter(Customer.is_active == True).count()

    arpu = total_revenue / active_customers if active_customers > 0 else 0
    cltv_data = calculate_cltv()
    retention_rate = calculate_retention_rate()

    return render_template('metrics.html', arpu=round(arpu, 2), cltv_data=cltv_data, retention_rate=round(retention_rate, 2))

# Function to calculate CLTV
def calculate_cltv():
    customers = Customer.query.all()
    cltv_data = []
    
    for customer in customers:
        # Sum of all monthly spend for the customer to get the total spend
        cltv = db.session.query(func.sum(Customer.monthly_spend)).filter(Customer.id == customer.id).scalar() or 0
        cltv_data.append({'name': customer.name, 'cltv': cltv})
    
    return cltv_data

# Function to calculate retention rate
def calculate_retention_rate():
    churned_customers = Customer.query.filter(Customer.is_active == False).count()
    total_customers = Customer.query.count()
    return (total_customers - churned_customers) / total_customers * 100 if total_customers > 0 else 0

# Filter by Date Range
@app.route('/filter', methods=['POST'])
def filter_customers():
    start_date = request.form['start_date']
    end_date = request.form['end_date']

    customers = Customer.query.filter(Customer.subscription_start >= start_date, 
                                      Customer.subscription_end <= end_date).all()
    return render_template('index.html', customers=customers)

# Filter by Active Status
@app.route('/filter_status', methods=['POST'])
def filter_status():
    status_filter = request.form['status_filter']
    
    if status_filter == 'active':
        customers = Customer.query.filter(Customer.is_active == True).all()
    elif status_filter == 'churned':
        customers = Customer.query.filter(Customer.is_active == False).all()
    else:
        customers = Customer.query.all()
    
    return render_template('index.html', customers=customers)

if __name__ == '__main__':
    app.run(debug=True)
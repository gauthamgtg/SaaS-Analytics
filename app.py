from flask import Flask, render_template, request, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
import plotly.graph_objs as go
import plotly.io as pio
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy import func
import csv
from io import StringIO

app = Flask(__name__)

# PostgreSQL configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin@localhost/analytics_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Customer Model
class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    city = db.Column(db.String(255))
    country = db.Column(db.String(255))
    
    # Define the relationship with Subscription
    subscriptions = db.relationship('Subscription', backref='customer', lazy=True)

    def __repr__(self):
        return f'<Customer {self.name}>'

# Subscription Model
class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    name = db.Column(db.String(50))
    subscription_start = db.Column(db.Date)
    subscription_end = db.Column(db.Date)
    subscription_amount = db.Column(db.Integer)
    
    # Define the foreign key to the SubscriptionPlan table
    subscription_plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'))
    
    payment_date = db.Column(db.Date)
    status = db.Column(db.String(6))
    card_type = db.Column(db.String(50))
    currency = db.Column(db.String(50))

    # Define the relationship to the SubscriptionPlan model
    subscription_plan = db.relationship('SubscriptionPlan', backref='subscriptions')

    def __repr__(self):
        return f'<Subscription {self.name}, Customer ID: {self.customer_id}>'

# Subscription Plan Model
class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'
    id = db.Column(db.Integer, primary_key=True)
    plan_name = db.Column(db.String(100))
    plan_details = db.Column(db.Text)
    price = db.Column(db.Integer)

    def __repr__(self):
        return f'<SubscriptionPlan {self.plan_name}>'


def group_by_period(query, period):
    if period == 'day':
        return func.date_trunc('day', query)
    elif period == 'week':
        return func.date_trunc('week', query)
    elif period == 'month':
        return func.date_trunc('month', query)
    elif period == 'year':
        return func.date_trunc('year', query)
    else:
        return func.date_trunc('month', query)  # Default is month

def get_grouped_data(period):
    # Group by period (day, week, month, year) based on request
    period_group = group_by_period(Subscription.subscription_start, period)
    
    # Revenue data
    revenue_data = db.session.query(
        period_group.label('period'), func.sum(Subscription.subscription_amount).label('total_revenue')
    ).group_by('period').order_by('period').all()

    # Growth data: Calculate % improvement over the last period
    growth_data = []
    last_revenue = None
    for revenue in revenue_data:
        if last_revenue is None:
            growth_data.append(0)  # No growth for the first period
        else:
            growth = ((revenue.total_revenue - last_revenue) / last_revenue) * 100 if last_revenue > 0 else 0
            growth_data.append(growth)
        last_revenue = revenue.total_revenue
    
    # Churn data: Calculate churn loss based on subscription end
    churn_data = db.session.query(
        period_group.label('period'), func.sum(Subscription.subscription_amount).label('churn_loss')
    ).filter(Subscription.subscription_end < datetime.today().date()).group_by('period').order_by('period').all()
    
    return revenue_data, growth_data, churn_data

@app.route('/')
def home():
    # Get the grouping period from the request (day, week, month, year)
    period = request.args.get('period', 'month')  # Default is 'month'

    # Group by period (day, week, month, year) based on request
    period_group = group_by_period(Subscription.subscription_start, period)

    # Example data fetching
    total_customers = Customer.query.count()
    mrr = db.session.query(func.sum(Subscription.subscription_amount)).scalar() or 0
    arr = mrr * 12  # Assuming ARR is MRR * 12
    active_customers = Subscription.query.filter(
        Subscription.subscription_start <= datetime.today().date(),
        Subscription.subscription_end >= datetime.today().date()
    ).count()

    # Retention and churn rate calculations (replace with actual logic)
    retention_rate = calculate_retention_rate()  # As defined in the code
    churn_rate = calculate_churn_rate()  # As defined in the code

    # Fetch top customers (replace with actual logic)
    top_customers = db.session.query(
        Customer.name, Customer.email, func.sum(Subscription.subscription_amount).label('total_spend')
    ).join(Subscription).group_by(Customer.id).order_by(func.sum(Subscription.subscription_amount).desc()).limit(5).all()

    # Fetch revenue data grouped by the selected period (day, week, month, year)
    revenue_data_query = db.session.query(
        period_group.label('period'), func.sum(Subscription.subscription_amount).label('total_revenue')
    ).group_by('period').order_by('period').all()

    # Prepare the labels and revenue data for the chart
    revenue_labels = [r.period.strftime('%Y-%m-%d') for r in revenue_data_query]
    revenue_data = [r.total_revenue for r in revenue_data_query]

    # Fetch growth data: Calculate % improvement over the last period
    growth_data = []
    last_revenue = None
    for r in revenue_data_query:
        if last_revenue is None:
            growth_data.append(0)  # No growth for the first period
        else:
            growth = ((r.total_revenue - last_revenue) / last_revenue) * 100 if last_revenue > 0 else 0
            growth_data.append(growth)
        last_revenue = r.total_revenue

    # Fetch churn data: Calculate churn loss based on subscription end
    churn_data_query = db.session.query(
        period_group.label('period'), func.sum(Subscription.subscription_amount).label('churn_loss')
    ).filter(Subscription.subscription_end < datetime.today().date()).group_by('period').order_by('period').all()

    churn_labels = [c.period.strftime('%Y-%m-%d') for c in churn_data_query]
    churn_data = [c.churn_loss for c in churn_data_query]

    # Fetch month-wise total amount received for the monthly amount chart
    monthly_data = []
    monthly_labels = []
    for i in range(11, -1, -1):  # Loop through last 12 months (ascending)
        month_start = (datetime.today().replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1)  # To get the next month's 1st day
        total_amount = db.session.query(func.sum(Subscription.subscription_amount)).filter(
            Subscription.payment_date >= month_start,
            Subscription.payment_date < month_end
        ).scalar() or 0
        monthly_labels.append(month_start.strftime('%B'))  # Append month name
        monthly_data.append(total_amount)

    # Render the template and pass all required data
    return render_template('index.html',
                           total_customers=total_customers,
                           mrr=mrr,
                           arr=arr,
                           active_customers=active_customers,
                           retention_rate=retention_rate,
                           churn_rate=churn_rate,
                           top_customers=top_customers,
                           growth_labels=revenue_labels,  # Using revenue labels for growth chart too
                           growth_data=growth_data,
                           churn_labels=churn_labels,
                           churn_data=churn_data,
                           revenue_labels=revenue_labels,
                           revenue_data=revenue_data,
                           monthly_labels=monthly_labels,
                           monthly_data=monthly_data,
                           period=period)  # Pass the selected period for the dropdown

def calculate_churn_rate():
    today = datetime.today().date()
    last_month = today - timedelta(days=30)

    # Get the number of customers whose subscriptions ended last month
    churned_customers_last_month = Subscription.query.filter(
        Subscription.subscription_end < today, 
        Subscription.subscription_end >= last_month
    ).count()

    # Total number of customers from last month (those who were subscribed)
    total_customers_last_month = Subscription.query.filter(
        Subscription.subscription_start <= last_month, 
        Subscription.subscription_end >= last_month
    ).count()

    # Calculate churn rate (customers lost / total customers) * 100
    churn_rate = (churned_customers_last_month / total_customers_last_month) * 100 if total_customers_last_month > 0 else 0
    return churn_rate


def calculate_retention_rate():
    today = datetime.today().date()

    # Calculate total number of active customers at the beginning of the month
    total_customers_at_start = Subscription.query.filter(
        Subscription.subscription_start <= today - timedelta(days=30)
    ).count()

    # Calculate number of customers still active at the end of the period (today)
    retained_customers = Subscription.query.filter(
        Subscription.subscription_start <= today - timedelta(days=30),
        Subscription.subscription_end >= today
    ).count()

    # Calculate retention rate (retained customers / total customers) * 100
    retention_rate = (retained_customers / total_customers_at_start) * 100 if total_customers_at_start > 0 else 0
    return retention_rate


# Charts Route
@app.route('/charts')
def charts():
    customers = Customer.query.all()
    today = datetime.today().date()
    dates = []
    active_counts = []

    # Generate active customer count over the past 30 days (optimized)
    for i in range(30):
        date = today - timedelta(days=i)
        active_count = Subscription.query.filter(
            Subscription.subscription_start <= date, 
            Subscription.subscription_end >= date
        ).count()
        dates.append(date)
        active_counts.append(active_count)

    # Create plot
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=active_counts, mode='lines+markers', name='Active Customers'))
    fig.update_layout(title='Active Customers Over Time', xaxis_title='Date', yaxis_title='Number of Active Customers')

    # Convert plot to HTML
    plot_html = pio.to_html(fig, full_html=False)

    return render_template('charts.html', plot_html=plot_html)

# Add Customer Route
@app.route('/add_customer', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        city = request.form['city']
        country = request.form['country']
        new_customer = Customer(name=name, email=email, phone=phone, address=address, city=city, country=country)
        db.session.add(new_customer)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('add_customer.html')

# Add Subscription Route
@app.route('/add_subscription', methods=['GET', 'POST'])
def add_subscription():
    customers = Customer.query.all()
    if request.method == 'POST':
        customer_id = request.form['customer_id']
        name = request.form['name']
        subscription_start = request.form['subscription_start']
        subscription_end = request.form['subscription_end']
        subscription_amount = request.form['subscription_amount']
        subscription_plan_id = request.form['subscription_plan_id']
        status = request.form['status']
        card_type = request.form['card_type']
        currency = request.form['currency']
        new_subscription = Subscription(customer_id=customer_id, name=name, subscription_start=subscription_start,
                                        subscription_end=subscription_end, subscription_amount=subscription_amount,
                                        subscription_plan_id=subscription_plan_id, status=status, card_type=card_type, currency=currency)
        db.session.add(new_subscription)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('add_subscription.html', customers=customers)


# Edit Customer Route
@app.route('/edit_customer/<int:id>', methods=['GET', 'POST'])
def edit_customer(id):
    customer = Customer.query.get_or_404(id)
    if request.method == 'POST':
        customer.name = request.form['name']
        customer.email = request.form['email']
        customer.phone = request.form['phone']
        customer.address = request.form['address']
        customer.city = request.form['city']
        customer.country = request.form['country']
        db.session.commit()
        return redirect(url_for('home'))  # Redirect to 'home' instead of 'index'
    return render_template('edit_customer.html', customer=customer)

# Edit subscription Route
@app.route('/edit_subscription/<int:id>', methods=['GET', 'POST'])
def edit_subscription(id):
    subscription = Subscription.query.get_or_404(id)
    customers = Customer.query.all()
    if request.method == 'POST':
        subscription.customer_id = request.form['customer_id']
        subscription.name = request.form['name']
        subscription.subscription_start = request.form['subscription_start']
        subscription.subscription_end = request.form['subscription_end']
        subscription.subscription_amount = request.form['subscription_amount']
        subscription.subscription_plan_id = request.form['subscription_plan_id']
        subscription.status = request.form['status']
        subscription.card_type = request.form['card_type']
        subscription.currency = request.form['currency']
        db.session.commit()
        return redirect(url_for('home'))  # Redirect to 'home' for consistency
    return render_template('edit_subscription.html', subscription=subscription, customers=customers)

# Dashboard Route
@app.route('/dashboard')
def dashboard():
    data = Customer.query.all()

    if not data:
        return render_template('dashboard.html', graph_html='No data available')

    names = [customer.name for customer in data]
    spends = [sum(sub.subscription_amount for sub in customer.subscriptions) for customer in data]

    df = pd.DataFrame({'Name': names, 'Monthly Spend': spends})

    # Create bar chart
    fig = px.bar(df, x='Name', y='Monthly Spend', title='Monthly Spend by Customer')
    graph_html = fig.to_html(full_html=False)

    return render_template('dashboard.html', graph_html=graph_html)

@app.route('/customers', methods=['GET', 'POST'])
def show_customers():
    # Get filter inputs from the request
    search_query = request.args.get('search', '')
    
    # Apply filters based on the search query
    customers = Customer.query.filter(
        Customer.name.ilike(f"%{search_query}%") | Customer.email.ilike(f"%{search_query}%")
    ).all()
    
    return render_template('customers.html', customers=customers, search_query=search_query)

@app.route('/subscriptions', methods=['GET', 'POST'])
def show_subscriptions():
    # Get filter inputs from the request
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')

    # Apply filters for search query and status
    subscriptions = Subscription.query.join(Customer).filter(
        (Subscription.status.ilike(f"%{status_filter}%")) &
        (Customer.name.ilike(f"%{search_query}%"))
    ).all()
    
    return render_template('subscriptions.html', subscriptions=subscriptions, search_query=search_query, status_filter=status_filter)


# Export Data Route
@app.route('/export')
def export():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Subscription Start', 'Subscription End', 'Monthly Spend'])
    for customer in Customer.query.all():
        writer.writerow([customer.name, customer.subscriptions[0].subscription_start, customer.subscriptions[0].subscription_end,
                         sum(sub.subscription_amount for sub in customer.subscriptions)])
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=customers.csv"
    return response

# Metrics Route for ARPU, CLTV, Retention
@app.route('/metrics')
def metrics():
    total_revenue = db.session.query(func.sum(Subscription.subscription_amount)).scalar() or 0
    active_customers = Subscription.query.filter(
        Subscription.subscription_start <= datetime.today().date(),
        Subscription.subscription_end >= datetime.today().date()
    ).count()

    arpu = total_revenue / active_customers if active_customers > 0 else 0
    cltv_data = calculate_cltv()
    retention_rate = calculate_retention_rate()

    return render_template('metrics.html', arpu=round(arpu, 2), cltv_data=cltv_data, retention_rate=round(retention_rate, 2))

# Function to calculate CLTV
def calculate_cltv():
    customers = Customer.query.all()
    cltv_data = []

    for customer in customers:
        cltv = sum(sub.subscription_amount for sub in customer.subscriptions)
        cltv_data.append({'name': customer.name, 'cltv': cltv})
    
    return cltv_data

# Function to calculate Retention Rate
def calculate_retention_rate():
    churned_customers = Subscription.query.filter(
        Subscription.subscription_end < datetime.today().date()
    ).count()
    total_customers = Customer.query.count()
    return (total_customers - churned_customers) / total_customers * 100 if total_customers > 0 else 0

# Filter by Date Range Route
@app.route('/filter', methods=['POST'])
def filter_customers():
    start_date = request.form['start_date']
    end_date = request.form['end_date']

    customers = Customer.query.join(Subscription).filter(
        Subscription.subscription_start >= start_date,
        Subscription.subscription_end <= end_date
    ).all()
    return render_template('index.html', customers=customers)

# Filter by Active Status Route
@app.route('/filter_status', methods=['POST'])
def filter_status():
    status_filter = request.form['status_filter']
    
    if status_filter == 'active':
        customers = Subscription.query.filter(
            Subscription.subscription_start <= datetime.today().date(),
            Subscription.subscription_end >= datetime.today().date()
        ).all()
    elif status_filter == 'churned':
        customers = Subscription.query.filter(
            Subscription.subscription_end < datetime.today().date()
        ).all()
    else:
        customers = Subscription.query.all()
    
    return render_template('index.html', customers=customers)

if __name__ == '__main__':
    app.run(debug=True)

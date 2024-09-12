from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
import plotly.graph_objs as go
import plotly.io as pio
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy import func
import csv
from io import StringIO
from flask import Flask, render_template, redirect, url_for, session, request, flash
# from models import db, Business  # Assuming your Business model is defined here
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import asc, desc
import pandas as pd

app = Flask(__name__)
app.secret_key = '12345'  # Use a strong secret key for session management


# PostgreSQL configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin@localhost/analytics_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)


# Models
# Business Model
class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    business_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200))
    city = db.Column(db.String(50))
    country = db.Column(db.String(50))

    # Relationships
    customers = db.relationship('Customer', backref='business', lazy=True)
    subscriptions = db.relationship('Subscription', backref='business', lazy=True)
    plans = db.relationship('SubscriptionPlan', backref='business', lazy=True)

    def __repr__(self):
        return f'<Business {self.business_name}>'

# Customer Model
class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    
    # Relationship with customer subscriptions
    subscriptions = db.relationship('CustomerSubscription', backref='customer', lazy=True)

    def __repr__(self):
        return f'<Customer {self.name}>'

# Subscription Model (Business Level)
class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    name = db.Column(db.String(50))
    subscription_start = db.Column(db.Date)
    subscription_end = db.Column(db.Date)
    subscription_amount = db.Column(db.Integer)
    subscription_plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.plan_id'))
    payment_date = db.Column(db.Date)
    status = db.Column(db.String(10))
    card_type = db.Column(db.String(50))
    currency = db.Column(db.String(50))

    def __repr__(self):
        return f'<Subscription {self.name} for Business ID {self.business_id}>'

# Subscription Plan Model (Business Level)
class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, unique=True, nullable=False)
    plan_name = db.Column(db.String(100), nullable=False)
    plan_details = db.Column(db.Text)
    price = db.Column(db.Integer)
    
    # Foreign key linking to the Business
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)

    def __repr__(self):
        return f'<SubscriptionPlan {self.plan_name}>'

# Customer Subscription Model (Customer Level)
class CustomerSubscription(db.Model):
    __tablename__ = 'customer_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    subscription_plan_id = db.Column(db.Integer, db.ForeignKey('customer_subscription_plans.plan_id'), nullable=False)
    subscription_start = db.Column(db.Date, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    subscription_end = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False)
    subscription_amount = db.Column(db.Numeric(10, 2))

    def __repr__(self):
        return f'<CustomerSubscription {self.id}>'

# Customer Subscription Plan Model (Customer Level)
class CustomerSubscriptionPlan(db.Model):
    __tablename__ = 'customer_subscription_plans'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    plan_name = db.Column(db.String(100), nullable=False)
    plan_details = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    plan_id = db.Column(db.Integer, unique=True, nullable=False)

    def __repr__(self):
        return f'<CustomerSubscriptionPlan {self.plan_name} for Customer ID {self.customer_id}>'


# Route for login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        business_name = request.form.get('business_name')
        
        # Find the business by name
        business = Business.query.filter_by(business_name=business_name).first()

        if business:
            session['business_id'] = business.id
            session['business_name'] = business.business_name
            return redirect(url_for('index'))  # Redirect to the index after login
        else:
            flash("Invalid business name, please try again.")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Clear session data to log out the user
    session.pop('business_id', None)
    session.pop('business_name', None)
    
    # Redirect to the login page after logging out
    return redirect(url_for('login'))


def group_by_period(query, period):
    if period == 'day':
        return func.date_trunc('day', query)
    elif period == 'week':
        return func.date_trunc('week', query)
    elif period == 'month':
        return func.date_trunc('month', query)
    elif period == 'quarter':
        return func.date_trunc('quarter', query)
    elif period == 'year':
        return func.date_trunc('year', query)
    else:
        return func.date_trunc('month', query)  # Default is month

def get_grouped_data(period):
    # Get the logged-in business_id from the session
    business_id = session.get('business_id')

    if not business_id:
        return "No business logged in", 403

    # Group by period (day, week, month, year) based on request
    period_group = group_by_period(Subscription.subscription_start, period)
    
    # Revenue data: filter by business_id
    revenue_data = db.session.query(
        period_group.label('period'), func.sum(Subscription.subscription_amount).label('total_revenue')
    ).filter(Subscription.business_id == business_id).group_by('period').order_by('period').all()

    # Growth data: Calculate % improvement over the last period
    growth_data = []
    last_revenue = None
    for revenue in revenue_data:
        if last_revenue is None:
            growth_data.append(0)  # No growth for the first period
        else:
            growth = round(((revenue.total_revenue - last_revenue) / last_revenue) * 100 if last_revenue > 0 else 0)
            growth_data.append(round(float(growth)))  # Convert to float and round it to nearest integer
        last_revenue = revenue.total_revenue
    
    # Churn data: Calculate churn loss based on subscription end, filter by business_id
    churn_data = db.session.query(
        period_group.label('period'), func.sum(Subscription.subscription_amount).label('churn_loss')
    ).filter(
        Subscription.subscription_end < datetime.today().date(),
        Subscription.business_id == business_id  # Filter by business_id
    ).group_by('period').order_by('period').all()
    
    return revenue_data, growth_data, churn_data

#Home data:
@app.route('/')
@app.route('/index')
def index():
    if 'business_id' not in session:
        return redirect(url_for('login'))  # Redirect to login if not logged in

    business_id = session['business_id']
    business_name = session['business_name']

    # Get the grouping period from the request (day, week, month, year)
    period = request.args.get('period', 'month')  # Default is 'month'

    # Group by period (day, week, month, year) based on request
    period_group = group_by_period(CustomerSubscription.subscription_start, period)

    # Fetch data related to the logged-in business only, filtering by business_id in the Customer table
    total_customers = Customer.query.filter_by(business_id=business_id).count()

    mrr = db.session.query(func.sum(CustomerSubscription.subscription_amount)).join(Customer, Customer.id == CustomerSubscription.customer_id).filter(
        Customer.business_id == business_id
    ).scalar() or 0

    arr = mrr * 12  # Assuming ARR is MRR * 12

    active_customers = CustomerSubscription.query.join(Customer, Customer.id == CustomerSubscription.customer_id).filter(
        CustomerSubscription.subscription_start <= datetime.today().date(),
        CustomerSubscription.subscription_end >= datetime.today().date(),
        Customer.business_id == business_id
    ).count()

    # Retention and churn rate calculations
    retention_rate = calculate_retention_rate(business_id)  # Pass business_id
    churn_rate = calculate_churn_rate(business_id)  # Pass business_id

    # Fetch top customers based on total spend, filtered by business_id
    top_customers = db.session.query(
        Customer.name, Customer.email, func.sum(CustomerSubscription.subscription_amount).label('total_spend')
    ).join(Customer, Customer.id == CustomerSubscription.customer_id).filter(
        Customer.business_id == business_id
    ).group_by(Customer.id).order_by(
        func.sum(CustomerSubscription.subscription_amount).desc()
    ).limit(5).all()

    # Fetch revenue data grouped by the selected period (day, week, month, year)
    revenue_data_query = db.session.query(
        period_group.label('period'), func.sum(CustomerSubscription.subscription_amount).label('total_revenue')
    ).join(Customer, Customer.id == CustomerSubscription.customer_id).filter(
        Customer.business_id == business_id
    ).group_by(period_group).order_by(period_group).all()

    # Convert revenue data to float and round
    revenue_labels = [r.period.strftime('%Y-%m-%d') for r in revenue_data_query]
    revenue_data = [round(float(r.total_revenue)) for r in revenue_data_query]

    # Fetch growth data: Calculate % improvement over the last period
    growth_data = []
    last_revenue = None
    for r in revenue_data_query:
        if last_revenue is None:
            growth_data.append(0)  # No growth for the first period
        else:
            growth = ((r.total_revenue - last_revenue) / last_revenue) * 100 if last_revenue > 0 else 0
            growth_data.append(round(float(growth)))
        last_revenue = r.total_revenue

    # Fetch churn data: Calculate churn loss based on subscription end
    churn_data_query = db.session.query(
        period_group.label('period'), func.sum(CustomerSubscription.subscription_amount).label('churn_loss')
    ).join(Customer, Customer.id == CustomerSubscription.customer_id).filter(
        CustomerSubscription.subscription_end < datetime.today().date(),
        Customer.business_id == business_id
    ).group_by(period_group).order_by(period_group).all()

    churn_labels = [c.period.strftime('%Y-%m-%d') for c in churn_data_query]
    churn_data = [round(float(c.churn_loss)) for c in churn_data_query]

    # Fetch month-wise total amount received for the monthly amount chart
    monthly_data = []
    monthly_labels = []
    for i in range(11, -1, -1):  # Loop through last 12 months (ascending)
        month_start = (datetime.today().replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1)  # To get the next month's 1st day
        total_amount = db.session.query(func.sum(CustomerSubscription.subscription_amount)).join(Customer, Customer.id == CustomerSubscription.customer_id).filter(
            CustomerSubscription.payment_date >= month_start,
            CustomerSubscription.payment_date < month_end,
            Customer.business_id == business_id
        ).scalar() or 0
        monthly_labels.append(month_start.strftime('%B'))  # Append month name
        monthly_data.append(round(float(total_amount)))

    # Debugging step: Print the fetched data to console for verification
    print(f"Revenue Labels: {revenue_labels}")
    print(f"Revenue Data: {revenue_data}")
    print(f"Growth Data: {growth_data}")
    print(f"Churn Data: {churn_data}")
    print(f"Monthly Data: {monthly_data}")

    # Render the template and pass all required data
    return render_template('index.html',
                           total_customers=total_customers,
                           mrr=round(float(mrr)),
                           arr=round(float(arr)),
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


# Churn rate calculation
def calculate_churn_rate(business_id):
    today = datetime.today().date()
    last_month = today - timedelta(days=30)

    # Get the number of customers whose subscriptions ended last month
    churned_customers_last_month = CustomerSubscription.query.join(Customer).filter(
        CustomerSubscription.subscription_end < today,
        CustomerSubscription.subscription_end >= last_month,
        Customer.business_id == business_id
    ).count()

    # Total number of customers from last month (those who were subscribed)
    total_customers_last_month = CustomerSubscription.query.join(Customer).filter(
        CustomerSubscription.subscription_start <= last_month,
        CustomerSubscription.subscription_end >= last_month,
        Customer.business_id == business_id
    ).count()

    # Calculate churn rate (customers lost / total customers) * 100
    churn_rate = (churned_customers_last_month / total_customers_last_month) * 100 if total_customers_last_month > 0 else 0
    return round(churn_rate)


# Retention rate calculation
def calculate_retention_rate(business_id):
    today = datetime.today().date()

    # Calculate total number of active customers at the beginning of the month
    total_customers_at_start = CustomerSubscription.query.join(Customer).filter(
        CustomerSubscription.subscription_start <= today - timedelta(days=30),
        Customer.business_id == business_id
    ).count()

    # Calculate number of customers still active at the end of the period (today)
    retained_customers = CustomerSubscription.query.join(Customer).filter(
        CustomerSubscription.subscription_start <= today - timedelta(days=30),
        CustomerSubscription.subscription_end >= today,
        Customer.business_id == business_id
    ).count()

    # Calculate retention rate (retained customers / total customers) * 100
    retention_rate = (retained_customers / total_customers_at_start) * 100 if total_customers_at_start > 0 else 0
    return round(retention_rate)


# Charts Route
@app.route('/charts')
def charts():
    if 'business_id' not in session:
        return redirect(url_for('login'))  # Ensure user is logged in
    
    business_id = session['business_id']
    today = datetime.today().date()
    dates = []
    active_counts = []

    # Generate active customer count over the past 30 days for the logged-in business
    for i in range(30):
        date = today - timedelta(days=i)
        active_count = CustomerSubscription.query.filter(
            CustomerSubscription.subscription_start <= date,
            CustomerSubscription.subscription_end >= date,
            CustomerSubscription.business_id == business_id
        ).count()
        dates.append(date)
        active_counts.append(active_count)

    # Create plot using Plotly
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

# Customer Routes
@app.route('/customers')
def show_customers():
    if 'business_id' not in session:
        return redirect(url_for('login'))

    business_id = session['business_id']
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    sort_by = request.args.get('sort_by', 'name')  # Default sort by 'name'
    order = request.args.get('order', 'asc')  # Default order is 'asc'

    # Define the sorting logic
    if sort_by == 'name':
        sort_column = Customer.name
    elif sort_by == 'email':
        sort_column = Customer.email
    elif sort_by == 'phone':
        sort_column = Customer.phone
    else:
        sort_column = Customer.name  # Default to sorting by name if unknown sort_by

    # Apply sorting direction
    if order == 'asc':
        sort_column = sort_column.asc()
    else:
        sort_column = sort_column.desc()

    # Filter customers by search query and business_id, and paginate results
    customers = Customer.query.filter(
        (Customer.name.ilike(f"%{search_query}%") | Customer.email.ilike(f"%{search_query}%")),
        Customer.business_id == business_id
    ).order_by(sort_column).paginate(page=page, per_page=per_page)

    return render_template(
        'customers.html', 
        customers=customers, 
        search_query=search_query, 
        per_page=per_page,
        sort_by=sort_by,
        order=order,
        page=page,
        min=min,
        max=max  # Pass the `max` function to the template
    )


# Subscription Routes
@app.route('/subscriptions', methods=['GET'])
def show_subscriptions():
    if 'business_id' not in session:
        return redirect(url_for('login'))

    business_id = session['business_id']
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    limit = int(request.args.get('limit', 20))  # Default to 20 items per page
    page = request.args.get('page', 1, type=int)  # Get current page

    # Sorting parameters
    sort_by = request.args.get('sort_by', 'customer.name')  # Default sorting by customer name
    order = request.args.get('order', 'asc')

    # Determine sorting order
    if order == 'asc':
        next_order = 'desc'
        sort_order = asc
        sort_arrow = '↑'
    else:
        next_order = 'asc'
        sort_order = desc
        sort_arrow = '↓'

    # Join CustomerSubscription with Customer and CustomerSubscriptionPlan
    query = db.session.query(CustomerSubscription, Customer, CustomerSubscriptionPlan).join(
        Customer, CustomerSubscription.customer_id == Customer.id
    ).join(
        CustomerSubscriptionPlan, CustomerSubscription.subscription_plan_id == CustomerSubscriptionPlan.id
    ).filter(
        Customer.business_id == business_id
    )

    if search_query:
        query = query.filter(Customer.name.ilike(f"%{search_query}%"))

    if status_filter:
        query = query.filter(CustomerSubscription.status == status_filter)

    # Handle sorting based on the selected field
    if sort_by == 'plan_name':
        query = query.order_by(sort_order(CustomerSubscriptionPlan.plan_name))
    elif sort_by == 'subscription_amount':
        query = query.order_by(sort_order(CustomerSubscription.subscription_amount))
    elif sort_by == 'customer_id':
        query = query.order_by(sort_order(Customer.id))
    else:
        query = query.order_by(sort_order(Customer.name))

    # Paginate the query
    subscriptions = query.paginate(page=page, per_page=limit)

    # Calculate pagination logic for nearest 5 pages
    start_page = max(1, page - 2)
    end_page = min(start_page + 4, subscriptions.pages)
    start_page = max(1, end_page - 4)

    return render_template('subscriptions.html', 
                           subscriptions=subscriptions, 
                           search_query=search_query,
                           status_filter=status_filter, 
                           limit=limit,
                           sort_by=sort_by, 
                           order=order, 
                           next_order=next_order,
                           sort_arrow=sort_arrow,  # Pass the arrow
                           start_page=start_page, 
                           end_page=end_page)


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

# Map view route

# Map view route
@app.route('/map')
def map_view():
    if 'business_id' not in session:
        return redirect(url_for('login'))
    
    business_id = session['business_id']
    data_type = request.args.get('data_type', 'customers')
    
    # Fetch data based on data type
    if data_type == 'customers':
        data = db.session.query(
            Customer.country, 
            func.count(Customer.id).label('count')
        ).filter(Customer.business_id == business_id).group_by(Customer.country).all()

    elif data_type == 'active_customers':
        today = datetime.today().date()
        data = db.session.query(
            Customer.country, 
            func.count(CustomerSubscription.id).label('count')
        ).select_from(Customer).join(
            CustomerSubscription, Customer.id == CustomerSubscription.customer_id
        ).filter(
            CustomerSubscription.subscription_start <= today,
            CustomerSubscription.subscription_end >= today,
            Customer.business_id == business_id
        ).group_by(Customer.country).all()

    elif data_type == 'avg_revenue':
        data = db.session.query(
            Customer.country, 
            func.avg(CustomerSubscription.subscription_amount).label('avg_revenue')
        ).select_from(Customer).join(
            CustomerSubscription, Customer.id == CustomerSubscription.customer_id
        ).filter(Customer.business_id == business_id).group_by(Customer.country).all()

    elif data_type == 'total_revenue':
        data = db.session.query(
            Customer.country, 
            func.sum(CustomerSubscription.subscription_amount).label('total_revenue')
        ).select_from(Customer).join(
            CustomerSubscription, Customer.id == CustomerSubscription.customer_id
        ).filter(Customer.business_id == business_id).group_by(Customer.country).all()

    # Ensure data is not None
    if not data:
        data = []

    # Convert data to dictionary format suitable for frontend
    country_data = {country: value for country, value in data}

    # Render the template and pass the data
    return render_template('map.html', country_data=country_data, data_type=data_type, overall_stats=calculate_overall_stats(business_id))


# Function to get data based on the data type
def get_map_data(data_type, business_id):
    today = datetime.today().date()

    if data_type == 'customers':
        # Number of customers per country
        data = db.session.query(
            Customer.country, 
            func.count(Customer.id).label('customer_count')
        ).filter(Customer.business_id == business_id).group_by(Customer.country).all()

        return {country: count for country, count in data}

    elif data_type == 'active_customers':
        # Number of active customers per country
        data = db.session.query(
            Customer.country, 
            func.count(CustomerSubscription.id).label('active_customer_count')
        ).select_from(Customer).join(
            CustomerSubscription, Customer.id == CustomerSubscription.customer_id
        ).filter(
            CustomerSubscription.subscription_start <= today,
            CustomerSubscription.subscription_end >= today,
            Customer.business_id == business_id
        ).group_by(Customer.country).all()

        return {country: count for country, count in data}

    elif data_type == 'avg_revenue':
        # Average revenue per customer per country
        data = db.session.query(
            Customer.country, 
            func.avg(CustomerSubscription.subscription_amount).label('avg_revenue')
        ).select_from(Customer).join(
            CustomerSubscription, Customer.id == CustomerSubscription.customer_id
        ).filter(Customer.business_id == business_id).group_by(Customer.country).all()

        return {country: avg_revenue for country, avg_revenue in data}

    elif data_type == 'total_revenue':
        # Total revenue per customer per country
        data = db.session.query(
            Customer.country, 
            func.sum(CustomerSubscription.subscription_amount).label('total_revenue')
        ).select_from(Customer).join(
            CustomerSubscription, Customer.id == CustomerSubscription.customer_id
        ).filter(Customer.business_id == business_id).group_by(Customer.country).all()

        return {country: total_revenue for country, total_revenue in data}


# Function to calculate overall stats for the business
def calculate_overall_stats(business_id):
    """Calculate overall stats for the business"""
    
    # Total number of customers
    total_customers = db.session.query(func.count(Customer.id)).filter(
        Customer.business_id == business_id
    ).scalar() or 0

    # Total number of active customers
    today = datetime.today().date()
    active_customers = db.session.query(func.count(Customer.id)).select_from(Customer).join(
        CustomerSubscription, Customer.id == CustomerSubscription.customer_id
    ).filter(
        CustomerSubscription.subscription_start <= today,
        CustomerSubscription.subscription_end >= today,
        Customer.business_id == business_id
    ).scalar() or 0

    # Average revenue per customer
    avg_revenue = db.session.query(func.avg(CustomerSubscription.subscription_amount)).select_from(Customer).join(
        CustomerSubscription, Customer.id == CustomerSubscription.customer_id
    ).filter(
        Customer.business_id == business_id
    ).scalar() or 0

    # Total revenue
    total_revenue = db.session.query(func.sum(CustomerSubscription.subscription_amount)).select_from(Customer).join(
        CustomerSubscription, Customer.id == CustomerSubscription.customer_id
    ).filter(
        Customer.business_id == business_id
    ).scalar() or 0

    # Return the stats in a dictionary format
    return {
        'total_customers': total_customers,
        'active_customers': active_customers,
        'avg_revenue': avg_revenue,
        'total_revenue': total_revenue
    }

# Function to calculate CLTV
def calculate_cltv():
    # Get the logged-in business_id from the session
    business_id = session.get('business_id')

    if not business_id:
        return "No business logged in", 403

    customers = Customer.query.filter_by(business_id=business_id).all()  # Filter by business_id
    cltv_data = []

    for customer in customers:
        # Calculate CLTV by summing subscription amounts for each customer
        cltv = sum(sub.subscription_amount for sub in customer.customer_subscriptions)
        cltv_data.append({'name': customer.name, 'cltv': cltv})
    
    return cltv_data

# Filter by Date Range Route
@app.route('/filter', methods=['POST'])
def filter_customers():
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    
    # Get the logged-in business_id from the session
    business_id = session.get('business_id')

    if not business_id:
        return "No business logged in", 403

    # Query customers within the date range and business_id
    customers = Customer.query.join(Subscription).filter(
        Subscription.subscription_start >= start_date,
        Subscription.subscription_end <= end_date,
        Subscription.business_id == business_id  # Filter by business_id
    ).all()

    return render_template('index.html', customers=customers)

# Filter by Active Status Route
@app.route('/filter_status', methods=['POST'])
def filter_status():
    status_filter = request.form['status_filter']

    # Get the logged-in business_id from the session
    business_id = session.get('business_id')

    if not business_id:
        return "No business logged in", 403

    # Filter customers based on active or churned status
    if status_filter == 'active':
        # Active customers
        customers = Customer.query.join(Subscription).filter(
            Subscription.subscription_start <= datetime.today().date(),
            Subscription.subscription_end >= datetime.today().date(),
            Subscription.business_id == business_id  # Filter by business_id
        ).all()
    elif status_filter == 'churned':
        # Churned customers
        customers = Customer.query.join(Subscription).filter(
            Subscription.subscription_end < datetime.today().date(),
            Subscription.business_id == business_id  # Filter by business_id
        ).all()
    else:
        # All customers for the business
        customers = Customer.query.filter_by(business_id=business_id).all()

    return render_template('index.html', customers=customers)


if __name__ == '__main__':
    app.run(debug=True)

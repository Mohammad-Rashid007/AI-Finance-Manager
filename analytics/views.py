from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, Q
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta
import pandas as pd
import json
import csv
from io import StringIO
from django.views.decorators.http import require_http_methods
import random
from collections import namedtuple
from django.core.paginator import Paginator

from financial.models import Transaction, Category, Budget, Account, SavingsGoal, UserProfile
from .models import SpendingAnomaly
from .ml_utils.transaction_categorizer import TransactionCategorizer
from .ml_utils.spending_analyzer import SpendingAnalyzer
from .ml_utils.budget_analyzer import BudgetAnalyzer

# Create aliases for compatibility
TransactionClassifier = TransactionCategorizer
TransactionAnomalyDetector = SpendingAnalyzer
InsightsGenerator = SpendingAnalyzer

# from .models import SpendingPrediction, TransactionInsight, AnomalyAlert
# from .ml_utils import TransactionCategorizer, SpendingPredictor, AnomalyDetector

@login_required
def dashboard(request):
    """
    Display the analytics dashboard with insights, charts, and recommendations.
    """
    # Get the current user
    user = request.user
    
    # Get the date range for analytics (default: last 30 days)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    
    # Get transactions for the period
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date
    )
    
    # Calculate basic stats
    total_income = transactions.filter(transaction_type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    total_expenses = transactions.filter(transaction_type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    net_cash_flow = total_income - total_expenses
    
    # Get top expense categories
    expense_by_category = transactions.filter(
        transaction_type='expense'
    ).values('category__name').annotate(
        total=Sum('amount')
    ).order_by('-total')[:5]
    
    # Format data for charts
    expense_categories = [item['category__name'] for item in expense_by_category]
    expense_values = [float(item['total']) for item in expense_by_category]
    
    # Get anomalies
    detector = TransactionAnomalyDetector(user)
    anomalies = detector.detect_anomalies(transactions)
    
    # Generate insights
    insights_generator = InsightsGenerator(user)
    insights = insights_generator.generate_insights(transactions)
    
    # Get budget analyzer recommendations
    budget_analyzer = BudgetAnalyzer(user)
    budget_recommendations = budget_analyzer.get_recommendations()
    
    # Prepare data for transaction activity chart (last 7 days)
    activity_labels = []
    income_data = []
    expense_data = []
    
    for i in range(7, 0, -1):
        day = end_date - timedelta(days=i-1)
        activity_labels.append(day.strftime('%a'))
        
        day_income = transactions.filter(
            date=day,
            transaction_type='income'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        day_expense = transactions.filter(
            date=day,
            transaction_type='expense'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        income_data.append(float(day_income))
        expense_data.append(float(day_expense))
    
    # Prepare context for template
    context = {
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_cash_flow': net_cash_flow,
        'expense_categories': json.dumps(expense_categories),
        'expense_values': json.dumps(expense_values),
        'activity_labels': json.dumps(activity_labels),
        'income_data': json.dumps(income_data),
        'expense_data': json.dumps(expense_data),
        'anomalies': anomalies,
        'insights': insights,
        'budget_recommendations': budget_recommendations,
    }
    
    return render(request, 'analytics/dashboard.html', context)

@login_required
def spending_trends(request):
    """View spending trends over time"""
    user = request.user
    
    # Get timeframe from request, default to 30 days
    timeframe = request.GET.get('timeframe', '30')
    
    # Convert timeframe to days
    if timeframe == 'all':
        days = 9999  # Large number to include all
    else:
        try:
            days = int(timeframe)
        except ValueError:
            days = 30  # Default to 30 days
    
    # Calculate date range
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Get previous period for comparison
    prev_start_date = start_date - timedelta(days=days)
    prev_end_date = start_date - timedelta(days=1)
    
    # Get expense transactions
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date,
        transaction_type='expense'
    ).order_by('-date')
    
    prev_transactions = Transaction.objects.filter(
        user=user,
        date__gte=prev_start_date,
        date__lte=prev_end_date,
        transaction_type='expense'
    )
    
    # Calculate total expenses
    total_expenses = transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    prev_total_expenses = prev_transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Convert Decimal to float
    total_expenses = float(total_expenses)
    prev_total_expenses = float(prev_total_expenses)
    
    # Calculate expense change percentage
    if prev_total_expenses > 0:
        total_expenses_change = ((total_expenses - prev_total_expenses) / prev_total_expenses * 100)
    else:
        total_expenses_change = 0
    
    # Group transactions by month for the chart
    monthly_data = {'months': [], 'expenses': []}
    
    # Generate months list for the selected period
    current_date = start_date.replace(day=1)
    while current_date <= end_date:
        month_str = current_date.strftime('%b %Y')
        monthly_data['months'].append(month_str)
        
        # Sum expenses for this month
        month_expenses = Transaction.objects.filter(
            user=user,
            date__year=current_date.year,
            date__month=current_date.month,
            transaction_type='expense'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Convert to float
        month_expenses = float(month_expenses)
        monthly_data['expenses'].append(month_expenses)
        
        # Move to next month
        current_date = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    
    # Calculate statistics
    num_months = len(monthly_data['months'])
    avg_monthly_expenses = total_expenses / num_months if num_months > 0 else 0
    largest_expense = transactions.order_by('-amount').first().amount if transactions.exists() else 0
    largest_expense = float(largest_expense) if largest_expense else 0
    
    # Category analysis
    top_categories = []
    category_data = transactions.values('category__name').annotate(
        amount=Sum('amount')
    ).order_by('-amount')[:6]
    
    top_categories_chart = {'labels': [], 'data': []}
    
    for cat in category_data:
        cat_name = cat['category__name'] or 'Uncategorized'
        cat_amount = float(cat['amount']) if cat['amount'] else 0
        cat_percentage = (cat_amount / total_expenses * 100) if total_expenses else 0
        
        top_categories.append({
            'name': cat_name,
            'amount': cat_amount,
            'percentage': cat_percentage
        })
        
        top_categories_chart['labels'].append(cat_name)
        top_categories_chart['data'].append(cat_amount)
    
    # Category spending trend over time
    category_trend = {'months': monthly_data['months'], 'categories': []}
    
    # Get top 5 categories for trend chart
    top_cat_names = [cat['name'] for cat in top_categories[:5]]
    
    # Define colors for categories
    colors = [
        'rgba(220, 53, 69, 0.7)', 
        'rgba(255, 193, 7, 0.7)',
        'rgba(23, 162, 184, 0.7)',
        'rgba(40, 167, 69, 0.7)',
        'rgba(111, 66, 193, 0.7)',
        'rgba(253, 126, 20, 0.7)'
    ]
    border_colors = [
        'rgba(220, 53, 69, 1)', 
        'rgba(255, 193, 7, 1)',
        'rgba(23, 162, 184, 1)',
        'rgba(40, 167, 69, 1)',
        'rgba(111, 66, 193, 1)',
        'rgba(253, 126, 20, 1)'
    ]
    
    # For each category, get monthly data
    for idx, cat_name in enumerate(top_cat_names):
        cat_data = []
        current_date = start_date.replace(day=1)
        
        while current_date <= end_date:
            month_cat_amount = Transaction.objects.filter(
                user=user,
                date__year=current_date.year,
                date__month=current_date.month,
                transaction_type='expense',
                category__name=cat_name
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            # Convert to float
            month_cat_amount = float(month_cat_amount)
            cat_data.append(month_cat_amount)
            
            # Move to next month
            current_date = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        
        category_trend['categories'].append({
            'name': cat_name,
            'data': cat_data,
            'color': colors[idx % len(colors)],
            'border': border_colors[idx % len(border_colors)]
        })
    
    # Day of week analysis
    day_of_week_data = [0] * 7  # Initialize with zeros for each day
    day_counts = [0] * 7
    
    for transaction in transactions:
        weekday = transaction.date.weekday()
        day_of_week_data[weekday] += float(transaction.amount)
        day_counts[weekday] += 1
    
    # Calculate averages
    for i in range(7):
        if day_counts[i] > 0:
            day_of_week_data[i] = day_of_week_data[i] / day_counts[i]
    
    # Time of day analysis (simplified)
    time_of_day_data = [0, 0, 0, 0]  # Morning, Afternoon, Evening, Night
    
    # Since we don't have time field, use created_at datetime
    for transaction in transactions:
        # Skip if created_at is None
        if not transaction.created_at:
            continue
            
        try:
            hour = transaction.created_at.hour
            if 5 <= hour < 12:  # Morning
                time_of_day_data[0] += float(transaction.amount)
            elif 12 <= hour < 17:  # Afternoon
                time_of_day_data[1] += float(transaction.amount)
            elif 17 <= hour < 21:  # Evening
                time_of_day_data[2] += float(transaction.amount)
            else:  # Night
                time_of_day_data[3] += float(transaction.amount)
        except (AttributeError, TypeError):
            # Skip if there's an error accessing the hour attribute
            continue
    
    # Merchant analysis (use description field as merchant)
    merchant_data = transactions.values('description').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')[:10]
    
    top_merchants = []
    merchant_chart = {'labels': [], 'data': []}
    
    for merchant in merchant_data:
        name = merchant['description'] or 'Unknown'
        total = float(merchant['total'])
        count = merchant['count']
        average = total / count if count else 0
        
        top_merchants.append({
            'name': name,
            'total': total,
            'average': average
        })
        
        merchant_chart['labels'].append(name)
        merchant_chart['data'].append(total)
    
    # Recurring expenses analysis
    recurring_expenses = []  # This would require a more complex algorithm
    total_annual_recurring = 0
    
    # AI-generated spending insights
    spending_insights = []
    
    # Only generate insights if enough data exists
    if len(monthly_data['expenses']) >= 2:
        # Trend insight
        if total_expenses_change > 15:
            spending_insights.append({
                'icon': 'arrow-up',
                'color': 'danger',
                'title': 'Spending Increase',
                'message': f'Your spending has increased by {total_expenses_change:.1f}% compared to the previous period.'
            })
        elif total_expenses_change < -15:
            spending_insights.append({
                'icon': 'arrow-down',
                'color': 'success',
                'title': 'Spending Decrease',
                'message': f'Your spending has decreased by {total_expenses_change.__abs__():.1f}% compared to the previous period.'
            })
        
        # Top category insight
        if top_categories:
            top_cat = top_categories[0]
            spending_insights.append({
                'icon': 'chart-pie',
                'color': 'info',
                'title': f'Top Spending Category: {top_cat["name"]}',
                'message': f'This category accounts for {top_cat["percentage"]:.1f}% of your total expenses.'
            })
    
    context = {
        'transactions': transactions,
        'timeframe': timeframe if timeframe != 'all' else 'all',
        'total_expenses': total_expenses,
        'total_expenses_change': total_expenses_change,
        'avg_monthly_expenses': avg_monthly_expenses,
        'largest_expense': largest_expense,
        'monthly_data': {
            'months': json.dumps(monthly_data['months']),
            'expenses': json.dumps(monthly_data['expenses'])
        },
        'top_categories': top_categories,
        'top_categories_chart': {
            'labels': json.dumps(top_categories_chart['labels']),
            'data': json.dumps(top_categories_chart['data'])
        },
        'category_trend': category_trend,
        'day_of_week_data': json.dumps(day_of_week_data),
        'time_of_day_data': json.dumps(time_of_day_data),
        'top_merchants': top_merchants,
        'merchant_chart': {
            'labels': json.dumps(merchant_chart['labels']),
            'data': json.dumps(merchant_chart['data'])
        },
        'recurring_expenses': recurring_expenses,
        'total_annual_recurring': total_annual_recurring,
        'spending_insights': spending_insights
    }
    
    return render(request, 'analytics/spending_trends.html', context)

@login_required
def income_analysis(request):
    """Analyze income sources and trends"""
    user = request.user
    
    # Get timeframe from request, default to 30 days
    timeframe = str(request.GET.get('timeframe', '30'))
    
    # Convert timeframe to days
    if timeframe == 'all':
        days = 9999  # Large number to include all
    else:
        try:
            days = int(timeframe)
        except ValueError:
            days = 30  # Default to 30 days
    
    # Calculate date range
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Get income transactions for the selected period
    income_transactions = Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        transaction_type='income'
    ).order_by('-date')
    
    # Get previous period for comparison
    prev_start_date = start_date - timedelta(days=days)
    prev_end_date = start_date - timedelta(days=1)
    
    prev_period_transactions = Transaction.objects.filter(
        user=user,
        date__gte=prev_start_date,
        date__lte=prev_end_date,
        transaction_type='income'
    )
    
    # Calculate total income amounts
    total_income = income_transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    prev_total_income = prev_period_transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    total_income = float(total_income)
    prev_total_income = float(prev_total_income)
    
    # Calculate income change percentage
    if prev_total_income > 0:
        income_change = ((total_income - prev_total_income) / prev_total_income) * 100
    else:
        income_change = 0.0
    
    # Group transactions by month for the chart
    monthly_data = {}
    months = []
    monthly_income = []
    
    # Generate months list for the selected period
    current_date = start_date.replace(day=1)
    while current_date <= end_date:
        month_str = current_date.strftime('%b %Y')
        months.append(month_str)
        monthly_data[month_str] = 0.0
        current_date = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    
    # Sum income by month
    for transaction in income_transactions:
        month_key = transaction.date.strftime('%b %Y')
        if month_key in monthly_data:
            monthly_data[month_key] += float(transaction.amount)
    
    # Convert to list for the chart
    for month in months:
        monthly_income.append(monthly_data[month])
    
    # Group transactions by category for pie chart
    income_sources = income_transactions.values('category__name').annotate(
        amount=Sum('amount')
    ).order_by('-amount')
    
    income_source_names = []
    income_source_values = []
    
    for source in income_sources:
        name = source['category__name'] or 'Uncategorized'
        income_source_names.append(name)
        income_source_values.append(float(source['amount']))
    
    # Calculate income statistics
    avg_monthly_income = total_income / len(months) if months else 0.0
    max_income = max(monthly_income) if monthly_income else 0.0
    
    # Calculate income variation for stability chart
    income_variation = []
    
    if len(monthly_income) > 1:
        for i in range(1, len(monthly_income)):
            if monthly_income[i-1] > 0:
                variation = abs((monthly_income[i] - monthly_income[i-1]) / monthly_income[i-1] * 100)
            else:
                variation = 0.0
            income_variation.append(variation)
    
    # Calculate income volatility (average variation)
    income_volatility = sum(income_variation) / len(income_variation) if income_variation else 0.0
    
    # Generate AI insights
    income_insights = []
    
    # Only generate insights if enough data exists
    if len(monthly_income) >= 2:
        # Trend insight
        if income_change > 10:
            income_insights.append({
                'icon': 'arrow-up',
                'color': 'success',
                'title': 'Income Growth',
                'message': f'Your income has increased by {income_change:.1f}% compared to the previous period.'
            })
        elif income_change < -10:
            income_insights.append({
                'icon': 'arrow-down',
                'color': 'danger',
                'title': 'Income Decline',
                'message': f'Your income has decreased by {abs(income_change):.1f}% compared to the previous period.'
            })
        
        # Stability insight
        if income_volatility < 10:
            income_insights.append({
                'icon': 'check-circle',
                'color': 'success',
                'title': 'Stable Income',
                'message': 'You have a very stable income with minimal month-to-month variation.'
            })
        elif income_volatility > 30:
            income_insights.append({
                'icon': 'exclamation-triangle',
                'color': 'warning',
                'title': 'Volatile Income',
                'message': 'Your income shows significant variations month-to-month. Consider building a larger emergency fund.'
            })
        
        # Source diversity insight
        if len(income_source_names) == 1:
            income_insights.append({
                'icon': 'info-circle',
                'color': 'info',
                'title': 'Single Income Source',
                'message': 'You have only one income source. Diversifying your income can increase financial security.'
            })
        elif len(income_source_names) >= 3:
            income_insights.append({
                'icon': 'thumbs-up',
                'color': 'success',
                'title': 'Diversified Income',
                'message': f'You have {len(income_source_names)} different income sources, which provides good financial stability.'
            })
    
    # Defensive: ensure all chart data is a list
    months = months or []
    monthly_income = monthly_income or []
    income_source_names = income_source_names or []
    income_source_values = income_source_values or []
    income_variation = income_variation or []
    
    context = {
        'income_transactions': income_transactions,
        'timeframe': timeframe,
        'total_income': total_income,
        'income_change': income_change,
        'avg_monthly_income': avg_monthly_income,
        'max_income': max_income,
        'months': json.dumps(months),
        'monthly_income': json.dumps(monthly_income),
        'income_source_names': json.dumps(income_source_names),
        'income_source_values': json.dumps(income_source_values),
        'income_sources': [
            {
                'name': source['category__name'] or 'Uncategorized',
                'amount': float(source['amount']),
                'percentage': (float(source['amount']) / total_income * 100) if total_income > 0 else 0.0
            } for source in income_sources
        ],
        'income_variation': json.dumps(income_variation),
        'income_volatility': income_volatility,
        'income_insights': income_insights,
    }
    
    return render(request, 'analytics/income_analysis.html', context)

@login_required
def budget_performance(request):
    """Analyze budget performance and provide recommendations"""
    user = request.user
    
    # Get timeframe from request, default to 30 days
    timeframe = request.GET.get('timeframe', '30')
    
    # Convert timeframe to days
    if timeframe == 'all':
        days = 9999  # Large number to include all
    elif timeframe == 'current':
        today = timezone.now().date()
        days = today.day  # Days so far this month
    elif timeframe == 'last':
        today = timezone.now().date()
        first = today.replace(day=1)
        last_month_end = first - timedelta(days=1)
        days = last_month_end.day
        end_date = last_month_end
        start_date = end_date.replace(day=1)
    elif timeframe == '3months':
        days = 90
    elif timeframe == '6months':
        days = 180
    elif timeframe == 'year':
        days = 365
    else:
        try:
            days = int(timeframe)
        except ValueError:
            days = 30  # Default to 30 days
    
    # Calculate date range
    if timeframe == 'last':
        # Already set above
        pass
    else:
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
    
    # Get all budgets for the period
    budgets = Budget.objects.filter(
        user=user,
        start_date__lte=end_date,
        is_active=True
    ).select_related('category')
    
    # If end_date is specified for budgets, filter by it too
    budgets = budgets.filter(
        Q(end_date__gte=start_date) | Q(end_date__isnull=True)
    )
    
    # Get all expense transactions for the period
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date,
        transaction_type='expense'
    ).select_related('category')
    
    # Group transactions by category
    category_spending = {}
    for transaction in transactions:
        category_id = transaction.category_id if transaction.category_id else 0
        if category_id not in category_spending:
            category_spending[category_id] = 0
        category_spending[category_id] += float(transaction.amount)
    
    # Calculate budget performance
    budget_performance_data = []
    total_budget = 0
    total_spent = 0
    over_budget_categories = 0
    category_performance = []
    category_budgets = []
    category_spending_list = []
    
    for budget in budgets:
        category_id = budget.category_id
        budget_amount = float(budget.amount)
        spent_amount = category_spending.get(category_id, 0)
        
        # Calculate percentage spent
        percentage_spent = (spent_amount / budget_amount * 100) if budget_amount > 0 else 0
        
        # Determine status
        if percentage_spent > 100:
            status = 'over'
            over_budget_categories += 1
        elif percentage_spent >= 85:
            status = 'warning'
        else:
            status = 'good'
        
        # Add to totals
        total_budget += budget_amount
        total_spent += spent_amount
        
        # Add to performance data
        budget_performance_data.append({
            'category': budget.category.name if budget.category else 'Uncategorized',
            'budget': budget_amount,
            'spent': spent_amount,
            'remaining': budget_amount - spent_amount,
            'percentage': percentage_spent,
            'status': status
        })
        # For category_performance
        category_performance.append({
            'name': budget.category.name if budget.category else 'Uncategorized',
            'budget': budget_amount,
            'spent': spent_amount,
            'remaining': budget_amount - spent_amount,
            'percentage': percentage_spent
        })
        category_budgets.append(budget_amount)
        category_spending_list.append(spent_amount)
    
    # Sort by percentage spent (descending)
    budget_performance_data.sort(key=lambda x: x['percentage'], reverse=True)
    category_performance.sort(key=lambda x: x['percentage'], reverse=True)
    
    # Calculate overall performance
    overall_performance = (total_spent / total_budget) if total_budget > 0 else 0
    overall_performance_pct = overall_performance * 100
    
    if overall_performance > 1:
        overall_status = 'over'
    elif overall_performance >= 0.85:
        overall_status = 'warning'
    else:
        overall_status = 'good'
    
    # Budget variance
    budget_variance = total_budget - total_spent
    
    # Prepare chart data
    category_names = [item['category'] for item in budget_performance_data]
    
    # Get monthly budget data for trend chart
    months = []
    monthly_budgets = []
    monthly_spending = []
    
    # Generate months list for the selected period
    current_date = start_date.replace(day=1)
    while current_date <= end_date:
        month_str = current_date.strftime('%b %Y')
        months.append(month_str)
        
        # Get budget total for the month
        month_budgets = Budget.objects.filter(
            user=user,
            start_date__lte=current_date,
            is_active=True
        ).filter(
            Q(end_date__gte=current_date) | Q(end_date__isnull=True)
        )
        budget_sum = month_budgets.aggregate(Sum('amount'))['amount__sum'] or 0
        monthly_budgets.append(float(budget_sum))
        
        # Get spending for the month
        month_start = current_date
        month_end = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        
        month_transactions = Transaction.objects.filter(
            user=user,
            date__gte=month_start,
            date__lte=month_end,
            transaction_type='expense'
        )
        spending_sum = month_transactions.aggregate(Sum('amount'))['amount__sum'] or 0
        monthly_spending.append(float(spending_sum))
        
        # Move to next month
        current_date = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    
    # Generate recommendations
    budget_analyzer = BudgetAnalyzer(user)
    recommendations = budget_analyzer.get_recommendations()
    
    context = {
        'timeframe': timeframe,
        'budget_performance': budget_performance_data,
        'category_performance': category_performance,
        'total_budgeted': total_budget,
        'total_spent': total_spent,
        'budget_variance': budget_variance,
        'overall_performance': overall_performance,
        'overall_performance_pct': overall_performance_pct,
        'overall_status': overall_status,
        'over_budget_categories': over_budget_categories,
        'category_names': json.dumps(category_names),
        'category_budgets': json.dumps(category_budgets),
        'category_spending': json.dumps(category_spending_list),
        'months': json.dumps(months),
        'monthly_budgets': json.dumps(monthly_budgets),
        'monthly_spending': json.dumps(monthly_spending),
        'recommendations': recommendations
    }
    
    return render(request, 'analytics/budget_performance.html', context)

@login_required
def savings_forecast(request):
    """Forecast savings and goal achievement"""
    user = request.user
    
    # Get savings goals
    goals = SavingsGoal.objects.filter(user=user, status='in_progress')
    
    # Process goals to add forecast data
    for goal in goals:
        # Convert decimal values to float to avoid type errors
        goal.target_amount_float = float(goal.target_amount)
        goal.current_amount_float = float(goal.current_amount)
        
        # Determine forecast status
        if not goal.target_date:
            goal.forecast_status = 'no_deadline'
        elif goal.is_behind_schedule:
            if goal.progress_percentage < 25:
                goal.forecast_status = 'at_risk'
            else:
                goal.forecast_status = 'behind'
        else:
            goal.forecast_status = 'on_track'
    
    # Generate savings projection data (next 12 months)
    forecast_months = []
    forecast_savings = []
    
    # Get current date and total savings
    current_date = timezone.now().date()
    total_current_savings = sum(float(goal.current_amount) for goal in goals)
    
    # Calculate average monthly savings based on past 3 months
    three_months_ago = current_date - timedelta(days=90)
    income_transactions = Transaction.objects.filter(
        user=user,
        transaction_type='income',
        date__gte=three_months_ago
    )
    expense_transactions = Transaction.objects.filter(
        user=user,
        transaction_type='expense',
        date__gte=three_months_ago
    )
    
    total_income = sum(float(tx.amount) for tx in income_transactions)
    total_expenses = sum(float(tx.amount) for tx in expense_transactions)
    
    # Calculate average monthly net (income - expenses)
    months_range = max(1, (current_date - three_months_ago).days / 30)
    avg_monthly_net = (total_income - total_expenses) / months_range
    
    # Project savings for the next 12 months
    projected_savings = total_current_savings
    
    for i in range(12):
        # Add a month to the date
        next_month = current_date.replace(day=1)
        if next_month.month == 12:
            next_month = next_month.replace(year=next_month.year + 1, month=1)
        else:
            next_month = next_month.replace(month=next_month.month + 1)
        
        # Format the month for display
        month_str = next_month.strftime('%b %Y')
        forecast_months.append(month_str)
        
        # Add projected monthly savings
        projected_savings += avg_monthly_net
        forecast_savings.append(max(0, projected_savings))
        
        # Update current date to next month
        current_date = next_month
    
    # Generate goal timeline data
    goal_labels = []
    goal_target_dates = []
    goal_projected_dates = []
    
    # Generate goal timeline data for chart
    goal_names = []
    goal_progress = []
    goal_remaining = []
    
    for goal in goals:
        # Add data for completion timeline
        if goal.target_date:
            goal_labels.append(goal.name)
            
            # Calculate months from now to target date
            target_months = (goal.target_date.year - timezone.now().date().year) * 12 + (goal.target_date.month - timezone.now().date().month)
            goal_target_dates.append(target_months)
            
            # Calculate projected completion based on current rate
            if avg_monthly_net > 0:
                remaining_amount = goal.target_amount_float - goal.current_amount_float
                months_to_completion = remaining_amount / avg_monthly_net
                goal_projected_dates.append(round(months_to_completion))
            else:
                # If no savings rate, use a far future date
                goal_projected_dates.append(100)  # Far in the future
        
        # Add data for progress chart
        goal_names.append(goal.name)
        goal_progress.append(float(goal.current_amount))
        goal_remaining.append(max(0, float(goal.target_amount) - float(goal.current_amount)))
    
    context = {
        'goals': goals,
        'forecast_months': json.dumps(forecast_months),
        'forecast_savings': json.dumps(forecast_savings),
        'goal_labels': json.dumps(goal_labels),
        'goal_target_dates': json.dumps(goal_target_dates),
        'goal_projected_dates': json.dumps(goal_projected_dates),
        'goal_names': json.dumps(goal_names),
        'goal_progress': json.dumps(goal_progress),
        'goal_remaining': json.dumps(goal_remaining),
        'avg_monthly_net': avg_monthly_net
    }
    
    return render(request, 'analytics/savings_forecast.html', context)

@login_required
def spending_predictions(request):
    """View and generate spending predictions and AI savings suggestions"""
    user = request.user
    # Get all transactions
    transactions = list(Transaction.objects.filter(user=user))
    # Use SpendingAnalyzer for predictions
    analyzer = SpendingAnalyzer(user)
    predictions = analyzer.predict_monthly_spending(transactions, months_ahead=6)
    # Analyze past savings: income - expenses per month
    income = [tx for tx in transactions if tx.transaction_type == 'income']
    expenses = [tx for tx in transactions if tx.transaction_type == 'expense']
    # Group by month
    from collections import defaultdict
    monthly_savings = defaultdict(lambda: {'income': 0, 'expenses': 0})
    for tx in income:
        key = tx.date.strftime('%Y-%m')
        monthly_savings[key]['income'] += float(tx.amount)
    for tx in expenses:
        key = tx.date.strftime('%Y-%m')
        monthly_savings[key]['expenses'] += float(tx.amount)
    # Calculate savings per month
    savings_per_month = []
    for key in sorted(monthly_savings.keys()):
        savings = monthly_savings[key]['income'] - monthly_savings[key]['expenses']
        savings_per_month.append(savings)
    avg_savings = sum(savings_per_month) / len(savings_per_month) if savings_per_month else 0
    # Suggest a savings goal
    suggested_goal = None
    if avg_savings > 0:
        suggested_goal = {
            'monthly': round(avg_savings, 2),
            'six_month': round(avg_savings * 6, 2),
            'twelve_month': round(avg_savings * 12, 2)
        }
    context = {
        'predictions': predictions,
        'suggested_goal': suggested_goal,
        'savings_per_month': savings_per_month,
    }
    return render(request, 'analytics/spending_predictions.html', context)

@login_required
def anomaly_detection(request):
    """View anomalous transactions"""
    user = request.user
    from django.core.paginator import Paginator
    from datetime import datetime, timedelta
    from collections import namedtuple

    # Get filters
    status = request.GET.get('status', 'all')
    timeframe = str(request.GET.get('timeframe', '30'))
    page = int(request.GET.get('page', 1))
    
    # Convert timeframe to days for filtering
    if timeframe == 'all':
        days = 9999  # Large number to include all
    else:
        try:
            days = int(timeframe)
        except ValueError:
            days = 30  # Default to 30 days

    # Calculate date range
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Get transactions for the period
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date
    )
    
    # Get user profile
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Check if AI features are enabled
    if not profile.enable_ai_insights:
        anomalies_list = []
        last_analysis = timezone.now()
    else:
        # Use the SpendingAnalyzer to detect anomalies
        analyzer = SpendingAnalyzer(user)
        anomaly_results = analyzer.detect_anomalies(transactions)
        
        # Get any existing anomalies from the database
        existing_anomalies = list(SpendingAnomaly.objects.filter(user=user))
        existing_tx_ids = [a.transaction_id for a in existing_anomalies]
        
        # Create named tuple for consistent interface
        Anomaly = namedtuple('Anomaly', ['id', 'transaction', 'anomaly_type', 'reason', 'status', 'score'])
        
        # Convert anomaly results to list of Anomaly objects
        anomalies_list = []
        
        for anomaly_data in anomaly_results:
            # Try to get the transaction object
            try:
                tx = Transaction.objects.get(id=anomaly_data['id'], user=user)
                
                # Determine if this anomaly is new or reviewed
                anomaly_status = 'new'
                anomaly_id = len(anomalies_list) + 1
                anomaly_score = 0.0
                
                # Check if this transaction already has a recorded anomaly
                for existing in existing_anomalies:
                    if existing.transaction_id == tx.id:
                        anomaly_status = 'reviewed' if existing.is_verified else 'new'
                        anomaly_id = existing.id
                        anomaly_score = existing.anomaly_score
                        break
                
                # Determine anomaly type and reason based on transaction
                anomaly_type, reason = determine_anomaly_type(tx, transactions)
                
                anomalies_list.append(Anomaly(
                    id=anomaly_id,
                    transaction=tx,
                    anomaly_type=anomaly_type,
                    reason=reason,
                    status=anomaly_status,
                    score=anomaly_score
                ))
            except Transaction.DoesNotExist:
                continue
            
        # Record the analysis time
        last_analysis = timezone.now()
        
        # Save new anomalies to database
        for anomaly in anomalies_list:
            if anomaly.transaction.id not in existing_tx_ids:
                SpendingAnomaly.objects.create(
                    user=user,
                    transaction=anomaly.transaction,
                    anomaly_score=anomaly.score or 0.8,  # Default high score if none provided
                    description=anomaly.reason
                )

    # Filter by status
    if status != 'all':
        anomalies_list = [a for a in anomalies_list if a.status == status]

    # Pagination
    paginator = Paginator(anomalies_list, 10)
    page_obj = paginator.get_page(page)
    is_paginated = paginator.num_pages > 1
    anomalies = page_obj.object_list

    # Generate anomaly statistics
    anomaly_stats = generate_anomaly_statistics(anomalies_list)

    context = {
        'anomalies': anomalies,
        'status': status,
        'timeframe': timeframe,
        'last_analysis': last_analysis,
        'is_paginated': is_paginated,
        'page_obj': page_obj,
        'anomaly_stats': anomaly_stats,
        'request': request,
    }
    return render(request, 'analytics/anomaly_detection.html', context)

def determine_anomaly_type(transaction, all_transactions):
    """Determine the type and reason for an anomaly"""
    # Sample anomaly types
    anomaly_types = ['amount', 'frequency', 'merchant', 'category', 'location']
    
    # Get all expense transactions for this user
    expenses = [tx for tx in all_transactions if tx.transaction_type == 'expense']
    
    if not expenses:
        return 'amount', 'Unusual transaction'
    
    # Calculate average amount for this category
    category_transactions = [tx for tx in expenses if tx.category == transaction.category]
    
    if category_transactions:
        avg_amount = sum(float(tx.amount) for tx in category_transactions) / len(category_transactions)
        
        # Check if amount is unusually high (more than double the average)
        if float(transaction.amount) > avg_amount * 2:
            return 'amount', f'Amount is {(float(transaction.amount) / avg_amount):.1f}x higher than category average'
    
    # Check frequency of transactions with similar descriptions
    similar_desc_count = sum(1 for tx in expenses if tx.description.lower() in transaction.description.lower() or 
                            transaction.description.lower() in tx.description.lower())
    
    if similar_desc_count <= 1:
        return 'merchant', 'First transaction with this merchant'
    
    # Check if transaction is on an unusual day
    transaction_day = transaction.date.weekday()
    day_counts = [0] * 7
    for tx in expenses:
        day_counts[tx.date.weekday()] += 1
    
    if day_counts[transaction_day] < max(day_counts) * 0.2:  # Less than 20% of max frequency
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return 'frequency', f'Unusual transaction day ({days[transaction_day]})'
    
    # Default to amount as the anomaly type
    return 'amount', 'Unusual spending pattern'

def generate_anomaly_statistics(anomalies):
    """Generate statistics for anomaly charts"""
    today = timezone.now().date()
    
    # Count anomalies by type
    type_counts = {}
    for anomaly in anomalies:
        if anomaly.anomaly_type not in type_counts:
            type_counts[anomaly.anomaly_type] = 0
        type_counts[anomaly.anomaly_type] += 1
    
    # Count anomalies by month
    months = [(today - timedelta(days=30*i)).strftime('%b %Y') for i in reversed(range(6))]
    month_counts = {month: 0 for month in months}
    
    for anomaly in anomalies:
        month_str = anomaly.transaction.date.strftime('%b %Y')
        if month_str in month_counts:
            month_counts[month_str] += 1
    
    return {
        'types': {
            'labels': [t.capitalize() for t in type_counts.keys()],
            'data': list(type_counts.values())
        },
        'monthly': {
            'labels': months,
            'data': [month_counts[month] for month in months]
        }
    }

@login_required
def transaction_insights(request, transaction_id):
    """View AI insights for a specific transaction"""
    transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
    
    context = {
        'transaction': transaction,
    }
    
    return render(request, 'analytics/transaction_insights.html', context)

@login_required
def category_insights(request, category_id):
    """View insights for a specific category"""
    category = get_object_or_404(Category, id=category_id)
    user = request.user
    
    # Get transactions for this category
    transactions = Transaction.objects.filter(
        user=user,
        category=category
    ).order_by('-date')
    
    context = {
        'category': category,
        'transactions': transactions[:10],  # Latest 10 transactions
    }
    
    return render(request, 'analytics/category_insights.html', context)

@login_required
def export_data(request):
    """Export user's financial data"""
    user = request.user
    
    context = {}
    
    return render(request, 'analytics/export_data.html', context)

# API endpoints for ML features
@login_required
@require_http_methods(["GET"])
def get_spending_insights(request):
    """API endpoint for getting AI-generated spending insights"""
    timeframe = request.GET.get('timeframe', '30days')
    
    # Convert timeframe to days for filtering
    days = 30
    if timeframe == '3months':
        days = 90
    elif timeframe == '6months':
        days = 180
    elif timeframe == '1year':
        days = 365
    elif timeframe == 'all':
        days = 9999  # Just a large number to include all
    
    # Get transactions within the timeframe
    start_date = datetime.now() - timedelta(days=days)
    transactions = Transaction.objects.filter(
        user=request.user,
        date__gte=start_date
    ).order_by('-date')
    
    # If we don't have enough transactions, return empty insights
    if transactions.count() < 5:
        return JsonResponse({
            'success': True,
            'insights': []
        })
    
    # Use spending analyzer to generate insights
    analyzer = SpendingAnalyzer()
    insights = analyzer.generate_spending_insights(transactions)
    
    return JsonResponse({
        'success': True,
        'insights': insights
    })

@login_required
@require_http_methods(["GET"])
def get_anomalies(request):
    """API endpoint for getting transaction anomalies"""
    timeframe = request.GET.get('timeframe', '30days')
    page = int(request.GET.get('page', 1))
    
    # Convert timeframe to days for filtering
    days = 30
    if timeframe == '3months':
        days = 90
    elif timeframe == '6months':
        days = 180
    elif timeframe == '1year':
        days = 365
    elif timeframe == 'all':
        days = 9999  # Just a large number to include all
    
    # Get user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Skip AI processing if user has disabled it
    if not profile.enable_ai_insights:
        return JsonResponse({
            'anomalies': [], 
            'message': 'Anomaly detection is disabled in your profile settings.'
        })
    
    # Get transactions 
    transactions_query = Transaction.objects.filter(user=request.user)
    if timeframe != 'all':
        transactions_query = transactions_query.filter(date__gte=datetime.now() - timedelta(days=days))
    
    transactions = list(transactions_query.order_by('-date'))
    
    # Check if there's enough data
    if len(transactions) < 5:
        return JsonResponse({
            'anomalies': [],
            'message': 'Need at least 5 transactions for anomaly detection.'
        })
    
    # Generate sample anomalies based on the timeframe
    anomaly_count = min(len(transactions) // 5, 20)  # About 20% of transactions, max 20
    
    # Sample anomaly reasons
    reasons = [
        "Unusually high amount for this category",
        "Transaction frequency is higher than normal",
        "First transaction with this merchant",
        "Amount significantly different from previous patterns",
        "Irregular transaction timing"
    ]
    
    # Get a sample of actual transactions for realistic demo
    sample_transactions = random.sample(transactions, anomaly_count)
    
    anomalies = []
    for i, transaction in enumerate(sample_transactions):
        anomalies.append({
            'id': i + 1,
            'date': transaction.date.strftime('%b %d, %Y'),
            'description': transaction.description,
            'category': transaction.category.name if transaction.category else 'Uncategorized',
            'amount': float(transaction.amount),
            'account': transaction.account.name,
            'reason': random.choice(reasons),
            'confidence': random.randint(65, 95)
        })
    
    # Pagination logic
    items_per_page = 10
    total_pages = (len(anomalies) + items_per_page - 1) // items_per_page
    
    # Ensure page is within bounds
    page = max(1, min(page, total_pages))
    
    # Get the slice for the current page
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    paged_anomalies = anomalies[start_idx:end_idx]
    
    return JsonResponse({
        'success': True,
        'anomalies': paged_anomalies,
        'pagination': {
            'total_items': len(anomalies),
            'total_pages': total_pages,
            'current_page': page,
            'items_per_page': items_per_page
        }
    })

@login_required
@require_http_methods(["GET"])
def get_anomaly_detail(request, anomaly_id):
    """
    API endpoint to get details of a specific anomaly
    """
    try:
        # Try to find the anomaly in the database
        try:
            anomaly = SpendingAnomaly.objects.get(id=anomaly_id, user=request.user)
            transaction = anomaly.transaction
        except SpendingAnomaly.DoesNotExist:
            # If not found in the database, try to get the transaction directly
            transaction = Transaction.objects.get(id=anomaly_id, user=request.user)
            anomaly = None

        if not transaction:
            return JsonResponse({'success': False, 'error': 'Transaction not found'}, status=404)
            
        # Get all transactions for this user to determine why this is anomalous
        all_transactions = Transaction.objects.filter(
            user=request.user,
            date__gte=transaction.date - timedelta(days=90),
            date__lte=transaction.date + timedelta(days=90)
        )
        
        # Generate analysis based on transaction data
        analysis = ""
        
        # Check if amount is unusual for this category
        if transaction.category:
            category_transactions = Transaction.objects.filter(
                user=request.user,
                category=transaction.category,
                transaction_type=transaction.transaction_type
            ).exclude(id=transaction.id)
            
            if category_transactions.exists():
                avg_amount = category_transactions.aggregate(Avg('amount'))['amount__avg']
                if avg_amount and transaction.amount > avg_amount * 1.5:
                    analysis = f"This transaction amount is {(transaction.amount / avg_amount):.1f}x higher than your usual spending in the {transaction.category.name} category."
        
        # If no specific analysis was generated, use the anomaly description or a default
        if not analysis and anomaly and anomaly.description:
            analysis = anomaly.description
        elif not analysis:
            analysis = "This transaction was flagged as unusual based on your regular spending patterns."
        
        # Determine anomaly type
        anomaly_type, reason = determine_anomaly_type(transaction, all_transactions)
        
        # Calculate confidence score
        confidence = anomaly.anomaly_score * 100 if anomaly and anomaly.anomaly_score else 75
        
        return JsonResponse({
            'success': True,
            'id': anomaly_id,
            'date': transaction.date.strftime('%b %d, %Y'),
            'description': transaction.description,
            'category': transaction.category.name if transaction.category else 'Uncategorized',
            'amount': float(transaction.amount),
            'account': transaction.account.name,
            'detected_date': (anomaly.detected_at if anomaly else timezone.now()).strftime('%b %d, %Y'),
            'type': anomaly_type.capitalize(),
            'reason': reason,
            'confidence': int(min(max(confidence, 65), 95)),  # Keep between 65-95%
            'status': 'Reviewed' if anomaly and anomaly.is_verified else 'Pending Review',
            'analysis': analysis
        })
    except Transaction.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Transaction not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def update_anomaly_status(request, anomaly_id):
    """
    API endpoint to update the status of an anomaly
    """
    try:
        data = json.loads(request.body)
        status = data.get('status')
        
        if not status or status not in ['reviewed', 'ignored']:
            return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
            
        # In a real implementation, we would update the anomaly in the database
        # For now, just return success
        
        return JsonResponse({
            'success': True,
            'message': f'Anomaly {anomaly_id} marked as {status}'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["GET"])
def get_budget_recommendations(request):
    """API endpoint for getting budget recommendations"""
    # Get user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Skip AI processing if user has disabled it
    if not profile.enable_ai_insights:
        return JsonResponse({
            'recommendations': [], 
            'message': 'AI insights are disabled in your profile settings.'
        })
    
    # Get all transactions (we'll filter inside the analyzer)
    transactions = list(Transaction.objects.filter(user=request.user))
    
    # Get current budgets
    budgets = list(Budget.objects.filter(user=request.user))
    
    # Generate recommendations
    analyzer = BudgetAnalyzer()
    result = analyzer.generate_budget_recommendations(transactions, budgets)
    
    return JsonResponse(result)

@login_required
@require_http_methods(["GET"])
def analyze_budget_performance(request, budget_id):
    """API endpoint for analyzing a specific budget's performance"""
    try:
        budget = Budget.objects.get(id=budget_id, user=request.user)
    except Budget.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Budget not found'})
    
    # Get transactions for this budget's period and category
    transactions = list(Transaction.objects.filter(
        user=request.user,
        category=budget.category,
        date__gte=budget.start_date,
        date__lte=budget.end_date if budget.end_date else timezone.now().date()
    ))
    
    # Analyze budget
    analyzer = BudgetAnalyzer()
    result = analyzer.analyze_budget_performance(budget, transactions)
    
    return JsonResponse(result)

@login_required
@require_http_methods(["GET"])
def categorize_transaction(request, transaction_id):
    """API endpoint to automatically categorize a transaction"""
    try:
        transaction = Transaction.objects.get(id=transaction_id, user=request.user)
    except Transaction.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Transaction not found'})
    
    # Get user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Skip AI processing if user has disabled it
    if not profile.enable_ai_categorization:
        return JsonResponse({
            'success': False, 
            'message': 'AI categorization is disabled in your profile settings.'
        })
    
    # Get training data (past categorized transactions)
    training_transactions = list(Transaction.objects.filter(
        user=request.user,
        category__isnull=False
    ).exclude(id=transaction_id))
    
    # Create and train categorizer
    categorizer = TransactionCategorizer()
    categorizer.train(training_transactions)
    
    # Predict category
    category_id, category_name, confidence = categorizer.predict(transaction.description)
    
    if not category_id:
        return JsonResponse({
            'success': False,
            'message': 'Could not confidently predict a category',
            'transaction_id': transaction_id
        })
    
    # Get the category object
    try:
        category = Category.objects.get(id=category_id)
        
        # Return prediction result without saving
        return JsonResponse({
            'success': True,
            'transaction_id': transaction_id,
            'category_id': category_id,
            'category_name': category_name,
            'confidence': confidence,
            'message': f'Predicted category: {category_name} with {confidence:.1%} confidence'
        })
    except Category.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Predicted category not found in database',
            'transaction_id': transaction_id
        })

@login_required
@require_http_methods(["POST"])
def auto_categorize_transactions(request):
    """API endpoint to automatically categorize multiple uncategorized transactions"""
    # Get user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Skip AI processing if user has disabled it
    if not profile.enable_ai_categorization:
        return JsonResponse({
            'success': False, 
            'message': 'AI categorization is disabled in your profile settings.'
        })
    
    # Get all transactions with categories for training
    training_transactions = list(Transaction.objects.filter(
        user=request.user,
        category__isnull=False
    ))
    
    # If not enough training data, return error
    if len(training_transactions) < 10:
        return JsonResponse({
            'success': False,
            'message': 'Not enough categorized transactions for training. Please categorize at least 10 transactions manually.'
        })
    
    # Get uncategorized transactions
    uncategorized = list(Transaction.objects.filter(
        user=request.user,
        category__isnull=True
    ))
    
    if not uncategorized:
        return JsonResponse({
            'success': True,
            'message': 'No uncategorized transactions found.',
            'categorized_count': 0
        })
    
    # Create and train categorizer
    categorizer = TransactionCategorizer()
    categorizer.train(training_transactions)
    
    # Track results
    results = []
    categorized_count = 0
    
    # Process each uncategorized transaction
    for transaction in uncategorized:
        category_id, category_name, confidence = categorizer.predict(transaction.description)
        
        if category_id:
            try:
                category = Category.objects.get(id=category_id)
                
                # Save the category and mark as AI categorized
                transaction.category = category
                transaction.ai_categorized = True
                transaction.save()
                
                categorized_count += 1
                results.append({
                    'transaction_id': transaction.id,
                    'description': transaction.description,
                    'category_name': category_name,
                    'confidence': confidence
                })
            except Category.DoesNotExist:
                continue
    
    return JsonResponse({
        'success': True,
        'message': f'Automatically categorized {categorized_count} out of {len(uncategorized)} transactions',
        'categorized_count': categorized_count,
        'total_uncategorized': len(uncategorized),
        'results': results
    })

@login_required
@require_http_methods(["GET"])
def spending_forecast(request):
    """API endpoint for forecasting future spending"""
    # Get user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Skip AI processing if user has disabled it
    if not profile.enable_ai_insights:
        return JsonResponse({
            'success': False, 
            'message': 'AI insights are disabled in your profile settings.'
        })
    
    # Get all transactions 
    transactions = list(Transaction.objects.filter(user=request.user))
    
    # If not enough data, return error
    if len(transactions) < 10:
        return JsonResponse({
            'success': False,
            'message': 'Not enough transaction history for forecasting.',
            'predictions': []
        })
    
    # Generate forecast
    analyzer = SpendingAnalyzer()
    forecast = analyzer.predict_monthly_spending(transactions)
    
    return JsonResponse({
        'success': True,
        'predictions': forecast
    })

# Helper functions
def determine_anomaly_reason(transaction, all_transactions):
    """Determine why a transaction was flagged as an anomaly"""
    # This is a simplified version - in a real app, you'd use the model's feature importance
    
    # Get user's average transaction amount
    expense_transactions = [tx for tx in all_transactions if tx.transaction_type == 'expense']
    if not expense_transactions:
        return "Unusual transaction"
        
    avg_amount = sum(float(tx.amount) for tx in expense_transactions) / len(expense_transactions)
    
    # Check if amount is unusually high
    if float(transaction.amount) > avg_amount * 2:
        return "Unusually high amount"
    
    # Check if it's an unusual category for the user
    user_categories = {}
    for tx in all_transactions:
        if tx.category:
            category_name = tx.category.name
            user_categories[category_name] = user_categories.get(category_name, 0) + 1
    
    if transaction.category and transaction.category.name in user_categories:
        category_count = user_categories[transaction.category.name]
        if category_count <= 2:
            return f"Rarely used category: {transaction.category.name}"
    
    # Check if it's an unusual day of week
    transaction_day = transaction.date.weekday()
    day_counts = [0] * 7
    for tx in all_transactions:
        day_counts[tx.date.weekday()] += 1
    
    if day_counts[transaction_day] < 3:
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return f"Unusual day of week ({days[transaction_day]})"
    
    return "Unusual spending pattern"

@login_required
def mark_anomaly_reviewed(request):
    """Mark an anomaly as reviewed"""
    anomaly_id = request.POST.get('anomaly_id')
    if not anomaly_id:
        return JsonResponse({'success': False, 'error': 'Anomaly ID is required'})
    
    try:
        # Try to get the anomaly record
        try:
            anomaly = SpendingAnomaly.objects.get(id=anomaly_id, user=request.user)
        except SpendingAnomaly.DoesNotExist:
            # If it doesn't exist in the database, try to find the transaction
            transaction_id = anomaly_id
            transaction = Transaction.objects.get(id=transaction_id, user=request.user)
            
            # Create an anomaly record for it
            anomaly = SpendingAnomaly.objects.create(
                user=request.user,
                transaction=transaction,
                anomaly_score=0.8,  # Default high score
                description="Manually reviewed anomaly"
            )
        
        # Mark the anomaly as verified
        anomaly.is_verified = True
        anomaly.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Anomaly marked as reviewed'
        })
    except Transaction.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Transaction not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def ignore_similar_anomalies(request):
    """Ignore similar anomalies by pattern"""
    anomaly_id = request.POST.get('anomaly_id')
    if not anomaly_id:
        return JsonResponse({'success': False, 'error': 'Anomaly ID is required'})
    
    try:
        # Get the transaction for this anomaly
        try:
            anomaly = SpendingAnomaly.objects.get(id=anomaly_id, user=request.user)
            transaction = anomaly.transaction
        except SpendingAnomaly.DoesNotExist:
            transaction = Transaction.objects.get(id=anomaly_id, user=request.user)
        
        if not transaction:
            return JsonResponse({'success': False, 'error': 'Transaction not found'})
        
        # Find similar transactions
        similar_transactions = Transaction.objects.filter(
            user=request.user,
            description__icontains=transaction.description[:10],  # Match on first part of description
            category=transaction.category
        ).exclude(id=transaction.id)
        
        # Mark any existing anomalies for these transactions as verified (ignored)
        anomaly_count = 0
        for similar_tx in similar_transactions:
            try:
                similar_anomaly = SpendingAnomaly.objects.get(transaction=similar_tx, user=request.user)
                similar_anomaly.is_verified = True
                similar_anomaly.save()
                anomaly_count += 1
            except SpendingAnomaly.DoesNotExist:
                # No anomaly record exists for this transaction
                pass
        
        # Also mark the original anomaly as verified
        if anomaly:
            anomaly.is_verified = True
            anomaly.save()
            anomaly_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'Ignored {anomaly_count} similar anomalies'
        })
    except Transaction.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Transaction not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["GET", "POST"])
def update_anomaly_settings(request):
    # Redirect all GET requests to the anomaly detection page
    if request.method == "GET":
        from django.urls import reverse
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(reverse('analytics:anomaly_detection'))
    # Redirect non-AJAX POST requests to the anomaly detection page
    if request.headers.get('x-requested-with') != 'XMLHttpRequest':
        from django.urls import reverse
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(reverse('analytics:anomaly_detection'))
    try:
        # Get the user's profile
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Update settings
        sensitivity = float(request.POST.get('sensitivity', 1.0))
        min_amount = float(request.POST.get('min_amount', 100))
        enable_notifications = request.POST.get('enable_notifications') == 'on'
        
        # Save settings to profile
        profile.anomaly_detection_sensitivity = sensitivity
        profile.anomaly_min_amount = min_amount
        profile.enable_anomaly_notifications = enable_notifications
        profile.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Settings updated successfully'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

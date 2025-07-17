from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import datetime, timedelta, date
from .models import Account, Transaction, Category, Budget, SavingsGoal, UserProfile
from django.http import HttpResponse, JsonResponse
import json
import csv
from .forms import AccountForm, TransactionForm, CategoryForm, BudgetForm, SavingsGoalForm, UserProfileForm
# from analytics.ml_utils import TransactionCategorizer
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
import decimal
from dateutil.relativedelta import relativedelta

def home(request):
    """
    Home page view - shows the main landing page
    """
    return render(request, 'financial/home.html')

def signup(request):
    """User registration view"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Create user profile
            UserProfile.objects.create(user=user)
            
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=raw_password)
            login(request, user)
            
            # Print debugging information
            print(f"User authenticated: {user is not None}")
            print(f"User is active: {user.is_active}")
            print(f"Redirecting to dashboard...")
            
            messages.success(request, 'Account created successfully!')
            return redirect('dashboard')
        else:
            # If the form is invalid, print the errors
            print(f"Form errors: {form.errors}")
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

@login_required
def dashboard(request):
    """Main dashboard view"""
    # Debug info
    print(f"Dashboard view called for user: {request.user.username}")
    
    user = request.user
    
    # Get accounts summary
    accounts = Account.objects.filter(user=user)
    total_balance = accounts.aggregate(Sum('balance'))['balance__sum'] or 0
    
    # Get recent transactions
    recent_transactions = Transaction.objects.filter(user=user).order_by('-date', '-created_at')[:5]
    
    # Get budget status for current month
    today = timezone.now().date()
    start_date = date(today.year, today.month, 1)
    if today.month == 12:
        end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)
    
    budgets = Budget.objects.filter(
        user=user,
        is_active=True,
        start_date__lte=end_date
    ).order_by('category__name')
    
    # Calculate spending for each budget
    for budget in budgets:
        # Get spending for this period
        expenses = Transaction.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date,
            category=budget.category,
            transaction_type='expense'
        )
        
        spent = expenses.aggregate(total=Sum('amount'))['total'] or 0
        budget.spent = spent
        
        # Calculate percentage safely
        if float(budget.amount) > 0:
            budget.percentage = min(100, (float(spent) / float(budget.amount)) * 100)
        else:
            budget.percentage = 0
            
        # Make sure percentage is a proper number
        budget.percentage = round(budget.percentage, 1)
        print(f"Budget {budget.name}: spent={spent}, amount={budget.amount}, percentage={budget.percentage}")
    
    # Get savings goals
    savings_goals = SavingsGoal.objects.filter(user=user, status='in_progress')
    
    # Log savings goal information for debugging
    for goal in savings_goals:
        print(f"Savings goal {goal.name}: current={goal.current_amount}, target={goal.target_amount}, percentage={goal.progress_percentage}")
    
    # Get spending by category (last 30 days)
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    category_spending = Transaction.objects.filter(
        user=user, 
        date__gte=thirty_days_ago,
        transaction_type='expense'
    ).values('category__name').annotate(
        total=Sum('amount')
    ).order_by('-total')
    
    context = {
        'accounts': accounts,
        'total_balance': total_balance,
        'recent_transactions': recent_transactions,
        'budgets': budgets,
        'savings_goals': savings_goals,
        'category_spending': category_spending,
    }
    
    print("Rendering dashboard template with context")
    return render(request, 'financial/dashboard.html', context)

# Account views
@login_required
def account_list(request):
    """View all user accounts"""
    accounts = Account.objects.filter(user=request.user)
    total_balance = accounts.aggregate(Sum('balance'))['balance__sum'] or 0
    
    context = {
        'accounts': accounts,
        'total_balance': total_balance,
    }
    
    return render(request, 'financial/accounts/account_list.html', context)

@login_required
def account_create(request):
    """Create a new account"""
    if request.method == 'POST':
        form = AccountForm(request.POST)
        if form.is_valid():
            # Debug info
            print(f"Form is valid. Creating account with name: {form.cleaned_data['name']}")
            
            account = form.save(commit=False)
            account.user = request.user
            account.save()
            
            print(f"Account created successfully with ID: {account.id}")
            messages.success(request, f'Account "{account.name}" was created successfully!')
            return redirect('financial:account_list')
        else:
            # If the form is invalid, print and display error messages
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Error in {field}: {error}')
    else:
        form = AccountForm()
    
    context = {'form': form}
    return render(request, 'financial/accounts/account_form.html', context)

@login_required
def account_detail(request, account_id):
    """View account details and transactions"""
    account = get_object_or_404(Account, id=account_id, user=request.user)
    transactions = Transaction.objects.filter(account=account).order_by('-date')
    
    context = {
        'account': account,
        'transactions': transactions,
    }
    
    return render(request, 'financial/accounts/account_detail.html', context)

@login_required
def account_edit(request, account_id):
    """Edit account details"""
    account = get_object_or_404(Account, id=account_id, user=request.user)
    
    if request.method == 'POST':
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, f'Account "{account.name}" was updated successfully!')
            return redirect('financial:account_list')
        else:
            # If the form is invalid, print and display error messages
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Error in {field}: {error}')
    else:
        form = AccountForm(instance=account)
    
    context = {'form': form, 'account': account}
    return render(request, 'financial/accounts/account_form.html', context)

@login_required
def account_delete(request, account_id):
    """Delete an account"""
    account = get_object_or_404(Account, id=account_id, user=request.user)
    
    if request.method == 'POST':
        # Check if there are any transactions associated with this account
        transaction_count = Transaction.objects.filter(account=account).count()
        if transaction_count > 0:
            messages.error(request, f'Cannot delete account "{account.name}" because it has {transaction_count} transactions. Consider marking it as inactive instead.')
            return redirect('financial:account_list')
        
        account_name = account.name
        account.delete()
        messages.success(request, f'Account "{account_name}" was deleted successfully!')
        return redirect('financial:account_list')
    
    return render(request, 'financial/accounts/account_confirm_delete.html', {'account': account})

# Transaction views
@login_required
def transaction_list(request):
    """View all transactions with filtering"""
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    
    # Get filter options
    accounts = Account.objects.filter(user=request.user)
    categories = Category.objects.filter(user=request.user) | Category.objects.filter(is_default=True)
    
    # Calculate summary statistics
    income_total = Transaction.objects.filter(
        user=request.user, 
        transaction_type='income'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    expense_total = Transaction.objects.filter(
        user=request.user, 
        transaction_type='expense'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    net_cash_flow = income_total - expense_total
    
    context = {
        'transactions': transactions,
        'accounts': accounts,
        'categories': categories,
        'income_total': income_total,
        'expense_total': expense_total,
        'net_cash_flow': net_cash_flow,
    }
    
    return render(request, 'financial/transactions/transaction_list.html', context)

@login_required
def transaction_create(request):
    """Create a new transaction"""
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            
            # Handle transfer transaction
            if transaction.transaction_type == 'transfer':
                to_account_id = request.POST.get('to_account')
                if not to_account_id:
                    messages.error(request, 'Please select a destination account for the transfer.')
                    return render(request, 'financial/transactions/transaction_form.html', {
                        'form': form,
                        'accounts': Account.objects.filter(user=request.user),
                        'categories': Category.objects.filter(user=request.user) | Category.objects.filter(is_default=True)
                    })
                
                to_account = get_object_or_404(Account, id=to_account_id, user=request.user)
                transaction.to_account = to_account
            
            transaction.save()
            
            # Update account balances
            if transaction.transaction_type == 'income':
                transaction.account.balance += transaction.amount
            elif transaction.transaction_type == 'expense':
                transaction.account.balance -= transaction.amount
            elif transaction.transaction_type == 'transfer':
                transaction.account.balance -= transaction.amount
                transaction.to_account.balance += transaction.amount
                transaction.to_account.save()
            
            transaction.account.save()
            
            messages.success(request, 'Transaction created successfully!')
            return redirect('financial:transaction_list')
        else:
            # If the form is invalid, print and display error messages
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Error in {field}: {error}')
    else:
        form = TransactionForm()
    
    context = {
        'form': form,
        'accounts': Account.objects.filter(user=request.user),
        'categories': Category.objects.filter(user=request.user) | Category.objects.filter(is_default=True)
    }
    return render(request, 'financial/transactions/transaction_form.html', context)

@login_required
def transaction_detail(request, transaction_id):
    """View transaction details"""
    transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
    
    # Find similar transactions
    similar_transactions = Transaction.objects.filter(
        user=request.user,
        category=transaction.category
    ).exclude(id=transaction.id).order_by('-date')[:5]
    
    # Get budget impact if transaction has a category and is an expense
    budget_impact = None
    if transaction.category and transaction.transaction_type == 'expense':
        # Use the transaction's date for budget calculation
        transaction_month = transaction.date.month
        transaction_year = transaction.date.year
        
        try:
            # Find a budget for this category active during the transaction period
            budget = Budget.objects.filter(
                user=request.user,
                category=transaction.category,
                is_active=True
            ).order_by('-created_at').first()
            
            if budget:
                # Calculate spending before and after this transaction
                # for the budget period containing this transaction
                period_start = date(transaction_year, transaction_month, 1)
                if transaction_month == 12:
                    period_end = date(transaction_year + 1, 1, 1) - timedelta(days=1)
                else:
                    period_end = date(transaction_year, transaction_month + 1, 1) - timedelta(days=1)
                
                category_expenses = Transaction.objects.filter(
                    user=request.user,
                    category=transaction.category,
                    transaction_type='expense',
                    date__gte=period_start,
                    date__lte=period_end
                ).exclude(id=transaction.id)
                
                spent_before = sum(t.amount for t in category_expenses)
                spent_after = spent_before + transaction.amount
                
                # Calculate percentages
                percentage_before = (spent_before / budget.amount) * 100 if budget.amount > 0 else 0
                percentage_after = (spent_after / budget.amount) * 100 if budget.amount > 0 else 0
                
                budget_impact = {
                    'id': budget.id,
                    'name': budget.name,
                    'category': budget.category,
                    'amount': budget.amount,
                    'spent_before': spent_before,
                    'spent_after': spent_after,
                    'percentage_before': percentage_before,
                    'percentage_after': percentage_after
                }
        except Exception as e:
            print(f"Error calculating budget impact: {str(e)}")
            pass
            
    # Generate AI insights
    ai_insights = []
    if transaction.transaction_type == 'expense':
        # Sample insights - in a real app, you would use ML models
        if transaction.category:
            user_transactions = Transaction.objects.filter(
                user=request.user,
                category=transaction.category,
                transaction_type='expense'
            ).exclude(id=transaction.id)
            
            if user_transactions.exists():
                avg_amount = sum(t.amount for t in user_transactions) / user_transactions.count()
                
                if transaction.amount > avg_amount * 1.5:
                    ai_insights.append(f"This transaction is {((transaction.amount / avg_amount) - 1) * 100:.1f}% higher than your average {transaction.category.name} expense.")
                elif transaction.amount < avg_amount * 0.5:
                    ai_insights.append(f"This transaction is {((avg_amount / transaction.amount) - 1) * 100:.1f}% lower than your average {transaction.category.name} expense.")
                    
        # Add frequency insights
        month_count = Transaction.objects.filter(
            user=request.user,
            description__icontains=transaction.description,
            date__month=transaction.date.month
        ).count()
        
        if month_count > 2:
            ai_insights.append(f"You've made {month_count} similar transactions this month.")
            
        # If no insights were generated, add a default one
        if not ai_insights:
            ai_insights.append("No unusual patterns detected for this transaction.")
    
    context = {
        'transaction': transaction,
        'similar_transactions': similar_transactions,
        'budget_impact': budget_impact,
        'ai_insights': ai_insights
    }
    
    return render(request, 'financial/transactions/transaction_detail.html', context)

@login_required
def transaction_edit(request, transaction_id):
    """Edit a transaction"""
    transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
    
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            
            # Handle transfer transaction
            if transaction.transaction_type == 'transfer':
                to_account_id = request.POST.get('to_account')
                if not to_account_id:
                    messages.error(request, 'Please select a destination account for the transfer.')
                    return render(request, 'financial/transactions/transaction_form.html', {
                        'form': form,
                        'accounts': Account.objects.filter(user=request.user),
                        'categories': Category.objects.filter(user=request.user) | Category.objects.filter(is_default=True)
                    })
                
                to_account = get_object_or_404(Account, id=to_account_id, user=request.user)
                transaction.to_account = to_account
            
            transaction.save()
            
            # Update account balances
            if transaction.transaction_type == 'income':
                transaction.account.balance += transaction.amount
            elif transaction.transaction_type == 'expense':
                transaction.account.balance -= transaction.amount
            elif transaction.transaction_type == 'transfer':
                transaction.account.balance -= transaction.amount
                transaction.to_account.balance += transaction.amount
                transaction.to_account.save()
            
            transaction.account.save()
            
            messages.success(request, 'Transaction updated successfully!')
            return redirect('financial:transaction_list')
    else:
        form = TransactionForm(instance=transaction)
    
    context = {
        'form': form,
        'accounts': Account.objects.filter(user=request.user),
        'categories': Category.objects.filter(user=request.user) | Category.objects.filter(is_default=True)
    }
    return render(request, 'financial/transactions/transaction_form.html', context)

@login_required
def transaction_delete(request, transaction_id):
    """Delete a transaction"""
    transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
    
    if request.method == 'POST':
        # Store transaction info before deletion for success message
        description = transaction.description
        
        # Handle updating account balance before deleting
        account = transaction.account
        if transaction.transaction_type == 'income':
            account.balance -= transaction.amount
        elif transaction.transaction_type == 'expense':
            account.balance += transaction.amount
        elif transaction.transaction_type == 'transfer':
            # For transfers, restore balances on both accounts
            account.balance += transaction.amount
            if transaction.to_account:
                to_account = transaction.to_account
                to_account.balance -= transaction.amount
                to_account.save()
        
        # Save account changes
        account.save()
        
        # Delete the transaction
        transaction.delete()
        
        messages.success(request, f'Transaction "{description}" was deleted successfully!')
        return redirect('financial:transaction_list')
    
    return render(request, 'financial/transactions/transaction_confirm_delete.html', {'transaction': transaction})

@login_required
def transaction_export(request):
    """Export transactions to CSV file"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    
    # Get filtered transactions based on request parameters
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Description', 'Category', 'Account', 'Amount', 'Type'])
    
    for transaction in transactions:
        writer.writerow([
            transaction.date.strftime('%Y-%m-%d'),
            transaction.description,
            transaction.category.name if transaction.category else 'Uncategorized',
            transaction.account.name,
            transaction.amount,
            transaction.transaction_type
        ])
    
    return response

# Category views
@login_required
@ensure_csrf_cookie
def category_list(request):
    """View all categories"""
    user_categories = Category.objects.filter(user=request.user)
    default_categories = Category.objects.filter(is_default=True)
    
    context = {
        'user_categories': user_categories,
        'default_categories': default_categories,
    }
    
    return render(request, 'financial/categories/category_list.html', context)

@login_required
@ensure_csrf_cookie
@require_http_methods(["POST"])
def category_create(request):
    """Create a new category via AJAX"""
    try:
        print("Category create view called")  # Debug log
        print("Request body:", request.body)  # Debug log
        
        data = json.loads(request.body)
        name = data.get('name')
        category_type = data.get('type')
        
        print(f"Received data - name: {name}, type: {category_type}")  # Debug log
        
        if not name:
            return JsonResponse({'success': False, 'error': 'Category name is required'})
        
        if not category_type:
            return JsonResponse({'success': False, 'error': 'Category type is required'})
        
        if category_type not in ['expense', 'income']:
            return JsonResponse({'success': False, 'error': 'Invalid category type'})
        
        # Check if category with same name exists
        if Category.objects.filter(user=request.user, name__iexact=name).exists():
            return JsonResponse({'success': False, 'error': 'A category with this name already exists'})
        
        category = Category.objects.create(
            name=name,
            type=category_type,
            user=request.user
        )
        
        print(f"Category created successfully: {category}")  # Debug log
        
        return JsonResponse({
            'success': True,
            'category': {
                'id': category.id,
                'name': category.name,
                'type': category.type
            }
        })
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")  # Debug log
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        print(f"Error creating category: {str(e)}")  # Debug log
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def category_edit(request, category_id):
    """Edit a category via AJAX"""
    try:
        category = get_object_or_404(Category, id=category_id, user=request.user)
        data = json.loads(request.body)
        name = data.get('name')
        category_type = data.get('type')
        
        if not name:
            return JsonResponse({'success': False, 'error': 'Category name is required'})
        
        if not category_type:
            return JsonResponse({'success': False, 'error': 'Category type is required'})
        
        if category_type not in ['expense', 'income']:
            return JsonResponse({'success': False, 'error': 'Invalid category type'})
        
        # Check if another category with same name exists
        if Category.objects.filter(user=request.user, name__iexact=name).exclude(id=category_id).exists():
            return JsonResponse({'success': False, 'error': 'A category with this name already exists'})
        
        category.name = name
        category.type = category_type
        category.save()
        
        return JsonResponse({
            'success': True,
            'category': {
                'id': category.id,
                'name': category.name,
                'type': category.type
            }
        })
    except Category.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Category not found'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        print(f"Error editing category: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def category_delete(request, category_id):
    """Delete a category via AJAX"""
    try:
        category = get_object_or_404(Category, id=category_id, user=request.user)
        
        # Check if category is being used
        if Transaction.objects.filter(category=category).exists():
            return JsonResponse({
                'success': False,
                'error': 'Cannot delete category because it is being used by transactions'
            })
        
        # Check if category is being used in budgets
        if Budget.objects.filter(category=category).exists():
            return JsonResponse({
                'success': False,
                'error': 'Cannot delete category because it is being used in budgets'
            })
        
        category.delete()
        return JsonResponse({'success': True})
    except Category.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Category not found'})
    except Exception as e:
        print(f"Error deleting category: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def category_spending_ajax(request):
    """Get average spending for a category via AJAX"""
    try:
        category_id = request.GET.get('category')
        if not category_id:
            return JsonResponse({'success': False, 'error': 'Category ID is required'})
        
        category = get_object_or_404(Category, id=category_id, user=request.user)
        
        # Calculate average monthly spending for the last 6 months
        six_months_ago = timezone.now().date() - timedelta(days=180)
        transactions = Transaction.objects.filter(
            user=request.user,
            category=category,
            date__gte=six_months_ago,
            transaction_type='expense'
        )
        
        total_spending = transactions.aggregate(total=Sum('amount'))['total'] or 0
        # Calculate average (divide by 6 for 6 months)
        average_spending = total_spending / 6 if total_spending > 0 else 0
        
        return JsonResponse({
            'success': True,
            'spending': {
                'average': average_spending,
                'total': total_spending
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Budget views
@login_required
def budget_list(request):
    """View all budgets"""
    # Get the requested month and year (default to current)
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year
    
    month_year = request.GET.get('month', f"{current_month}-{current_year}")
    try:
        month, year = map(int, month_year.split('-'))
    except ValueError:
        month = current_month
        year = current_year
    
    # Get the start and end dates for the selected month
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Get budgets applicable for this month
    budgets = Budget.objects.filter(
        user=request.user,
        is_active=True,
        start_date__lte=end_date
    ).order_by('category__name')
    
    # Calculate spending for each budget
    for budget in budgets:
        # Get the date range for this budget period
        period_start = start_date
        period_end = end_date
        
        # Get spending for this period
        expenses = Transaction.objects.filter(
            user=request.user,
            date__gte=period_start,
            date__lte=period_end,
            category=budget.category,
            transaction_type='expense'
        )
        
        spent = expenses.aggregate(total=Sum('amount'))['total'] or 0
        budget.spent = spent
        budget.remaining = float(budget.amount) - float(spent)
        budget.percentage = (float(spent) / float(budget.amount)) * 100 if float(budget.amount) > 0 else 0
    
    # Calculate totals
    total_budget = sum(float(budget.amount) for budget in budgets)
    total_spent = sum(float(budget.spent) for budget in budgets)
    remaining = total_budget - total_spent
    
    # Generate list of available months (last 6 months + next 3 months)
    available_months = []
    for i in range(-6, 4):  # -6 to +3 (10 months total)
        d = today.replace(day=1) + relativedelta(months=i)
        month_data = {
            'month': d.month,
            'year': d.year,
            'month_name': d.strftime('%B')
        }
        available_months.append(month_data)
    
    # Get month name for display
    from calendar import month_name
    current_month_name = month_name[month]
    
    context = {
        'budgets': budgets,
        'total_budget': total_budget,
        'total_spent': total_spent,
        'remaining': remaining,
        'current_month': month,
        'current_year': year,
        'current_month_name': current_month_name,
        'available_months': available_months
    }
    
    return render(request, 'financial/budgets/budget_list.html', context)

@login_required
def budget_create(request):
    """Create a new budget"""
    if request.method == 'POST':
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            
            # Handle month/year fields that are not part of the model directly
            if 'month' in request.POST and 'year' in request.POST:
                month = int(request.POST.get('month'))
                year = int(request.POST.get('year'))
                # Set start_date to the first day of the selected month
                budget.start_date = date(year, month, 1)
                
                # Set a default name if not provided
                if not budget.name or budget.name.strip() == '':
                    from calendar import month_name
                    budget.name = f"{budget.category.name} budget for {month_name[month]} {year}"
            
            # Set default period to monthly if not selected
            if not budget.period:
                budget.period = 'monthly'
                
            budget.save()
            messages.success(request, 'Budget created successfully!')
            return redirect('financial:budget_list')
        else:
            # If the form is invalid, print and display error messages
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Error in {field}: {error}')
    else:
        form = BudgetForm(user=request.user, initial={'is_active': True, 'period': 'monthly'})
    
    # Get expense categories
    expense_categories = Category.objects.filter(
        user=request.user,
        type='expense'
    ).order_by('name')
    
    # Get months and years for dropdowns
    current_date = timezone.now().date()
    months = [
        (i, datetime(2000, i, 1).strftime('%B'))
        for i in range(1, 13)
    ]
    years = range(current_date.year, current_date.year + 2)
    
    context = {
        'form': form,
        'expense_categories': expense_categories,
        'months': months,
        'years': years,
        'current_month': current_date.month,
        'current_year': current_date.year
    }
    
    return render(request, 'financial/budgets/budget_form.html', context)

@login_required
def budget_detail(request, budget_id):
    """View budget details and progress"""
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    
    # Get transactions for this budget's category in the current period
    transactions = Transaction.objects.filter(
        user=request.user,
        category=budget.category,
        transaction_type='expense',
        date__gte=budget.period_start_date,
        date__lte=budget.period_end_date
    ).order_by('-date')
    
    # Calculate budget metrics
    budget.spent = budget.get_spent_amount()
    budget.remaining = budget.get_remaining_amount()
    budget.percentage = budget.get_percentage_used()
    
    # Calculate daily budget (for daily burn rate)
    total_days = (budget.period_end_date - budget.period_start_date).days + 1
    budget.daily_amount = float(budget.amount) / total_days if total_days > 0 else 0
    
    # Calculate days elapsed and days remaining
    today = timezone.now().date()
    days_elapsed = (min(today, budget.period_end_date) - budget.period_start_date).days + 1
    days_remaining = (budget.period_end_date - today).days + 1 if today <= budget.period_end_date else 0
    
    # Calculate expected spending by today and actual spending
    expected_spent = (float(budget.amount) / total_days) * days_elapsed if days_elapsed > 0 else 0
    actual_spent = float(budget.spent)
    
    # Determine if spending is on track
    budget.on_track = actual_spent <= expected_spent * 1.1  # 10% buffer
    budget.is_overpace = actual_spent > expected_spent * 1.1 and actual_spent < float(budget.amount)
    
    # Calculate daily average spent
    budget.daily_average = actual_spent / days_elapsed if days_elapsed > 0 else 0
    
    # Prepare data for daily progress chart
    daily_data = []
    cumulative_ideal = 0
    cumulative_actual = 0
    
    # Create a date range from period start to today (or period end if past)
    current_date = budget.period_start_date
    end_date = min(today, budget.period_end_date)
    
    # Create a dict of transaction amounts by date
    transaction_by_date = {}
    for transaction in transactions:
        date_str = transaction.date.strftime('%Y-%m-%d')
        if date_str not in transaction_by_date:
            transaction_by_date[date_str] = 0
        transaction_by_date[date_str] += float(transaction.amount)
    
    # Generate daily data
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Add ideal daily amount
        daily_ideal = budget.daily_amount
        cumulative_ideal += daily_ideal
        
        # Add actual spending for this day
        daily_actual = transaction_by_date.get(date_str, 0)
        cumulative_actual += daily_actual
        
        daily_data.append({
            'date': current_date,
            'ideal_amount': cumulative_ideal,
            'actual_amount': cumulative_actual
        })
        
        current_date += timedelta(days=1)
    
    context = {
        'budget': budget,
        'transactions': transactions,
        'days_elapsed': days_elapsed,
        'days_remaining': days_remaining,
        'expected_spent': expected_spent,
        'actual_spent': actual_spent,
        'daily_data': daily_data
    }
    
    return render(request, 'financial/budgets/budget_detail.html', context)

@login_required
def budget_edit(request, budget_id):
    """Edit a budget"""
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Budget "{budget.name}" was updated successfully!')
            return redirect('financial:budget_list')
        else:
            # If the form is invalid, print and display error messages
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Error in {field}: {error}')
    else:
        form = BudgetForm(instance=budget, user=request.user)
    
    # Get expense categories
    expense_categories = Category.objects.filter(
        user=request.user,
        type='expense'
    ).order_by('name')
    
    # Get months and years for dropdowns
    current_date = timezone.now().date()
    months = [
        (i, datetime(2000, i, 1).strftime('%B'))
        for i in range(1, 13)
    ]
    years = range(current_date.year, current_date.year + 2)
    
    context = {
        'form': form,
        'budget': budget,
        'expense_categories': expense_categories,
        'months': months,
        'years': years,
        'current_month': current_date.month,
        'current_year': current_date.year
    }
    
    return render(request, 'financial/budgets/budget_form.html', context)

@login_required
def budget_delete(request, budget_id):
    """Delete a budget"""
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    
    if request.method == 'POST':
        budget_name = budget.name
        budget.delete()
        messages.success(request, f'Budget "{budget_name}" was deleted successfully!')
        return redirect('financial:budget_list')
        
    return render(request, 'financial/budgets/budget_confirm_delete.html', {'budget': budget})

# Savings Goal views
@login_required
def savings_goal_list(request):
    """View all savings goals"""
    goals = SavingsGoal.objects.filter(user=request.user).order_by('-created_at')
    
    # Get active (in progress) and completed goals separately
    active_goals = goals.filter(status='in_progress')
    completed_goals = goals.filter(status='completed')
    
    # Calculate summary statistics
    active_goals_count = active_goals.count()
    total_goals_amount = sum(float(goal.target_amount) for goal in goals)
    total_saved_amount = sum(float(goal.current_amount) for goal in goals)
    
    context = {
        'goals': active_goals,
        'completed_goals': completed_goals,
        'active_goals_count': active_goals_count,
        'total_goals_amount': total_goals_amount,
        'total_saved_amount': total_saved_amount,
    }
    
    return render(request, 'financial/goals/goal_list.html', context)

@login_required
def savings_goal_create(request):
    """Create a new savings goal"""
    if request.method == 'POST':
        form = SavingsGoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, 'Savings goal created successfully!')
            return redirect('financial:savings_goal_list')
        else:
            # If the form is invalid, print and display error messages
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Error in {field}: {error}')
    else:
        form = SavingsGoalForm()
    
    # Get categories for the form
    categories = Category.objects.filter(user=request.user).order_by('name')
    
    context = {
        'form': form,
        'categories': categories,
    }
    
    return render(request, 'financial/goals/goal_form.html', context)

@login_required
def savings_goal_detail(request, goal_id):
    """View savings goal details"""
    goal = get_object_or_404(SavingsGoal, id=goal_id, user=request.user)
    
    # Get contributions for this goal (transactions with description matching the goal)
    contributions = Transaction.objects.filter(
        user=request.user,
        description__contains=f"Contribution to {goal.name}"
    ).order_by('-date')
    
    context = {
        'goal': goal,
        'contributions': contributions
    }
    
    return render(request, 'financial/goals/goal_detail.html', context)

@login_required
def savings_goal_edit(request, goal_id):
    """Edit a savings goal"""
    goal = get_object_or_404(SavingsGoal, id=goal_id, user=request.user)
    
    if request.method == 'POST':
        form = SavingsGoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            messages.success(request, 'Savings goal updated successfully!')
            return redirect('financial:savings_goal_list')
        else:
            # If the form is invalid, print and display error messages
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Error in {field}: {error}')
    else:
        form = SavingsGoalForm(instance=goal)
    
    # Get categories for the form
    categories = Category.objects.filter(user=request.user).order_by('name')
    
    context = {
        'form': form,
        'goal': goal,
        'categories': categories,
    }
    
    return render(request, 'financial/goals/goal_form.html', context)

@login_required
def savings_goal_delete(request, goal_id):
    """Delete a savings goal"""
    goal = get_object_or_404(SavingsGoal, id=goal_id, user=request.user)
    
    if request.method == 'POST':
        goal_name = goal.name
        goal.delete()
        messages.success(request, f'Savings goal "{goal_name}" was deleted successfully!')
        return redirect('financial:savings_goal_list')
        
    return render(request, 'financial/goals/goal_confirm_delete.html', {'goal': goal})

@login_required
def savings_goal_add_contribution(request, goal_id):
    """Add a contribution to a savings goal"""
    goal = get_object_or_404(SavingsGoal, id=goal_id, user=request.user)
    accounts = Account.objects.filter(user=request.user)
    
    if request.method == 'POST':
        # Get form data
        amount_str = request.POST.get('amount')
        date_str = request.POST.get('date')
        account_id = request.POST.get('account')
        notes = request.POST.get('notes')
        
        # Add debug prints
        print(f"Received contribution data - amount: {amount_str}, date: {date_str}, account: {account_id}")
        
        try:
            # Validate amount
            if not amount_str:
                raise ValueError("Amount is required")
                
            amount = float(amount_str)
            
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero.')
                return render(request, 'financial/goals/goal_contribution_form.html', {
                    'goal': goal, 
                    'accounts': accounts,
                    'today': timezone.now().date()
                })
            
            # Parse date with various formats or use today
            contribution_date = None
            if date_str:
                try:
                    # Try different date formats
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                        try:
                            contribution_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    
                    if not contribution_date:
                        raise ValueError("Invalid date format")
                except ValueError:
                    messages.warning(request, 'Invalid date format. Using today\'s date instead.')
                    contribution_date = timezone.now().date()
            else:
                contribution_date = timezone.now().date()
                
            # Update goal current amount
            goal.current_amount += decimal.Decimal(str(amount))  # Convert to Decimal for precision
            goal.save()
            
            # If account is selected, create a transaction and update account balance
            if account_id:
                try:
                    account = get_object_or_404(Account, id=account_id, user=request.user)
                    
                    # Create transaction
                    transaction = Transaction.objects.create(
                        user=request.user,
                        account=account,
                        amount=amount,
                        transaction_type='expense',
                        date=contribution_date,
                        description=f"Contribution to {goal.name}",
                        notes=notes
                    )
                    
                    # Update account balance
                    account.balance -= decimal.Decimal(str(amount))
                    account.save()
                    
                    print(f"Created transaction {transaction.id} for contribution")
                except Exception as e:
                    print(f"Error creating transaction: {str(e)}")
                    messages.error(request, f"Error creating transaction: {str(e)}")
                    # Still show success for the contribution itself
            
            messages.success(request, f'Contribution of ₹{amount:.2f} added successfully!')
            return redirect('financial:savings_goal_detail', goal_id=goal.id)
            
        except ValueError as e:
            print(f"Value error: {str(e)}")
            messages.error(request, f'Invalid amount provided: {str(e)}')
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            messages.error(request, f'An error occurred: {str(e)}')
    
    context = {
        'goal': goal,
        'accounts': accounts,
        'today': timezone.now().date()
    }
    
    return render(request, 'financial/goals/goal_contribution_form.html', context)

# User Profile views
@login_required
def user_profile(request):
    """View user profile"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'financial/profile/profile_detail.html', {'profile': profile})

@login_required
def user_profile_edit(request):
    """Edit user profile"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            # Save will handle both profile and user model changes
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('financial:user_profile')
    else:
        form = UserProfileForm(instance=profile)
    
    return render(request, 'financial/profile/profile_form.html', {'form': form, 'profile': profile})

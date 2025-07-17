import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from django.utils import timezone
import logging
from django.db.models import Sum, Avg
from financial.models import Transaction, Budget, Category

logger = logging.getLogger(__name__)

class BudgetAnalyzer:
    """
    Analyzes budget performance and provides recommendations for future budgets.
    """
    
    def __init__(self, user=None):
        """
        Initialize the budget analyzer.
        
        Args:
            user: User object for personalized analysis
        """
        self.user = user
    
    def analyze_budget_performance(self, budget, transactions):
        """
        Analyze how well a user is sticking to their budget
        
        Args:
            budget: Budget object
            transactions: QuerySet of relevant transactions
            
        Returns:
            Dict with budget performance metrics
        """
        if not budget or not transactions:
            return {
                'success': False,
                'message': 'No budget or transactions provided'
            }
            
        # Filter transactions for the budget's category and time period
        category_transactions = [
            tx for tx in transactions 
            if tx.category and tx.category.id == budget.category.id and
            tx.transaction_type == 'expense'
        ]
        
        if not category_transactions:
            return {
                'success': False,
                'message': 'No transactions found for this budget category'
            }
            
        # Calculate total spent
        total_spent = sum(float(tx.amount) for tx in category_transactions)
        
        # Calculate metrics
        budget_amount = float(budget.amount)
        remaining = budget_amount - total_spent
        percentage_used = (total_spent / budget_amount) * 100 if budget_amount > 0 else 0
        
        # Determine status
        if percentage_used > 100:
            status = 'over_budget'
            message = f"You've exceeded your budget by ₹{-remaining:.2f}"
        elif percentage_used >= 90:
            status = 'at_risk'
            message = f"You've used {percentage_used:.1f}% of your budget. Be careful with further spending."
        elif percentage_used >= 75:
            status = 'warning'
            message = f"You've used {percentage_used:.1f}% of your budget."
        else:
            status = 'on_track'
            message = f"You're on track with this budget. ₹{remaining:.2f} remaining."
            
        # Calculate daily spending rate
        days_in_period = 30  # Assuming monthly budget
        days_elapsed = min(days_in_period, (timezone.now().date() - budget.start_date).days + 1)
        daily_rate = total_spent / days_elapsed if days_elapsed > 0 else 0
        
        # Calculate projected end amount
        projected_total = total_spent + (daily_rate * (days_in_period - days_elapsed))
        projected_remaining = budget_amount - projected_total
        
        return {
            'success': True,
            'budget_id': budget.id,
            'category': budget.category.name,
            'amount': budget_amount,
            'spent': total_spent,
            'remaining': remaining,
            'percentage_used': percentage_used,
            'status': status,
            'message': message,
            'daily_rate': daily_rate,
            'projected_total': projected_total,
            'projected_remaining': projected_remaining,
            'days_elapsed': days_elapsed,
            'days_in_period': days_in_period
        }
        
    def generate_budget_recommendations(self, transactions, current_budgets=None):
        """
        Generate budget recommendations based on transaction history
        
        Args:
            transactions: QuerySet of Transaction objects
            current_budgets: List of current Budget objects
            
        Returns:
            Dict with budget recommendations by category
        """
        if not transactions:
            return {
                'success': False,
                'message': 'Not enough transaction history',
                'recommendations': []
            }
            
        # Filter to expenses only and ensure they have categories
        expense_transactions = [
            tx for tx in transactions 
            if tx.transaction_type == 'expense' and tx.category
        ]
        
        if len(expense_transactions) < 5:
            return {
                'success': False,
                'message': 'Not enough categorized expense transactions',
                'recommendations': []
            }
            
        # Create a DataFrame of expenses
        expenses_data = []
        for tx in expense_transactions:
            expenses_data.append({
                'date': tx.date,
                'amount': float(tx.amount),
                'category_id': tx.category.id,
                'category_name': tx.category.name,
                'month': tx.date.month,
                'year': tx.date.year
            })
            
        df = pd.DataFrame(expenses_data)
        
        # Get last 3 months data for more accurate recommendations
        three_months_ago = timezone.now().date() - timedelta(days=90)
        
        # Convert to pandas datetime for comparison
        if 'date' in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df['date']):
                df['date'] = pd.to_datetime(df['date'])
            three_months_ago_pd = pd.to_datetime(three_months_ago)
            recent_df = df[df['date'] >= three_months_ago_pd]
        else:
            recent_df = df
        
        if recent_df.empty:
            recent_df = df  # Use all data if not enough recent data
            
        # Calculate average monthly spending by category
        df['month_year'] = pd.to_datetime(df['date']).dt.to_period('M')
        monthly_category = df.groupby(['month_year', 'category_name'])['amount'].sum().unstack(fill_value=0)
        
        # Count unique months to calculate true monthly average
        unique_months = df['month_year'].nunique()
        if unique_months < 1:
            unique_months = 1
            
        # Calculate the average and add a small buffer for recommendations
        category_totals = df.groupby('category_name')['amount'].sum()
        category_avgs = category_totals / unique_months
        
        # Get current budget amounts by category
        current_budget_amounts = {}
        if current_budgets:
            for budget in current_budgets:
                if budget.category:
                    current_budget_amounts[budget.category.name] = float(budget.amount)
                    
        # Generate recommendations
        recommendations = []
        
        for category, avg_spend in category_avgs.items():
            # Skip very small categories
            if avg_spend < 100:  # Skip categories with very low spending
                continue
                
            # Calculate recommended budget amount (10% buffer over average)
            recommended_amount = avg_spend * 1.1
            
            # Check against current budget if it exists
            current_amount = current_budget_amounts.get(category, 0)
            
            if current_amount > 0:
                # If current budget exists, only recommend if it's significantly different
                if recommended_amount > current_amount * 1.2:
                    message = f"Consider increasing your {category} budget by {((recommended_amount / current_amount) - 1) * 100:.0f}%"
                    adjustment = 'increase'
                elif current_amount > recommended_amount * 1.2:
                    message = f"You may be able to reduce your {category} budget by {((current_amount / recommended_amount) - 1) * 100:.0f}%"
                    adjustment = 'decrease'
                else:
                    # Current budget is close to recommendation, skip
                    continue
            else:
                message = f"Consider setting a budget of ₹{recommended_amount:.0f} for {category}"
                adjustment = 'new'
                
            recommendations.append({
                'category': category,
                'current_amount': current_amount,
                'recommended_amount': recommended_amount,
                'average_spending': avg_spend,
                'message': message,
                'adjustment': adjustment
            })
            
        # Sort by recommended amount descending
        recommendations.sort(key=lambda x: x['recommended_amount'], reverse=True)
        
        return {
            'success': True,
            'message': f'Generated {len(recommendations)} budget recommendations',
            'recommendations': recommendations
        }
        
    def find_problematic_categories(self, transactions, current_budgets):
        """
        Identify categories where the user consistently exceeds their budget
        
        Args:
            transactions: QuerySet of Transaction objects
            current_budgets: List of current Budget objects
            
        Returns:
            List of problematic categories
        """
        if not transactions or not current_budgets:
            return []
            
        # Create budget lookup by category
        budget_by_category = {}
        for budget in current_budgets:
            if budget.category:
                budget_by_category[budget.category.id] = float(budget.amount)
                
        if not budget_by_category:
            return []
            
        # Create dataframe of expenses
        expenses_data = []
        for tx in transactions:
            if tx.transaction_type == 'expense' and tx.category and tx.category.id in budget_by_category:
                expenses_data.append({
                    'date': tx.date,
                    'amount': float(tx.amount),
                    'category_id': tx.category.id,
                    'category_name': tx.category.name,
                    'month': tx.date.month,
                    'year': tx.date.year
                })
                
        if not expenses_data:
            return []
            
        df = pd.DataFrame(expenses_data)
        
        # Ensure date is in datetime format
        if 'date' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['date']):
            df['date'] = pd.to_datetime(df['date'])
            
        # Group by month and category
        df['month_year'] = df['date'].dt.to_period('M')
        monthly_spending = df.groupby(['month_year', 'category_id', 'category_name'])['amount'].sum().reset_index()
        
        # Compare with budgets
        problematic_categories = []
        
        for category_id, budget_amount in budget_by_category.items():
            category_df = monthly_spending[monthly_spending['category_id'] == category_id]
            
            if len(category_df) < 2:  # Need at least 2 months of data
                continue
                
            # Count how many months exceed budget
            over_budget_count = sum(category_df['amount'] > budget_amount)
            
            # If over budget more than half the time, flag it
            if over_budget_count > len(category_df) / 2:
                category_name = category_df['category_name'].iloc[0]
                avg_overage = (category_df['amount'].mean() - budget_amount) / budget_amount
                
                problematic_categories.append({
                    'category_id': category_id,
                    'category_name': category_name,
                    'budget_amount': budget_amount,
                    'average_spending': category_df['amount'].mean(),
                    'average_overage_percent': avg_overage * 100,
                    'over_budget_months': over_budget_count,
                    'total_months': len(category_df),
                    'message': f"You consistently exceed your {category_name} budget by {avg_overage:.1%} on average."
                })
                
        return problematic_categories 

    def get_recommendations(self):
        """
        Generate budget recommendations based on user's spending patterns.
        
        Returns:
            List of budget recommendation dictionaries
        """
        recommendations = []
        
        if not self.user:
            return recommendations
        
        try:
            # Get recent transactions for analysis
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=90)  # Last 3 months
            
            transactions = Transaction.objects.filter(
                user=self.user,
                date__gte=start_date,
                date__lte=end_date
            )
            
            expense_transactions = transactions.filter(transaction_type='expense')
            
            if expense_transactions.count() < 5:
                # Not enough data for recommendations
                recommendations.append({
                    'type': 'info',
                    'message': 'Add more transactions to get personalized budget recommendations.',
                    'action': 'Add more transactions'
                })
                return recommendations
            
            # Get top spending categories
            category_spending = expense_transactions.values('category__id', 'category__name').annotate(
                total=Sum('amount')
            ).order_by('-total')[:5]
            
            # Get existing budgets
            existing_budgets = Budget.objects.filter(
                user=self.user,
                month=end_date.month,
                year=end_date.year
            ).values_list('category_id', flat=True)
            
            # Recommend budgets for top categories without budgets
            for cat in category_spending:
                if cat['category__id'] and cat['category__id'] not in existing_budgets:
                    # Calculate average monthly spending in this category
                    avg_spending = expense_transactions.filter(
                        category_id=cat['category__id']
                    ).aggregate(avg=Avg('amount'))['avg'] or 0
                    
                    # Recommend a budget slightly less than current spending
                    recommended_amount = avg_spending * 0.9  # 10% reduction
                    
                    recommendations.append({
                        'type': 'new_budget',
                        'category_id': cat['category__id'],
                        'category_name': cat['category__name'],
                        'suggested_amount': round(float(recommended_amount), 2),
                        'message': f"Create a budget for {cat['category__name']} based on your spending patterns.",
                        'action': 'Create budget'
                    })
            
            # Recommend adjustments to existing budgets that are consistently over/under
            existing_category_budgets = Budget.objects.filter(
                user=self.user,
                month__gte=start_date.month,
                year__gte=start_date.year
            ).select_related('category')
            
            for budget in existing_category_budgets:
                if not budget.category:
                    continue
                
                # Check actual spending for this budget's category
                actual_spending = expense_transactions.filter(
                    category=budget.category,
                    date__month=budget.month,
                    date__year=budget.year
                ).aggregate(Sum('amount'))['amount__sum'] or 0
                
                # Calculate overspending percentage
                if budget.amount > 0:
                    percentage_diff = (actual_spending - budget.amount) / budget.amount * 100
                    
                    if percentage_diff > 20:  # Consistently over budget by 20%+
                        recommendations.append({
                            'type': 'adjust_budget',
                            'budget_id': budget.id,
                            'category_name': budget.category.name,
                            'current_amount': float(budget.amount),
                            'suggested_amount': round(float(actual_spending * 0.95), 2),  # Suggest 5% less than actual
                            'message': f"Your {budget.category.name} budget is consistently exceeded. Consider adjusting it.",
                            'action': 'Adjust budget'
                        })
                    elif percentage_diff < -30:  # Consistently under budget by 30%+
                        recommendations.append({
                            'type': 'adjust_budget',
                            'budget_id': budget.id,
                            'category_name': budget.category.name,
                            'current_amount': float(budget.amount),
                            'suggested_amount': round(float(actual_spending * 1.1), 2),  # Suggest 10% more than actual
                            'message': f"You consistently spend less than budgeted for {budget.category.name}.",
                            'action': 'Adjust budget'
                        })
        
        except Exception as e:
            logger.error(f"Error generating budget recommendations: {str(e)}")
            recommendations.append({
                'type': 'error',
                'message': 'Unable to generate recommendations at this time.',
                'action': None
            })
        
        return recommendations 
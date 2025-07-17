from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
from datetime import date, timedelta
from django.db.models import Sum

class Category(models.Model):
    """Model for transaction categories"""
    CATEGORY_TYPES = (
        ('expense', 'Expense'),
        ('income', 'Income'),
    )
    
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=CATEGORY_TYPES)
    icon = models.CharField(max_length=50, blank=True, null=True)  # For storing CSS icon classes
    color = models.CharField(max_length=20, blank=True, null=True)  # For UI color coding
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)  # Allow user-specific categories
    is_default = models.BooleanField(default=False)  # For system default categories
    
    class Meta:
        verbose_name_plural = "Categories"
        
    def __str__(self):
        return self.name

class Account(models.Model):
    """Model for financial accounts"""
    ACCOUNT_TYPES = (
        ('checking', 'Checking Account'),
        ('savings', 'Savings Account'),
        ('credit', 'Credit Card'),
        ('investment', 'Investment Account'),
        ('loan', 'Loan'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='INR')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class Transaction(models.Model):
    """Model for financial transactions"""
    TRANSACTION_TYPES = (
        ('expense', 'Expense'),
        ('income', 'Income'),
        ('transfer', 'Transfer'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=255)
    notes = models.TextField(blank=True, null=True)
    receipt = models.ImageField(upload_to='receipts/', blank=True, null=True)
    is_recurring = models.BooleanField(default=False)
    
    # For transfers between accounts
    to_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, 
                                  related_name='incoming_transfers')
    
    # For AI/ML features
    ai_categorized = models.BooleanField(default=False)  # True if category was auto-assigned by ML
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.description} (₹{self.amount})"
        
    @property
    def display_amount(self):
        """Return formatted amount with sign based on transaction type"""
        if self.transaction_type == 'expense':
            return f"-₹{self.amount}"
        elif self.transaction_type == 'income':
            return f"+₹{self.amount}"
        elif self.transaction_type == 'transfer':
            return f"₹{self.amount}"
        return f"₹{self.amount}"
        
    @property
    def css_class(self):
        """Return CSS class for transaction type"""
        if self.transaction_type == 'expense':
            return "text-danger"
        elif self.transaction_type == 'income':
            return "text-success"
        return ""

class Budget(models.Model):
    """Model for user budgets"""
    PERIOD_CHOICES = (
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(blank=True, null=True)
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default='monthly')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        
    def __str__(self):
        return f"{self.name} - {self.amount} ({self.period})"
        
    @property
    def period_start_date(self):
        """Get the start date for the current period"""
        today = timezone.now().date()
        
        if self.period == 'daily':
            return today
        elif self.period == 'weekly':
            # Start from the beginning of the week
            return today - timedelta(days=today.weekday())
        elif self.period == 'monthly':
            # Start from the beginning of the month
            return date(today.year, today.month, 1)
        elif self.period == 'yearly':
            # Start from the beginning of the year
            return date(today.year, 1, 1)
        return self.start_date
        
    @property
    def period_end_date(self):
        """Get the end date for the current period"""
        today = timezone.now().date()
        
        if self.period == 'daily':
            return today
        elif self.period == 'weekly':
            # End at the end of the week
            return today + timedelta(days=6-today.weekday())
        elif self.period == 'monthly':
            # End at the end of the month
            if today.month == 12:
                return date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                return date(today.year, today.month + 1, 1) - timedelta(days=1)
        elif self.period == 'yearly':
            # End at the end of the year
            return date(today.year, 12, 31)
        return self.end_date or today
        
    def get_spent_amount(self):
        """Calculate amount spent in the current period"""
        expenses = Transaction.objects.filter(
            user=self.user,
            category=self.category,
            transaction_type='expense',
            date__gte=self.period_start_date,
            date__lte=self.period_end_date
        )
        
        total = expenses.aggregate(total=Sum('amount'))['total'] or 0
        return total
        
    def get_remaining_amount(self):
        """Calculate remaining amount for the current period"""
        spent = self.get_spent_amount()
        return float(self.amount) - float(spent)
        
    def get_percentage_used(self):
        """Calculate percentage of budget used"""
        spent = float(self.get_spent_amount())
        if float(self.amount) > 0:
            return (spent / float(self.amount)) * 100
        return 0
        
    def is_overspent(self):
        """Check if budget is overspent"""
        return self.get_remaining_amount() < 0

class SavingsGoal(models.Model):
    """Model for user savings goals"""
    GOAL_STATUS = (
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    target_date = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=15, choices=GOAL_STATUS, default='in_progress')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} - {self.current_amount}/{self.target_amount}"
        
    @property
    def progress_percentage(self):
        """Calculate percentage of goal completion"""
        if self.target_amount and float(self.target_amount) > 0:
            return (float(self.current_amount) / float(self.target_amount)) * 100
        return 0
        
    @property
    def is_completed(self):
        """Check if goal is completed based on amount or status"""
        return self.status == 'completed' or float(self.current_amount) >= float(self.target_amount)
        
    @property
    def is_behind_schedule(self):
        """Check if goal is behind schedule based on current amount and target date"""
        if not self.target_date or self.is_completed:
            return False
            
        # Calculate expected progress based on time elapsed
        total_days = (self.target_date - self.created_at.date()).days
        if total_days <= 0:
            return float(self.current_amount) < float(self.target_amount)
            
        days_passed = (timezone.now().date() - self.created_at.date()).days
        expected_progress = min(1.0, max(0.0, days_passed / total_days))
        expected_amount = float(self.target_amount) * expected_progress
        
        # Behind schedule if current amount is less than 90% of expected amount
        return float(self.current_amount) < (expected_amount * 0.9)
        
    @property
    def monthly_contribution_needed(self):
        """Calculate monthly contribution needed to reach goal by target date"""
        if not self.target_date or self.is_completed:
            return 0
            
        today = timezone.now().date()
        
        # If target date is in the past, return remaining amount
        if self.target_date <= today:
            return float(self.target_amount) - float(self.current_amount)
            
        # Calculate months between today and target date
        months_remaining = ((self.target_date.year - today.year) * 12 + 
                          self.target_date.month - today.month)
        
        if months_remaining <= 0:
            return float(self.target_amount) - float(self.current_amount)
        
        # Calculate monthly contribution
        remaining_amount = float(self.target_amount) - float(self.current_amount)
        return remaining_amount / months_remaining if months_remaining > 0 else remaining_amount

class UserProfile(models.Model):
    """Extended user profile for additional user settings"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    birth_date = models.DateField(null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    default_currency = models.CharField(max_length=3, default='INR')
    notification_preferences = models.JSONField(default=dict)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    
    # Settings for AI features
    enable_ai_insights = models.BooleanField(default=True)
    enable_ai_categorization = models.BooleanField(default=True)
    anomaly_detection_sensitivity = models.FloatField(default=1.0)
    anomaly_min_amount = models.FloatField(default=100.0)
    enable_anomaly_notifications = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Profile for {self.user.username}"

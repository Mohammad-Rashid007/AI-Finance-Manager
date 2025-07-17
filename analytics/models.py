from django.db import models
from django.contrib.auth.models import User
from financial.models import Category, Transaction
from django.utils import timezone

class SpendingPrediction(models.Model):
    """Model for storing ML spending predictions"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    prediction_date = models.DateField()
    predicted_amount = models.DecimalField(max_digits=12, decimal_places=2)
    confidence_score = models.FloatField(default=0.0)  # 0.0 to 1.0
    description = models.TextField(blank=True, null=True)
    model_version = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-prediction_date']
    
    def __str__(self):
        return f"Prediction for {self.user.username} - {self.category.name}: ${self.predicted_amount}"

class InsightReport(models.Model):
    """Model for storing AI-generated insights"""
    INSIGHT_TYPES = (
        ('spending_pattern', 'Spending Pattern'),
        ('budget_alert', 'Budget Alert'),
        ('saving_opportunity', 'Saving Opportunity'),
        ('anomaly_detection', 'Anomaly Detection'),
        ('financial_advice', 'Financial Advice'),
    )
    
    SEVERITY_LEVELS = (
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('alert', 'Alert'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS, default='info')
    title = models.CharField(max_length=100)
    description = models.TextField()
    data_json = models.JSONField(default=dict)  # For storing structured insight data
    is_read = models.BooleanField(default=False)
    action_taken = models.BooleanField(default=False)
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.title} ({self.insight_type})"
    
    @property
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

class FinancialGoalProgress(models.Model):
    """Model for tracking user progress towards financial goals"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    goal_name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    target_date = models.DateField()
    start_date = models.DateField(default=timezone.now)
    prediction_success_percent = models.FloatField(default=0.0)  # ML prediction of success chance
    recommendations = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['target_date']
    
    def __str__(self):
        return f"{self.goal_name} - Progress: {self.current_amount}/{self.target_amount} ({self.prediction_success_percent}%)"
    
    @property
    def progress_percentage(self):
        if self.target_amount:
            return (self.current_amount / self.target_amount) * 100
        return 0

class SpendingAnomaly(models.Model):
    """Model for storing detected spending anomalies"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE)
    anomaly_score = models.FloatField()  # Higher = more anomalous
    description = models.TextField()
    is_verified = models.BooleanField(default=False)  # Whether user has confirmed it's truly anomalous
    detected_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Spending Anomalies"
        ordering = ['-anomaly_score']
    
    def __str__(self):
        return f"Anomaly for {self.transaction.description} (Score: {self.anomaly_score})"

class TransactionInsight(models.Model):
    """Model for storing AI-generated insights about specific transactions"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='insight')
    insights_json = models.JSONField(default=dict)  # Stores structured insight data
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Insight for transaction {self.transaction.id}"

class AnomalyAlert(models.Model):
    """Model for storing anomaly alerts for users"""
    SEVERITY_LEVELS = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=100)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS, default='medium')
    anomaly_score = models.FloatField(default=0.0)  # 0.0 to 1.0
    is_resolved = models.BooleanField(default=False)
    is_false_positive = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.severity} (Resolved: {self.is_resolved})"

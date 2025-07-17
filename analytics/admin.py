from django.contrib import admin
from .models import SpendingPrediction, InsightReport, FinancialGoalProgress, SpendingAnomaly

@admin.register(SpendingPrediction)
class SpendingPredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'prediction_date', 'predicted_amount', 'confidence_score')
    list_filter = ('prediction_date', 'category')
    search_fields = ('user__username', 'description')
    date_hierarchy = 'prediction_date'

@admin.register(InsightReport)
class InsightReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'insight_type', 'severity', 'is_read', 'action_taken', 'generated_at')
    list_filter = ('insight_type', 'severity', 'is_read', 'action_taken')
    search_fields = ('title', 'description', 'user__username')
    date_hierarchy = 'generated_at'

@admin.register(FinancialGoalProgress)
class FinancialGoalProgressAdmin(admin.ModelAdmin):
    list_display = ('goal_name', 'user', 'target_amount', 'current_amount', 'target_date', 'prediction_success_percent')
    list_filter = ('target_date',)
    search_fields = ('goal_name', 'user__username', 'recommendations')
    date_hierarchy = 'target_date'

@admin.register(SpendingAnomaly)
class SpendingAnomalyAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction', 'anomaly_score', 'is_verified', 'detected_at')
    list_filter = ('is_verified', 'detected_at')
    search_fields = ('user__username', 'description', 'transaction__description')
    date_hierarchy = 'detected_at'

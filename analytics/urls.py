from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Dashboard and main views
    path('dashboard/', views.dashboard, name='dashboard'),
    path('spending-trends/', views.spending_trends, name='spending_trends'),
    path('income-analysis/', views.income_analysis, name='income_analysis'),
    path('budget-performance/', views.budget_performance, name='budget_performance'),
    path('savings-forecast/', views.savings_forecast, name='savings_forecast'),
    path('spending-predictions/', views.spending_predictions, name='spending_predictions'),
    path('anomaly-detection/', views.anomaly_detection, name='anomaly_detection'),
    path('anomaly-detection/settings/', views.update_anomaly_settings, name='update_anomaly_settings'),
    path('transaction-insights/<int:transaction_id>/', views.transaction_insights, name='transaction_insights'),
    path('category-insights/<int:category_id>/', views.category_insights, name='category_insights'),
    path('export-data/', views.export_data, name='export_data'),
    path('mark-anomaly-reviewed/', views.mark_anomaly_reviewed, name='mark_anomaly_reviewed'),
    path('ignore-similar-anomalies/', views.ignore_similar_anomalies, name='ignore_similar_anomalies'),
    
    # API Endpoints
    path('api/insights/', views.get_spending_insights, name='api_insights'),
    path('api/anomalies/', views.get_anomalies, name='api_anomalies'),
    path('api/anomalies/<int:anomaly_id>/', views.get_anomaly_detail, name='api_anomaly_detail'),
    path('api/anomalies/<int:anomaly_id>/status/', views.update_anomaly_status, name='api_update_anomaly_status'),
    path('api/budget-recommendations/', views.get_budget_recommendations, name='api_budget_recommendations'),
    path('api/budget-performance/<int:budget_id>/', views.analyze_budget_performance, name='api_budget_performance'),
    path('api/categorize-transaction/<int:transaction_id>/', views.categorize_transaction, name='api_categorize_transaction'),
    path('api/auto-categorize/', views.auto_categorize_transactions, name='api_auto_categorize'),
    path('api/spending-forecast/', views.spending_forecast, name='api_spending_forecast'),
] 
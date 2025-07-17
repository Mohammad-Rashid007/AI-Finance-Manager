from django.urls import path
from . import views

app_name = 'financial'

urlpatterns = [
    path('accounts/', views.account_list, name='account_list'),
    path('accounts/create/', views.account_create, name='account_create'),
    path('accounts/<int:account_id>/', views.account_detail, name='account_detail'),
    path('accounts/<int:account_id>/edit/', views.account_edit, name='account_edit'),
    path('accounts/<int:account_id>/delete/', views.account_delete, name='account_delete'),
    
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/create/', views.transaction_create, name='transaction_create'),
    path('transactions/<int:transaction_id>/', views.transaction_detail, name='transaction_detail'),
    path('transactions/<int:transaction_id>/edit/', views.transaction_edit, name='transaction_edit'),
    path('transactions/<int:transaction_id>/delete/', views.transaction_delete, name='transaction_delete'),
    path('transactions/export/', views.transaction_export, name='transaction_export'),
    
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:category_id>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:category_id>/delete/', views.category_delete, name='category_delete'),
    path('categories/spending/', views.category_spending_ajax, name='category_spending_ajax'),
    
    path('budgets/', views.budget_list, name='budget_list'),
    path('budgets/create/', views.budget_create, name='budget_create'),
    path('budgets/<int:budget_id>/', views.budget_detail, name='budget_detail'),
    path('budgets/<int:budget_id>/edit/', views.budget_edit, name='budget_edit'),
    path('budgets/<int:budget_id>/delete/', views.budget_delete, name='budget_delete'),
    
    path('goals/', views.savings_goal_list, name='savings_goal_list'),
    path('goals/create/', views.savings_goal_create, name='savings_goal_create'),
    path('goals/<int:goal_id>/', views.savings_goal_detail, name='savings_goal_detail'),
    path('goals/<int:goal_id>/edit/', views.savings_goal_edit, name='savings_goal_edit'),
    path('goals/<int:goal_id>/delete/', views.savings_goal_delete, name='savings_goal_delete'),
    path('goals/<int:goal_id>/contribute/', views.savings_goal_add_contribution, name='savings_goal_add_contribution'),
    
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/edit/', views.user_profile_edit, name='user_profile_edit'),
] 
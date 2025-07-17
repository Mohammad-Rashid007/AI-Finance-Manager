from django.contrib import admin
from .models import Category, Account, Transaction, Budget, SavingsGoal, UserProfile

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'user', 'is_default')
    list_filter = ('type', 'is_default')
    search_fields = ('name',)

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'account_type', 'balance', 'currency', 'is_active')
    list_filter = ('account_type', 'is_active', 'currency')
    search_fields = ('name', 'user__username')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('description', 'user', 'amount', 'transaction_type', 'category', 'date', 'account')
    list_filter = ('transaction_type', 'date', 'ai_categorized')
    search_fields = ('description', 'user__username', 'notes')
    date_hierarchy = 'date'

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'category', 'amount', 'period', 'start_date', 'is_active')
    list_filter = ('period', 'is_active')
    search_fields = ('name', 'user__username')
    date_hierarchy = 'start_date'

@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'target_amount', 'current_amount', 'target_date', 'status')
    list_filter = ('status',)
    search_fields = ('name', 'user__username', 'description')
    date_hierarchy = 'target_date'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'default_currency', 'enable_ai_insights', 'enable_ai_categorization')
    list_filter = ('default_currency', 'enable_ai_insights', 'enable_ai_categorization')
    search_fields = ('user__username', 'user__email')

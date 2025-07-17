from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Transaction, Account, Budget, Category, SavingsGoal, UserProfile

class UserRegisterForm(UserCreationForm):
    """Form for user registration"""
    email = forms.EmailField()
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class UserProfileForm(forms.ModelForm):
    """Form for user profile settings"""
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=30, required=False)
    email = forms.EmailField(required=False)
    
    class Meta:
        model = UserProfile
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'birth_date', 
            'address', 'default_currency', 'profile_picture', 
            'enable_ai_insights', 'enable_ai_categorization'
        ]
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email
            
    def save(self, commit=True):
        profile = super().save(commit=False)
        
        # Save user model fields
        if profile.user:
            profile.user.first_name = self.cleaned_data.get('first_name', '')
            profile.user.last_name = self.cleaned_data.get('last_name', '')
            profile.user.email = self.cleaned_data.get('email', '')
            profile.user.save()
            
        if commit:
            profile.save()
            
        return profile

class TransactionForm(forms.ModelForm):
    """Form for adding/editing transactions"""
    class Meta:
        model = Transaction
        fields = ['account', 'category', 'amount', 'transaction_type', 'date', 
                  'description', 'notes', 'receipt', 'is_recurring']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(TransactionForm, self).__init__(*args, **kwargs)
        
        # Filter account choices by user
        if self.user:
            self.fields['account'].queryset = Account.objects.filter(user=self.user)
            self.fields['category'].queryset = Category.objects.filter(
                user=self.user) | Category.objects.filter(is_default=True)

class TransferForm(forms.Form):
    """Form for transferring money between accounts"""
    from_account = forms.ModelChoiceField(queryset=Account.objects.none())
    to_account = forms.ModelChoiceField(queryset=Account.objects.none())
    amount = forms.DecimalField(decimal_places=2)
    description = forms.CharField(max_length=255, required=False)
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(TransferForm, self).__init__(*args, **kwargs)
        
        if self.user:
            self.fields['from_account'].queryset = Account.objects.filter(user=self.user)
            self.fields['to_account'].queryset = Account.objects.filter(user=self.user)

class AccountForm(forms.ModelForm):
    """Form for adding/editing accounts"""
    class Meta:
        model = Account
        fields = ['name', 'account_type', 'balance', 'currency', 'is_active']

class BudgetForm(forms.ModelForm):
    """Form for creating/editing budgets"""
    class Meta:
        model = Budget
        fields = ['name', 'category', 'amount', 'period', 'start_date', 'end_date', 'is_active']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(BudgetForm, self).__init__(*args, **kwargs)
        
        # Filter category choices by type (expense only) and user
        if self.user:
            self.fields['category'].queryset = Category.objects.filter(
                type='expense', user=self.user) | Category.objects.filter(
                type='expense', is_default=True)

class CategoryForm(forms.ModelForm):
    """Form for creating custom categories"""
    class Meta:
        model = Category
        fields = ['name', 'type', 'icon', 'color']

class SavingsGoalForm(forms.ModelForm):
    """Form for creating savings goals"""
    class Meta:
        model = SavingsGoal
        fields = ['name', 'target_amount', 'target_date', 'description']
        widgets = {
            'target_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

class DateRangeForm(forms.Form):
    """Form for selecting date ranges for reports"""
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'})) 
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class SpendingAnalyzer:
    """
    Analyzes spending patterns and provides insights and anomaly detection.
    """
    
    def __init__(self, user=None):
        self.anomaly_model = IsolationForest(
            contamination=0.05,  # Expect about 5% of transactions to be anomalies
            random_state=42
        )
        self.user = user
        
    def detect_anomalies(self, transactions):
        """
        Detect anomalies in a list of transactions
        Compatible with TransactionAnomalyDetector usage in views
        
        Args:
            transactions: List or QuerySet of Transaction objects
            
        Returns:
            List of dictionaries with anomaly information
        """
        anomaly_ids = self.detect_spending_anomalies(transactions)
        
        # Format the results to match expected output in views
        anomalies = []
        for tx_id in anomaly_ids:
            try:
                tx = next(t for t in transactions if t.id == tx_id)
                anomalies.append({
                    'id': tx.id,
                    'date': tx.date,
                    'description': tx.description,
                    'amount': float(tx.amount),
                    'category': tx.category.name if tx.category else 'Uncategorized',
                    'reason': 'Unusual spending pattern'
                })
            except StopIteration:
                continue
                
        return anomalies
        
    def generate_insights(self, transactions):
        """
        Generate insights based on transaction data
        Compatible with InsightsGenerator usage in views
        
        Args:
            transactions: List or QuerySet of Transaction objects
            
        Returns:
            List of insight dictionaries
        """
        # Analyze spending by category
        category_analysis = self.analyze_spending_by_category(transactions)
        
        # Start with insights from category analysis
        insights = []
        
        # Add the insights from category analysis
        for insight in category_analysis.get('insights', []):
            insights.append({
                'type': 'category_trend',
                'message': insight,
                'priority': 'medium'
            })
            
        # Add cash flow insights
        income_transactions = [tx for tx in transactions if tx.transaction_type == 'income']
        expense_transactions = [tx for tx in transactions if tx.transaction_type == 'expense']
        
        total_income = sum(float(tx.amount) for tx in income_transactions)
        total_expenses = sum(float(tx.amount) for tx in expense_transactions)
        net_flow = total_income - total_expenses
        
        if net_flow < 0:
            insights.append({
                'type': 'cash_flow',
                'message': f'Your expenses exceed your income by ${abs(net_flow):.2f} in this period.',
                'priority': 'high'
            })
        elif net_flow > 0 and net_flow < total_income * 0.1:
            insights.append({
                'type': 'cash_flow',
                'message': f'You saved only ${net_flow:.2f} ({(net_flow/total_income*100):.1f}% of income). Consider increasing savings.',
                'priority': 'medium'
            })
        elif net_flow > total_income * 0.2:
            insights.append({
                'type': 'cash_flow',
                'message': f'Great job! You saved ${net_flow:.2f} ({(net_flow/total_income*100):.1f}% of income).',
                'priority': 'low'
            })
            
        return insights
        
    def forecast_monthly_spending(self, transactions):
        """
        Alias for predict_monthly_spending to maintain compatibility
        """
        return self.predict_monthly_spending(transactions)
        
    def prepare_transaction_data(self, transactions):
        """
        Prepare transaction data for analysis by converting to a pandas DataFrame
        
        Args:
            transactions: QuerySet of Transaction objects
            
        Returns:
            DataFrame with transaction data
        """
        # Convert transactions to a list of dictionaries
        transaction_data = []
        
        for tx in transactions:
            data = {
                'id': tx.id,
                'date': tx.date,
                'amount': float(tx.amount),
                'category_id': tx.category.id if tx.category else None,
                'category_name': tx.category.name if tx.category else 'Uncategorized',
                'transaction_type': tx.transaction_type,
                'description': tx.description,
                'month': tx.date.month,
                'year': tx.date.year,
                'day_of_week': tx.date.weekday(),
                'day_of_month': tx.date.day
            }
            transaction_data.append(data)
            
        # Convert to DataFrame
        df = pd.DataFrame(transaction_data)
        
        # Add additional time-based features if data exists
        if not df.empty and 'date' in df.columns:
            # Convert date to datetime if it's not already
            if not pd.api.types.is_datetime64_any_dtype(df['date']):
                df['date'] = pd.to_datetime(df['date'])
            
            # Extract week of year
            df['week_of_year'] = df['date'].dt.isocalendar().week
            
            # Add quarter
            df['quarter'] = df['date'].dt.quarter
            
        return df
        
    def detect_spending_anomalies(self, transactions, sensitivity=None):
        """
        Detect anomalies in spending patterns
        
        Args:
            transactions: QuerySet of Transaction objects
            sensitivity: Optional override for sensitivity (uses user settings if None)
            
        Returns:
            List of transaction IDs identified as anomalies
        """
        # Only look at expense transactions
        expense_transactions = [tx for tx in transactions if tx.transaction_type == 'expense']
        
        if len(expense_transactions) < 10:
            logger.warning("Not enough expense transactions for anomaly detection")
            return []
            
        # Get user settings if available
        if self.user:
            try:
                profile = self.user.userprofile
                min_amount = profile.anomaly_min_amount
                if sensitivity is None:
                    sensitivity = profile.anomaly_detection_sensitivity
            except:
                min_amount = 100.0
                if sensitivity is None:
                    sensitivity = 1.0
        else:
            min_amount = 100.0
            if sensitivity is None:
                sensitivity = 1.0
                
        # Filter out transactions below minimum amount
        expense_transactions = [tx for tx in expense_transactions if float(tx.amount) >= min_amount]
            
        # Prepare data
        df = self.prepare_transaction_data(expense_transactions)
        
        if df.empty:
            return []
            
        # Features for anomaly detection
        features = ['amount']
        
        # Add category frequency as a feature
        category_counts = df['category_id'].value_counts()
        df['category_frequency'] = df['category_id'].map(category_counts)
        features.append('category_frequency')
        
        # Train the model
        try:
            # Scale the features
            X = df[features].copy()
            
            # Adjust contamination based on sensitivity
            self.anomaly_model.set_params(contamination=0.05 * sensitivity)
            
            # Fit and predict
            df['anomaly_score'] = self.anomaly_model.fit_predict(X)
            
            # Anomalies are labeled as -1
            anomalies = df[df['anomaly_score'] == -1]
            
            # Return the IDs of anomalous transactions
            return anomalies['id'].tolist()
            
        except Exception as e:
            logger.error("Error detecting anomalies: %s", str(e))
            return []
            
    def analyze_spending_by_category(self, transactions, months=3):
        """
        Analyze spending by category over the specified period
        
        Args:
            transactions: QuerySet of Transaction objects
            months: Number of months to analyze
            
        Returns:
            Dict with category insights
        """
        # Filter to only include expense transactions
        expense_transactions = [tx for tx in transactions if tx.transaction_type == 'expense']
        
        if not expense_transactions:
            return {
                'categories': [],
                'trends': [],
                'insights': []
            }
            
        # Prepare data
        df = self.prepare_transaction_data(expense_transactions)
        
        # Filter for the specified time period
        cutoff_date = timezone.now().date() - timedelta(days=30 * months)
        # Convert cutoff_date to pandas datetime for proper comparison
        cutoff_date_pd = pd.to_datetime(cutoff_date)
        
        if not df.empty and 'date' in df.columns:
            # Make sure date column is datetime
            if not pd.api.types.is_datetime64_any_dtype(df['date']):
                df['date'] = pd.to_datetime(df['date'])
            
            # Filter using pandas datetime
            df = df[df['date'] >= cutoff_date_pd]
        
        # Group by month and category
        if not df.empty:
            # Add month-year column for grouping
            df['month_year'] = df['date'].dt.to_period('M')
            
            # Group by month-year and category
            monthly_category_spending = df.groupby(['month_year', 'category_name'])['amount'].sum().unstack(fill_value=0)
            
            # Calculate total spending by category over the entire period
            total_by_category = df.groupby('category_name')['amount'].sum().sort_values(ascending=False)
            
            # Calculate average monthly spending by category
            monthly_average = df.groupby('category_name')['amount'].mean()
            
            # Calculate month-over-month change for each category
            category_trends = {}
            insights = []
            
            # For each of the top categories, analyze the trend
            for category in total_by_category.index[:5]:  # Top 5 categories
                if category in monthly_category_spending.columns:
                    category_data = monthly_category_spending[category].sort_index()
                    
                    # Skip categories with less than 2 months of data
                    if len(category_data) < 2:
                        continue
                        
                    # Calculate month-over-month change
                    mom_change = (category_data.iloc[-1] - category_data.iloc[-2]) / category_data.iloc[-2]
                    category_trends[category] = {
                        'trend': mom_change,
                        'current': float(category_data.iloc[-1]),
                        'previous': float(category_data.iloc[-2])
                    }
                    
                    # Generate insights
                    if mom_change > 0.2:  # More than 20% increase
                        insights.append(f"Your spending on {category} increased by {mom_change:.1%} compared to last month.")
                    elif mom_change < -0.2:  # More than 20% decrease
                        insights.append(f"You've reduced spending on {category} by {-mom_change:.1%} compared to last month.")
            
            # Return the analysis results
            return {
                'categories': [
                    {
                        'name': cat,
                        'total': float(total),
                        'average': float(monthly_average.get(cat, 0)),
                        'percentage': float(total / total_by_category.sum() * 100)
                    }
                    for cat, total in total_by_category.items()
                ],
                'trends': [
                    {
                        'category': cat,
                        'change': data['trend'],
                        'current_month': data['current'],
                        'previous_month': data['previous']
                    }
                    for cat, data in category_trends.items()
                ],
                'insights': insights
            }
        
        return {
            'categories': [],
            'trends': [],
            'insights': []
        }
        
    def predict_monthly_spending(self, transactions, months_ahead=3):
        """
        Predict future monthly spending based on historical data
        
        Args:
            transactions: QuerySet of Transaction objects
            months_ahead: Number of months to forecast
            
        Returns:
            Dict with monthly spending predictions
        """
        # Filter to only include expense transactions
        expense_transactions = [tx for tx in transactions if tx.transaction_type == 'expense']
        
        if len(expense_transactions) < 3:
            logger.warning("Not enough historical transactions for forecasting")
            return {'predictions': []}
            
        # Prepare data
        df = self.prepare_transaction_data(expense_transactions)
        
        # Group by month and calculate total spending
        if not df.empty:
            # Create month-year column for grouping
            df['month_year'] = df['date'].dt.to_period('M')
            
            # Calculate monthly totals
            monthly_totals = df.groupby('month_year')['amount'].sum()
            
            # Need at least 3 months of data for a reasonable prediction
            if len(monthly_totals) < 3:
                return {'predictions': []}
                
            # Use simple moving average for prediction
            avg_spending = monthly_totals.tail(3).mean()
            
            # Calculate trend based on last few months
            if len(monthly_totals) >= 6:
                recent = monthly_totals.tail(3).mean()
                older = monthly_totals.iloc[-6:-3].mean()
                trend_factor = (recent / older) if older > 0 else 1
            else:
                trend_factor = 1
                
            # Generate predictions
            predictions = []
            last_date = monthly_totals.index[-1].to_timestamp()
            
            for i in range(1, months_ahead + 1):
                next_month = (last_date + pd.DateOffset(months=i)).to_period('M')
                # Apply increasing trend for future months
                prediction = avg_spending * (trend_factor ** i)
                
                predictions.append({
                    'month': next_month.strftime('%b %Y'),
                    'amount': float(prediction)
                })
                
            return {'predictions': predictions}
            
        return {'predictions': []}
        
    def generate_spending_insights(self, transactions):
        """
        Alias for generate_insights method
        
        Args:
            transactions: List or QuerySet of Transaction objects
            
        Returns:
            List of insight dictionaries
        """
        return self.generate_insights(transactions) 
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, mean_squared_error
import joblib
import os
from datetime import datetime, timedelta
from django.conf import settings
from financial.models import Transaction, Category

# Path for saving ML models
MODEL_DIR = os.path.join(settings.BASE_DIR, 'analytics', 'ml_models')
os.makedirs(MODEL_DIR, exist_ok=True)

class TransactionCategorizer:
    """Machine learning model for auto-categorizing transactions based on description"""
    
    def __init__(self):
        self.model_path = os.path.join(MODEL_DIR, 'categorizer_model.pkl')
        self.model = None
        self.load_model()
    
    def load_model(self):
        """Load the trained model if it exists"""
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                return True
            except Exception as e:
                print(f"Error loading model: {e}")
                return False
        return False
    
    def save_model(self):
        """Save the trained model"""
        if self.model:
            joblib.dump(self.model, self.model_path)
    
    def train_model(self, user_id=None):
        """Train the transaction categorization model"""
        
        # Get training data - either for specific user or all users
        if user_id:
            transactions = Transaction.objects.filter(
                user_id=user_id, 
                category__isnull=False,
                ai_categorized=False  # Don't use AI-categorized transactions for training
            ).values('description', 'category__id')
        else:
            transactions = Transaction.objects.filter(
                category__isnull=False,
                ai_categorized=False
            ).values('description', 'category__id')
        
        if not transactions:
            return False
        
        # Convert to DataFrame
        df = pd.DataFrame.from_records(transactions)
        
        # Create and train model pipeline
        self.model = Pipeline([
            ('tfidf', TfidfVectorizer(max_features=5000, stop_words='english')),
            ('classifier', MultinomialNB())
        ])
        
        # Train the model
        self.model.fit(df['description'], df['category__id'])
        self.save_model()
        
        return True
    
    def predict_category(self, description):
        """Predict category for a transaction description"""
        if not self.model:
            if not self.train_model():
                return None
        
        # Predict category ID
        category_id = self.model.predict([description])[0]
        
        # Get confidence scores
        probabilities = self.model.predict_proba([description])[0]
        confidence = max(probabilities)
        
        return category_id, confidence

class SpendingPredictor:
    """Predicts future spending based on historical transactions"""
    
    def __init__(self):
        self.model_path = os.path.join(MODEL_DIR, 'spending_predictor_model.pkl')
        self.model = None
        self.feature_columns = None
        self.load_model()
    
    def load_model(self):
        """Load the trained model if it exists"""
        if os.path.exists(self.model_path):
            try:
                model_data = joblib.load(self.model_path)
                self.model = model_data['model']
                self.feature_columns = model_data['features']
                return True
            except Exception as e:
                print(f"Error loading model: {e}")
                return False
        return False
    
    def save_model(self):
        """Save the trained model"""
        if self.model and self.feature_columns:
            model_data = {
                'model': self.model,
                'features': self.feature_columns
            }
            joblib.dump(model_data, self.model_path)
    
    def prepare_features(self, transactions_df):
        """Prepare features for the spending prediction model"""
        
        # Group by date and category
        daily_spending = transactions_df.groupby(['date', 'category_id'])['amount'].sum().reset_index()
        
        # Create time-based features
        daily_spending['day_of_week'] = pd.to_datetime(daily_spending['date']).dt.dayofweek
        daily_spending['day_of_month'] = pd.to_datetime(daily_spending['date']).dt.day
        daily_spending['month'] = pd.to_datetime(daily_spending['date']).dt.month
        
        # Create lagging features (spending from previous days/weeks)
        for category in daily_spending['category_id'].unique():
            cat_data = daily_spending[daily_spending['category_id'] == category].sort_values('date')
            
            # Add previous spending patterns
            cat_data['prev_day_amount'] = cat_data['amount'].shift(1)
            cat_data['prev_week_amount'] = cat_data['amount'].shift(7)
            cat_data['rolling_7day_mean'] = cat_data['amount'].rolling(window=7, min_periods=1).mean()
            cat_data['rolling_30day_mean'] = cat_data['amount'].rolling(window=30, min_periods=1).mean()
            
            # Update the original dataframe
            daily_spending.loc[daily_spending['category_id'] == category] = cat_data
        
        # Fill missing values
        daily_spending.fillna(0, inplace=True)
        
        # One-hot encode category_id
        category_dummies = pd.get_dummies(daily_spending['category_id'], prefix='category')
        daily_spending = pd.concat([daily_spending, category_dummies], axis=1)
        
        # Features for prediction
        feature_columns = [col for col in daily_spending.columns if col not in ['date', 'amount', 'category_id']]
        
        return daily_spending, feature_columns
    
    def train_model(self, user_id):
        """Train the spending prediction model for a specific user"""
        
        # Get user's transaction data
        transactions = Transaction.objects.filter(
            user_id=user_id,
            transaction_type='expense'
        ).values('date', 'amount', 'category_id')
        
        if not transactions or len(transactions) < 30:  # Need enough data
            return False
        
        # Convert to DataFrame
        df = pd.DataFrame.from_records(transactions)
        
        # Prepare features
        processed_df, self.feature_columns = self.prepare_features(df)
        
        # Split data
        X = processed_df[self.feature_columns]
        y = processed_df['amount']
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Train model
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.model.fit(X_train, y_train)
        
        # Evaluate model
        y_pred = self.model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        
        print(f"Model MAE: {mae}, RMSE: {rmse}")
        
        # Save model
        self.save_model()
        
        return True
    
    def predict_future_spending(self, user_id, category_id, prediction_date):
        """Predict spending for a specific category and date"""
        
        if not self.model:
            if not self.train_model(user_id):
                return None, 0.0
        
        # Get recent transaction data to create features
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=60)  # Get last 60 days of data
        
        transactions = Transaction.objects.filter(
            user_id=user_id,
            date__gte=start_date,
            date__lte=end_date,
            transaction_type='expense'
        ).values('date', 'amount', 'category_id')
        
        if not transactions:
            return None, 0.0
        
        # Convert to DataFrame and prepare features
        df = pd.DataFrame.from_records(transactions)
        processed_df, _ = self.prepare_features(df)
        
        # Create a new row for prediction date
        pred_row = {
            'date': prediction_date,
            'amount': 0,  # Placeholder
            'category_id': category_id,
            'day_of_week': prediction_date.weekday(),
            'day_of_month': prediction_date.day,
            'month': prediction_date.month
        }
        
        # Add category one-hot encoding
        for col in processed_df.columns:
            if col.startswith('category_'):
                category_val = int(col.split('_')[1])
                pred_row[col] = 1 if category_val == category_id else 0
        
        # Add previous spending patterns from recent data
        category_data = processed_df[processed_df['category_id'] == category_id].sort_values('date')
        if not category_data.empty:
            pred_row['prev_day_amount'] = category_data['amount'].iloc[-1] if len(category_data) > 0 else 0
            pred_row['prev_week_amount'] = category_data['amount'].iloc[-7] if len(category_data) > 7 else 0
            pred_row['rolling_7day_mean'] = category_data['amount'].iloc[-7:].mean() if len(category_data) > 0 else 0
            pred_row['rolling_30day_mean'] = category_data['amount'].iloc[-30:].mean() if len(category_data) > 0 else 0
        else:
            pred_row['prev_day_amount'] = 0
            pred_row['prev_week_amount'] = 0
            pred_row['rolling_7day_mean'] = 0
            pred_row['rolling_30day_mean'] = 0
        
        # Create prediction DataFrame
        pred_df = pd.DataFrame([pred_row])
        
        # Make prediction
        try:
            pred_features = pred_df[self.feature_columns]
            prediction = self.model.predict(pred_features)[0]
            
            # Calculate confidence score based on feature importance
            feature_importance = self.model.feature_importances_
            confidence_score = min(0.95, sum(feature_importance) / len(feature_importance))
            
            return prediction, confidence_score
        except Exception as e:
            print(f"Prediction error: {e}")
            return None, 0.0

class AnomalyDetector:
    """Detects unusual spending transactions that deviate from normal patterns"""
    
    def __init__(self):
        self.model_path = os.path.join(MODEL_DIR, 'anomaly_detector_model.pkl')
        self.model = None
        self.scaler = None
        self.load_model()
    
    def load_model(self):
        """Load the trained model if it exists"""
        if os.path.exists(self.model_path):
            try:
                model_data = joblib.load(self.model_path)
                self.model = model_data['model']
                self.scaler = model_data['scaler']
                return True
            except Exception as e:
                print(f"Error loading model: {e}")
                return False
        return False
    
    def save_model(self):
        """Save the trained model"""
        if self.model and self.scaler:
            model_data = {
                'model': self.model,
                'scaler': self.scaler
            }
            joblib.dump(model_data, self.model_path)
    
    def train_model(self, user_id):
        """Train the anomaly detection model for a specific user"""
        
        # Get user's transaction data
        transactions = Transaction.objects.filter(
            user_id=user_id,
            transaction_type='expense'
        ).values('date', 'amount', 'category_id')
        
        if not transactions or len(transactions) < 50:  # Need enough data
            return False
        
        # Convert to DataFrame
        df = pd.DataFrame.from_records(transactions)
        
        # Create features for anomaly detection
        df['date'] = pd.to_datetime(df['date'])
        df['day_of_week'] = df['date'].dt.dayofweek
        df['day_of_month'] = df['date'].dt.day
        
        # Aggregate by category for historical patterns
        category_stats = df.groupby('category_id')['amount'].agg(['mean', 'std']).reset_index()
        category_stats.columns = ['category_id', 'category_mean', 'category_std']
        
        # Merge stats back
        df = pd.merge(df, category_stats, on='category_id', how='left')
        
        # Create features for anomaly detection
        df['amount_vs_mean'] = df['amount'] / df['category_mean']
        df['z_score'] = (df['amount'] - df['category_mean']) / df['category_std'].replace(0, 1)
        
        # Select features for anomaly detection
        features = df[['amount', 'amount_vs_mean', 'z_score', 'day_of_week', 'day_of_month']]
        
        # Normalize features
        self.scaler = StandardScaler()
        scaled_features = self.scaler.fit_transform(features)
        
        # Train model
        self.model = IsolationForest(contamination=0.05, random_state=42)
        self.model.fit(scaled_features)
        
        # Save model
        self.save_model()
        
        return True
    
    def detect_anomalies(self, transactions_data):
        """Detect anomalies in a list of transactions"""
        if not self.model or not self.scaler:
            return []
        
        if not transactions_data:
            return []
        
        # Convert to DataFrame
        df = pd.DataFrame(transactions_data)
        
        # Create features
        df['date'] = pd.to_datetime(df['date'])
        df['day_of_week'] = df['date'].dt.dayofweek
        df['day_of_month'] = df['date'].dt.day
        
        # Get category stats
        category_ids = df['category_id'].unique()
        category_stats = {}
        
        for cat_id in category_ids:
            cat_transactions = Transaction.objects.filter(
                category_id=cat_id
            ).values('amount')
            
            if cat_transactions:
                amounts = [t['amount'] for t in cat_transactions]
                category_stats[cat_id] = {
                    'mean': np.mean(amounts),
                    'std': np.std(amounts) if len(amounts) > 1 else 1.0
                }
            else:
                category_stats[cat_id] = {'mean': 0, 'std': 1.0}
        
        # Add category stats to DataFrame
        df['category_mean'] = df['category_id'].map(lambda x: category_stats.get(x, {'mean': 0})['mean'])
        df['category_std'] = df['category_id'].map(lambda x: category_stats.get(x, {'std': 1.0})['std'])
        
        # Create features
        df['amount_vs_mean'] = df['amount'] / df['category_mean'].replace(0, 1)
        df['z_score'] = (df['amount'] - df['category_mean']) / df['category_std'].replace(0, 1)
        
        # Select and scale features
        features = df[['amount', 'amount_vs_mean', 'z_score', 'day_of_week', 'day_of_month']]
        scaled_features = self.scaler.transform(features)
        
        # Detect anomalies
        anomaly_scores = self.model.decision_function(scaled_features)
        anomaly_predictions = self.model.predict(scaled_features)
        
        # Prepare results
        anomalies = []
        for i, (score, prediction) in enumerate(zip(anomaly_scores, anomaly_predictions)):
            if prediction == -1:  # -1 indicates anomaly
                anomaly_score = 1.0 - (score + 0.5)  # Convert to 0-1 range (higher = more anomalous)
                anomalies.append({
                    'index': i,
                    'transaction_id': transactions_data[i].get('id'),
                    'amount': transactions_data[i].get('amount'),
                    'anomaly_score': max(0, min(1, anomaly_score))
                })
        
        return sorted(anomalies, key=lambda x: x['anomaly_score'], reverse=True) 
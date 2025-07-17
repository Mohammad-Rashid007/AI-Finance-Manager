import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
import joblib
import os
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class TransactionCategorizer:
    """
    Machine learning model to automatically categorize financial transactions
    based on their descriptions.
    """
    
    def __init__(self):
        self.model = None
        self.model_path = os.path.join(settings.BASE_DIR, 'analytics', 'ml_models', 'transaction_categorizer.joblib')
        self.categories = {}
        self.category_id_map = {}
        self.min_confidence = 0.35  # Minimum confidence score to accept a prediction
        
    def _preprocess_text(self, text):
        """Preprocess transaction description for better feature extraction"""
        if not text:
            return ""
            
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters but keep spaces
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
        
    def train(self, transactions, force_retrain=False):
        """
        Train the model using historical transaction data
        
        Args:
            transactions: List of transaction objects with description and category
            force_retrain: Whether to force retraining even if model exists
        """
        if self.model and not force_retrain:
            logger.info("Model already loaded, skipping training")
            return
            
        if os.path.exists(self.model_path) and not force_retrain:
            logger.info("Loading existing model from %s", self.model_path)
            self._load_model()
            return
            
        logger.info("Training new transaction categorization model")
        
        # Extract descriptions and categories
        descriptions = []
        labels = []
        self.categories = {}
        
        for transaction in transactions:
            if not transaction.category:
                continue
                
            description = self._preprocess_text(transaction.description)
            category_id = transaction.category.id
            category_name = transaction.category.name
            
            descriptions.append(description)
            labels.append(category_id)
            
            self.categories[category_id] = category_name
            self.category_id_map[category_name] = category_id
            
        if len(descriptions) < 10:
            logger.warning("Not enough data to train model (only %d samples)", len(descriptions))
            return False
            
        # Create and train the model
        self.model = Pipeline([
            ('vectorizer', TfidfVectorizer(
                analyzer='word',
                ngram_range=(1, 2),
                min_df=2,
                max_features=5000
            )),
            ('classifier', MultinomialNB(alpha=0.1))
        ])
        
        # Split data for training and testing
        X_train, X_test, y_train, y_test = train_test_split(
            descriptions, labels, test_size=0.2, random_state=42
        )
        
        # Train the model
        self.model.fit(X_train, y_train)
        
        # Evaluate the model
        accuracy = self.model.score(X_test, y_test)
        logger.info("Model trained with accuracy: %.2f", accuracy)
        
        # Save the model
        self._save_model()
        
        return True
        
    def predict(self, description):
        """
        Predict the category for a transaction description
        
        Args:
            description: Transaction description text
            
        Returns:
            Tuple of (category_id, category_name, confidence_score)
            Returns (None, None, 0) if no prediction can be made
        """
        if not self.model:
            try:
                self._load_model()
            except Exception as e:
                logger.error("Failed to load model: %s", str(e))
                return None, None, 0
                
        if not self.model:
            logger.warning("No model available for prediction")
            return None, None, 0
            
        # Preprocess the description
        processed_text = self._preprocess_text(description)
        
        if not processed_text:
            return None, None, 0
            
        # Get prediction probabilities
        probabilities = self.model.predict_proba([processed_text])[0]
        
        # Get the highest probability and its index
        max_prob = max(probabilities)
        max_index = np.argmax(probabilities)
        
        # Get the predicted category ID
        predicted_category_id = self.model.classes_[max_index]
        
        # If confidence is too low, return None
        if max_prob < self.min_confidence:
            return None, None, 0
            
        # Get the category name
        category_name = self.categories.get(predicted_category_id)
        
        return predicted_category_id, category_name, max_prob
        
    def _save_model(self):
        """Save the trained model to disk"""
        if not self.model:
            logger.warning("No model to save")
            return
            
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        # Save the model
        model_data = {
            'model': self.model,
            'categories': self.categories,
            'category_id_map': self.category_id_map
        }
        
        joblib.dump(model_data, self.model_path)
        logger.info("Model saved to %s", self.model_path)
        
    def _load_model(self):
        """Load a trained model from disk"""
        if not os.path.exists(self.model_path):
            logger.warning("Model file not found at %s", self.model_path)
            return False
            
        try:
            model_data = joblib.load(self.model_path)
            self.model = model_data['model']
            self.categories = model_data['categories']
            self.category_id_map = model_data['category_id_map']
            logger.info("Model loaded from %s", self.model_path)
            return True
        except Exception as e:
            logger.error("Failed to load model: %s", str(e))
            return False 
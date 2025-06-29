import os
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import joblib
import json
from driver.Surrogate.drivers.Scaler_driver import DataScaler
from driver.Surrogate.surrogate_interface import SurrogateInterface

class RandomForestSurrogateDriver(SurrogateInterface):
    """
    Random Forest surrogate model driver implementing the SurrogateInterface.
    Uses scikit-learn's RandomForestRegressor for regression tasks.
    """
    
    def __init__(self, x_cols, y_cols, model=None, scaler=None):
        """
        Initialize the Random Forest surrogate driver with input/output columns and optional model/scaler
        
        Args:
            x_cols (list): List of input column names
            y_cols (list): List of output column names
            model (RandomForestRegressor, optional): Pre-trained RandomForestRegressor model
            scaler (DataScaler, optional): Pre-configured DataScaler
        """
        self.x_cols = x_cols
        self.y_cols = y_cols
        self.model = model
        
        # Initialize scaler if not provided
        if scaler is None:
            self.scaler = DataScaler()
        else:
            self.scaler = scaler
            
        # Store model versions
        self.model_versions = {}
        if model is not None:
            self.model_versions['base'] = model

    @classmethod
    def load_from_path(cls, model_path, x_cols, y_cols, **kwargs):
        """
        Load an existing model and scaler from a directory path
        
        Args:
            model_path (str): Path to the directory containing model files
            x_cols (list): List of input column names
            y_cols (list): List of output column names
            **kwargs: Additional arguments
            
        Returns:
            RandomForestSurrogateDriver: Initialized driver with loaded model
        """
        # Check if model_path is a directory or a specific file
        if os.path.isdir(model_path):
            # Try to find model.joblib and scaler.joblib in the directory
            model_file = os.path.join(model_path, "model.joblib")
            scaler_file = os.path.join(model_path, "scaler.joblib")
        else:
            # Assume model_path is the model file and look for scaler in the same directory
            model_file = model_path
            scaler_file = os.path.join(os.path.dirname(model_path), "scaler.joblib")
        
        # Load model and scaler
        return cls.load_from_files(model_file, scaler_file, x_cols, y_cols)

    @classmethod
    def load_from_files(cls, model_file, scaler_file, x_cols, y_cols):
        """
        Load an existing model and scaler from specific files
        
        Args:
            model_file (str): Path to the saved sklearn model (.joblib)
            scaler_file (str): Path to the saved scaler (.joblib)
            x_cols (list): List of input column names
            y_cols (list): List of output column names
            
        Returns:
            RandomForestSurrogateDriver: Initialized driver with loaded model
        """
        # Load model
        model = joblib.load(model_file)
        
        # Load scaler
        scaler = DataScaler()
        scaler.load_scalers(scaler_file)
        
        # Create surrogate driver instance
        return cls(x_cols=x_cols, y_cols=y_cols, model=model, scaler=scaler)

    def load_model(self, model_path):
        """
        Load a pre-trained surrogate model.
        
        Args:
            model_path (str): Path to the saved model
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if model_path is a directory or a specific file
            if os.path.isdir(model_path):
                # Try to find model.joblib and scaler.joblib in the directory
                model_file = os.path.join(model_path, "model.joblib")
                scaler_file = os.path.join(model_path, "scaler.joblib")
                
                # Also try to load model_info.json to update x_cols and y_cols
                info_file = os.path.join(model_path, "model_info.json")
                if os.path.exists(info_file):
                    with open(info_file, 'r') as f:
                        model_info = json.load(f)
                        self.x_cols = model_info.get('x_cols', self.x_cols)
                        self.y_cols = model_info.get('y_cols', self.y_cols)
            else:
                # Assume model_path is the model file and look for scaler in the same directory
                model_file = model_path
                scaler_file = os.path.join(os.path.dirname(model_path), "scaler.joblib")
            
            # Load model
            self.model = joblib.load(model_file)
            self.model_versions['base'] = self.model
            
            # Load scaler
            self.scaler = DataScaler()
            self.scaler.load_scalers(scaler_file)
            
            print(f"Model loaded successfully from {model_path}")
            return True
        except Exception as e:
            print(f"Error loading model: {str(e)}")
            return False

    def train(self, data, n_estimators=100, max_depth=None, min_samples_split=2,
              min_samples_leaf=1, max_features=None, random_state=42, test_size=0.2,
              model_save_path='Model_Fitting/00_Model_database/', model_version_name=None):
        """
        Train a new Random Forest model using the provided data
        
        Args:
            data (DataFrame): DataFrame containing both input and output columns
            n_estimators (int): Number of trees in the forest
            max_depth (int, optional): Maximum depth of the trees
            min_samples_split (int): Minimum number of samples required to split an internal node
            min_samples_leaf (int): Minimum number of samples required to be at a leaf node
            max_features (str or int): Number of features to consider for the best split
            random_state (int): Random seed for reproducibility
            test_size (float): Proportion of the dataset to include in the test split
            model_save_path (str): Directory to save the trained model
            model_version_name (str, optional): Optional name for the model version
            
        Returns:
            tuple: (model, metrics, model_folder) - The trained model, performance metrics, and save path
        """
        # Prepare input data
        X = data[self.x_cols]
        y = data[self.y_cols]
        
        # Scale data using DataScaler
        scaled_data = self.scaler.fit_transform(data, self.x_cols, self.y_cols)
        X_scaled = scaled_data[self.x_cols]
        y_scaled = scaled_data[self.y_cols]

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y_scaled, test_size=test_size, random_state=random_state
        )

        # Create and train the model
        rf = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            random_state=random_state,
            verbose=1
        )
        
        rf.fit(X_train, y_train)
        
        # Calculate metrics
        train_score = rf.score(X_train, y_train)
        test_score = rf.score(X_test, y_test)
        
        # Make predictions on test set for more detailed metrics
        y_pred_scaled = rf.predict(X_test)
        
        # Convert to DataFrame for inverse scaling
        if len(y_pred_scaled.shape) == 1:
            y_pred_scaled = y_pred_scaled.reshape(1, -1)
        y_pred_scaled_df = pd.DataFrame(y_pred_scaled, columns=self.y_cols)
        
        # Inverse scale predictions and actual values
        y_pred = self.scaler.inverse_transform_y(y_pred_scaled_df)
        
        # Convert y_test to DataFrame for inverse scaling
        y_test_df = pd.DataFrame(y_test, columns=self.y_cols)
        y_test_actual = self.scaler.inverse_transform_y(y_test_df)
        
        # Calculate detailed metrics for each output variable
        detailed_metrics = {}
        for col in self.y_cols:
            detailed_metrics[col] = {
                'r2': r2_score(y_test_actual[col], y_pred[col]),
                'mse': mean_squared_error(y_test_actual[col], y_pred[col]),
                'rmse': np.sqrt(mean_squared_error(y_test_actual[col], y_pred[col])),
                'mae': mean_absolute_error(y_test_actual[col], y_pred[col])
            }
        
        # Calculate feature importances
        feature_importances = {}
        for i, feature in enumerate(self.x_cols):
            feature_importances[feature] = float(rf.feature_importances_[i])
        
        metrics = {
            'train_score': train_score,
            'test_score': test_score,
            'detailed_metrics': detailed_metrics,
            'feature_importances': feature_importances
        }
        
        # Save model and scaler
        os.makedirs(model_save_path, exist_ok=True)
        
        if model_version_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_folder = f"rf_model_{timestamp}"
        else:
            model_folder = model_version_name
            
        model_dir = f"{model_save_path}/{model_folder}"
        os.makedirs(model_dir, exist_ok=True)
        
        model_file = f"{model_dir}/model.joblib"
        scaler_file = f"{model_dir}/scaler.joblib"
        
        joblib.dump(rf, model_file)
        self.scaler.save_scalers(scaler_file)
        
        # Save model info
        model_info = {
            'x_cols': self.x_cols,
            'y_cols': self.y_cols,
            'model_type': 'rf',
            'model_versions': ['base'],
            'hyperparameters': {
                'n_estimators': n_estimators,
                'max_depth': max_depth,
                'min_samples_split': min_samples_split,
                'min_samples_leaf': min_samples_leaf,
                'max_features': str(max_features)
            },
            'creation_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'metrics': {
                'train_score': float(train_score),
                'test_score': float(test_score)
            },
            'feature_importances': feature_importances
        }
        
        with open(f"{model_dir}/model_info.json", 'w') as f:
            json.dump(model_info, f, indent=4)
        
        # Update class attributes
        self.model = rf
        self.model_versions['base'] = rf
        
        print(f"Model trained and saved to {model_dir}")
        return rf, metrics, model_folder

    def predict(self, input_params, model_version=None):
        """
        Make predictions using the trained model
        
        Args:
            input_params (dict or DataFrame): Dictionary of input parameters or DataFrame with input columns
            model_version (str, optional): Optional model version to use for prediction
            
        Returns:
            dict or DataFrame: Predicted output values
        """
        # Select model version
        if model_version and model_version in self.model_versions:
            model_to_use = self.model_versions[model_version]
        else:
            model_to_use = self.model
            
        if model_to_use is None:
            raise ValueError("No model available for prediction. Train or load a model first.")

        # Handle different input types
        if isinstance(input_params, dict):
            # Single row prediction from dictionary
            X = pd.DataFrame([input_params])
            # Ensure all required columns are present
            for col in self.x_cols:
                if col not in X.columns:
                    raise ValueError(f"Required input column '{col}' not found in input data")
            X = X[self.x_cols]
        elif isinstance(input_params, pd.DataFrame):
            # Multiple row prediction from DataFrame
            # Ensure all required columns are present
            for col in self.x_cols:
                if col not in input_params.columns:
                    raise ValueError(f"Required input column '{col}' not found in input data")
            X = input_params[self.x_cols]
        else:
            raise ValueError("Input must be either a dictionary or a DataFrame")

        # Scale inputs - ensure X remains a DataFrame to preserve column names
        X_scaled = self.scaler.transform(X, x_only=True)
        
        # Make predictions
        y_pred_scaled = model_to_use.predict(X_scaled)
        
        # Convert to DataFrame for inverse scaling
        if len(y_pred_scaled.shape) == 1:
            y_pred_scaled = y_pred_scaled.reshape(1, -1)
        y_pred_scaled_df = pd.DataFrame(y_pred_scaled, columns=self.y_cols)
        
        # Inverse scale predictions
        y_pred = self.scaler.inverse_transform_y(y_pred_scaled_df)
        
        # Return format based on input type
        if isinstance(input_params, dict):
            return y_pred.iloc[0].to_dict()
        
        return y_pred

    def evaluate(self, test_data):
        """
        Evaluate the surrogate model performance on test data
        
        Args:
            test_data (DataFrame): Test data containing input and output columns
            
        Returns:
            dict: Dictionary of performance metrics
        """
        if self.model is None:
            raise ValueError("No model available for evaluation. Train or load a model first.")
            
        # Extract inputs and outputs
        X_test = test_data[self.x_cols]
        y_test = test_data[self.y_cols]
        
        # Scale data
        X_test_scaled = self.scaler.transform(X_test, x_only=True)
        
        # Make predictions
        y_pred_scaled = self.model.predict(X_test_scaled)
        
        # Convert to DataFrame for inverse scaling
        if len(y_pred_scaled.shape) == 1:
            y_pred_scaled = y_pred_scaled.reshape(1, -1)
        y_pred_scaled_df = pd.DataFrame(y_pred_scaled, columns=self.y_cols)
        
        # Inverse scale predictions
        y_pred = self.scaler.inverse_transform_y(y_pred_scaled_df)
        
        # Calculate metrics for each output variable
        metrics = {}
        overall_r2 = 0
        overall_mse = 0
        overall_rmse = 0
        overall_mae = 0
        
        for col in self.y_cols:
            col_metrics = {
                'r2': r2_score(y_test[col], y_pred[col]),
                'mse': mean_squared_error(y_test[col], y_pred[col]),
                'rmse': np.sqrt(mean_squared_error(y_test[col], y_pred[col])),
                'mae': mean_absolute_error(y_test[col], y_pred[col])
            }
            metrics[col] = col_metrics
            
            # Accumulate for overall metrics
            overall_r2 += col_metrics['r2']
            overall_mse += col_metrics['mse']
            overall_rmse += col_metrics['rmse']
            overall_mae += col_metrics['mae']
        
        # Calculate average metrics across all outputs
        num_outputs = len(self.y_cols)
        metrics['overall'] = {
            'r2': overall_r2 / num_outputs,
            'mse': overall_mse / num_outputs,
            'rmse': overall_rmse / num_outputs,
            'mae': overall_mae / num_outputs,
            'score': self.model.score(X_test_scaled, y_test)
        }
        
        # Add feature importances
        feature_importances = {}
        for i, feature in enumerate(self.x_cols):
            feature_importances[feature] = float(self.model.feature_importances_[i])
        
        metrics['feature_importances'] = feature_importances
        
        return metrics

    def add_model_version(self, model, version_name):
        """
        Add a new model version
        
        Args:
            model: Trained RandomForestRegressor model
            version_name: Name for the model version
        """
        self.model_versions[version_name] = model
        
    def reset_to_base(self):
        """Reset surrogate model to base version"""
        if 'base' in self.model_versions:
            self.model = self.model_versions['base']
        else:
            print("Warning: No base model found")
            
    def save_model(self, path, version_name=None):
        """
        Save the current model and scaler
        
        Args:
            path: Directory path to save the model
            version_name: Optional model version name to use in filename
            
        Returns:
            str: Path to the saved model directory
        """
        os.makedirs(path, exist_ok=True)
        
        if version_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            version_name = f"rf_model_{timestamp}"
            
        model_dir = f"{path}/{version_name}"
        os.makedirs(model_dir, exist_ok=True)
        
        model_to_save = self.model
        
        joblib.dump(model_to_save, f"{model_dir}/model.joblib")
        self.scaler.save_scalers(f"{model_dir}/scaler.joblib")
        
        # Save model info
        model_info = {
            'x_cols': self.x_cols,
            'y_cols': self.y_cols,
            'model_type': 'rf',
            'model_versions': list(self.model_versions.keys()),
            'creation_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Add feature importances if available
        if hasattr(self.model, 'feature_importances_'):
            feature_importances = {}
            for i, feature in enumerate(self.x_cols):
                feature_importances[feature] = float(self.model.feature_importances_[i])
            model_info['feature_importances'] = feature_importances
        
        with open(f"{model_dir}/model_info.json", 'w') as f:
            json.dump(model_info, f, indent=4)
        
        print(f"Model saved to {model_dir}")
        return model_dir

    @classmethod
    def load_complete_model(cls, model_dir):
        """
        Load a complete model including the model itself, scaler, and column information
        
        Args:
            model_dir: Directory containing the saved model files
            
        Returns:
            RandomForestSurrogateDriver: Initialized surrogate driver with loaded model and scaler
        """
        try:
            # Load model info
            with open(f"{model_dir}/model_info.json", 'r') as f:
                model_info = json.load(f)
            
            x_cols = model_info.get('x_cols', [])
            y_cols = model_info.get('y_cols', [])
            
            # Load model and scaler
            model_file = f"{model_dir}/model.joblib"
            scaler_file = f"{model_dir}/scaler.joblib"
            
            # Create and return surrogate driver instance
            return cls.load_from_files(model_file, scaler_file, x_cols, y_cols)
        except Exception as e:
            raise ValueError(f"Error loading model from {model_dir}: {str(e)}")


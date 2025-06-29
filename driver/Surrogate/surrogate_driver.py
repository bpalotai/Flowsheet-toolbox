import os
import json
import importlib
from datetime import datetime
from driver.Surrogate.surrogate_interface import SurrogateInterface

class SurrogateDriver:
    """
    Unified surrogate model driver that can work with different model types.
    This class acts as a factory and facade for the specific surrogate drivers.
    """
    
    # Registry of available surrogate drivers
    DRIVERS = {
        'neural_network': 'driver.Surrogate.drivers.ANN_driver.ANNSurrogateDriver',
        'random_forest': 'driver.Surrogate.drivers.RF_driver.RandomForestSurrogateDriver',
        # Add more drivers as they become available
        # 'xgboost': 'driver.Surrogate.drivers.XGBoost_driver.XGBoostSurrogateDriver',
        # 'gaussian_process': 'driver.Surrogate.drivers.GP_driver.GaussianProcessSurrogateDriver',
    }
    
    @classmethod
    def create(cls, model_type, x_cols, y_cols, **kwargs):
        """
        Create a new surrogate driver instance
        
        Args:
            model_type (str): Type of surrogate model
            x_cols (list): List of input column names
            y_cols (list): List of output column names
            **kwargs: Additional arguments to pass to the driver
            
        Returns:
            SurrogateInterface: Instance of a surrogate driver
        """
        if model_type not in cls.DRIVERS:
            raise ValueError(f"Unsupported model type: {model_type}. "
                            f"Supported types are: {', '.join(cls.DRIVERS.keys())}")
        
        # Import the driver class dynamically
        module_path, class_name = cls.DRIVERS[model_type].rsplit('.', 1)
        try:
            module = importlib.import_module(module_path)
            driver_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            # Fallback to ANNSurrogateDriver if the specific driver is not found
            print(f"Warning: Could not import {cls.DRIVERS[model_type]}: {str(e)}")
            print(f"Falling back to ANNSurrogateDriver")
            from driver.Surrogate.drivers.ANN_driver import ANNSurrogateDriver
            driver_class = ANNSurrogateDriver
        
        # Create an instance of the driver
        return driver_class(x_cols, y_cols, **kwargs)
    
    def train(self, data, **kwargs):
        """
        Train the surrogate model.
        
        Args:
            data (DataFrame): Training data
            **kwargs: Additional training parameters
            
        Returns:
            tuple: (trained_model, metrics, model_folder)
        """
        return self.driver.train(data, **kwargs)
    
    def predict(self, input_data):
        """
        Make predictions using the trained model.
        
        Args:
            input_data (dict or DataFrame): Input data for prediction
            
        Returns:
            dict or DataFrame: Predicted output values
        """
        # For inverse models, we need to handle the prediction differently
        # since the input_data contains what would normally be outputs
        if hasattr(self, 'is_inverse_model') and self.is_inverse_model:
            # For inverse models, the prediction interface should match the original interface
            # but internally we need to swap the columns
            return self.driver.predict(input_data)
        else:
            return self.driver.predict(input_data)
    
    def evaluate(self, test_data):
        """
        Evaluate the model on test data.
        
        Args:
            test_data (DataFrame): Test data containing both inputs and outputs
            
        Returns:
            dict: Dictionary of evaluation metrics
        """
        if hasattr(self.driver, 'evaluate'):
            return self.driver.evaluate(test_data)
        
        # Default implementation if driver doesn't have evaluate method
        from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
        import numpy as np
        
        # Make predictions
        X_test = test_data[self.x_cols]
        y_true = test_data[self.y_cols]
        
        y_pred = self.predict(X_test)
        
        # Calculate metrics for each output
        metrics = {'detailed': {}}
        overall_r2 = 0
        overall_mae = 0
        overall_mse = 0
        
        for col in self.y_cols:
            if col in y_pred.columns:
                r2 = r2_score(y_true[col], y_pred[col])
                mae = mean_absolute_error(y_true[col], y_pred[col])
                mse = mean_squared_error(y_true[col], y_pred[col])
                rmse = np.sqrt(mse)
                
                metrics['detailed'][col] = {
                    'r2': r2,
                    'mae': mae,
                    'mse': mse,
                    'rmse': rmse
                }
                
                overall_r2 += r2
                overall_mae += mae
                overall_mse += mse
        
        # Calculate overall metrics
        num_outputs = len(self.y_cols)
        if num_outputs > 0:
            metrics['overall'] = {
                'r2': overall_r2 / num_outputs,
                'mae': overall_mae / num_outputs,
                'mse': overall_mse / num_outputs,
                'rmse': np.sqrt(overall_mse / num_outputs),
                'score': overall_r2 / num_outputs  # Use R² as the overall score
            }
        
        return metrics
    
    def save_model(self, path, version_name=None):
        """
        Save the surrogate model.
        
        Args:
            path (str): Directory path to save the model
            version_name (str, optional): Optional version name
            
        Returns:
            str: Path to the saved model directory
        """
        return self.driver.save_complete_model(path, version_name)
    
    @classmethod
    def load_complete_model(cls, model_dir):
        """
        Load a complete model from a directory
        
        Args:
            model_dir (str): Directory containing the model files
            
        Returns:
            SurrogateInterface: Instance of a surrogate driver with loaded model
        """
        # Try to load model_info.json to determine model type
        import json
        try:
            with open(os.path.join(model_dir, 'model_info.json'), 'r') as f:
                model_info = json.load(f)
                
            model_type = model_info.get('model_type', 'neural_network')
            x_cols = model_info.get('x_cols', [])
            y_cols = model_info.get('y_cols', [])
            
            # Import the driver class dynamically
            if model_type in cls.DRIVERS:
                module_path, class_name = cls.DRIVERS[model_type].rsplit('.', 1)
                try:
                    module = importlib.import_module(module_path)
                    driver_class = getattr(module, class_name)
                    
                    # Load the model using the driver's load_from_path method
                    return driver_class.load_from_path(model_dir, x_cols, y_cols)
                except (ImportError, AttributeError) as e:
                    print(f"Warning: Could not import {cls.DRIVERS[model_type]}: {str(e)}")
            
            # Fallback to ANNSurrogateDriver
            from driver.Surrogate.drivers.ANN_driver import ANNSurrogateDriver
            return ANNSurrogateDriver.load_from_path(model_dir, x_cols, y_cols)
            
        except Exception as e:
            # If model_info.json doesn't exist or can't be parsed, try a generic approach
            print(f"Warning: Could not load model_info.json: {str(e)}")
            print("Trying generic model loading approach...")
            
            # Try to find model.joblib and scaler.joblib
            model_file = os.path.join(model_dir, 'model.joblib')
            scaler_file = os.path.join(model_dir, 'scaler.joblib')
            
            if os.path.exists(model_file) and os.path.exists(scaler_file):
                # Use ANNSurrogateDriver as a fallback
                from driver.Surrogate.drivers.ANN_driver import ANNSurrogateDriver
                return ANNSurrogateDriver.load_from_files(model_file, scaler_file, [], [])
            
            raise ValueError(f"Could not load model from {model_dir}")
    
    @classmethod
    def register_driver(cls, name, driver_path):
        """
        Register a new surrogate driver.
        
        Args:
            name (str): Name of the driver
            driver_path (str): Import path to the driver class
        """
        cls.DRIVERS[name.lower()] = driver_path
    
    @classmethod
    def get_available_drivers(cls):
        """
        Get a list of available surrogate drivers.
        
        Returns:
            list: List of available driver names
        """
        return list(cls.DRIVERS.keys())

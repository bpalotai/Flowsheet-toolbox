from abc import ABC, abstractmethod
import pandas as pd

class SurrogateInterface(ABC):
    """
    Abstract base class defining the interface for all surrogate model drivers.
    This ensures that all surrogate drivers implement the same methods
    and can be used interchangeably.
    """
    
    @abstractmethod
    def load_model(self, model_path):
        """
        Load a pre-trained surrogate model.
        
        Args:
            model_path (str): Path to the saved model
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def train(self, data, **kwargs):
        """
        Train a new surrogate model using the provided data.
        
        Args:
            data (DataFrame): Training data containing input and output columns
            **kwargs: Additional training parameters specific to the model type
            
        Returns:
            tuple: (model, metrics, model_path) - The trained model, performance metrics, and save path
        """
        pass
    
    @abstractmethod
    def predict(self, input_data):
        """
        Make predictions using the trained surrogate model.
        
        Args:
            input_data (dict or DataFrame): Input parameters for prediction
            
        Returns:
            dict or DataFrame: Predicted output values
        """
        pass
    
    @abstractmethod
    def save_model(self, path, version_name=None):
        """
        Save the current surrogate model.
        
        Args:
            path (str): Directory path to save the model
            version_name (str, optional): Optional name for the model version
            
        Returns:
            str: Path to the saved model
        """
        pass
    
    @abstractmethod
    def evaluate(self, test_data):
        """
        Evaluate the surrogate model performance on test data.
        
        Args:
            test_data (DataFrame): Test data containing input and output columns
            
        Returns:
            dict: Dictionary of performance metrics
        """
        pass

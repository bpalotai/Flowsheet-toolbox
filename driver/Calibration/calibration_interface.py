from abc import ABC, abstractmethod
import pandas as pd

class CalibrationInterface(ABC):
    """
    Abstract base class defining the interface for all calibration drivers.
    This ensures that all calibration drivers implement the same methods
    and can be used interchangeably.
    """
    
    @abstractmethod
    def load_model(self):
        """
        Load the calibration model.
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def set_parameters(self, parameters):
        """
        Set the parameters for calibration.
        
        Args:
            parameters (dict): Dictionary containing parameter settings
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def set_reference_data(self, reference_data):
        """
        Set the reference data for calibration.
        
        Args:
            reference_data (dict): Dictionary containing reference data
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def run_calibration(self):
        """
        Run the calibration process.
        
        Returns:
            dict: Dictionary containing calibration results
        """
        pass
    
    @abstractmethod
    def get_results(self):
        """
        Get the results of the calibration.
        
        Returns:
            dict: Dictionary containing calibration results
        """
        pass
    
    @abstractmethod
    def convert_to_dataframe(self, calibration_results):
        """
        Convert calibration results to a pandas DataFrame.
        
        Args:
            calibration_results (dict): The result from get_results method
            
        Returns:
            pandas.DataFrame: DataFrame with calibration results
        """
        pass
    
    @abstractmethod
    def validate_calibration(self, validation_data=None):
        """
        Validate the calibration results against validation data or the reference data.
        
        Args:
            validation_data (dict, optional): Dictionary with validation data.
                If None, uses the reference data.
                
        Returns:
            dict: Dictionary with validation metrics
        """
        pass
    
    @abstractmethod
    def close(self):
        """
        Close the calibration and release resources.
        """
        pass

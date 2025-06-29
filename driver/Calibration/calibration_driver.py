import os
import importlib
import json
from sklearn.preprocessing import MinMaxScaler
import numpy as np

class CalibrationDriver:
    """
    Unified calibration driver that can work with different calibration algorithms.
    This class acts as a factory and facade for the specific calibration drivers.
    It supports calibration using either surrogate models or direct simulation.
    """
    
    # Registry of available calibration drivers
    DRIVERS = {
        'pso': 'driver.Calibration.drivers.PSO_driver_withscaler.pso',
        # Add more drivers as they become available
        # 'ga': 'driver.Calibration.drivers.GA_driver.GeneticAlgorithm',
        # 'bayesian': 'driver.Calibration.drivers.Bayesian_driver.BayesianOptimization',
    }
    
    def __init__(self, calibration_type, driver, use_surrogate=False, **kwargs):
        """
        Initialize the calibration driver.
        
        Args:
            calibration_type (str): Type of calibration ('pso', 'ga', etc.)
            driver: The driver to use (simulation or surrogate)
            use_surrogate (bool): Whether to use a surrogate model
            **kwargs: Additional arguments to pass to the specific driver
        """
        self.calibration_type = calibration_type.lower()
        self.driver = driver
        self.use_surrogate = use_surrogate
        self.parameters = {}
        self.reference_data = {}
        self.results = None
        self.scaler = None
        
        # Load the appropriate driver
        if self.calibration_type not in self.DRIVERS:
            raise ValueError(f"Unsupported calibration type: {calibration_type}. "
                            f"Supported types are: {', '.join(self.DRIVERS.keys())}")
        
        # Import the driver class dynamically
        module_path, class_name = self.DRIVERS[self.calibration_type].rsplit('.', 1)
        module = importlib.import_module(module_path)
        driver_class = getattr(module, class_name)
        
        # Store the driver class for later instantiation
        self.driver_class = driver_class
        self.driver_kwargs = kwargs
        self.calibration_driver = None
    
    def load_model(self):
        """Load the model (simulation or surrogate)"""
        return self.driver.load_model()
    
    def set_parameters(self, parameters):
        """
        Set the parameters for calibration.
        
        Args:
            parameters (dict): Dictionary containing:
                - 'particles': List of dictionaries with initial parameter values
                - 'opt_params': List of parameter names to optimize
                - 'param_limits': Dictionary with min/max limits for each parameter
                
        Returns:
            bool: True if successful
        """
        self.parameters = parameters
        return True
    
    def set_reference_data(self, reference_data):
        """
        Set the reference data for calibration.
        
        Args:
            reference_data (dict): Dictionary containing:
                - 'y_true': Dictionary with target output values
                - 'y_fitt': Dictionary with fitting weights and standard deviations
                
        Returns:
            bool: True if successful
        """
        self.reference_data = reference_data
        
        # If using surrogate, get the scaler from the surrogate model
        if self.use_surrogate and hasattr(self.driver, 'scaler'):
            self.scaler = self.driver.scaler
        # Otherwise, create a new scaler for the reference data
        elif 'y_true' in reference_data:
            y_values = list(reference_data['y_true'].values())
            self.scaler = MinMaxScaler()
            self.scaler.fit(np.array(y_values).reshape(-1, 1))
        
        return True
    
    def run_calibration(self):
        """
        Run the calibration process.
        
        Returns:
            dict: Dictionary containing calibration results
        """
        # Create an instance of the driver with the necessary parameters
        self.calibration_driver = self.driver_class(
            particles=self.parameters.get('particles', {}),
            opt_params=self.parameters.get('opt_params', []),
            y_true=self.reference_data.get('y_true', {}),
            y_fitt=self.reference_data.get('y_fitt', {}),
            y_scaler=self.scaler.y_scaler if hasattr(self.scaler, 'y_scaler') else self.scaler,
            fitparamlimit=self.parameters.get('param_limits', {}),
            **self.driver_kwargs
        )
        
        # Run the calibration
        costs, io_values, best_params, best_cost = self.calibration_driver.run_pso(self.driver)
        
        # Store the results
        self.results = {
            'costs': costs,
            'io_values': io_values,
            'best_params': best_params,
            'best_cost': best_cost
        }
        
        return self.results
    
    def get_results(self):
        """
        Get the results of the calibration.
        
        Returns:
            dict: Dictionary containing calibration results
        """
        if self.results is None:
            raise ValueError("No calibration results available. Run calibration first.")
        
        return self.results
    
    def convert_to_dataframe(self, calibration_results=None):
        """
        Convert calibration results to a pandas DataFrame.
        
        Args:
            calibration_results (dict, optional): The result from get_results method.
                If None, uses the stored results.
                
        Returns:
            dict: Dictionary containing DataFrames with calibration results
        """
        import pandas as pd
        
        if calibration_results is None:
            calibration_results = self.get_results()
        
        result_dfs = {}
        
        # Create DataFrame for costs
        if 'costs' in calibration_results:
            costs_data = calibration_results['costs']
            iterations = range(len(costs_data))
            costs_df = pd.DataFrame({
                'Iteration': iterations,
                'Cost': [min(cost) for cost in costs_data]
            })
            result_dfs['costs'] = costs_df
        
        # Create DataFrame for best parameters
        if 'best_params' in calibration_results:
            best_params = calibration_results['best_params']
            params_df = pd.DataFrame([best_params])
            result_dfs['best_params'] = params_df
        
        # Create DataFrame for IO values if available
        if 'io_values' in calibration_results:
            io_values = calibration_results['io_values']
            # Flatten the IO values structure
            flattened_io = []
            for iteration, particles in enumerate(io_values):
                for particle_idx, particle_values in enumerate(particles):
                    row = {'Iteration': iteration, 'Particle': particle_idx}
                    for i, val in enumerate(particle_values):
                        row[f'Value_{i}'] = val
                    flattened_io.append(row)
            
            io_df = pd.DataFrame(flattened_io)
            result_dfs['io_values'] = io_df
        
        return result_dfs
    
    def close(self):
        """Close the calibration and release resources"""
        # Clean up any resources
        self.calibration_driver = None
        
        # Check if the driver has a close method before calling it
        if hasattr(self.driver, 'close') and callable(getattr(self.driver, 'close')):
            return self.driver.close()
        
        return True
    
    def validate_calibration(self, validation_data=None):
        """
        Validate the calibration results against validation data or the reference data.
        
        Args:
            validation_data (dict, optional): Dictionary with validation data.
                If None, uses the reference data.
                
        Returns:
            dict: Dictionary with validation metrics
        """
        if self.results is None:
            raise ValueError("No calibration results available. Run calibration first.")
        
        validation_data = validation_data or self.reference_data.get('y_true', {})
        best_params = self.results['best_params']
        
        # Run the model with the best parameters
        prediction = self.driver.predict(best_params)
        
        # Calculate validation metrics
        metrics = {}
        for key in validation_data:
            if key in prediction:
                metrics[key] = {
                    'true': validation_data[key],
                    'predicted': prediction[key],
                    'error': abs(validation_data[key] - prediction[key]),
                    'percent_error': abs(validation_data[key] - prediction[key]) / validation_data[key] * 100 if validation_data[key] != 0 else float('inf')
                }
        
        # Calculate overall metrics
        true_values = [validation_data[k] for k in metrics.keys()]
        pred_values = [prediction[k] for k in metrics.keys()]
        
        from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
        
        overall_metrics = {
            'mse': mean_squared_error(true_values, pred_values),
            'rmse': mean_squared_error(true_values, pred_values, squared=False),
            'mae': mean_absolute_error(true_values, pred_values),
            'r2': r2_score(true_values, pred_values) if len(true_values) > 1 else float('nan')
        }
        
        return {
            'parameter_metrics': metrics,
            'overall_metrics': overall_metrics
        }
    
    @classmethod
    def register_driver(cls, name, driver_path):
        """
        Register a new calibration driver.
        
        Args:
            name (str): Name of the driver
            driver_path (str): Import path to the driver class
        """
        cls.DRIVERS[name.lower()] = driver_path
    
    @classmethod
    def get_available_drivers(cls):
        """
        Get a list of available calibration drivers.
        
        Returns:
            list: List of available driver names
        """
        return list(cls.DRIVERS.keys())
    
    @staticmethod
    def load_config(config_file):
        """
        Load calibration configuration from a JSON file.
        
        Args:
            config_file (str): Path to the configuration file
            
        Returns:
            dict: Calibration configuration dictionary
        """
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading configuration file: {str(e)}")
            return {}
    
    def save_config(self, config_file):
        """
        Save the current calibration configuration to a JSON file.
        
        Args:
            config_file (str): Path to save the configuration file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            config = {
                'parameters': self.parameters,
                'reference_data': self.reference_data,
                'use_surrogate': self.use_surrogate
            }
            
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving configuration file: {str(e)}")
            return False

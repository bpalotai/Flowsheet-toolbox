import numpy as np
import pandas as pd
from smt.sampling_methods import LHS, Random, FullFactorial
from driver.Sampling.sampling_interface import SamplingInterface

class SMTSamplingDriver(SamplingInterface):
    """
    Unified sampling driver that can work with different sampling methods from SMT.
    """
    
    # Registry of available sampling methods
    SAMPLING_METHODS = {
        'lhs': 'LHS',
        'random': 'Random',
        'full_factorial': 'FullFactorial'
    }
    
    def __init__(self, param_ranges, random_seed=42, sampling_method='lhs'):
        """
        Initialize the SMT sampling driver.
        
        Args:
            param_ranges (dict): Dictionary of parameter ranges with format:
                                {param_name: {'min': min_value, 'max': max_value}}
            random_seed (int): Random seed for reproducibility
            sampling_method (str): Type of sampling method ('lhs', 'random', 'full_factorial')
        """
        self.param_ranges = param_ranges
        self.sampling_method = sampling_method.lower()
        self.random_seed = random_seed
        self.param_names = list(param_ranges.keys())
        
        # Validate sampling method
        if self.sampling_method not in self.SAMPLING_METHODS:
            raise ValueError(f"Unsupported sampling method: {sampling_method}. "
                            f"Supported methods are: {', '.join(self.SAMPLING_METHODS.keys())}")
        
        # Create xlimits for SMT sampling (min and max for each parameter)
        self.xlimits = []
        for param in self.param_names:
            self.xlimits.append([
                self.param_ranges[param]['min'],
                self.param_ranges[param]['max']
            ])
        
        # Convert xlimits to a NumPy array
        self.xlimits = np.array(self.xlimits)
    
    def generate_samples(self, num_samples=None):
        """
        Generate samples using the specified sampling method.
        
        Args:
            num_samples (int, optional): Number of samples to generate.
                                        If None, uses a default value.
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated samples
        """
        if not num_samples:
            # Default number of samples based on sampling method
            if self.sampling_method == 'full_factorial':
                # For full factorial, default to 2 levels per parameter
                num_samples = 2 ** len(self.param_names)
            else:
                # For other methods, use a reasonable default
                num_samples = 100
        
        print(f"Generating {num_samples} samples using {self.sampling_method} method with seed {self.random_seed}")
        
        # Create the appropriate sampler based on the method
        if self.sampling_method == 'lhs':
            # LHS supports random_state
            sampling = LHS(xlimits=self.xlimits, random_state=self.random_seed)
            x = sampling(num_samples)
        
        elif self.sampling_method == 'random':
            # For Random, we need to set the seed using numpy directly
            # since Random doesn't have a random_state parameter
            np.random.seed(self.random_seed)
            sampling = Random(xlimits=self.xlimits)
            x = sampling(num_samples)
        
        elif self.sampling_method == 'full_factorial':
            # For full factorial, we need to determine the number of levels
            # based on the desired number of samples
            
            # Calculate levels as the nth root of num_samples, where n is the number of parameters
            # Then round to the nearest integer
            n_params = len(self.param_names)
            levels = max(2, round(num_samples ** (1/n_params)))
            
            print(f"Using {levels} levels for each parameter in full factorial design")
            
            # For FullFactorial, we need to create the sampling object with the number of levels
            # The levels parameter is passed during initialization, not during the call
            sampling = FullFactorial(xlimits=self.xlimits, levels=[levels] * n_params)
            
            # FullFactorial doesn't take any arguments in the call
            x = sampling()
        
        # Create a DataFrame to store all samples
        samples_df = pd.DataFrame()
        
        # Add parameters to DataFrame
        for i, param in enumerate(self.param_names):
            samples_df[param] = x[:, i]
        
        return samples_df
    
    def export_samples(self, samples_df, export_path):
        """
        Export the generated samples to an Excel file.
        
        Args:
            samples_df (pandas.DataFrame): DataFrame containing the samples
            export_path (str): Path to export the samples
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            samples_df.to_excel(export_path, index=False)
            print(f"Exported {len(samples_df)} samples to {export_path}")
            return True
        except Exception as e:
            print(f"Error exporting samples: {e}")
            return False
    
    @classmethod
    def get_available_methods(cls):
        """
        Get a list of available sampling methods.
        
        Returns:
            list: List of available sampling method names
        """
        return list(cls.SAMPLING_METHODS.keys())
    
    @classmethod
    def register_method(cls, name, method_class):
        """
        Register a new sampling method.
        
        Args:
            name (str): Name of the sampling method
            method_class (str): Name of the SMT sampling class
        """
        cls.SAMPLING_METHODS[name.lower()] = method_class


class LHSSamplingDriver(SamplingInterface):
    """
    Driver for Latin Hypercube Sampling using SMT.
    """
    
    def __init__(self, param_ranges, random_seed=42, **kwargs):
        """
        Initialize the LHS sampling driver.
        
        Args:
            param_ranges (dict): Dictionary of parameter ranges with format:
                                {param_name: {'min': min_value, 'max': max_value}}
            random_seed (int): Random seed for reproducibility
            **kwargs: Additional arguments (not used but included for compatibility)
        """
        self.param_ranges = param_ranges
        self.random_seed = random_seed
        self.param_names = list(param_ranges.keys())
        
        # Create xlimits for LHS sampling
        self.xlimits = []
        for param in self.param_names:
            self.xlimits.append([
                self.param_ranges[param]['min'],
                self.param_ranges[param]['max']
            ])
        
        # Convert xlimits to a NumPy array
        self.xlimits = np.array(self.xlimits)
    
    def generate_samples(self, num_samples=100):
        """
        Generate samples using Latin Hypercube Sampling.
        
        Args:
            num_samples (int, optional): Number of samples to generate.
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated samples
        """
        print(f"Generating {num_samples} LHS samples with seed {self.random_seed}")
        
        # Create LHS sampler with random_state parameter (LHS supports this)
        sampling = LHS(xlimits=self.xlimits, random_state=self.random_seed)
        
        # Generate samples
        x = sampling(num_samples)
        
        # Create a DataFrame to store all samples
        samples_df = pd.DataFrame()
        
        # Add parameters to DataFrame
        for i, param in enumerate(self.param_names):
            samples_df[param] = x[:, i]
        
        return samples_df
    
    def export_samples(self, samples_df, export_path):
        """
        Export the generated samples to an Excel file.
        
        Args:
            samples_df (pandas.DataFrame): DataFrame containing the samples
            export_path (str): Path to export the samples
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            samples_df.to_excel(export_path, index=False)
            print(f"Exported {len(samples_df)} LHS samples to {export_path}")
            return True
        except Exception as e:
            print(f"Error exporting samples: {e}")
            return False


class RandomSamplingDriver(SamplingInterface):
    """
    Driver for Random Sampling using SMT.
    """
    
    def __init__(self, param_ranges, random_seed=42, **kwargs):
        """
        Initialize the Random sampling driver.
        
        Args:
            param_ranges (dict): Dictionary of parameter ranges with format:
                                {param_name: {'min': min_value, 'max': max_value}}
            random_seed (int): Random seed for reproducibility
            **kwargs: Additional arguments (not used but included for compatibility)
        """
        self.param_ranges = param_ranges
        self.random_seed = random_seed
        self.param_names = list(param_ranges.keys())
        
        # Create xlimits for Random sampling
        self.xlimits = []
        for param in self.param_names:
            self.xlimits.append([
                self.param_ranges[param]['min'],
                self.param_ranges[param]['max']
            ])
        
        # Convert xlimits to a NumPy array
        self.xlimits = np.array(self.xlimits)
    
    def generate_samples(self, num_samples=100):
        """
        Generate samples using Random Sampling.
        
        Args:
            num_samples (int, optional): Number of samples to generate.
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated samples
        """
        print(f"Generating {num_samples} Random samples with seed {self.random_seed}")
        
        # Set numpy random seed directly since Random doesn't support random_state
        np.random.seed(self.random_seed)
        
        # Create Random sampler (without random_state parameter)
        sampling = Random(xlimits=self.xlimits)
        
        # Generate samples
        x = sampling(num_samples)
        
        # Create a DataFrame to store all samples
        samples_df = pd.DataFrame()
        
        # Add parameters to DataFrame
        for i, param in enumerate(self.param_names):
            samples_df[param] = x[:, i]
        
        return samples_df
    
    def export_samples(self, samples_df, export_path):
        """
        Export the generated samples to an Excel file.
        
        Args:
            samples_df (pandas.DataFrame): DataFrame containing the samples
            export_path (str): Path to export the samples
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            samples_df.to_excel(export_path, index=False)
            print(f"Exported {len(samples_df)} Random samples to {export_path}")
            return True
        except Exception as e:
            print(f"Error exporting samples: {e}")
            return False


class FullFactorialSamplingDriver(SamplingInterface):
    """
    Driver for Full Factorial Sampling using SMT.
    """
    
    def __init__(self, param_ranges, random_seed=42, **kwargs):
        """
        Initialize the Full Factorial sampling driver.
        
        Args:
            param_ranges (dict): Dictionary of parameter ranges with format:
                                {param_name: {'min': min_value, 'max': max_value}}
            random_seed (int): Random seed for reproducibility (not used for full factorial)
            **kwargs: Additional arguments (not used but included for compatibility)
        """
        self.param_ranges = param_ranges
        self.random_seed = random_seed  # Not used for full factorial but kept for consistency
        self.param_names = list(param_ranges.keys())
        
        # Create xlimits for Full Factorial sampling
        self.xlimits = []
        for param in self.param_names:
            self.xlimits.append([
                self.param_ranges[param]['min'],
                self.param_ranges[param]['max']
            ])
        
        # Convert xlimits to a NumPy array
        self.xlimits = np.array(self.xlimits)
    
    def generate_samples(self, num_samples=None):
        """
        Generate samples using Full Factorial Sampling.
        
        Args:
            num_samples (int, optional): Target number of samples to generate.
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated samples
        """
        if not num_samples:
            # Default to a reasonable number if not specified
            num_samples = 2 ** len(self.param_names)
        
        print(f"Generating Full Factorial design with approximately {num_samples} samples")
        
        # Create the FullFactorial sampler and generate samples
        # This follows the example from SMT documentation
        sampling = FullFactorial(xlimits=self.xlimits)
        x = sampling(num_samples)
        
        print(f"Generated {x.shape[0]} samples")
        
        # Create a DataFrame to store all samples
        samples_df = pd.DataFrame()
        
        # Add parameters to DataFrame
        for i, param in enumerate(self.param_names):
            samples_df[param] = x[:, i]
        
        return samples_df

    
    def export_samples(self, samples_df, export_path):
        """
        Export the generated samples to an Excel file.
        
        Args:
            samples_df (pandas.DataFrame): DataFrame containing the samples
            export_path (str): Path to export the samples
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            samples_df.to_excel(export_path, index=False)
            print(f"Exported {len(samples_df)} Full Factorial samples to {export_path}")
            return True
        except Exception as e:
            print(f"Error exporting samples: {e}")
            return False


import numpy as np
import pandas as pd

from driver.Sampling.sampling_interface import SamplingInterface

class MonteCarloSamplingDriver(SamplingInterface):
    """
    Driver for Monte Carlo Sampling using SMT's Random sampler with additional options.
    """
    
    def __init__(self, param_ranges, random_seed=42, **kwargs):
        """
        Initialize the Monte Carlo sampling driver.
        
        Args:
            param_ranges (dict): Dictionary of parameter ranges with format:
                                {param_name: {'min': min_value, 'max': max_value}}
            random_seed (int): Random seed for reproducibility
            **kwargs: Additional arguments including distribution types
        """
        self.param_ranges = param_ranges
        self.random_seed = random_seed
        self.param_names = list(param_ranges.keys())
        self.distributions = kwargs.get('distributions', {})
        
        # Create xlimits for sampling
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
        Generate samples using Monte Carlo Sampling with specified distributions.
        
        Args:
            num_samples (int, optional): Number of samples to generate.
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated samples
        """
        print(f"Generating {num_samples} Monte Carlo samples with seed {self.random_seed}")
        
        # Set numpy random seed
        np.random.seed(self.random_seed)
        
        # Create a DataFrame to store all samples
        samples_df = pd.DataFrame()
        
        # Generate samples for each parameter based on its distribution
        for i, param in enumerate(self.param_names):
            min_val = self.xlimits[i, 0]
            max_val = self.xlimits[i, 1]
            
            # Get distribution for this parameter (default to uniform)
            dist_type = self.distributions.get(param, 'uniform')
            
            if dist_type == 'uniform':
                # Uniform distribution between min and max
                samples = np.random.uniform(min_val, max_val, num_samples)
            
            elif dist_type == 'normal':
                # Normal distribution with mean at center and std dev of range/6
                # (so that ~99.7% of values fall within the range)
                mean = (min_val + max_val) / 2
                std_dev = (max_val - min_val) / 6
                samples = np.random.normal(mean, std_dev, num_samples)
                # Clip values to ensure they stay within bounds
                samples = np.clip(samples, min_val, max_val)
            
            elif dist_type == 'triangular':
                # Triangular distribution with mode at center
                mode = (min_val + max_val) / 2
                samples = np.random.triangular(min_val, mode, max_val, num_samples)
            
            elif dist_type == 'lognormal':
                # Log-normal distribution
                # We need to transform parameters to work with log-normal
                # Assuming we want the log-normal distribution to have 
                # most of its mass between min_val and max_val
                if min_val <= 0:
                    # Log-normal can't handle negative or zero values
                    # Shift everything to be positive
                    shift = abs(min_val) + 1
                    min_val += shift
                    max_val += shift
                    
                    # Calculate parameters for log-normal
                    mu = np.log(min_val) + (np.log(max_val) - np.log(min_val)) / 2
                    sigma = (np.log(max_val) - np.log(min_val)) / 4
                    
                    # Generate samples and shift back
                    samples = np.random.lognormal(mu, sigma, num_samples) - shift
                else:
                    # Calculate parameters for log-normal
                    mu = np.log(min_val) + (np.log(max_val) - np.log(min_val)) / 2
                    sigma = (np.log(max_val) - np.log(min_val)) / 4
                    
                    # Generate samples
                    samples = np.random.lognormal(mu, sigma, num_samples)
                
                # Clip values to ensure they stay within bounds
                samples = np.clip(samples, self.xlimits[i, 0], self.xlimits[i, 1])

            elif dist_type == 'exponential':
                # Exponential distribution
                # For exponential distribution, we use the max value as a scale parameter
                # The min value is used as an offset
                
                # Calculate scale parameter (lambda)
                # We'll use max_val as a guide for the scale
                # Typically, we want most of the probability mass to be below max_val
                scale = max_val / 3  # This ensures ~95% of values are below max_val
                
                # Generate samples
                samples = np.random.exponential(scale=scale, size=num_samples)
                
                # Add min_val as offset
                samples = samples + min_val
                
                # Clip values to ensure they stay within bounds
                samples = np.clip(samples, min_val, max_val)
                
            else:
                # Default to uniform if distribution not recognized
                samples = np.random.uniform(min_val, max_val, num_samples)
            
            # Add to DataFrame
            samples_df[param] = samples
        
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
            print(f"Exported {len(samples_df)} Monte Carlo samples to {export_path}")
            return True
        except Exception as e:
            print(f"Error exporting samples: {e}")
            return False

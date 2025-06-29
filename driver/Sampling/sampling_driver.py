import importlib

class SamplingDriver:
    """
    Factory class for creating sampling drivers based on the specified method.
    """
    
    # Registry of available sampling drivers
    DRIVERS = {
        'lhs': 'driver.Sampling.drivers.SMT_driver.LHSSamplingDriver',
        'random': 'driver.Sampling.drivers.SMT_driver.RandomSamplingDriver',
        'full_factorial': 'driver.Sampling.drivers.SMT_driver.FullFactorialSamplingDriver',
        'montecarlo': 'driver.Sampling.drivers.MonteCarlo_driver.MonteCarloSamplingDriver',
    }
    
    def __init__(self, method, param_ranges, random_seed=42, **kwargs):
        """
        Initialize the sampling driver.
        
        Args:
            method (str): Sampling method ('lhs', 'random', 'full_factorial')
            param_ranges (dict): Dictionary of parameter ranges
            random_seed (int): Random seed for reproducibility
            **kwargs: Additional arguments to pass to the specific driver
        """
        self.method = method.lower()
        self.param_ranges = param_ranges
        self.random_seed = random_seed
        
        # Load the appropriate driver
        if self.method not in self.DRIVERS:
            raise ValueError(f"Unsupported sampling method: {method}. "
                            f"Supported methods are: {', '.join(self.DRIVERS.keys())}")
        
        # Import the driver class dynamically
        module_path, class_name = self.DRIVERS[self.method].rsplit('.', 1)
        module = importlib.import_module(module_path)
        driver_class = getattr(module, class_name)
        
        # Create an instance of the driver
        self.driver = driver_class(param_ranges, random_seed, **kwargs)
    
    def generate_samples(self, num_samples=None):
        """Generate samples using the specified method"""
        return self.driver.generate_samples(num_samples)
    
    def export_samples(self, samples_df, export_path):
        """Export the generated samples to a file"""
        return self.driver.export_samples(samples_df, export_path)
    
    @classmethod
    def register_driver(cls, name, driver_path):
        """
        Register a new sampling driver.
        
        Args:
            name (str): Name of the driver
            driver_path (str): Import path to the driver class
        """
        cls.DRIVERS[name.lower()] = driver_path
    
    @classmethod
    def get_available_drivers(cls):
        """
        Get a list of available sampling drivers.
        
        Returns:
            list: List of available driver names
        """
        return list(cls.DRIVERS.keys())

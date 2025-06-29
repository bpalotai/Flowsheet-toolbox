import os
import importlib
import json

class SimulationDriver:
    """
    Unified simulation driver that can work with different simulation engines.
    This class acts as a factory and facade for the specific simulation drivers.
    """
    
    # Registry of available simulation drivers
    DRIVERS = {
        'hysys': 'driver.Simulation.drivers.Hysys_driver.HysysSimulationDriver',
        # Add more drivers as they become available
        # 'aspen': 'driver.Simulation.drivers.Aspen_driver.AspenSimulationDriver',
        # 'prosim': 'driver.Simulation.drivers.Prosim_driver.ProsimSimulationDriver',
    }
    
    def __init__(self, sim_type, model_path, cols_mapping=None, **kwargs):
        """
        Initialize the simulation driver.
        
        Args:
            sim_type (str): Type of simulation ('hysys', 'aspen', etc.)
            model_path (str): Path to the simulation model file
            cols_mapping (dict, optional): Mapping of parameters for reading/writing
            **kwargs: Additional arguments to pass to the specific driver
        """
        self.sim_type = sim_type.lower()
        self.model_path = model_path
        self.cols_mapping = cols_mapping or {}
        
        # Load the appropriate driver
        if self.sim_type not in self.DRIVERS:
            raise ValueError(f"Unsupported simulation type: {sim_type}. "
                            f"Supported types are: {', '.join(self.DRIVERS.keys())}")
        
        # Import the driver class dynamically
        module_path, class_name = self.DRIVERS[self.sim_type].rsplit('.', 1)
        module = importlib.import_module(module_path)
        driver_class = getattr(module, class_name)
        
        # Create an instance of the driver
        self.driver = driver_class(model_path, cols_mapping, **kwargs)
    
    def load_model(self):
        """Load the simulation model"""
        return self.driver.load_model()
    
    def explore(self):
        """Explore the simulation model"""
        return self.driver.explore()
    
    def sim_write(self, data):
        """Write input data to the simulation"""
        return self.driver.sim_write(data)
    
    def sim_run(self):
        """Run the simulation"""
        return self.driver.sim_run()
    
    def sim_read(self, include_inputs=False, flatten_components=True):
        """Read output data from the simulation"""
        return self.driver.sim_read(include_inputs, flatten_components)
    
    def predict(self, data, include_inputs=False, flatten_components=True):
        """Run a prediction with the simulation model"""
        return self.driver.predict(data, include_inputs, flatten_components)
    
    def convert_to_dataframe(self, sim_read_result):
        """Convert simulation read results to a pandas DataFrame"""
        return self.driver.convert_to_dataframe(sim_read_result)
    
    def close(self):
        """Close the simulation and release resources"""
        return self.driver.close()
    
    @classmethod
    def register_driver(cls, name, driver_path):
        """
        Register a new simulation driver.
        
        Args:
            name (str): Name of the driver
            driver_path (str): Import path to the driver class
        """
        cls.DRIVERS[name.lower()] = driver_path
    
    @classmethod
    def get_available_drivers(cls):
        """
        Get a list of available simulation drivers.
        
        Returns:
            list: List of available driver names
        """
        return list(cls.DRIVERS.keys())
    
    @staticmethod
    def load_mapping(mapping_file):
        """
        Load parameter mapping from a JSON file.
        
        Args:
            mapping_file (str): Path to the mapping file
            
        Returns:
            dict: Parameter mapping dictionary
        """
        try:
            with open(mapping_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading mapping file: {str(e)}")
            return {}
    
    def save_mapping(self, mapping_file):
        """
        Save the current parameter mapping to a JSON file.
        
        Args:
            mapping_file (str): Path to save the mapping file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(mapping_file, 'w') as f:
                json.dump(self.cols_mapping, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving mapping file: {str(e)}")
            return False
from abc import ABC, abstractmethod
import pandas as pd

class SimulationInterface(ABC):
    """
    Abstract base class defining the interface for all simulation drivers.
    This ensures that all simulation drivers implement the same methods
    and can be used interchangeably.
    """
    
    @abstractmethod
    def load_model(self):
        """
        Load the simulation model.
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def explore(self):
        """
        Explore the simulation model to discover its structure.
        
        Returns:
            dict: Dictionary containing discovered model elements
        """
        pass
    
    @abstractmethod
    def sim_write(self, data):
        """
        Write input data to the simulation.
        
        Args:
            data (dict): Dictionary containing input parameters and values
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def sim_run(self):
        """
        Run the simulation.
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def sim_read(self, include_inputs=False, flatten_components=True):
        """
        Read output data from the simulation.
        
        Args:
            include_inputs (bool): Whether to include input parameters in the output
            flatten_components (bool): Whether to flatten component-specific parameters
            
        Returns:
            dict: Dictionary containing output parameters and values
        """
        pass
    
    @abstractmethod
    def predict(self, data, include_inputs=False, flatten_components=True):
        """
        Run a prediction with the simulation model.
        
        Args:
            data (dict): Dictionary containing input parameters and values
            include_inputs (bool): Whether to include input parameters in the output
            flatten_components (bool): Whether to flatten component-specific parameters
            
        Returns:
            dict: Dictionary containing output parameters and values
        """
        pass
    
    @abstractmethod
    def convert_to_dataframe(self, sim_read_result):
        """
        Convert simulation read results to a pandas DataFrame.
        
        Args:
            sim_read_result (dict): The result from sim_read method
            
        Returns:
            pandas.DataFrame: DataFrame with simulation results
        """
        pass
    
    @abstractmethod
    def close(self):
        """
        Close the simulation and release resources.
        """
        pass

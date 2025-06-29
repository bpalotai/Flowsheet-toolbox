from abc import ABC, abstractmethod

class SamplingInterface(ABC):
    """
    Abstract base class defining the interface for all sampling drivers.
    This ensures that all sampling drivers implement the same methods.
    """
    
    @abstractmethod
    def generate_samples(self, num_samples=None):
        """
        Generate samples based on the defined parameter ranges.
        
        Args:
            num_samples (int, optional): Number of samples to generate.
                                        If None, uses the value from settings.
            
        Returns:
            pandas.DataFrame: DataFrame containing the generated samples
        """
        pass
    
    @abstractmethod
    def export_samples(self, samples_df, export_path):
        """
        Export the generated samples to a file.
        
        Args:
            samples_df (pandas.DataFrame): DataFrame containing the samples
            export_path (str): Path to export the samples
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        pass

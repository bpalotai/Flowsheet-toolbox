import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import joblib
import os

class DataScaler:
    def __init__(self):
        self.x_scaler = StandardScaler()
        self.y_scaler = StandardScaler()
        self.x_cols = None
        self.y_cols = None


    def save_scalers(self, path):
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(path), exist_ok=True)
        scaler_data = {
            'x_scaler': self.x_scaler,
            'y_scaler': self.y_scaler,
            'x_cols': self.x_cols,
            'y_cols': self.y_cols
        }
        joblib.dump(scaler_data, path)

    def load_scalers(self, path):
        scaler_data = joblib.load(path)
        self.x_scaler = scaler_data['x_scaler']
        self.y_scaler = scaler_data['y_scaler']
        self.x_cols = scaler_data['x_cols']
        self.y_cols = scaler_data['y_cols']

    def fit_transform(self, df, x_cols, y_cols, scaling=True):
        self.x_cols = x_cols
        self.y_cols = y_cols
        
        xdf = df[x_cols]
        ydf = df[y_cols]
        
        if scaling:
            x_scaled = self.x_scaler.fit_transform(xdf)
            y_scaled = self.y_scaler.fit_transform(ydf)
            
            xdf_scaled = pd.DataFrame(x_scaled, columns=x_cols)
            ydf_scaled = pd.DataFrame(y_scaled, columns=y_cols)
        else:
            xdf_scaled = xdf
            ydf_scaled = ydf
            
        scaled_df = pd.concat([xdf_scaled, ydf_scaled], axis=1)
        return scaled_df
    
    def transform(self, df, x_only=False):
        """
        Transform data using the fitted scalers
        
        Args:
            df: DataFrame or ndarray containing input columns (and optionally output columns)
            x_only: If True, only transform and return input columns
            
        Returns:
            DataFrame or ndarray with scaled values (returns same type as input)
        """
        
        # Track if input was a numpy array to return same type
        input_is_numpy = isinstance(df, np.ndarray)
        
        # Convert numpy array to DataFrame if needed
        if input_is_numpy:
            # Create column names based on the shape
            if df.ndim == 1:
                # 1D array - reshape to 2D
                df = df.reshape(1, -1)
                columns = self.x_cols if len(self.x_cols) == df.shape[1] else [f'x{i}' for i in range(df.shape[1])]
            else:
                # 2D array
                columns = self.x_cols if len(self.x_cols) == df.shape[1] else [f'x{i}' for i in range(df.shape[1])]
            
            # Convert to DataFrame
            df = pd.DataFrame(df, columns=columns)
        
        # Ensure we have a DataFrame with proper column names
        if not isinstance(df, pd.DataFrame):
            raise ValueError("Input must be a pandas DataFrame or numpy array")
        
        # Special case: if the DataFrame has the same number of columns as x_cols or y_cols
        # but different names, assume it's in the same order and rename the columns
        if len(df.columns) == len(self.x_cols) and not all(col in df.columns for col in self.x_cols):
            # Create a copy with renamed columns
            df = df.copy()
            df.columns = self.x_cols
        elif len(df.columns) == len(self.y_cols) and not all(col in df.columns for col in self.y_cols):
            # Create a copy with renamed columns
            df = df.copy()
            df.columns = self.y_cols
        
        # Check that all required input columns are present
        for col in self.x_cols:
            if col not in df.columns:
                raise ValueError(f"Required input column '{col}' not found: {col}")
        
        # Extract input data
        xdf = df[self.x_cols]
        
        # Transform input data while preserving DataFrame structure
        x_scaled = self.x_scaler.transform(xdf)
        xdf_scaled = pd.DataFrame(x_scaled, columns=self.x_cols, index=df.index)
        
        # If only input transformation is requested, return just that
        if x_only:
            return xdf_scaled.values if input_is_numpy else xdf_scaled
        
        # For output columns, check if they exist in the input DataFrame
        ydf_scaled = None
        if all(col in df.columns for col in self.y_cols):
            ydf = df[self.y_cols]
            y_scaled = self.y_scaler.transform(ydf)
            ydf_scaled = pd.DataFrame(y_scaled, columns=self.y_cols, index=df.index)
        
        # Combine and return the result
        if ydf_scaled is not None:
            result = pd.concat([xdf_scaled, ydf_scaled], axis=1)
        else:
            result = xdf_scaled
        
        # Return numpy array if input was numpy
        if input_is_numpy:
            return result.values
        
        return result

    def inverse_transform_y(self, y_scaled):
        if isinstance(y_scaled, pd.DataFrame):
            y_orig = self.y_scaler.inverse_transform(y_scaled)
            return pd.DataFrame(y_orig, columns=self.y_cols)
        return pd.DataFrame(
            self.y_scaler.inverse_transform(y_scaled), 
            columns=self.y_cols
        )

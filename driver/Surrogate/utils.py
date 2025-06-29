import os
import json
import pandas as pd
import numpy as np
from driver.Surrogate.surrogate_driver import SurrogateDriver

def list_available_models(base_dir='Model_Fitting/00_Model_database/'):
    """
    List all available surrogate models in the model database
    
    Args:
        base_dir (str): Base directory for model storage
        
    Returns:
        list: List of dictionaries containing model information
    """
    models = []
    
    if not os.path.exists(base_dir):
        return models
    
    # Iterate through all subdirectories
    for model_dir in os.listdir(base_dir):
        model_path = os.path.join(base_dir, model_dir)
        
        # Check if it's a directory and contains model_info.json
        if os.path.isdir(model_path) and os.path.exists(os.path.join(model_path, 'model_info.json')):
            try:
                # Load model info
                with open(os.path.join(model_path, 'model_info.json'), 'r') as f:
                    model_info = json.load(f)
                
                # Extract key information
                model_type = model_info.get('model_type', 'unknown')
                x_cols = model_info.get('x_cols', [])
                y_cols = model_info.get('y_cols', [])
                creation_date = model_info.get('creation_date', 'unknown')
                metrics = model_info.get('metrics', {})
                
                # Add to list
                models.append({
                    'name': model_dir,
                    'type': model_type,
                    'path': model_path,
                    'inputs': x_cols,
                    'outputs': y_cols,
                    'creation_date': creation_date,
                    'test_score': metrics.get('test_score', 'N/A'),
                    'train_score': metrics.get('train_score', 'N/A')
                })
            except Exception as e:
                print(f"Error reading model info for {model_dir}: {str(e)}")
    
    # Sort by creation date (newest first)
    models.sort(key=lambda x: x.get('creation_date', ''), reverse=True)
    
    return models

def load_model_by_name(model_name, base_dir='Model_Fitting/00_Model_database/'):
    """
    Load a surrogate model by name
    
    Args:
        model_name (str): Name of the model directory
        base_dir (str): Base directory for model storage
        
    Returns:
        SurrogateDriver: Loaded surrogate model driver
    """
    model_path = os.path.join(base_dir, model_name)
    
    if not os.path.exists(model_path):
        raise ValueError(f"Model {model_name} not found in {base_dir}")
    
    # Load the model using the SurrogateDriver factory
    return SurrogateDriver.load_complete_model(model_path)

def compare_models(model_list, test_data, base_dir='Model_Fitting/00_Model_database/'):
    """
    Compare multiple surrogate models using the same test data
    
    Args:
        model_list (list): List of model names to compare
        test_data (DataFrame): Test data containing input and output columns
        base_dir (str): Base directory for model storage
        
    Returns:
        DataFrame: Comparison of model performance metrics
    """
    results = []
    
    for model_name in model_list:
        try:
            # Load the model
            model = load_model_by_name(model_name, base_dir)
            
            # Evaluate on test data
            metrics = model.evaluate(test_data)
            
            # Extract overall metrics
            overall = metrics.get('overall', {})
            
            # Add to results
            results.append({
                'model_name': model_name,
                'model_type': model.driver.__class__.__name__,
                'r2_score': overall.get('r2', 0),
                'mse': overall.get('mse', 0),
                'rmse': overall.get('rmse', 0),
                'mae': overall.get('mae', 0),
                'score': overall.get('score', 0)
            })
        except Exception as e:
            print(f"Error evaluating model {model_name}: {str(e)}")
    
    # Convert to DataFrame and sort by R² score (higher is better)
    if results:
        df = pd.DataFrame(results)
        return df.sort_values('r2_score', ascending=False)
    else:
        return pd.DataFrame()

def create_ensemble_predictions(model_list, input_data, weights=None, base_dir='Model_Fitting/00_Model_database/'):
    """
    Create ensemble predictions by combining multiple models
    
    Args:
        model_list (list): List of model names to include in the ensemble
        input_data (dict or DataFrame): Input data for prediction
        weights (list, optional): List of weights for each model (must match model_list length)
        base_dir (str): Base directory for model storage
        
    Returns:
        dict or DataFrame: Ensemble predictions
    """
    if not model_list:
        raise ValueError("Model list cannot be empty")
    
    # Validate weights if provided
    if weights is not None:
        if len(weights) != len(model_list):
            raise ValueError("Number of weights must match number of models")
        # Normalize weights to sum to 1
        weights = np.array(weights) / sum(weights)
    else:
        # Equal weights if not provided
        weights = np.ones(len(model_list)) / len(model_list)
    
    # Load all models
    models = []
    for model_name in model_list:
        try:
            model = load_model_by_name(model_name, base_dir)
            models.append(model)
        except Exception as e:
            print(f"Error loading model {model_name}: {str(e)}")
    
    if not models:
        raise ValueError("No valid models could be loaded")
    
    # Make predictions with each model
    all_predictions = []
    for i, model in enumerate(models):
        try:
            pred = model.predict(input_data)
            all_predictions.append(pred)
        except Exception as e:
            print(f"Error making predictions with model {model_list[i]}: {str(e)}")
            # Adjust weights if a model fails
            weights = np.delete(weights, i)
            weights = weights / sum(weights)  # Renormalize
    
    if not all_predictions:
        raise ValueError("No valid predictions could be made")
    
    # Combine predictions based on input type
    if isinstance(input_data, dict):
        # Single prediction case
        ensemble_pred = {}
        for col in all_predictions[0].keys():
            ensemble_pred[col] = sum(pred[col] * w for pred, w in zip(all_predictions, weights))
        return ensemble_pred
    else:
        # DataFrame case
        ensemble_df = pd.DataFrame(index=all_predictions[0].index)
        for col in all_predictions[0].columns:
            ensemble_df[col] = sum(pred[col] * w for pred, w in zip(all_predictions, weights))
        return ensemble_df

import os
import json
import pandas as pd
import numpy as np
from flask import Blueprint, request, jsonify, render_template, current_app, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
from datetime import datetime
import tempfile
import joblib
from sklearn.model_selection import train_test_split
import time

from api.database import db, Case, SimulationResult, Surrogate
from driver.Surrogate.surrogate_driver import SurrogateDriver
from sklearn.metrics import r2_score, mean_absolute_error

# Create blueprint
surrogate_bp = Blueprint('surrogate', __name__, url_prefix='/surrogate')

@surrogate_bp.route('/')
def surrogate_index():
    """Render the surrogate models index page"""
    # Get all surrogate models
    models = Surrogate.query.all()
    return render_template('surrogate/surrogate.html', models=models, active_page='surrogate')

@surrogate_bp.route('/new')
def create_model():
    """Render the create surrogate model page"""
    # Get all cases for the dropdown
    cases = Case.query.all()
    return render_template('surrogate/create.html', cases=cases, active_page='surrogate')

@surrogate_bp.route('/model/<int:model_id>')
def model_detail(model_id):
    """Render the surrogate model detail page"""
    # Get the model
    model = Surrogate.query.get_or_404(model_id)
    # Get the case
    case = Case.query.get_or_404(model.case_id)
    
    return render_template('surrogate/detail.html', model=model, case=case, active_page='surrogate')

@surrogate_bp.route('/api/parameters/<int:case_id>', methods=['GET'])
def get_case_parameters(case_id):
    """Get available parameters for a case"""
    case = Case.query.get_or_404(case_id)
    
    # Format the parameters for the frontend
    result = {
        'inputs': {},
        'outputs': {}
    }
    
    if case.parameters:
        # Process input parameters
        if 'InputParams' in case.parameters:
            result['inputs'] = case.parameters['InputParams']
        
        # Process output parameters
        if 'OutputParameters' in case.parameters:
            result['outputs'] = case.parameters['OutputParameters']
    
    return jsonify(result)

@surrogate_bp.route('/api/components/<int:case_id>', methods=['GET'])
def get_components(case_id):
    """Get components for a material stream parameter"""
    case = Case.query.get_or_404(case_id)
    
    # Get stream name and parameter type from query parameters
    stream_name = request.args.get('stream')
    param_type = request.args.get('param_type')
    
    if not stream_name or not param_type:
        return jsonify({"error": "Stream name and parameter type are required"}), 400
    
    try:
        # Check if we have component data in the case parameters
        if case.parameters:
            # Look for component data in input parameters
            if 'InputParams' in case.parameters and 'MaterialStream' in case.parameters['InputParams']:
                for param_name, param_config in case.parameters['InputParams']['MaterialStream'].items():
                    if param_config.get('StreamName') == stream_name and param_config.get('ParameterType') == param_type:
                        # If we have component data for this parameter, return it
                        if 'Components' in param_config:
                            components = param_config['Components']
                            
                            # Determine unit based on parameter type
                            unit = param_config.get('UOM', '')
                            if not unit:
                                if param_type == 'MassFrac':
                                    unit = 'fraction'
                                elif param_type == 'MassFlow':
                                    unit = 'kg/h'
                                elif param_type == 'MolarFlow':
                                    unit = 'kgmole/h'
                            
                            return jsonify({
                                "components": components,
                                "unit": unit
                            })
            
            # If not found in input parameters, check output parameters
            if 'OutputParameters' in case.parameters and 'MaterialStream' in case.parameters['OutputParameters']:
                for param_name, param_config in case.parameters['OutputParameters']['MaterialStream'].items():
                    if param_config.get('StreamName') == stream_name and param_config.get('ParameterType') == param_type:
                        # If we have component data for this parameter, return it
                        if 'Components' in param_config:
                            components = param_config['Components']
                            
                            # Determine unit based on parameter type
                            unit = param_config.get('UOM', '')
                            if not unit:
                                if param_type == 'MassFrac':
                                    unit = 'fraction'
                                elif param_type == 'MassFlow':
                                    unit = 'kg/h'
                                elif param_type == 'MolarFlow':
                                    unit = 'kgmole/h'
                            
                            return jsonify({
                                "components": components,
                                "unit": unit
                            })
        
        # If we don't have component data in the case parameters, return an empty object
        return jsonify({
            "components": {},
            "unit": ""
        })
            
    except Exception as e:
        current_app.logger.error(f"Error getting components: {str(e)}")
        return jsonify({"error": f"Error getting components: {str(e)}"}), 500

@surrogate_bp.route('/api/batch_results/<int:case_id>', methods=['GET'])
def get_batch_results(case_id):
    """Get batch simulation results for a case"""
    # Get all simulation results of type 'Batch Run' for the case
    results = SimulationResult.query.filter_by(
        case_id=case_id,
        simulation_type='Batch Run'
    ).all()
    
    # Format results
    formatted_results = []
    
    for result in results:
        formatted_results.append({
            'id': result.id,
            'name': result.name,
            'timestamp': result.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'completed': result.data.get('completed', 0),
            'total': result.data.get('total_samples', 0)
        })
    
    return jsonify({"results": formatted_results})

@surrogate_bp.route('/api/train', methods=['POST'])
def train_surrogate_model():
    """Train a surrogate model"""
    # Extract parameters from request
    case_id = request.form.get('case_id')
    model_name = request.form.get('model_name')
    model_type = request.form.get('model_type')
    training_data_source = request.form.get('training_data_source')
    is_inverse_model = request.form.get('is_inverse_model') == 'true'
    
    # Validate required parameters
    if not case_id or not model_name or not model_type or not training_data_source:
        return jsonify({"error": "Missing required parameters"}), 400
    
    # Get case
    case = Case.query.get_or_404(case_id)
    
    # Get input and output parameters
    input_params = request.form.getlist('input_params[]')
    output_params = request.form.getlist('output_params[]')
    
    if not input_params or not output_params:
        return jsonify({"error": "At least one input and one output parameter must be selected"}), 400
    
    # Create model directory
    model_base_dir = os.path.join('Cases', case.name, 'SurrogateModels')
    os.makedirs(model_base_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_folder = f"{model_name.replace(' ', '_')}_{timestamp}"
    model_dir = os.path.join(model_base_dir, model_folder)
    os.makedirs(model_dir, exist_ok=True)
    
    # Get training data based on source
    try:
        if training_data_source == 'batch_results':
            # Use existing batch results
            batch_id = request.form.get('batch_id')
            
            if not batch_id:
                return jsonify({"error": "Batch ID is required"}), 400
            
            # Get batch result
            batch_result = SimulationResult.query.get_or_404(batch_id)
            
            # Load data with original parameters (not swapped yet)
            training_data = load_batch_data(batch_result, input_params, output_params)
            
        elif training_data_source == 'upload':
            # Use uploaded data file
            if 'data_file' not in request.files:
                return jsonify({"error": "No file uploaded"}), 400
            
            data_file = request.files['data_file']
            
            if data_file.filename == '':
                return jsonify({"error": "No file selected"}), 400
            
            # Save uploaded file
            file_path = os.path.join(model_dir, secure_filename(data_file.filename))
            data_file.save(file_path)
            
            # Load data from file
            if file_path.endswith('.csv'):
                training_data = pd.read_csv(file_path)
            elif file_path.endswith(('.xlsx', '.xls')):
                training_data = pd.read_excel(file_path)
            else:
                return jsonify({"error": "Unsupported file format. Please upload CSV or Excel file."}), 400
            
            # Validate that all required columns exist
            missing_inputs = [col for col in input_params if col not in training_data.columns]
            missing_outputs = [col for col in output_params if col not in training_data.columns]
            
            if missing_inputs or missing_outputs:
                missing_cols = missing_inputs + missing_outputs
                return jsonify({"error": f"Missing columns in uploaded data: {', '.join(missing_cols)}"}), 400
        
        else:
            return jsonify({"error": f"Invalid training data source: {training_data_source}"}), 400
    except Exception as e:
        current_app.logger.error(f"Error getting training data: {str(e)}")
        return jsonify({"error": f"Error getting training data: {str(e)}"}), 500

    if training_data is None or training_data.empty:
        return jsonify({"error": "No training data available"}), 400

    # Save training data
    training_data_path = os.path.join(model_dir, 'training_data.csv')
    training_data.to_csv(training_data_path, index=False)

    # For inverse models, swap input and output parameters AFTER loading data
    if is_inverse_model:
        input_params, output_params = output_params, input_params
        current_app.logger.info('Swapped input and output parameters for inverse model')
        
    # Get model-specific parameters
    model_params = {}
    
    # Common parameters - fixed test_size that was the main issue
    test_size = float(request.form.get('test_size', 0.2))
    random_seed = int(request.form.get('random_seed', 42))
    
    # Model-specific parameters
    try:
        if model_type == 'random_forest':
            model_params = {
                'n_estimators': int(request.form.get('n_estimators', 100)),
                'max_depth': None if request.form.get('max_depth') == 'None' else int(request.form.get('max_depth', 10)),
                'min_samples_split': int(request.form.get('min_samples_split', 2)),
                'min_samples_leaf': int(request.form.get('min_samples_leaf', 1)),
                'max_features': 'sqrt' if request.form.get('max_features', 'auto') == 'auto' else request.form.get('max_features', 'sqrt'),
                'random_state': random_seed
            }
        elif model_type == 'neural_network':
            hidden_layer_sizes = request.form.get('hidden_layer_sizes', '100,100')
            hidden_layer_sizes = tuple(int(x) for x in hidden_layer_sizes.split(','))
            
            model_params = {
                'hidden_layer_sizes': hidden_layer_sizes,
                'activation': request.form.get('activation', 'relu'),
                'solver': request.form.get('solver', 'adam'),
                'alpha': float(request.form.get('alpha', 0.0001)),
                'batch_size': request.form.get('batch_size', 'auto'),
                'learning_rate': request.form.get('learning_rate', 'constant'),
                'learning_rate_init': float(request.form.get('learning_rate_init', 0.001)),
                'max_iter': int(request.form.get('max_iter', 200)),
                'random_state': random_seed
            }
        elif model_type == 'gaussian_process':
            model_params = {
                'kernel': request.form.get('kernel', 'rbf'),
                'alpha': float(request.form.get('alpha', 1e-10)),
                'random_state': random_seed
            }
        elif model_type == 'polynomial':
            model_params = {
                'degree': int(request.form.get('degree', 2)),
                'include_bias': request.form.get('include_bias', 'true') == 'true'
            }
        elif model_type == 'svr':
            model_params = {
                'kernel': request.form.get('kernel', 'rbf'),
                'C': float(request.form.get('C', 1.0)),
                'epsilon': float(request.form.get('epsilon', 0.1)),
                'gamma': request.form.get('gamma', 'scale')
            }
    except Exception as e:
        current_app.logger.error(f"Error processing model parameters: {str(e)}")
        return jsonify({"error": f"Error processing model parameters: {str(e)}"}), 500
    
    # Create and train surrogate model
    try:
        # Create surrogate driver
        surrogate_driver = SurrogateDriver.create(model_type, input_params, output_params)
        
        # Add test_size to model_params
        model_params['test_size'] = test_size
        
        start_time = time.time()
        # Train the model
        model, metrics, _ = surrogate_driver.train(
            training_data,
            model_save_path=model_dir,
            model_version_name='base',
            **model_params
        )
        # Calculate actual training time
        training_time = time.time() - start_time
    except Exception as e:
        current_app.logger.error(f"Error training model: {str(e)}")
        return jsonify({"error": f"Error training model: {str(e)}"}), 500
    
    # Save model configuration
    model_config = {
        'model_type': model_type,
        'input_params': input_params,
        'output_params': output_params,
        'is_inverse_model': is_inverse_model,
        'training_data_source': training_data_source,
        'test_size': test_size,
        'random_seed': random_seed,
        'model_params': model_params
    }
    
    with open(os.path.join(model_dir, 'model_config.json'), 'w') as f:
        json.dump(model_config, f, indent=4)
    
    # Helper function to make values JSON serializable
    def make_json_serializable(obj):
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_json_serializable(item) for item in obj]
        return obj
    
    # Extract and process metrics
    r2_score = metrics.get('test_score', 0)
    detailed_metrics = metrics.get('detailed_metrics', {})
    
    # Calculate MAE and RMSE as average of all outputs
    mae = 0
    rmse = 0
    valid_outputs = 0
    
    for output in output_params:
        if output in detailed_metrics:
            output_metrics = detailed_metrics[output]
            if output_metrics.get('mae') is not None:
                mae += output_metrics.get('mae', 0)
                valid_outputs += 1
            if output_metrics.get('rmse') is not None:
                rmse += output_metrics.get('rmse', 0)
    
    # Calculate averages
    if valid_outputs > 0:
        mae /= valid_outputs
        rmse /= valid_outputs
    else:
        mae = None
        rmse = None
    
    # Handle NaN values
    if r2_score is None or (isinstance(r2_score, (float, np.float64)) and (np.isnan(r2_score) or np.isinf(r2_score))):
        r2_score = None
    if mae is None or (isinstance(mae, (float, np.float64)) and (np.isnan(mae) or np.isinf(mae))):
        mae = None
    if rmse is None or (isinstance(rmse, (float, np.float64)) and (np.isnan(rmse) or np.isinf(rmse))):
        rmse = None
    
    # Process metrics to ensure they're JSON serializable
    safe_metrics = {
        'r2_score': make_json_serializable(r2_score),
        'mae': make_json_serializable(mae),
        'rmse': make_json_serializable(rmse),
        'training_time': make_json_serializable(training_time)
    }
    
    # Process model_config to ensure it's JSON serializable
    safe_model_config = make_json_serializable(model_config)
    
    # Create the surrogate model object
    try:
        surrogate_model = Surrogate(
            name=model_name,
            case_id=case.id,
            model_type=model_type,
            input_params=input_params,
            output_params=output_params,
            is_inverse_model=is_inverse_model,
            model_path=model_dir,
            created_at=datetime.now(),
            metrics=safe_metrics,
            model_config=safe_model_config
        )
        
        # Add to session and commit
        db.session.add(surrogate_model)
        db.session.commit()
        
        return jsonify({
            "model_id": surrogate_model.id,
            "metrics": safe_metrics,
            "model_info": {
                "type": model_type,
                "is_inverse_model": is_inverse_model,
                "input_params_count": len(input_params),
                "output_params_count": len(output_params),
                "training_samples_count": len(training_data)
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error saving model to database: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Error saving model to database: {str(e)}"}), 500


def load_batch_data(batch_result, input_params, output_params):
    """Load data from a batch simulation result"""
    try:
        # Check if this is a batch result
        if batch_result.simulation_type != "Batch Run":
            raise ValueError("Not a batch simulation result")
        
        # Get the results path from the data
        results_path = batch_result.data.get('results_path')
        
        if not results_path or not os.path.exists(results_path):
            raise ValueError("Results file not found")
        
        # Read inputs and outputs from Excel
        try:
            inputs_df = pd.read_excel(results_path, sheet_name='Inputs', index_col='Sample ID')
            outputs_df = pd.read_excel(results_path, sheet_name='Outputs', index_col='Sample ID')
        except KeyError:
            # If 'Sample ID' is not set as index, try reading without index
            inputs_df = pd.read_excel(results_path, sheet_name='Inputs')
            outputs_df = pd.read_excel(results_path, sheet_name='Outputs')
            
            # If Sample ID exists as a column, set it as index
            if 'Sample ID' in inputs_df.columns and 'Sample ID' in outputs_df.columns:
                inputs_df.set_index('Sample ID', inplace=True)
                outputs_df.set_index('Sample ID', inplace=True)
        
        # Reset index to make sure Sample ID becomes a regular column if it was an index
        inputs_df = inputs_df.reset_index()
        outputs_df = outputs_df.reset_index()
        
        # Filter columns to only include requested parameters
        available_input_params = [col for col in input_params if col in inputs_df.columns]
        available_output_params = [col for col in output_params if col in outputs_df.columns]
        
        if not available_input_params:
            raise ValueError(f"None of the requested input parameters {input_params} found in batch data")
        
        if not available_output_params:
            raise ValueError(f"None of the requested output parameters {output_params} found in batch data")
        
        # Check if there's a common column to merge on (like Sample ID)
        common_columns = set(inputs_df.columns).intersection(set(outputs_df.columns))
        merge_column = next((col for col in ['Sample ID', 'index'] if col in common_columns), None)
        
        if merge_column:
            # Merge on the common column
            merged_df = pd.merge(
                inputs_df[available_input_params + [merge_column]], 
                outputs_df[available_output_params + [merge_column]], 
                on=merge_column
            )
            # Remove the merge column from the final dataframe
            if merge_column in merged_df.columns:
                merged_df = merged_df.drop(columns=[merge_column])
        else:
            # If no common column, assume rows align and concatenate
            if len(inputs_df) != len(outputs_df):
                raise ValueError("Input and output data have different numbers of rows and no common index")
            
            # Select only the available columns and concatenate
            merged_df = pd.concat([
                inputs_df[available_input_params], 
                outputs_df[available_output_params]
            ], axis=1)
        
        # Check if we have any missing values
        if merged_df.isnull().any().any():
            print(f"Warning: Training data contains {merged_df.isnull().sum().sum()} missing values")
        
        return merged_df
        
    except Exception as e:
        current_app.logger.error(f"Error loading batch data: {str(e)}")
        raise


@surrogate_bp.route('/api/download/<int:model_id>', methods=['GET'])
def api_download_model(model_id):
    """Download a surrogate model"""
    model = Surrogate.query.get_or_404(model_id)
    case = Case.query.get_or_404(model.case_id)
    
    try:
        # Create a temporary file to store the model
        with tempfile.NamedTemporaryFile(suffix='.joblib', delete=False) as tmp:
            temp_path = tmp.name

        model_path = os.path.join(model.model_path, 'base', 'model.joblib')
        # Load the model from the model path
        if not os.path.exists(model_path):
            return jsonify({"error": "Model file not found"}), 404
        
        # Copy the model file to the temporary file
        import shutil
        shutil.copy2(model_path, temp_path)
        
        # Generate filename
        filename = f"{case.name}_{model.name}_surrogate_model.joblib"
        safe_filename = secure_filename(filename)
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=safe_filename,
            mimetype='application/octet-stream'
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading model: {str(e)}")
        return jsonify({"error": f"Error downloading model: {str(e)}"}), 500

@surrogate_bp.route('/api/model/<int:model_id>', methods=['DELETE'])
def api_delete_model(model_id):
    """Delete a surrogate model"""
    model = Surrogate.query.get_or_404(model_id)
    
    try:
        # Delete the model file and directory if they exist
        if model.model_path and os.path.exists(model.model_path):            
            try:
                # Use shutil.rmtree to recursively delete the directory and all its contents
                import shutil
                if os.path.exists(model.model_path):
                    shutil.rmtree(model.model_path, ignore_errors=True)
                    current_app.logger.info(f"Deleted directory tree: {model.model_path}")
            except Exception as fs_error:
                current_app.logger.warning(f"Error cleaning up model files: {str(fs_error)}")
                # Continue with database deletion even if file deletion fails
        
        # Delete from database
        db.session.delete(model)
        db.session.commit()
        
        return jsonify({"success": True, "message": "Model deleted successfully"})
    except Exception as e:
        current_app.logger.error(f"Error deleting model: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Error deleting model: {str(e)}"}), 500



@surrogate_bp.route('/api/predict/<int:model_id>', methods=['POST'])
def api_predict(model_id):
    """Make predictions using a surrogate model"""
    try:
        model_record = Surrogate.query.get_or_404(model_id)
        
        # Get input data from request
        data = request.json
        input_data = data.get('input_data', {})
        
        if not input_data:
            return jsonify({"error": "No input data provided"}), 400
        
        # Get model directory
        #model_dir = os.path.dirname(model_record.model_path)
        
        # Get the model path from the directory TODO versioning need to added later
        model_path = os.path.join(model_record.model_path, 'base', 'model.joblib')

        # Load the surrogate model
        try:
            # Use the directory containing the model file
            surrogate_driver = SurrogateDriver.load_complete_model(os.path.dirname(model_path))
        except Exception as e:
            current_app.logger.error(f"Error loading surrogate model: {str(e)}")
            return jsonify({"error": f"Error loading surrogate model: {str(e)}"}), 500
        
        # Validate input data
        for param in model_record.input_params:
            if param not in input_data:
                return jsonify({"error": f"Missing input parameter: {param}"}), 400
        
        # Make prediction
        try:
            predictions = surrogate_driver.predict(input_data)
            
            # Convert predictions to a dictionary if it's not already
            if not isinstance(predictions, dict):
                if hasattr(predictions, 'to_dict'):
                    # It's a DataFrame
                    predictions = predictions.iloc[0].to_dict() if len(predictions) > 0 else {}
                else:
                    # Try to convert to a dictionary
                    predictions = {param: float(val) for param, val in zip(model_record.output_params, predictions)}
            
            return jsonify({
                "predictions": predictions,
                "model_info": {
                    "name": model_record.name,
                    "type": model_record.model_type,
                    "case": model_record.case.name
                }
            })
        except Exception as e:
            current_app.logger.error(f"Error making prediction: {str(e)}")
            return jsonify({"error": f"Error making prediction: {str(e)}"}), 500
            
    except Exception as e:
        current_app.logger.error(f"Error in prediction endpoint: {str(e)}")
        return jsonify({"error": f"Error in prediction endpoint: {str(e)}"}), 500

@surrogate_bp.route('/api/models/<int:case_id>', methods=['GET'])
def api_get_case_models(case_id):
    """Get all surrogate models for a case"""
    case = Case.query.get_or_404(case_id)
    
    # Get all models for the case
    models = Surrogate.query.filter_by(case_id=case_id).all()
    
    # Format models
    formatted_models = []
    
    for model in models:
        formatted_models.append({
            'id': model.id,
            'name': model.name,
            'model_type': model.model_type,
            'created_at': model.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'metrics': model.metrics,
            'input_params': model.input_params,
            'output_params': model.output_params
        })
    
    return jsonify({"models": formatted_models})

@surrogate_bp.route('/api/model/<int:model_id>', methods=['GET'])
def api_get_model(model_id):
    """Get details of a specific surrogate model"""
    model = Surrogate.query.get_or_404(model_id)
    
    # Format model details
    model_details = {
        'id': model.id,
        'name': model.name,
        'case_id': model.case_id,
        'case_name': model.case.name,
        'model_type': model.model_type,
        'created_at': model.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'metrics': model.metrics,
        'input_params': model.input_params,
        'output_params': model.output_params,
        'model_config': model.model_config
    }
    
    return jsonify(model_details)

@surrogate_bp.route('/api/compare', methods=['POST'])
def api_compare_models():
    """Compare multiple surrogate models"""
    try:
        data = request.json
        model_ids = data.get('model_ids', [])
        test_data = data.get('test_data', [])
        
        if not model_ids:
            return jsonify({"error": "No model IDs provided"}), 400
        
        if not test_data:
            return jsonify({"error": "No test data provided"}), 400
        
        # Get models
        models = []
        for model_id in model_ids:
            model = Surrogate.query.get(model_id)
            if model:
                models.append(model)
        
        if not models:
            return jsonify({"error": "No valid models found"}), 400
        
        # Convert test data to DataFrame
        test_df = pd.DataFrame(test_data)
        
        # Get all input and output parameters
        all_inputs = set()
        all_outputs = set()
        
        for model in models:
            all_inputs.update(model.input_params)
            all_outputs.update(model.output_params)
        
        # Validate test data
        missing_inputs = [col for col in all_inputs if col not in test_df.columns]
        
        if missing_inputs:
            return jsonify({"error": f"Missing input columns in test data: {', '.join(missing_inputs)}"}), 400
        
        # Make predictions with each model
        results = []
        
        for model in models:
            try:
                # Load the surrogate model
                model_path = os.path.join(model.model_path, 'base', 'model.joblib')
                surrogate_driver = SurrogateDriver.load_complete_model(os.path.dirname(model_path))
                
                # Make predictions
                predictions = surrogate_driver.predict(test_df)
                
                # Calculate metrics if actual values are provided
                metrics = {}
                for output in model.output_params:
                    if output in test_df.columns:
                        from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
                        import numpy as np
                        
                        r2 = r2_score(test_df[output], predictions[output])
                        mae = mean_absolute_error(test_df[output], predictions[output])
                        rmse = np.sqrt(mean_squared_error(test_df[output], predictions[output]))
                        
                        metrics[output] = {
                            'r2': r2,
                            'mae': mae,
                            'rmse': rmse
                        }
                
                # Add to results
                results.append({
                    'model_id': model.id,
                    'model_name': model.name,
                    'model_type': model.model_type,
                    'predictions': predictions.to_dict(orient='records'),
                    'metrics': metrics
                })
            except Exception as e:
                current_app.logger.error(f"Error making predictions with model {model.id}: {str(e)}")
                results.append({
                    'model_id': model.id,
                    'model_name': model.name,
                    'model_type': model.model_type,
                    'error': str(e)
                })
        
        return jsonify({"results": results})
    except Exception as e:
        current_app.logger.error(f"Error comparing models: {str(e)}")
        return jsonify({"error": f"Error comparing models: {str(e)}"}), 500

@surrogate_bp.route('/api/ensemble', methods=['POST'])
def api_ensemble_predict():
    """Make ensemble predictions using multiple surrogate models"""
    try:
        data = request.json
        model_ids = data.get('model_ids', [])
        weights = data.get('weights', [])
        input_data = data.get('input_data', {})
        
        if not model_ids:
            return jsonify({"error": "No model IDs provided"}), 400
        
        if not input_data:
            return jsonify({"error": "No input data provided"}), 400
        
        # Validate weights if provided
        if weights and len(weights) != len(model_ids):
            return jsonify({"error": "Number of weights must match number of models"}), 400
        
        # Get models
        models = []
        for model_id in model_ids:
            model = Surrogate.query.get(model_id)
            if model:
                models.append(model)
        
        if not models:
            return jsonify({"error": "No valid models found"}), 400
        
        # Normalize weights if provided
        if weights:
            total_weight = sum(weights)
            if total_weight > 0:
                weights = [w / total_weight for w in weights]
        else:
            # Equal weights if not provided
            weights = [1.0 / len(models)] * len(models)
        
        # Make predictions with each model
        all_predictions = []
        model_infos = []
        
        for i, model in enumerate(models):
            try:
                # Load the surrogate model
                model_path = os.path.join(model.model_path, 'base', 'model.joblib')
                surrogate_driver = SurrogateDriver.load_complete_model(os.path.dirname(model_path))
                
                # Make prediction
                prediction = surrogate_driver.predict(input_data)
                all_predictions.append(prediction)
                
                # Add model info
                model_infos.append({
                    'id': model.id,
                    'name': model.name,
                    'type': model.model_type,
                    'weight': weights[i]
                })
            except Exception as e:
                current_app.logger.error(f"Error making prediction with model {model.id}: {str(e)}")
                # Skip this model and adjust weights
                weights = [w / (1 - weights[i]) for j, w in enumerate(weights) if j != i]
        
        if not all_predictions:
            return jsonify({"error": "No valid predictions could be made"}), 500
        
        # Combine predictions
        ensemble_prediction = {}
        
        # Get all output parameters
        all_outputs = set()
        for prediction in all_predictions:
            all_outputs.update(prediction.keys())
        
        # Calculate weighted average for each output
        for output in all_outputs:
            values = []
            output_weights = []
            
            for i, prediction in enumerate(all_predictions):
                if output in prediction:
                    values.append(prediction[output])
                    output_weights.append(weights[i])
            
            if values:
                # Normalize weights for this output
                total_weight = sum(output_weights)
                if total_weight > 0:
                    normalized_weights = [w / total_weight for w in output_weights]
                    # Calculate weighted average
                    ensemble_prediction[output] = sum(v * w for v, w in zip(values, normalized_weights))
        
        return jsonify({
            "ensemble_prediction": ensemble_prediction,
            "individual_models": model_infos
        })
    except Exception as e:
        current_app.logger.error(f"Error making ensemble prediction: {str(e)}")
        return jsonify({"error": f"Error making ensemble prediction: {str(e)}"}), 500

@surrogate_bp.route('/api/feature-importance/<int:model_id>', methods=['GET'])
def api_feature_importance(model_id):
    """Get feature importance for a surrogate model"""
    model = Surrogate.query.get_or_404(model_id)
    
    try:
        # Load the surrogate model
        model_path = os.path.join(model.model_path, 'base', 'model.joblib')

        # Check if model_info.json exists
        model_info_path = os.path.join(model.model_path, 'base', 'model_info.json')
        if os.path.exists(model_info_path):
            with open(model_info_path, 'r') as f:
                model_info = json.load(f)
                
                # Check if feature importances are available
                if 'feature_importances' in model_info:
                    return jsonify({
                        "feature_importances": model_info['feature_importances']
                    })
        
        # If not available in model_info.json, try to load the model and calculate
        surrogate_driver = SurrogateDriver.load_complete_model(os.path.dirname(model_path))
        
        # Check if the model has feature_importances_ attribute (e.g., Random Forest)
        if hasattr(surrogate_driver.model, 'feature_importances_'):
            feature_importances = {}
            for i, feature in enumerate(model.input_params):
                feature_importances[feature] = float(surrogate_driver.model.feature_importances_[i])
                
            return jsonify({
                "feature_importances": feature_importances
            })
        
        # If not available, return an error
        return jsonify({"error": "Feature importance not available for this model type"}), 400
    except Exception as e:
        current_app.logger.error(f"Error getting feature importance: {str(e)}")
        return jsonify({"error": f"Error getting feature importance: {str(e)}"}), 500

@surrogate_bp.route('/api/training-data/<int:model_id>', methods=['GET'])
def api_get_training_data(model_id):
    """Get training data for a surrogate model"""
    model = Surrogate.query.get_or_404(model_id)
    
    try:
        # Get limit parameter (number of samples to return)
        limit = request.args.get('limit', type=int)

        # Check if training data exists
        training_data_path = os.path.join(model.model_path, 'training_data.csv')
        print(f"Training data path: {training_data_path}")
        if not os.path.exists(training_data_path):
            return jsonify({"error": "Training data not found"}), 404
        
        # Load training data
        training_data = pd.read_csv(training_data_path)
        
        # Apply limit if specified
        if limit and limit > 0:
            training_data = training_data.head(limit)
        
        # Convert to list of dictionaries
        samples = training_data.to_dict(orient='records')
        
        return jsonify({
            "samples": samples,
            "total_samples": len(training_data)
        })
    except Exception as e:
        current_app.logger.error(f"Error getting training data: {str(e)}")
        return jsonify({"error": f"Error getting training data: {str(e)}"}), 500

@surrogate_bp.route('/api/loss-curve/<int:model_id>', methods=['GET'])
def api_get_loss_curve(model_id):
    """Get loss curve data for a surrogate model"""
    model = Surrogate.query.get_or_404(model_id)
    
    try:
        # Get the model directory
        model_path = os.path.join(model.model_path, 'base', 'model.joblib')
        # Load the model to get the loss curve
        if not os.path.exists(model_path):
            return jsonify({"error": "Model file not found"}), 404
        
        # Load the model
        surrogate_model = joblib.load(model_path)
        
        # Check if the model has a loss_curve_ attribute (neural networks have this)
        loss_curve = None
        if hasattr(surrogate_model, 'loss_curve_'):
            loss_curve = surrogate_model.loss_curve_
            # Convert numpy array to list for JSON serialization
            loss_curve = [float(x) for x in loss_curve]
        
        return jsonify({
            "loss_curve": loss_curve
        })
    except Exception as e:
        current_app.logger.error(f"Error getting loss curve: {str(e)}")
        return jsonify({"error": f"Error getting loss curve: {str(e)}"}), 500

@surrogate_bp.route('/api/prediction-data/<int:model_id>', methods=['GET'])
def api_get_prediction_data(model_id):
    """Get actual vs predicted data for a specific parameter"""
    model = Surrogate.query.get_or_404(model_id)
    
    try:
        # Get parameter from query string
        parameter = request.args.get('parameter')
        if not parameter:
            return jsonify({"error": "Parameter is required"}), 400
        
        # Check if parameter is in output parameters
        if parameter not in model.output_params:
            return jsonify({"error": f"Parameter {parameter} is not an output parameter"}), 400
        
        # Check if training data exists
        training_data_path = os.path.join(model.model_path, 'training_data.csv')

        print(f"Training data path: {training_data_path}")
        if not os.path.exists(training_data_path):
            return jsonify({"error": "Training data not found"}), 404
        
        # Load training data
        training_data = pd.read_csv(training_data_path)
        
        # Get the surrogate driver
        try:
            model_path = os.path.join(model.model_path, 'base', 'model.joblib')
            # Use the directory containing the model file
            surrogate_driver = SurrogateDriver.load_complete_model(os.path.dirname(model_path))
        except Exception as e:
            current_app.logger.error(f"Error loading surrogate model: {str(e)}")
            return jsonify({"error": f"Error loading surrogate model: {str(e)}"}), 500
        
        # Get input data
        X = training_data[model.input_params]
        
        # Get actual output data for the selected parameter
        y_actual = training_data[parameter].values.tolist()
        
        # Make predictions
        predictions = surrogate_driver.predict(X)
        y_pred = predictions[parameter].values.tolist()
        r2_metric = float(r2_score(y_actual, y_pred))
        mae_metric = float(mean_absolute_error(y_actual, y_pred))
        
        return jsonify({
            "parameter": parameter,
            "actual": y_actual,
            "predicted": y_pred,
            "metrics": {
                "r2": r2_metric,
                "mae": mae_metric
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error getting prediction data: {str(e)}")
        return jsonify({"error": f"Error getting prediction data: {str(e)}"}), 500

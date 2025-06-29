from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app, session, send_file
from api.database import db, Case, Surrogate
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
from driver.Surrogate_driver import surrogate_driver
from driver.Simulation_driver import simulation_driver
from driver.Calibration.drivers.PSO_driver_withscaler import pso
import time
import pythoncom  # For COM initialization

calibration_bp = Blueprint('calibration', __name__, url_prefix='/calibration')

@calibration_bp.route('/')
def calibration():
    # Get all cases
    cases = Case.query.all()
    
    # Get all surrogate models
    surrogate_models = Surrogate.query.filter_by(is_trained=True).all()
    
    return render_template('calibration.html', 
                          active_page='calibration',
                          cases=cases,
                          surrogate_models=surrogate_models,
                          now=datetime.now)

@calibration_bp.route('/get_case_info/<int:case_id>', methods=['GET'])
def get_case_info(case_id):
    """Get information about a specific case including calibration parameters"""
    case = Case.query.get_or_404(case_id)
    
    # Get case parameters
    case_parameters = json.loads(case.parameters) if case.parameters else {}
    
    # Extract input parameters
    input_params = {}
    if 'InputParams' in case_parameters:
        for subtype, params in case_parameters['InputParams'].items():
            for name, param_config in params.items():
                input_params[name] = {
                    'min': param_config.get('min', 0),
                    'max': param_config.get('max', 1),
                    'default': param_config.get('default', 0)
                }
    
    # Extract output parameters
    output_params = {}
    if 'OutputParameters' in case_parameters:
        for subtype, params in case_parameters['OutputParameters'].items():
            for name, param_config in params.items():
                output_params[name] = {
                    'target_value': param_config.get('target_value', 0),
                    'weight': param_config.get('weight', 1.0),
                    'sdev': param_config.get('sdev', 0.1)
                }
    
    return jsonify({
        "case_name": case.name,
        "simulation_file": case.simulation_file,
        "input_params": input_params,
        "output_params": output_params
    })

@calibration_bp.route('/get_surrogate_models/<int:case_id>', methods=['GET'])
def get_surrogate_models(case_id):
    """Get all surrogate models for a specific case"""
    surrogate_models = Surrogate.query.filter_by(case_id=case_id, is_trained=True).all()
    
    models = []
    for model in surrogate_models:
        config = json.loads(model.config) if model.config else {}
        models.append({
            "id": model.id,
            "name": model.name,
            "is_inverse": config.get('is_inverse', False),
            "active_inputs": config.get('active_inputs', []),
            "active_outputs": config.get('active_outputs', [])
        })
    
    return jsonify({"models": models})

@calibration_bp.route('/run_calibration', methods=['POST'])
def run_calibration():
    """Run the calibration process"""
    data = request.json
    
    case_id = data.get('case_id')
    surrogate_id = data.get('surrogate_id')
    target_values = data.get('target_values', {})
    pso_params = data.get('pso_params', {})
    weights = data.get('weights', {})
    sdevs = data.get('sdevs', {})
    
    # Validate required fields
    if not case_id or not surrogate_id:
        return jsonify({"error": "Case ID and surrogate model ID are required"}), 400
    
    # Get case and surrogate model
    case = Case.query.get_or_404(case_id)
    surrogate = Surrogate.query.get_or_404(surrogate_id)
    
    # Check if surrogate model is trained
    if not surrogate.is_trained:
        return jsonify({"error": "Surrogate model is not trained"}), 400
    
    try:
        # Initialize COM for this thread
        pythoncom.CoInitialize()
        
        # Parse surrogate configuration
        config = json.loads(surrogate.config)
        is_inverse = config.get('is_inverse', False)
        
        # Get case parameters
        case_parameters = json.loads(case.parameters) if case.parameters else {}
        
        # Load surrogate model
        if not surrogate.model_path:
            return jsonify({"error": "Surrogate model path not found"}), 404
        
        # Determine model and scaler paths
        model_dir = surrogate.model_path
        model_path = os.path.join(model_dir, 'model.joblib')
        scaler_path = os.path.join(model_dir, 'scaler.joblib')
        
        # If not found, check in subfolders
        if not os.path.exists(model_path):
            # Look for subfolders that might contain the model
            for root, dirs, files in os.walk(model_dir):
                if 'model.joblib' in files:
                    model_path = os.path.join(root, 'model.joblib')
                    scaler_path = os.path.join(root, 'scaler.joblib')
                    break
        
        if not os.path.exists(model_path):
            return jsonify({"error": f"Model file not found at {model_path}"}), 404
        
        # Determine input and output columns
        if is_inverse:
            x_cols = config.get('active_outputs', [])
            y_cols = config.get('active_inputs', [])
        else:
            x_cols = config.get('active_inputs', [])
            y_cols = config.get('active_outputs', [])
        
        # Load surrogate model
        surrogate_model = surrogate_driver.load_from_files(
            model_path=model_path,
            scaler_path=scaler_path,
            x_cols=x_cols,
            y_cols=y_cols
        )
        
        # Prepare target values and weights
        y_true = {}
        y_fitt = {}
        
        for param in config.get('active_outputs', []):
            if param in target_values:
                y_true[param] = float(target_values[param])
                y_fitt[param] = {
                    'Weight': float(weights.get(param, 1.0)),
                    'SDEV': float(sdevs.get(param, 0.1))
                }
        
        # Get parameter ranges for calibration
        param_ranges = {}
        if 'InputParams' in case_parameters:
            for subtype, params in case_parameters['InputParams'].items():
                for name, param_config in params.items():
                    if name in config.get('active_inputs', []):
                        param_ranges[name] = {
                            'min': param_config.get('min', 0),
                            'max': param_config.get('max', 1),
                            'step': 0.0001
                        }
        
        # Run calibration based on model type
        if is_inverse:
            # Run inverse surrogate model
            input_data = {param: value for param, value in y_true.items()}
            calibration_result = surrogate_model.predict(input_data)
        else:
            # Run PSO optimization
            # Generate random input grid
            n_samples = int(pso_params.get('particles', 50))
            random_grid = {}
            
            np.random.seed(42)  # For reproducibility
            for i in range(1, n_samples + 1):
                sample = {}
                for param, range_info in param_ranges.items():
                    min_val = range_info['min']
                    max_val = range_info['max']
                    sample[param] = np.random.uniform(min_val, max_val)
                random_grid[i] = sample
            
            # Initialize PSO
            pso_optimizer = pso(
                particles=random_grid,
                opt_params=x_cols,
                y_true=y_true,
                y_scaler=surrogate_model.scaler.y_scaler,
                iterations=int(pso_params.get('iterations', 100)),
                c1=float(pso_params.get('c1', 0.1)),
                c2=float(pso_params.get('c2', 0.4)),
                w=float(pso_params.get('w', 0.7)),
                stopping_treshold=float(pso_params.get('stopping_threshold', 0.00001)),
                stopping_MSE=float(pso_params.get('stopping_MSE', 0.0000001)),
                debug=pso_params.get('debug', False),
                y_fitt=y_fitt,
                fitparamlimit=param_ranges
            )
            
            costs_values, iovalues, gbest, final_mse = pso_optimizer.run_pso(surrogate_model)
            calibration_result = gbest
        
        # Initialize Hysys and run simulation with calibrated parameters
        hysys = None
        try:
            # Get simulation file path
            sim_file_path = case.simulation_file
            
            # Check if the file exists
            if not os.path.exists(sim_file_path):
                # Try alternative paths
                alt_paths = [
                    os.path.join('Cases', case.name, 'HysysModel', case.simulation_file),
                    os.path.join('Cases', case.name, case.simulation_file)
                ]
                
                for path in alt_paths:
                    if os.path.exists(path):
                        sim_file_path = path
                        break
                else:
                    raise FileNotFoundError(f"Simulation file not found. Tried paths: {[sim_file_path] + alt_paths}")
            
            # Initialize Hysys driver
            hysys = simulation_driver(sim_file_path, case_parameters, resultindict=True)
            
            # Load model
            hysys.load_model()
            
            # Run simulation with calibrated parameters
            simulation_result = hysys.predict(calibration_result)
            
            # Get surrogate prediction for the same input if not using inverse model
            surrogate_result = {}
            if not is_inverse:
                surrogate_result = surrogate_model.predict(calibration_result)
            
            # Calculate accuracy metrics
            metrics = {}
            for key in y_true.keys():
                if key in simulation_result:
                    true_val = y_true[key]
                    sim_val = simulation_result[key]
                    
                    # Calculate simulation absolute errors
                    sim_abs_error = abs(true_val - sim_val)
                    
                    # Calculate simulation relative errors (percentage)
                    if true_val != 0:
                        sim_rel_error = (sim_abs_error / abs(true_val)) * 100
                    else:
                        sim_rel_error = float('inf')  # Avoid division by zero
                    
                    # Initialize metric dictionary with simulation values
                    metric_entry = {
                        'true_value': true_val,
                        'simulation_value': sim_val,
                        'sim_absolute_error': sim_abs_error,
                        'sim_relative_error': sim_rel_error
                    }
                    
                    # Add surrogate metrics if available
                    if key in surrogate_result:
                        surr_val = surrogate_result[key]
                        
                        # Calculate surrogate absolute errors
                        surr_abs_error = abs(true_val - surr_val)
                        
                        # Calculate surrogate relative errors (percentage)
                        if true_val != 0:
                            surr_rel_error = (surr_abs_error / abs(true_val)) * 100
                        else:
                            surr_rel_error = float('inf')  # Avoid division by zero
                        
                        # Add surrogate metrics to the entry
                        metric_entry.update({
                            'surrogate_value': surr_val,
                            'surr_absolute_error': surr_abs_error,
                            'surr_relative_error': surr_rel_error
                        })
                    
                    metrics[key] = metric_entry
            
            # Calculate overall metrics
            overall_metrics = {
                'sim_mean_abs_error': np.mean([m['sim_absolute_error'] for m in metrics.values()]),
                'sim_mean_rel_error': np.mean([m['sim_relative_error'] for m in metrics.values() if m['sim_relative_error'] != float('inf')])
            }
            
            if surrogate_result:
                overall_metrics.update({
                    'surr_mean_abs_error': np.mean([m['surr_absolute_error'] for m in metrics.values() if 'surr_absolute_error' in m]),
                    'surr_mean_rel_error': np.mean([m['surr_relative_error'] for m in metrics.values() if 'surr_relative_error' in m and m['surr_relative_error'] != float('inf')])
                })
            
            # Save results
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            results_folder = os.path.join('Cases', case.name, "CalibrationResults")
            
            # Create folder if it doesn't exist
            if not os.path.exists(results_folder):
                os.makedirs(results_folder)
            
            # Create Excel file
            result_path = os.path.join(results_folder, f"calibration_results_{timestamp}.xlsx")
            with pd.ExcelWriter(result_path) as writer:
                # Save input parameters
                pd.DataFrame.from_dict(calibration_result, orient='index', columns=['Value']).to_excel(writer, sheet_name='Input Parameters')
                
                # Save simulation results
                pd.DataFrame.from_dict(simulation_result, orient='index', columns=['Value']).to_excel(writer, sheet_name='Simulation Results')
                
                # Save surrogate results if available
                if surrogate_result:
                    pd.DataFrame.from_dict(surrogate_result, orient='index', columns=['Value']).to_excel(writer, sheet_name='Surrogate Results')
                
                # Save metrics
                pd.DataFrame.from_dict(metrics, orient='index').to_excel(writer, sheet_name='Accuracy Metrics')
                
                # Save summary
                summary = pd.DataFrame({
                    'Case': [case.name],
                    'Timestamp': [timestamp],
                    'Sim Mean Absolute Error': [overall_metrics['sim_mean_abs_error']],
                    'Sim Mean Relative Error (%)': [overall_metrics['sim_mean_rel_error']]
                })
                
                if 'surr_mean_abs_error' in overall_metrics:
                    summary['Surr Mean Absolute Error'] = overall_metrics['surr_mean_abs_error']
                    summary['Surr Mean Relative Error (%)'] = overall_metrics['surr_mean_rel_error']
                    
                summary.to_excel(writer, sheet_name='Summary')
            
            # Close Hysys
            if hysys:
                hysys.close()
            
            return jsonify({
                "success": True,
                "calibration_result": calibration_result,
                "simulation_result": simulation_result,
                "surrogate_result": surrogate_result,
                "metrics": metrics,
                "overall_metrics": overall_metrics,
                "result_file": result_path,
                "timestamp": timestamp
            })
            
        finally:
            # Ensure Hysys is closed even if an error occurs
            if hysys:
                try:
                    hysys.close()
                except:
                    pass
            
            # Uninitialize COM
            pythoncom.CoUninitialize()
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error during calibration: {str(e)}"}), 500

@calibration_bp.route('/calibration_history/<int:case_id>', methods=['GET'])
def get_calibration_history(case_id):
    """Get calibration history for a specific case"""
    case = Case.query.get_or_404(case_id)
    results_folder = os.path.join('Cases', case.name, "CalibrationResults")
    
    if not os.path.exists(results_folder):
        return jsonify({"history": []})
    
    history = []
    for file in os.listdir(results_folder):
        if file.endswith('.xlsx') and file.startswith('calibration_results_'):
            file_path = os.path.join(results_folder, file)
            timestamp = file.replace('calibration_results_', '').replace('.xlsx', '')
            
            # Try to extract summary information
            try:
                summary = pd.read_excel(file_path, sheet_name='Summary')
                metrics = {
                    'sim_mean_abs_error': summary['Sim Mean Absolute Error'].iloc[0],
                    'sim_mean_rel_error': summary['Sim Mean Relative Error (%)'].iloc[0]
                }
                
                if 'Surr Mean Absolute Error' in summary.columns:
                    metrics['surr_mean_abs_error'] = summary['Surr Mean Absolute Error'].iloc[0]
                    metrics['surr_mean_rel_error'] = summary['Surr Mean Relative Error (%)'].iloc[0]
            except:
                metrics = {}
            
            history.append({
                "timestamp": timestamp,
                "file_path": file_path,
                "metrics": metrics
            })
    
    # Sort by timestamp (newest first)
    history.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return jsonify({"history": history})

@calibration_bp.route('/calibration_result/<int:case_id>/<timestamp>', methods=['GET'])
def get_calibration_result(case_id, timestamp):
    """Get detailed calibration result for a specific run"""
    case = Case.query.get_or_404(case_id)
    file_path = os.path.join('Cases', case.name, "CalibrationResults", f"calibration_results_{timestamp}.xlsx")
    
    if not os.path.exists(file_path):
        return jsonify({"error": "Calibration result file not found"}), 404
    
    try:
        # Read all sheets from the Excel file
        input_params = pd.read_excel(file_path, sheet_name='Input Parameters')
        sim_results = pd.read_excel(file_path, sheet_name='Simulation Results')
        
        # Convert to dictionaries
        input_dict = input_params.set_index('Unnamed: 0')['Value'].to_dict()
        sim_dict = sim_results.set_index('Unnamed: 0')['Value'].to_dict()
        
        # Try to read surrogate results if available
        surr_dict = {}
        try:
            surr_results = pd.read_excel(file_path, sheet_name='Surrogate Results')
            surr_dict = surr_results.set_index('Unnamed: 0')['Value'].to_dict()
        except:
            pass
        
        # Read metrics
        metrics_df = pd.read_excel(file_path, sheet_name='Accuracy Metrics')
        metrics = metrics_df.to_dict(orient='index')
        
        # Read summary
        summary = pd.read_excel(file_path, sheet_name='Summary').to_dict(orient='records')[0]
        
        return jsonify({
            "input_parameters": input_dict,
            "simulation_results": sim_dict,
            "surrogate_results": surr_dict,
            "metrics": metrics,
            "summary": summary
        })
    except Exception as e:
        return jsonify({"error": f"Error reading calibration result: {str(e)}"}), 500

@calibration_bp.route('/download_calibration/<int:case_id>/<timestamp>', methods=['GET'])
def download_calibration_result(case_id, timestamp):
    """Download calibration result file"""
    case = Case.query.get_or_404(case_id)
    file_path = os.path.join('Cases', case.name, "CalibrationResults", f"calibration_results_{timestamp}.xlsx")
    
    if not os.path.exists(file_path):
        return jsonify({"error": "Calibration result file not found"}), 404
    
    return send_file(file_path, as_attachment=True, download_name=f"calibration_results_{timestamp}.xlsx")

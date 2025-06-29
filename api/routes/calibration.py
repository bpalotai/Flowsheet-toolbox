import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for, send_file
from werkzeug.utils import secure_filename
import tempfile
import pythoncom

from api.database import db, Case, SimulationResult, Surrogate
from driver.Calibration.calibration_driver import CalibrationDriver
from driver.Simulation.simulation_driver import SimulationDriver
from driver.Surrogate.surrogate_driver import SurrogateDriver

# Create blueprint
calibration_bp = Blueprint('calibration', __name__, url_prefix='/calibration')

# Convert numpy values to regular Python floats for JSON serialization
def convert_numpy_to_python(obj):
    """Recursively convert numpy types to Python native types"""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, (np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, list):
        return [convert_numpy_to_python(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_numpy_to_python(value) for key, value in obj.items()}
    else:
        return obj

@calibration_bp.route('/', methods=['GET'])
def index():
    """
    Render the calibration landing page
    """
    try:
        # Query all simulation results that are calibration runs
        calibrations = SimulationResult.query.filter(
            db.or_(
                SimulationResult.simulation_type.like('Calibration%'),
                SimulationResult.simulation_type.like('Batch Calibration%')
            )
        ).order_by(SimulationResult.timestamp.desc()).all()
        
        # Parse the data for each calibration
        calibration_data = []
        for calibration in calibrations:
            data = json.loads(calibration.data) if calibration.data else {}
            error_value = None
            if data and 'overall_metrics' in data and 'sim_mean_rel_error' in data['overall_metrics']:
                error_value = data['overall_metrics']['sim_mean_rel_error']
            
            calibration_data.append({
                'calibration': calibration,
                'error_value': error_value
            })
        
        return render_template('calibration/calibration_landing.html', calibration_data=calibration_data)
    
    except Exception as e:
        current_app.logger.error(f"Error in calibration index: {str(e)}")
        flash(f"An error occurred: {str(e)}", "danger")
        return render_template('calibration/calibration_landing.html', calibration_data=[])


@calibration_bp.route('/create', methods=['GET'])
def create_calibration():
    """
    Render the create calibration page
    """
    try:
        # Get all available cases for the dropdown
        cases = Case.query.all()
        
        return render_template('calibration/create_calibration.html', cases=cases)
    
    except Exception as e:
        current_app.logger.error(f"Error in create_calibration: {str(e)}")
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('calibration.index'))

@calibration_bp.route('/details/<int:result_id>', methods=['GET'])
def calibration_details(result_id):
    """
    Render the calibration details page
    """
    try:
        # Get the calibration result
        calibration = SimulationResult.query.get_or_404(result_id)
        
        # Check if it's a calibration result
        if not calibration.simulation_type.startswith('Calibration'):
            flash("The requested result is not a calibration run", "warning")
            return redirect(url_for('calibration.index'))
        
        # Parse the JSON data here instead of in the template
        data = json.loads(calibration.data) if calibration.data else {}
        
        # Pass both the calibration object and the parsed data to the template
        return render_template('calibration/calibration_details.html', 
                              calibration=calibration,
                              data=data,
                              float=float)  # Also include float function for the infinity comparison
    
    except Exception as e:
        current_app.logger.error(f"Error in calibration_details: {str(e)}")
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('calibration.index'))

@calibration_bp.route('/api/case_info/<int:case_id>', methods=['GET'])
def get_case_info(case_id):
    """Get information about a specific case including calibration parameters"""
    try:
        case = Case.query.get_or_404(case_id)
        
        # Get case parameters - use the property directly, it already returns a dictionary
        case_parameters = case.parameters
        
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
    
    except Exception as e:
        current_app.logger.error(f"Error in get_case_info: {str(e)}")
        return jsonify({"error": str(e)}), 500


@calibration_bp.route('/api/surrogate_models/<int:case_id>', methods=['GET'])
def get_surrogate_models(case_id):
    """
    Get all surrogate models for a specific case
    """
    try:
        # Don't filter by is_trained since it doesn't exist
        surrogate_models = Surrogate.query.filter_by(case_id=case_id).all()
        
        models = []
        for model in surrogate_models:
            # Access model_config using the property if it exists, otherwise use an empty dict
            if hasattr(model, 'model_config'):
                model_config = model.model_config  # This should already be a dictionary
            else:
                # Try to parse model_config_json directly if model_config property doesn't exist
                model_config = json.loads(model.model_config_json) if model.model_config_json else {}
                    
            models.append({
                "id": model.id,
                "name": model.name,
                "is_inverse": model.is_inverse_model if hasattr(model, 'is_inverse_model') else False,
                "active_inputs": model_config.get('input_params', []),
                "active_outputs": model_config.get('output_params', [])
            })
        
        return jsonify({"models": models})
    
    except Exception as e:
        current_app.logger.error(f"Error in get_surrogate_models: {str(e)}")
        return jsonify({"error": str(e)}), 500


@calibration_bp.route('/api/run_calibration', methods=['POST'])
def run_calibration():
    """
    Run the calibration process
    """
    try:
        data = request.json
        
        # Get case and surrogate model
        case_id = data.get('case_id')
        case = Case.query.get_or_404(case_id)
        
        # Get case parameters
        case_parameters = case.parameters if case.parameters else {}
        
        # Check if using surrogate model
        use_surrogate = data.get('use_surrogate', False)
        surrogate_id = data.get('surrogate_id')
        is_inverse = data.get('is_inverse', False)
        
        # Get target values and weights
        target_values = data.get('target_values', {})
        weights = data.get('weights', {})
        sdevs = data.get('sdevs', {})
        
        # Get input parameters to calibrate
        input_params = data.get('input_params', {}) 

        # Get optimizer parameters
        optimizer = data.get('optimizer', 'pso')
        pso_params = data.get('pso_params', {})
        
        # Initialize COM for this thread if needed
        if not use_surrogate:
            pythoncom.CoInitialize()
        
        # Get simulation file path
        sim_file_path = case.simulation_file
        
        # Check if the file exists
        if not os.path.exists(sim_file_path):
            # Try alternative paths
            alt_paths = [
                os.path.join('Cases', case.name, 'HysysModel', os.path.basename(case.simulation_file)),
                os.path.join('Cases', case.name, os.path.basename(case.simulation_file))
            ]
            
            for path in alt_paths:
                if os.path.exists(path):
                    sim_file_path = path
                    break
            else:
                return jsonify({"error": f"Simulation file not found. Tried paths: {[sim_file_path] + alt_paths}"}), 404
        
        # Initialize driver (surrogate or simulation)
        driver = None
        surrogate = None
        
        if use_surrogate:
            # Get surrogate model
            surrogate = Surrogate.query.get_or_404(surrogate_id)
            
            # Parse surrogate configuration
            config = surrogate.model_config
            
            # Determine model and scaler paths
            model_path = os.path.join(surrogate.model_path, 'base', 'model.joblib')

            if not os.path.exists(model_path):
                return jsonify({"error": f"Model file not found at {model_path}"}), 404
            
            driver = SurrogateDriver.load_complete_model(os.path.dirname(model_path))
        else:
            # Initialize simulation driver
            sim_type = case_parameters.get('SimulationType', 'hysys')
            driver = SimulationDriver(sim_type, sim_file_path, case.parameters, resultindict=True)
            
            # Load model
            driver.load_model()
        
        # Prepare target values and weights for calibration
        y_true = {}
        y_fitt = {}
        
        for param, value in target_values.items():
            y_true[param] = float(value)
            y_fitt[param] = {
                'Weight': float(weights.get(param, 1.0)),
                'SDEV': float(sdevs.get(param, 0.1))
            }

        # Run calibration based on model type
        if use_surrogate and is_inverse:
            surrogate_result = None
            # Run inverse surrogate model directly
            input_data = {param: value for param, value in y_true.items()}
            calibration_result = driver.predict(input_data)
            
            # Initialize simulation driver to validate results
            sim_type = case_parameters.get('SimulationType', 'hysys')
            sim_driver = SimulationDriver(sim_type, sim_file_path, case.parameters, resultindict=True)
            sim_driver.load_model()

            # Run simulation with calibrated parameters
            simulation_result = sim_driver.predict(calibration_result)
            
            # Extract values from simulation_result if it has a nested structure
            sim_values = {}
            if 'outputs' in simulation_result:
                for key, value_dict in simulation_result['outputs'].items():
                    if isinstance(value_dict, dict) and 'value' in value_dict:
                        sim_values[key] = value_dict['value']
            else:
                # If simulation_result is already flat, use it directly
                sim_values = simulation_result

            # Calculate metrics
            metrics = {}
            print("y_true:", y_true)
            print("sim_values:", sim_values)
            print("surrogate_result:", surrogate_result)

            try:
                for key in y_true.keys():
                    if key in sim_values:
                        true_val = y_true[key]
                        sim_val = sim_values[key]
                        
                        # Calculate simulation absolute errors
                        sim_abs_error = abs(true_val - sim_val)
                        
                        # Calculate simulation relative errors (percentage)
                        if true_val != 0:
                            sim_rel_error = (sim_abs_error / abs(true_val)) * 100
                        else:
                            sim_rel_error = float('inf')  # Avoid division by zero
                        
                        # Initialize metric dictionary with simulation values
                        metrics[key] = {
                            'true_value': true_val,
                            'simulation_value': sim_val,
                            'sim_absolute_error': sim_abs_error,
                            'sim_relative_error': sim_rel_error
                        }
                        
                        # Add surrogate metrics if available
                        if surrogate_result and key in surrogate_result:
                            surr_val = surrogate_result[key]
                            
                            # Calculate surrogate absolute errors
                            surr_abs_error = abs(true_val - surr_val)
                            
                            # Calculate surrogate relative errors (percentage)
                            if true_val != 0:
                                surr_rel_error = (surr_abs_error / abs(true_val)) * 100
                            else:
                                surr_rel_error = float('inf')  # Avoid division by zero
                            
                            # Add surrogate metrics to the entry
                            metrics[key].update({
                                'surrogate_value': surr_val,
                                'surr_absolute_error': surr_abs_error,
                                'surr_relative_error': surr_rel_error
                            })
            except Exception as e:
                print(f"Error calculating metrics: {str(e)}")
                import traceback
                traceback.print_exc()

            # Print metrics for debugging
            print("Metrics:", metrics)

            # Calculate overall metrics
            overall_metrics = {}
            try:
                if metrics:
                    abs_errors = [m['sim_absolute_error'] for m in metrics.values() if 'sim_absolute_error' in m]
                    rel_errors = [m['sim_relative_error'] for m in metrics.values() if 'sim_relative_error' in m and m['sim_relative_error'] != float('inf')]
                    
                    if abs_errors:
                        overall_metrics['sim_mean_abs_error'] = float(np.mean(abs_errors))
                    else:
                        overall_metrics['sim_mean_abs_error'] = float('nan')
                    
                    if rel_errors:
                        overall_metrics['sim_mean_rel_error'] = float(np.mean(rel_errors))
                    else:
                        overall_metrics['sim_mean_rel_error'] = float('nan')
                    
                    if surrogate_result:
                        surr_abs_errors = [m['surr_absolute_error'] for m in metrics.values() if 'surr_absolute_error' in m]
                        surr_rel_errors = [m['surr_relative_error'] for m in metrics.values() if 'surr_relative_error' in m and m['surr_relative_error'] != float('inf')]
                        
                        if surr_abs_errors:
                            overall_metrics['surr_mean_abs_error'] = float(np.mean(surr_abs_errors))
                        else:
                            overall_metrics['surr_mean_abs_error'] = float('nan')
                        
                        if surr_rel_errors:
                            overall_metrics['surr_mean_rel_error'] = float(np.mean(surr_rel_errors))
                        else:
                            overall_metrics['surr_mean_rel_error'] = float('nan')
            except Exception as e:
                print(f"Error calculating overall metrics: {str(e)}")
                import traceback
                traceback.print_exc()

            # Print overall metrics for debugging
            print("Overall metrics:", overall_metrics)
             
            # Close simulation driver
            sim_driver.close()
            
            # Return results
            return jsonify({
                "success": True,
                "calibration_result": calibration_result,
                "simulation_result": simulation_result,
                "surrogate_result": calibration_result,  # Same as calibration result for inverse models
                "metrics": metrics,
                "overall_metrics": overall_metrics,
                "costs_values": [[0]]  # No iterations for inverse model
            })
        else:
            # Run PSO optimization
            # Generate random input grid
            n_samples = int(pso_params.get('particles', 50))
            random_grid = {}

            # Initialize the grid with empty dictionaries
            for i in range(1, n_samples + 1):
                random_grid[i] = {}

            np.random.seed(42)  # For reproducibility
            # Get parameter ranges for calibration
            param_limits = {}
            fixed_params = data.get('fixed_params', {})
            calibrate_params = data.get('calibrate_params', {})

            # Add fixed parameters to the input grid
            for param, value in fixed_params.items():
                for i in range(1, n_samples + 1):
                    random_grid[i][param] = value

            # Add calibration parameters with ranges
            for param, range_info in calibrate_params.items():
                min_val = range_info.get('min', 0)
                max_val = range_info.get('max', 1)
                param_limits[param] = {
                    'min': min_val,
                    'max': max_val
                }
                # Add random values within range to the grid
                for i in range(1, n_samples + 1):
                    random_grid[i][param] = np.random.uniform(min_val, max_val)
            
            # Initialize calibration driver
            calibration_driver = CalibrationDriver(
                calibration_type=optimizer,
                driver=driver,
                use_surrogate=use_surrogate,
                iterations=int(pso_params.get('iterations', 100)),
                c1=float(pso_params.get('c1', 0.1)),
                c2=float(pso_params.get('c2', 0.4)),
                w=float(pso_params.get('w', 0.7)),
                stopping_treshold=float(pso_params.get('stopping_threshold', 0.00001)),
                stopping_MSE=float(pso_params.get('stopping_MSE', 0.0000001)),
                debug=pso_params.get('debug', False)
            )
            
            # Set parameters and reference data
            calibration_driver.set_parameters({
                'particles': random_grid,
                'opt_params': list(calibrate_params.keys()),
                'param_limits': param_limits
            })
            
            calibration_driver.set_reference_data({
                'y_true': y_true,
                'y_fitt': y_fitt
            })
            
            # Run calibration
            calibration_results = calibration_driver.run_calibration()
            
            # Get best parameters
            best_params = calibration_results['best_params']
            
            # If using surrogate, validate with simulation
            if use_surrogate:
                # Initialize simulation driver
                sim_type = case_parameters.get('SimulationType', 'hysys')
                sim_driver = SimulationDriver(sim_type, sim_file_path, case.parameters, resultindict=True)
                sim_driver.load_model()
                
                print("best_params:", best_params)
                # Run simulation with calibrated parameters
                simulation_result = sim_driver.predict(best_params)
                
                # Get surrogate prediction for the same input
                surrogate_result = driver.predict(best_params)
                
                # Close simulation driver
                sim_driver.close()
            else:
                # If using simulation directly, get the result from the last run
                simulation_result = driver.sim_read(include_inputs=False)
                surrogate_result = None
            
            # Extract values from simulation_result if it has a nested structure
            sim_values = {}
            if 'outputs' in simulation_result:
                for key, value_dict in simulation_result['outputs'].items():
                    if isinstance(value_dict, dict) and 'value' in value_dict:
                        sim_values[key] = value_dict['value']
            else:
                # If simulation_result is already flat, use it directly
                sim_values = simulation_result

            # Calculate metrics
            metrics = {}
            print("y_true:", y_true)
            print("sim_values:", sim_values)
            print("surrogate_result:", surrogate_result)

            try:
                for key in y_true.keys():
                    if key in sim_values:
                        true_val = y_true[key]
                        sim_val = sim_values[key]
                        
                        # Calculate simulation absolute errors
                        sim_abs_error = abs(true_val - sim_val)
                        
                        # Calculate simulation relative errors (percentage)
                        if true_val != 0:
                            sim_rel_error = (sim_abs_error / abs(true_val)) * 100
                        else:
                            sim_rel_error = float('inf')  # Avoid division by zero
                        
                        # Initialize metric dictionary with simulation values
                        metrics[key] = {
                            'true_value': true_val,
                            'simulation_value': sim_val,
                            'sim_absolute_error': sim_abs_error,
                            'sim_relative_error': sim_rel_error
                        }
                        
                        # Add surrogate metrics if available
                        if surrogate_result and key in surrogate_result:
                            surr_val = surrogate_result[key]
                            
                            # Calculate surrogate absolute errors
                            surr_abs_error = abs(true_val - surr_val)
                            
                            # Calculate surrogate relative errors (percentage)
                            if true_val != 0:
                                surr_rel_error = (surr_abs_error / abs(true_val)) * 100
                            else:
                                surr_rel_error = float('inf')  # Avoid division by zero
                            
                            # Add surrogate metrics to the entry
                            metrics[key].update({
                                'surrogate_value': surr_val,
                                'surr_absolute_error': surr_abs_error,
                                'surr_relative_error': surr_rel_error
                            })
            except Exception as e:
                print(f"Error calculating metrics: {str(e)}")
                import traceback
                traceback.print_exc()

            # Print metrics for debugging
            print("Metrics:", metrics)

            # Calculate overall metrics
            overall_metrics = {}
            try:
                if metrics:
                    abs_errors = [m['sim_absolute_error'] for m in metrics.values() if 'sim_absolute_error' in m]
                    rel_errors = [m['sim_relative_error'] for m in metrics.values() if 'sim_relative_error' in m and m['sim_relative_error'] != float('inf')]
                    
                    if abs_errors:
                        overall_metrics['sim_mean_abs_error'] = float(np.mean(abs_errors))
                    else:
                        overall_metrics['sim_mean_abs_error'] = float('nan')
                    
                    if rel_errors:
                        overall_metrics['sim_mean_rel_error'] = float(np.mean(rel_errors))
                    else:
                        overall_metrics['sim_mean_rel_error'] = float('nan')
                    
                    if surrogate_result:
                        surr_abs_errors = [m['surr_absolute_error'] for m in metrics.values() if 'surr_absolute_error' in m]
                        surr_rel_errors = [m['surr_relative_error'] for m in metrics.values() if 'surr_relative_error' in m and m['surr_relative_error'] != float('inf')]
                        
                        if surr_abs_errors:
                            overall_metrics['surr_mean_abs_error'] = float(np.mean(surr_abs_errors))
                        else:
                            overall_metrics['surr_mean_abs_error'] = float('nan')
                        
                        if surr_rel_errors:
                            overall_metrics['surr_mean_rel_error'] = float(np.mean(surr_rel_errors))
                        else:
                            overall_metrics['surr_mean_rel_error'] = float('nan')
            except Exception as e:
                print(f"Error calculating overall metrics: {str(e)}")
                import traceback
                traceback.print_exc()

            # Print overall metrics for debugging
            print("Overall metrics:", overall_metrics)

            # Close drivers
            calibration_driver.close()
            
            # Return results
            return jsonify({
                "success": True,
                "calibration_result": best_params,
                "simulation_result": simulation_result,
                "surrogate_result": surrogate_result,
                "metrics": metrics,
                "overall_metrics": overall_metrics,
                "costs_values": calibration_results['costs']
            })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        current_app.logger.error(f"Error in run_calibration: {str(e)}")
        return jsonify({"error": f"Error during calibration: {str(e)}"}), 500
    
    finally:
        # Uninitialize COM
        pythoncom.CoUninitialize()

@calibration_bp.route('/api/save_results', methods=['POST'])
def save_results():
    """
    Save calibration results to the database
    """
    try:
        data = request.json
        
        # Create new simulation result
        result = SimulationResult(
            name=data.get('name', f"Calibration {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            case_id=data.get('case_id'),
            simulation_type=data.get('simulation_type', 'Calibration (PSO)'),
            data=json.dumps(data.get('data', {})),
            timestamp=datetime.now()
        )
        
        # Save to database
        db.session.add(result)
        db.session.commit()
        
        # Create Excel file with results
        try:
            results_folder = os.path.join('Cases', result.case.name, "CalibrationResults")
            
            # Create folder if it doesn't exist
            if not os.path.exists(results_folder):
                os.makedirs(results_folder)
            
            # Create Excel file
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            result_path = os.path.join(results_folder, f"calibration_results_{timestamp}.xlsx")
            
            # Extract data
            result_data = json.loads(result.data)
            calibration_result = result_data.get('calibration_result', {})
            simulation_result = result_data.get('simulation_result', {})
            surrogate_result = result_data.get('surrogate_result', {})
            metrics = result_data.get('metrics', {})
            overall_metrics = result_data.get('overall_metrics', {})
            
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
                    'Case': [result.case.name],
                    'Timestamp': [timestamp],
                    'Sim Mean Absolute Error': [overall_metrics.get('sim_mean_abs_error')],
                    'Sim Mean Relative Error (%)': [overall_metrics.get('sim_mean_rel_error')]
                })
                
                if 'surr_mean_abs_error' in overall_metrics:
                    summary['Surr Mean Absolute Error'] = overall_metrics['surr_mean_abs_error']
                    summary['Surr Mean Relative Error (%)'] = overall_metrics['surr_mean_rel_error']
                    
                summary.to_excel(writer, sheet_name='Summary')
            
            # Update result with file path
            result.file_path = result_path
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Error creating Excel file: {str(e)}")
        
        return jsonify({
            "success": True,
            "result_id": result.id
        })
    
    except Exception as e:
        current_app.logger.error(f"Error in save_results: {str(e)}")
        return jsonify({"error": str(e)}), 500

@calibration_bp.route('/api/download_result/<int:result_id>', methods=['GET'])
def download_result(result_id):
    """
    Download calibration result file
    """
    try:
        result = SimulationResult.query.get_or_404(result_id)
        
        if not result.file_path or not os.path.exists(result.file_path):
            # Try to find the file in the default location
            results_folder = os.path.join('Cases', result.case.name, "CalibrationResults")
            timestamp = result.timestamp.strftime("%Y%m%d-%H%M%S")
            result_path = os.path.join(results_folder, f"calibration_results_{timestamp}.xlsx")
            
            if not os.path.exists(result_path):
                return jsonify({"error": "Result file not found"}), 404
            
            result.file_path = result_path
            db.session.commit()
        
        return send_file(
            result.file_path,
            as_attachment=True,
            download_name=f"calibration_results_{result.timestamp.strftime('%Y%m%d-%H%M%S')}.xlsx"
        )
    
    except Exception as e:
        current_app.logger.error(f"Error in download_result: {str(e)}")
        return jsonify({"error": str(e)}), 500

@calibration_bp.route('/api/delete_result/<int:result_id>', methods=['DELETE'])
def delete_result(result_id):
    """
    Delete calibration result
    """
    try:
        result = SimulationResult.query.get_or_404(result_id)
        
        # Delete file if it exists
        if result.file_path and os.path.exists(result.file_path):
            os.remove(result.file_path)
        
        # Delete from database
        db.session.delete(result)
        db.session.commit()
        
        return jsonify({"success": True})
    
    except Exception as e:
        current_app.logger.error(f"Error in delete_result: {str(e)}")
        return jsonify({"error": str(e)}), 500

@calibration_bp.route('/api/parameter_ranges/<int:case_id>', methods=['GET'])
def get_parameter_ranges(case_id):
    """
    Get parameter ranges for calibration, using surrogate training data if available
    """
    try:
        # Get surrogate model ID from query parameters (optional)
        surrogate_id = request.args.get('surrogate_id', type=int)
        
        # Get case
        case = Case.query.get_or_404(case_id)
        
        # Get case parameters
        case_parameters = case.parameters
        
        # Initialize parameter ranges from case parameters
        param_ranges = {}
        if 'InputParams' in case_parameters:
            for subtype, params in case_parameters['InputParams'].items():
                for name, param_config in params.items():
                    param_ranges[name] = {
                        'min': param_config.get('min', 0),
                        'max': param_config.get('max', 1),
                        'default': param_config.get('default', 0),
                        'source': 'case_parameters'
                    }
        
        # If surrogate model is specified, use its training data to refine ranges
        if surrogate_id:
            surrogate = Surrogate.query.get_or_404(surrogate_id)
            
            # Get training data path
            training_data_path = os.path.join(surrogate.model_path, 'training_data.csv')
            
            if os.path.exists(training_data_path):
                # Load training data
                training_data = pd.read_csv(training_data_path)
                
                # Get input parameters from surrogate model
                input_params = surrogate.input_params
                
                # Calculate min and max for each input parameter from training data
                for param in input_params:
                    if param in training_data.columns:
                        # Only update if the parameter exists in param_ranges
                        if param in param_ranges:
                            # Calculate min and max from training data
                            min_val = float(training_data[param].min())
                            max_val = float(training_data[param].max())
                            
                            # Update param_ranges with training data values
                            param_ranges[param].update({
                                'training_min': min_val,
                                'training_max': max_val,
                                'source': 'surrogate_training_data'
                            })
                            
                            # If case parameters don't specify min/max, use training data
                            if 'min' not in param_ranges[param] or param_ranges[param]['min'] is None:
                                param_ranges[param]['min'] = min_val
                            
                            if 'max' not in param_ranges[param] or param_ranges[param]['max'] is None:
                                param_ranges[param]['max'] = max_val
        
        return jsonify({
            "parameter_ranges": param_ranges
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting parameter ranges: {str(e)}")
        return jsonify({"error": str(e)}), 500

## Batch calibration
@calibration_bp.route('/batch', methods=['GET'])
def batch_calibration():
    """
    Render the batch calibration page
    """
    try:
        # Get all available cases for the dropdown
        cases = Case.query.all()
        
        return render_template('calibration/batch_calibration.html', cases=cases)
    
    except Exception as e:
        current_app.logger.error(f"Error in batch_calibration: {str(e)}")
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('calibration.index'))

@calibration_bp.route('/api/upload_batch_excel', methods=['POST'])
def upload_batch_excel():
    """
    Upload and process Excel file for batch calibration
    """
    try:
        if 'excel_file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['excel_file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({"error": "File must be an Excel file (.xlsx or .xls)"}), 400
        
        # Read Excel file
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({"error": f"Error reading Excel file: {str(e)}"}), 400
        
        # Validate that we have data
        if df.empty:
            return jsonify({"error": "Excel file is empty"}), 400
        
        # Get column names
        columns = df.columns.tolist()
        
        # Convert to records for preview (first 10 rows)
        preview_data = df.head(10).to_dict('records')
        
        # Convert NaN values to None for JSON serialization
        for row in preview_data:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None
        
        # Store full data for later use
        full_data = df.to_dict('records')
        for row in full_data:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None
        
        return jsonify({
            "columns": columns,
            "preview_data": preview_data,
            "full_data": full_data,
            "total_rows": len(df)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error in upload_batch_excel: {str(e)}")
        return jsonify({"error": str(e)}), 500

@calibration_bp.route('/api/run_batch_calibration', methods=['POST'])
def run_batch_calibration():
    """
    Run batch calibration process
    """
    try:
        data = request.json
        
        # Get case and surrogate model
        case_id = data.get('case_id')
        case = Case.query.get_or_404(case_id)
        
        # Get case parameters
        case_parameters = case.parameters if case.parameters else {}
        
        # Check if using surrogate model
        use_surrogate = data.get('use_surrogate', False)
        surrogate_id = data.get('surrogate_id')
        is_inverse = data.get('is_inverse', False)
        
        # Get Excel data
        excel_data = data.get('excel_data', {})
        full_data = excel_data.get('full_data', [])
        
        if not full_data:
            return jsonify({"error": "No Excel data provided"}), 400
        
        # Debug: Print available columns in Excel data
        if full_data:
            excel_columns = list(full_data[0].keys())
            current_app.logger.info(f"Excel columns available: {excel_columns}")
        
        # Get surrogate model details for debugging
        if use_surrogate and surrogate_id:
            surrogate = Surrogate.query.get_or_404(surrogate_id)
            current_app.logger.info(f"Surrogate input params: {surrogate.input_params}")
            current_app.logger.info(f"Surrogate output params: {surrogate.output_params}")
            current_app.logger.info(f"Is inverse model: {is_inverse}")

        # Get optimizer parameters
        optimizer = data.get('optimizer', 'pso')
        pso_params = data.get('pso_params', {})
        
        # Get calibration parameters
        calibrate_params = data.get('calibrate_params', {})
        output_params = data.get('output_params', {})
        weights = data.get('weights', {})
        sdevs = data.get('sdevs', {})
        
        # Initialize COM for this thread if needed
        if not use_surrogate:
            pythoncom.CoInitialize()
        
        # Get simulation file path
        sim_file_path = case.simulation_file
        
        # Check if the file exists
        if not os.path.exists(sim_file_path):
            alt_paths = [
                os.path.join('Cases', case.name, 'HysysModel', os.path.basename(case.simulation_file)),
                os.path.join('Cases', case.name, os.path.basename(case.simulation_file))
            ]
            
            for path in alt_paths:
                if os.path.exists(path):
                    sim_file_path = path
                    break
            else:
                return jsonify({"error": f"Simulation file not found. Tried paths: {[sim_file_path] + alt_paths}"}), 404
        
        # Initialize driver (surrogate or simulation)
        driver = None
        surrogate = None
        
        if use_surrogate:
            # Get surrogate model
            surrogate = Surrogate.query.get_or_404(surrogate_id)
            
            # Determine model path
            model_path = os.path.join(surrogate.model_path, 'base', 'model.joblib')

            if not os.path.exists(model_path):
                return jsonify({"error": f"Model file not found at {model_path}"}), 404
            
            driver = SurrogateDriver.load_complete_model(os.path.dirname(model_path))
        else:
            # Initialize simulation driver
            sim_type = case_parameters.get('SimulationType', 'hysys')
            driver = SimulationDriver(sim_type, sim_file_path, case.parameters, resultindict=True)
            
            # Load model
            driver.load_model()
        
        # Process each row in the Excel data
        batch_results = []
        successful_runs = 0
        total_errors = []
        
        for row_index, row_data in enumerate(full_data):
            try:
                current_app.logger.info(f"Processing row {row_index + 1}/{len(full_data)}")
                current_app.logger.info(f"Row data keys: {list(row_data.keys())}")
                current_app.logger.info(f"Row data values: {row_data}")
                
                if is_inverse:
                    # For inverse models, use target values from Excel as inputs
                    surrogate_inputs = {}
                    # Debug: Check what parameters we're looking for
                    current_app.logger.info(f"Looking for surrogate input params: {surrogate.input_params}")

                    for param in surrogate.input_params:
                        current_app.logger.info(f"Checking for parameter: {param}")
                        if param in row_data and row_data[param] is not None:
                            surrogate_inputs[param] = float(row_data[param])
                            current_app.logger.info(f"Found {param} = {row_data[param]}")
                        else:
                            current_app.logger.warning(f"Parameter {param} not found in row data or is None")
                    
                    if not surrogate_inputs:
                        # Create a more detailed error message
                        available_cols = list(row_data.keys())
                        missing_params = [p for p in surrogate.input_params if p not in row_data]
                        error_msg = f"No valid input data found in Excel row. Missing parameters: {missing_params}. Available columns: {available_cols}"
                        raise ValueError(error_msg)
                    
                    # Run inverse surrogate model
                    calibration_result = driver.predict(surrogate_inputs)
                    
                    # Validate with simulation if needed
                    if not use_surrogate:
                        # Initialize simulation driver for validation
                        sim_type = case_parameters.get('SimulationType', 'hysys')
                        sim_driver = SimulationDriver(sim_type, sim_file_path, case.parameters, resultindict=True)
                        sim_driver.load_model()
                        
                        simulation_result = sim_driver.predict(calibration_result)
                        sim_driver.close()
                    else:
                        simulation_result = None
                    
                    # Calculate metrics
                    metrics = {}
                    for param, target_value in surrogate_inputs.items():
                        if simulation_result and param in simulation_result:
                            sim_value = simulation_result[param]
                            abs_error = abs(target_value - sim_value)
                            rel_error = (abs_error / abs(target_value)) * 100 if target_value != 0 else float('inf')
                            
                            metrics[param] = {
                                'true_value': target_value,
                                'simulation_value': sim_value,
                                'sim_absolute_error': abs_error,
                                'sim_relative_error': rel_error
                            }
                    
                    # Calculate overall metrics
                    if metrics:
                        rel_errors = [m['sim_relative_error'] for m in metrics.values() if m['sim_relative_error'] != float('inf')]
                        overall_metrics = {
                            'sim_mean_rel_error': float(np.mean(rel_errors)) if rel_errors else float('nan')
                        }
                    else:
                        overall_metrics = {'sim_mean_rel_error': float('nan')}
                    
                    batch_results.append({
                        'success': True,
                        'row_index': row_index,
                        'input_data': surrogate_inputs,
                                                'calibration_result': calibration_result,
                        'simulation_result': simulation_result,
                        'metrics': metrics,
                        'overall_metrics': overall_metrics
                    })
                    
                    if overall_metrics['sim_mean_rel_error'] != float('nan'):
                        total_errors.append(overall_metrics['sim_mean_rel_error'])
                    successful_runs += 1
                    
                else:
                    # For regular models, run PSO optimization
                    
                    y_true = {}
                    y_fitt = {}
                    
                    for param in output_params.keys():
                        if param in row_data and row_data[param] is not None:
                            y_true[param] = float(row_data[param])
                            y_fitt[param] = {
                                'Weight': float(weights.get(param, 1.0)),
                                'SDEV': float(sdevs.get(param, 0.1))
                            }
                    
                    current_app.logger.info(f"Target values (y_true): {y_true}")
                    
                    if not y_true:
                        raise ValueError("No valid target values found in Excel row")
                    
                    # Get ALL input parameters that the surrogate model expects
                    if use_surrogate:
                        surrogate = Surrogate.query.get_or_404(surrogate_id)
                        required_input_params = surrogate.input_params
                        current_app.logger.info(f"Surrogate requires these input parameters: {required_input_params}")
                    else:
                        # For simulation models, get all input parameters from case
                        required_input_params = []
                        if 'InputParams' in case_parameters:
                            for subtype, params in case_parameters['InputParams'].items():
                                required_input_params.extend(params.keys())
                        current_app.logger.info(f"Simulation requires these input parameters: {required_input_params}")

                    # Generate random input grid for PSO
                    n_samples = int(pso_params.get('particles', 50))
                    random_grid = {}
                    param_limits = {}

                    for i in range(1, n_samples + 1):
                        random_grid[i] = {}

                    np.random.seed(42 + row_index)  # Different seed for each row

                    # Process ALL required input parameters
                    for param in required_input_params:
                        current_app.logger.info(f"Processing required parameter: {param}")
                        
                        if param in calibrate_params:
                            # This parameter should be calibrated - use random values within range
                            range_info = calibrate_params[param]
                            min_val = range_info.get('min', 0)
                            max_val = range_info.get('max', 1)
                            
                            # Also add to param_limits for PSO
                            param_limits[param] = {
                                'min': min_val,
                                'max': max_val
                            }
                            
                            current_app.logger.info(f"Parameter {param} will be calibrated in range [{min_val}, {max_val}]")
                            for i in range(1, n_samples + 1):
                                random_grid[i][param] = np.random.uniform(min_val, max_val)
                                
                        elif param in row_data and row_data[param] is not None:
                            # This parameter has a fixed value from Excel
                            fixed_value = float(row_data[param])
                            current_app.logger.info(f"Parameter {param} fixed at value: {fixed_value}")
                            for i in range(1, n_samples + 1):
                                random_grid[i][param] = fixed_value
                                
                        else:
                            # This parameter is missing - try to get default from case parameters
                            default_value = None
                            if 'InputParams' in case_parameters:
                                for subtype, params in case_parameters['InputParams'].items():
                                    if param in params:
                                        default_value = params[param].get('default', 0)
                                        break
                            
                            if default_value is not None:
                                current_app.logger.info(f"Parameter {param} using default value: {default_value}")
                                for i in range(1, n_samples + 1):
                                    random_grid[i][param] = default_value
                            else:
                                # Last resort - use 0 or raise error
                                current_app.logger.error(f"Parameter {param} not found in Excel data and no default available")
                                raise ValueError(f"Required parameter '{param}' not found in Excel data and no default value available")

                    # Debug: Print a sample from the random grid
                    current_app.logger.info(f"Sample random grid entry: {random_grid[1]}")
                    current_app.logger.info(f"All parameters in grid: {list(random_grid[1].keys())}")
                    current_app.logger.info(f"Required parameters: {required_input_params}")

                    # Verify all required parameters are present
                    missing_params = [p for p in required_input_params if p not in random_grid[1]]
                    if missing_params:
                        raise ValueError(f"Missing required parameters in random grid: {missing_params}")
                    
                    # NEW IMPROVED CODE ENDS HERE
                    # ===========================
                    
                    # Initialize calibration driver (keep the rest as is)
                    calibration_driver = CalibrationDriver(
                        calibration_type=optimizer,
                        driver=driver,
                        use_surrogate=use_surrogate,
                        iterations=int(pso_params.get('iterations', 100)),
                        c1=float(pso_params.get('c1', 0.1)),
                        c2=float(pso_params.get('c2', 0.4)),
                        w=float(pso_params.get('w', 0.7)),
                        stopping_treshold=float(pso_params.get('stopping_threshold', 0.00001)),
                        stopping_MSE=float(pso_params.get('stopping_MSE', 0.0000001)),
                        debug=pso_params.get('debug', False)
                    )
                    
                    # Set parameters and reference data
                    calibration_driver.set_parameters({
                        'particles': random_grid,
                        'opt_params': list(calibrate_params.keys()),
                        'param_limits': param_limits
                    })
                    
                    calibration_driver.set_reference_data({
                        'y_true': y_true,
                        'y_fitt': y_fitt
                    })
                    
                    # Run calibration
                    current_app.logger.info("Running calibration...")
                    calibration_results = calibration_driver.run_calibration()

                    # Convert the costs data
                    costs_data = calibration_results.get('costs', [])
                    converted_costs = convert_numpy_to_python(costs_data)

                    # Get best parameters
                    best_params = calibration_results['best_params']
                    
                    # Add fixed parameters to best_params
                    for param in case_parameters.get('InputParams', {}).get('Process', {}).keys():
                        if param not in calibrate_params and param in row_data and row_data[param] is not None:
                            best_params[param] = float(row_data[param])
                    
                    # If using surrogate, validate with simulation
                    if use_surrogate:
                        # Initialize simulation driver
                        sim_type = case_parameters.get('SimulationType', 'hysys')
                        sim_driver = SimulationDriver(sim_type, sim_file_path, case.parameters, resultindict=True)
                        sim_driver.load_model()

                        current_app.logger.info("Running validation with simulation...")
                        # Run simulation with calibrated parameters
                        simulation_result = sim_driver.predict(best_params)
                        
                        # Get surrogate prediction for the same input
                        surrogate_result = driver.predict(best_params)
                        
                        # Close simulation driver
                        #sim_driver.close()
                    else:
                        # If using simulation directly, get the result from the last run
                        simulation_result = driver.sim_read(include_inputs=False)
                        surrogate_result = None
                    
                    # Extract values from simulation_result if it has a nested structure
                    sim_values = {}
                    if isinstance(simulation_result, dict) and 'outputs' in simulation_result:
                        for key, value_dict in simulation_result['outputs'].items():
                            if isinstance(value_dict, dict) and 'value' in value_dict:
                                sim_values[key] = value_dict['value']
                    else:
                        sim_values = simulation_result if simulation_result else {}
                    
                    # Calculate metrics
                    metrics = {}
                    for key in y_true.keys():
                        if key in sim_values:
                            true_val = y_true[key]
                            sim_val = sim_values[key]
                            
                            sim_abs_error = abs(true_val - sim_val)
                            sim_rel_error = (sim_abs_error / abs(true_val)) * 100 if true_val != 0 else float('inf')
                            
                            metrics[key] = {
                                'true_value': true_val,
                                'simulation_value': sim_val,
                                'sim_absolute_error': sim_abs_error,
                                'sim_relative_error': sim_rel_error
                            }
                            
                            if surrogate_result and key in surrogate_result:
                                surr_val = surrogate_result[key]
                                surr_abs_error = abs(true_val - surr_val)
                                surr_rel_error = (surr_abs_error / abs(true_val)) * 100 if true_val != 0 else float('inf')
                                
                                metrics[key].update({
                                    'surrogate_value': surr_val,
                                    'surr_absolute_error': surr_abs_error,
                                    'surr_relative_error': surr_rel_error
                                })
                    
                    # Calculate overall metrics
                    if metrics:
                        rel_errors = [m['sim_relative_error'] for m in metrics.values() if m['sim_relative_error'] != float('inf')]
                        overall_metrics = {
                            'sim_mean_rel_error': float(np.mean(rel_errors)) if rel_errors else float('nan')
                        }
                        
                        if surrogate_result:
                            surr_rel_errors = [m['surr_relative_error'] for m in metrics.values() if 'surr_relative_error' in m and m['surr_relative_error'] != float('inf')]
                            if surr_rel_errors:
                                overall_metrics['surr_mean_rel_error'] = float(np.mean(surr_rel_errors))
                    else:
                        overall_metrics = {'sim_mean_rel_error': float('nan')}
                    
                    # Close calibration driver
                    calibration_driver.close()
                    
                    batch_results.append({
                        'success': True,
                        'row_index': row_index,
                        'input_data': row_data,
                        'calibration_result': best_params,
                        'simulation_result': simulation_result,
                        'surrogate_result': surrogate_result,
                        'metrics': metrics,
                        'overall_metrics': overall_metrics,
                        'costs_values': converted_costs
                    })
                    
                    if overall_metrics['sim_mean_rel_error'] != float('nan'):
                        total_errors.append(overall_metrics['sim_mean_rel_error'])
                    successful_runs += 1
                
            except Exception as e:
                current_app.logger.error(f"Error processing row {row_index + 1}: {str(e)}")
                batch_results.append({
                    'success': False,
                    'row_index': row_index,
                    'input_data': row_data,
                    'error': str(e)
                })
        
        # Close main driver
        if hasattr(driver, 'close'):
            driver.close()
        
        # Calculate overall summary
        overall_summary = {
            'total_runs': len(full_data),
            'successful_runs': successful_runs,
            'failed_runs': len(full_data) - successful_runs,
            'average_error': float(np.mean(total_errors)) if total_errors else None
        }
        
        return jsonify({
            "success": True,
            "batch_results": batch_results,
            "overall_summary": overall_summary
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        current_app.logger.error(f"Error in run_batch_calibration: {str(e)}")
        return jsonify({"error": f"Error during batch calibration: {str(e)}"}), 500
    
    finally:
        # Uninitialize COM
        try:
            pythoncom.CoUninitialize()
        except:
            pass
#TODO: It should save the results to the database, to the case as batch calibration results
#TODO: It should save how many iterations were run in every row
#TODO: It should save the best parameters found in every row
#TODO: It should save the costs curve for in every row
#TODO: It should save the overall metrics found in every row
#TODO: It should save the simulation results for in every row
#TODO: It should save the validation results for in every row
#TODO: As it is batch, the details page should show a chart where user could select the output parameter and see the results (target, surrogate, simulation result) for all the rows (as a line chart)
@calibration_bp.route('/api/save_batch_results', methods=['POST'])
def save_batch_results():
    """
    Save batch calibration results to the database
    """
    try:
        data = request.json
        
        # Extract batch results and summary
        batch_results = data.get('data', {}).get('batch_results', [])
        summary = data.get('data', {}).get('summary', {})
        batch_metrics = data.get('data', {}).get('batch_metrics', {})
        
        # Create new simulation result with enhanced data structure
        enhanced_data = {
            'batch_results': batch_results,
            'summary': summary,
            'batch_metrics': batch_metrics,
            'configuration': {
                'use_surrogate': data.get('data', {}).get('use_surrogate', False),
                'surrogate_id': data.get('data', {}).get('surrogate_id'),
                'is_inverse': data.get('data', {}).get('is_inverse', False),
                'optimizer': data.get('data', {}).get('optimizer', 'pso'),
                'pso_params': data.get('data', {}).get('pso_params', {}),
                'calibrate_params': data.get('data', {}).get('calibrate_params', {}),
                'output_params': data.get('data', {}).get('output_params', {}),
                'total_rows': len(batch_results),
                'successful_rows': summary.get('successful_runs', 0),
                'failed_rows': summary.get('failed_runs', 0)
            },
            # Store detailed results for each row
            'row_details': []
        }
        
        # Process each row's detailed results
        for i, result in enumerate(batch_results):
            row_detail = {
                'row_index': i + 1,
                'success': result.get('success', False),
                'input_data': result.get('input_data', {}),
                'calibration_result': result.get('calibration_result', {}),
                'simulation_result': result.get('simulation_result', {}),
                'surrogate_result': result.get('surrogate_result', {}),
                'metrics': result.get('metrics', {}),
                'overall_metrics': result.get('overall_metrics', {}),
                'error': result.get('error', None)
            }
            
            # Add iteration count and costs if available
            if 'costs_values' in result:
                costs = result['costs_values']
                row_detail['iterations_run'] = len(costs) if costs else 0
                row_detail['costs_curve'] = costs
                row_detail['final_cost'] = costs[-1] if costs else None
            else:
                row_detail['iterations_run'] = 0 if result.get('success', False) else None
                row_detail['costs_curve'] = []
                row_detail['final_cost'] = None
            
            enhanced_data['row_details'].append(row_detail)
        
        # Create simulation result entry
        result = SimulationResult(
            name=data.get('name', f"Batch Calibration {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            case_id=data.get('case_id'),
            simulation_type=data.get('simulation_type', 'Batch Calibration (PSO)'),
            data=json.dumps(enhanced_data),
            timestamp=datetime.now()
        )
        
        # Save to database
        db.session.add(result)
        db.session.commit()
        
        # Create comprehensive Excel file with batch results
        try:
            results_folder = os.path.join('Cases', result.case.name, "CalibrationResults")
            
            # Create folder if it doesn't exist
            if not os.path.exists(results_folder):
                os.makedirs(results_folder)
            
            # Create Excel file
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            result_path = os.path.join(results_folder, f"batch_calibration_results_{timestamp}.xlsx")
            
            with pd.ExcelWriter(result_path) as writer:
                # 1. Batch Summary Sheet
                batch_summary_data = {
                    'Metric': [
                        'Total Rows',
                        'Successful Runs',
                        'Failed Runs',
                        'Success Rate (%)',
                        'Average Simulation Error (%)',
                        'Std Simulation Error (%)',
                        'Average Surrogate Error (%)',
                        'Std Surrogate Error (%)',
                        'Total Processing Time',
                        'Case Name',
                        'Timestamp'
                    ],
                    'Value': [
                        summary.get('total_rows', 0),
                        summary.get('successful_runs', 0),
                        summary.get('failed_runs', 0),
                        f"{summary.get('success_rate', 0):.2f}",
                        f"{batch_metrics.get('batch_sim_mean_rel_error', 'N/A'):.4f}" if isinstance(batch_metrics.get('batch_sim_mean_rel_error'), (int, float)) else 'N/A',
                        f"{batch_metrics.get('batch_sim_std_rel_error', 'N/A'):.4f}" if isinstance(batch_metrics.get('batch_sim_std_rel_error'), (int, float)) else 'N/A',
                        f"{batch_metrics.get('batch_surr_mean_rel_error', 'N/A'):.4f}" if isinstance(batch_metrics.get('batch_surr_mean_rel_error'), (int, float)) else 'N/A',
                        f"{batch_metrics.get('batch_surr_std_rel_error', 'N/A'):.4f}" if isinstance(batch_metrics.get('batch_surr_std_rel_error'), (int, float)) else 'N/A',
                        'N/A',  # Could be calculated if timing is tracked
                        result.case.name,
                        timestamp
                    ]
                }
                pd.DataFrame(batch_summary_data).to_excel(writer, sheet_name='Batch_Summary', index=False)
                
                # 2. Row-by-Row Summary Sheet
                summary_data = []
                for i, row_detail in enumerate(enhanced_data['row_details']):
                    row_summary = {
                        'Row': i + 1,
                        'Status': 'Success' if row_detail['success'] else 'Failed',
                        'Iterations_Run': row_detail.get('iterations_run', 'N/A'),
                        'Final_Cost': f"{row_detail.get('final_cost', 'N/A'):.6f}" if isinstance(row_detail.get('final_cost'), (int, float)) else 'N/A',
                        'Mean_Rel_Error_Percent': f"{row_detail.get('overall_metrics', {}).get('sim_mean_rel_error', 'N/A'):.4f}" if isinstance(row_detail.get('overall_metrics', {}).get('sim_mean_rel_error'), (int, float)) else 'N/A'
                    }
                    
                    # Add input data columns
                    if row_detail.get('input_data'):
                        for key, value in row_detail['input_data'].items():
                            if key not in ['Unnamed: 0', 'timestamp']:  # Skip metadata columns
                                row_summary[f'Input_{key}'] = value
                    
                    # Add calibrated parameters
                    if row_detail.get('calibration_result'):
                        for key, value in row_detail['calibration_result'].items():
                            row_summary[f'Calibrated_{key}'] = f"{value:.6f}" if isinstance(value, (int, float)) else value
                    
                    # Add target vs actual results
                    if row_detail.get('metrics'):
                        for param, metrics in row_detail['metrics'].items():
                            row_summary[f'{param}_Target'] = f"{metrics.get('true_value', 'N/A'):.4f}" if isinstance(metrics.get('true_value'), (int, float)) else 'N/A'
                            row_summary[f'{param}_Simulation'] = f"{metrics.get('simulation_value', 'N/A'):.4f}" if isinstance(metrics.get('simulation_value'), (int, float)) else 'N/A'
                            row_summary[f'{param}_Error_Percent'] = f"{metrics.get('sim_relative_error', 'N/A'):.4f}" if isinstance(metrics.get('sim_relative_error'), (int, float)) and metrics.get('sim_relative_error') != float('inf') else 'N/A'
                            
                            if 'surrogate_value' in metrics:
                                row_summary[f'{param}_Surrogate'] = f"{metrics.get('surrogate_value', 'N/A'):.4f}" if isinstance(metrics.get('surrogate_value'), (int, float)) else 'N/A'
                    
                    # Add error message for failed runs
                    if not row_detail['success']:
                        row_summary['Error_Message'] = row_detail.get('error', 'Unknown error')
                    
                    summary_data.append(row_summary)
                
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Row_Summary', index=False)
                
                # 3. Convergence Data Sheet (PSO costs for each row)
                convergence_data = []
                for i, row_detail in enumerate(enhanced_data['row_details']):
                    if row_detail['success'] and row_detail.get('costs_curve'):
                        costs = row_detail['costs_curve']
                        for iteration, cost in enumerate(costs):
                            convergence_data.append({
                                'Row': i + 1,
                                'Iteration': iteration + 1,
                                'Cost': cost
                            })
                
                if convergence_data:
                    pd.DataFrame(convergence_data).to_excel(writer, sheet_name='Convergence_Data', index=False)
                
                # 4. Detailed Results for each successful row (first 10 rows to avoid too many sheets)
                for i, row_detail in enumerate(enhanced_data['row_details'][:10]):
                    if row_detail['success']:
                        sheet_name = f'Row_{i+1}_Details'
                        
                        detailed_data = {}
                        
                        # Input parameters
                        if row_detail.get('calibration_result'):
                            for key, value in row_detail['calibration_result'].items():
                                detailed_data[f'Input_{key}'] = [value]
                        
                        # Simulation results
                        if row_detail.get('simulation_result'):
                            sim_result = row_detail['simulation_result']
                            if isinstance(sim_result, dict):
                                if 'outputs' in sim_result:
                                    for key, value_dict in sim_result['outputs'].items():
                                        if isinstance(value_dict, dict) and 'value' in value_dict:
                                            detailed_data[f'Output_{key}'] = [value_dict['value']]
                                else:
                                    for key, value in sim_result.items():
                                        if key not in ['inputs']:  # Skip inputs to avoid duplication
                                            detailed_data[f'Output_{key}'] = [value]
                        
                        # Metrics
                        if row_detail.get('metrics'):
                            for param, metrics in row_detail['metrics'].items():
                                detailed_data[f'{param}_Target'] = [metrics.get('true_value')]
                                detailed_data[f'{param}_Simulation'] = [metrics.get('simulation_value')]
                                detailed_data[f'{param}_Abs_Error'] = [metrics.get('sim_absolute_error')]
                                detailed_data[f'{param}_Rel_Error_Percent'] = [metrics.get('sim_relative_error')]
                                
                                if 'surrogate_value' in metrics:
                                    detailed_data[f'{param}_Surrogate'] = [metrics.get('surrogate_value')]
                                    detailed_data[f'{param}_Surr_Abs_Error'] = [metrics.get('surr_absolute_error')]
                                    detailed_data[f'{param}_Surr_Rel_Error_Percent'] = [metrics.get('surr_relative_error')]
                        
                        if detailed_data:
                            detailed_df = pd.DataFrame(detailed_data)
                            detailed_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Update result with file path
            result.file_path = result_path
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Error creating Excel file: {str(e)}")
        
        return jsonify({
            "success": True,
            "result_id": result.id,
            "summary": summary,
            "batch_metrics": batch_metrics
        })
    
    except Exception as e:
        current_app.logger.error(f"Error in save_batch_results: {str(e)}")
        return jsonify({"error": str(e)}), 500


@calibration_bp.route('/batch_details/<int:result_id>', methods=['GET'])
def batch_calibration_details(result_id):
    """
    Render the batch calibration details page with enhanced analytics
    """
    try:
        # Get the batch calibration result
        calibration = SimulationResult.query.get_or_404(result_id)
        
        # Check if it's a batch calibration result
        if not calibration.simulation_type.startswith('Batch Calibration'):
            flash("The requested result is not a batch calibration run", "warning")
            return redirect(url_for('calibration.index'))
        
        # Parse the JSON data with error handling
        try:
            data = json.loads(calibration.data) if calibration.data else {}
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Error parsing calibration data JSON: {str(e)}")
            data = {}
        
        # Extract data structure with defaults
        batch_results = data.get('batch_results', [])
        row_details = data.get('row_details', batch_results)  # Use row_details if available, fallback to batch_results
        
        # Calculate summary if not present
        summary = data.get('summary', {})
        if not summary and row_details:
            total_rows = len(row_details)
            successful_runs = sum(1 for result in row_details if result.get('success', False))
            failed_runs = total_rows - successful_runs
            success_rate = (successful_runs / total_rows * 100) if total_rows > 0 else 0
            
            summary = {
                'total_rows': total_rows,
                'successful_runs': successful_runs,
                'failed_runs': failed_runs,
                'success_rate': success_rate
            }
        
        # Calculate batch metrics if not present
        batch_metrics = data.get('batch_metrics', {})
        if not batch_metrics and row_details:
            successful_results = [r for r in row_details if r.get('success', False) and r.get('overall_metrics')]
            
            if successful_results:
                sim_errors = []
                surr_errors = []
                
                for result in successful_results:
                    metrics = result.get('overall_metrics', {})
                    if 'sim_mean_rel_error' in metrics and metrics['sim_mean_rel_error'] != float('inf'):
                        sim_errors.append(metrics['sim_mean_rel_error'])
                    if 'surr_mean_rel_error' in metrics and metrics['surr_mean_rel_error'] != float('inf'):
                        surr_errors.append(metrics['surr_mean_rel_error'])
                
                if sim_errors:
                    batch_metrics['batch_sim_mean_rel_error'] = sum(sim_errors) / len(sim_errors)
                    batch_metrics['batch_sim_std_rel_error'] = (sum((x - batch_metrics['batch_sim_mean_rel_error'])**2 for x in sim_errors) / len(sim_errors))**0.5
                
                if surr_errors:
                    batch_metrics['batch_surr_mean_rel_error'] = sum(surr_errors) / len(surr_errors)
                    batch_metrics['batch_surr_std_rel_error'] = (sum((x - batch_metrics['batch_surr_mean_rel_error'])**2 for x in surr_errors) / len(surr_errors))**0.5
        
        # Get configuration
        configuration = data.get('configuration', data)  # Fallback to root level data
        
        # Clean the row details data for template compatibility
        try:
            cleaned_row_details = clean_batch_results_for_template(row_details)
        except Exception as e:
            current_app.logger.error(f"Error cleaning batch results data: {str(e)}")
            cleaned_row_details = row_details  # Use original data as fallback
        
        # Prepare chart data for visualization with error handling
        try:
            chart_data = prepare_batch_chart_data(cleaned_row_details)
        except Exception as e:
            current_app.logger.error(f"Error preparing chart data: {str(e)}")
            chart_data = {
                'parameters': [],
                'rows': [],
                'target_values': {},
                'simulation_values': {},
                'surrogate_values': {},
                'convergence_data': {},
                'error_data': {}
            }
        
        return render_template('calibration/batch_calibration_details.html', 
                              calibration=calibration,
                              data=data,
                              batch_results=batch_results,
                              summary=summary,
                              batch_metrics=batch_metrics,
                              configuration=configuration,
                              row_details=cleaned_row_details,
                              chart_data=chart_data,
                              float=float)
    
    except Exception as e:
        current_app.logger.error(f"Error in batch_calibration_details: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('calibration.index'))

def prepare_batch_chart_data(row_details):
    """
    Prepare data for batch calibration charts with robust error handling
    """
    chart_data = {
        'parameters': [],
        'rows': [],
        'target_values': {},
        'simulation_values': {},
        'surrogate_values': {},
        'convergence_data': {},
        'error_data': {}
    }
    
    try:
        # Get all unique parameters from successful runs
        parameters_set = set()
        for row_detail in row_details:
            if row_detail.get('success') and row_detail.get('metrics'):
                parameters_set.update(row_detail['metrics'].keys())
        
        chart_data['parameters'] = sorted(list(parameters_set))
        
        # Prepare data for each row
        for i, row_detail in enumerate(row_details):
            row_num = i + 1
            chart_data['rows'].append(row_num)
            
            if row_detail.get('success') and row_detail.get('metrics'):
                # Extract target, simulation, and surrogate values for each parameter
                for param in chart_data['parameters']:
                    if param not in chart_data['target_values']:
                        chart_data['target_values'][param] = []
                        chart_data['simulation_values'][param] = []
                        chart_data['surrogate_values'][param] = []
                        chart_data['error_data'][param] = []
                    
                    if param in row_detail['metrics']:
                        metrics = row_detail['metrics'][param]
                        
                        # Safely extract numeric values with validation
                        def safe_numeric_extract(value, default=None):
                            if value is None:
                                return default
                            if isinstance(value, (int, float)):
                                return float(value) if not (isinstance(value, float) and (value != value or value == float('inf') or value == float('-inf'))) else default
                            if isinstance(value, list):
                                # If it's a list, try to get the first numeric value
                                for item in value:
                                    if isinstance(item, (int, float)) and not (isinstance(item, float) and (item != item or item == float('inf') or item == float('-inf'))):
                                        return float(item)
                                return default
                            try:
                                return float(value)
                            except (ValueError, TypeError):
                                return default
                        
                        target_val = safe_numeric_extract(metrics.get('true_value'))
                        sim_val = safe_numeric_extract(metrics.get('simulation_value'))
                        surr_val = safe_numeric_extract(metrics.get('surrogate_value'))
                        error_val = safe_numeric_extract(metrics.get('sim_relative_error'))
                        
                        chart_data['target_values'][param].append(target_val)
                        chart_data['simulation_values'][param].append(sim_val)
                        chart_data['surrogate_values'][param].append(surr_val)
                        chart_data['error_data'][param].append(error_val)
                    else:
                        chart_data['target_values'][param].append(None)
                        chart_data['simulation_values'][param].append(None)
                        chart_data['surrogate_values'][param].append(None)
                        chart_data['error_data'][param].append(None)
            else:
                # For failed runs, add None values
                for param in chart_data['parameters']:
                    if param not in chart_data['target_values']:
                        chart_data['target_values'][param] = []
                        chart_data['simulation_values'][param] = []
                        chart_data['surrogate_values'][param] = []
                        chart_data['error_data'][param] = []
                    
                    chart_data['target_values'][param].append(None)
                    chart_data['simulation_values'][param].append(None)
                    chart_data['surrogate_values'][param].append(None)
                    chart_data['error_data'][param].append(None)
            
            # Prepare convergence data with validation
            if row_detail.get('success') and row_detail.get('costs_curve'):
                costs = row_detail['costs_curve']
                if isinstance(costs, list) and len(costs) > 0:
                    # Validate and clean costs data
                    clean_costs = []
                    for cost_item in costs:
                        if isinstance(cost_item, list):
                            # If it's a list of costs (PSO particles), take the minimum
                            try:
                                numeric_costs = [float(c) for c in cost_item if isinstance(c, (int, float)) and not (isinstance(c, float) and (c != c or c == float('inf') or c == float('-inf')))]
                                if numeric_costs:
                                    clean_costs.append(min(numeric_costs))
                            except (ValueError, TypeError):
                                pass
                        elif isinstance(cost_item, (int, float)):
                            if not (isinstance(cost_item, float) and (cost_item != cost_item or cost_item == float('inf') or cost_item == float('-inf'))):
                                clean_costs.append(float(cost_item))
                    
                    if clean_costs:
                        chart_data['convergence_data'][row_num] = clean_costs
            
            # Also check costs_values as fallback
            elif row_detail.get('success') and row_detail.get('costs_values'):
                costs = row_detail['costs_values']
                if isinstance(costs, list) and len(costs) > 0:
                    clean_costs = []
                    for cost_item in costs:
                        if isinstance(cost_item, list):
                            try:
                                numeric_costs = [float(c) for c in cost_item if isinstance(c, (int, float)) and not (isinstance(c, float) and (c != c or c == float('inf') or c == float('-inf')))]
                                if numeric_costs:
                                    clean_costs.append(min(numeric_costs))
                            except (ValueError, TypeError):
                                pass
                        elif isinstance(cost_item, (int, float)):
                            if not (isinstance(cost_item, float) and (cost_item != cost_item or cost_item == float('inf') or cost_item == float('-inf'))):
                                clean_costs.append(float(cost_item))
                    
                    if clean_costs:
                        chart_data['convergence_data'][row_num] = clean_costs
        
    except Exception as e:
        current_app.logger.error(f"Error preparing batch chart data: {str(e)}")
        # Return empty chart data structure on error
        chart_data = {
            'parameters': [],
            'rows': [],
            'target_values': {},
            'simulation_values': {},
            'surrogate_values': {},
            'convergence_data': {},
            'error_data': {}
        }
    
    return chart_data

def clean_batch_results_for_template(row_details):
    """
    Clean batch results data to ensure template compatibility
    """
    cleaned_results = []
    
    for result in row_details:
        cleaned_result = result.copy()
        
        # Clean final_cost
        if 'final_cost' in cleaned_result and cleaned_result['final_cost'] is not None:
            final_cost = cleaned_result['final_cost']
            if isinstance(final_cost, list):
                if len(final_cost) > 0:
                    # Take minimum if it's a list of costs
                    try:
                        numeric_costs = [float(c) for c in final_cost if isinstance(c, (int, float)) and not (isinstance(c, float) and (c != c or c == float('inf') or c == float('-inf')))]
                        cleaned_result['final_cost'] = min(numeric_costs) if numeric_costs else None
                    except (ValueError, TypeError):
                        cleaned_result['final_cost'] = None
                else:
                    cleaned_result['final_cost'] = None
            elif not isinstance(final_cost, (int, float)):
                cleaned_result['final_cost'] = None
        
        # Clean costs_values
        if 'costs_values' in cleaned_result and cleaned_result['costs_values'] is not None:
            costs_values = cleaned_result['costs_values']
            if isinstance(costs_values, list) and len(costs_values) > 0:
                cleaned_costs = []
                for cost_item in costs_values:
                    if isinstance(cost_item, list):
                        try:
                            numeric_costs = [float(c) for c in cost_item if isinstance(c, (int, float)) and not (isinstance(c, float) and (c != c or c == float('inf') or c == float('-inf')))]
                            if numeric_costs:
                                cleaned_costs.append(min(numeric_costs))
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(cost_item, (int, float)):
                        if not (isinstance(cost_item, float) and (cost_item != cost_item or cost_item == float('inf') or cost_item == float('-inf'))):
                            cleaned_costs.append(float(cost_item))
                
                cleaned_result['costs_values'] = cleaned_costs if cleaned_costs else None
        
        # Clean iterations_run
        if 'iterations_run' in cleaned_result and cleaned_result['iterations_run'] is not None:
            iterations = cleaned_result['iterations_run']
            if isinstance(iterations, list):
                cleaned_result['iterations_run'] = len(iterations)
            elif not isinstance(iterations, (int, float)):
                cleaned_result['iterations_run'] = None
        
        # Clean overall_metrics values
        if 'overall_metrics' in cleaned_result and cleaned_result['overall_metrics']:
            cleaned_metrics = {}
            for key, value in cleaned_result['overall_metrics'].items():
                if isinstance(value, list):
                    try:
                        numeric_values = [float(v) for v in value if isinstance(v, (int, float)) and not (isinstance(v, float) and (v != v or v == float('inf') or v == float('-inf')))]
                        cleaned_metrics[key] = sum(numeric_values) / len(numeric_values) if numeric_values else None
                    except (ValueError, TypeError):
                        cleaned_metrics[key] = None
                else:
                    cleaned_metrics[key] = value
            cleaned_result['overall_metrics'] = cleaned_metrics
        
        cleaned_results.append(cleaned_result)
    
    return cleaned_results




import os
import json
from flask import Blueprint, render_template, request, jsonify, current_app
from api.database import db, Case
from driver.Simulation.simulation_driver import SimulationDriver
import pythoncom

parameters_bp = Blueprint('parameters', __name__, url_prefix='/parameters')

@parameters_bp.route('/configure/<int:case_id>')
def configure_parameters(case_id):
    """Render the parameter configuration page for a case"""
    case = Case.query.get_or_404(case_id)
    return render_template('cases/parameters/configure.html', case=case, active_page='cases')

@parameters_bp.route('/api/explore/<int:case_id>')
def explore_model(case_id):
    """API endpoint to explore the HYSYS model and return its structure"""
    case = Case.query.get_or_404(case_id)
    
    # Check if simulation file exists
    if not case.simulation_file:
        return jsonify({"error": "No simulation file associated with this case"}), 400
    
    # Construct the full path to the simulation file
    sim_file_path = os.path.join(case.folder_path, 'HysysModel', case.simulation_file)
    if not os.path.exists(sim_file_path):
        return jsonify({"error": f"Simulation file not found at {sim_file_path}"}), 404
    
    try:
        # Initialize COM
        pythoncom.CoInitialize()

        # Initialize the simulation driver
        sim_driver = SimulationDriver('hysys', sim_file_path)
        
        # Load the model
        sim_driver.load_model()
        
        # Explore the model
        model_info = sim_driver.explore()
        
        # Close the driver
        sim_driver.close()
        
        return jsonify(model_info)
    except Exception as e:
        current_app.logger.error(f"Error exploring model: {str(e)}")
        return jsonify({"error": f"Failed to explore model: {str(e)}"}), 500
    finally:
        # Always uninitialize COM
        pythoncom.CoUninitialize()

@parameters_bp.route('/api/configure/<int:case_id>', methods=['POST'])
def save_parameters(case_id):
    """API endpoint to save parameter configuration for a case"""
    case = Case.query.get_or_404(case_id)
    
    # Get parameters from request
    data = request.json
    parameters = data.get('parameters', [])
    
    if not parameters:
        return jsonify({"error": "No parameters provided"}), 400
    
    try:
        # Initialize the driver format structure
        driver_format_parameters = {
            "InputParams": {
                "Spreadsheet": {},
                "MaterialStream": {},
                "EnergyStream": {}
            },
            "OutputParameters": {
                "Spreadsheet": {},
                "MaterialStream": {},
                "EnergyStream": {}
            }
        }
        
        # Process each parameter
        for param in parameters:
            param_type = "InputParams" if param['type'] == 'input' else "OutputParameters"
            source = param['subtype']
            name = param['parameterName']
            
            if source == 'Spreadsheet':
                driver_format_parameters[param_type]["Spreadsheet"][name] = {
                    "SpreadsheetName": param['spreadsheetName'],
                    "Cell": param['cell']
                }
                
                if 'uom' in param and param['uom']:
                    driver_format_parameters[param_type]["Spreadsheet"][name]["UOM"] = param['uom']
                    
            elif source == 'MaterialStream':
                param_config = {
                    "StreamName": param['streamName'],
                    "ParameterType": param['parameterType']
                }
                
                if param['parameterType'] == 'Property':
                    param_config["PropertyName"] = param['propertyName']
                    if 'uom' in param and param['uom']:
                        param_config["UOM"] = param['uom']
                else:
                    # Component-based parameter
                    if 'components' in param and param['components']:
                        param_config["GetComponents"] = param['components']
                    
                    if 'scaleFactor' in param:
                        param_config["ScaleFactor"] = param['scaleFactor']
                
                driver_format_parameters[param_type]["MaterialStream"][name] = param_config
                
            elif source == 'EnergyStream':
                driver_format_parameters[param_type]["EnergyStream"][name] = {
                    "StreamName": param['streamName'],
                    "PropertyName": param['propertyName']
                }
                
                if 'uom' in param and param['uom']:
                    driver_format_parameters[param_type]["EnergyStream"][name]["UOM"] = param['uom']

        # Persist flattened input/output name lists so other workflows
        # can reuse the case's simulation model config directly.
        driver_format_parameters["x_cols"] = list(dict.fromkeys(
            list(driver_format_parameters["InputParams"]["Spreadsheet"].keys()) +
            list(driver_format_parameters["InputParams"]["MaterialStream"].keys()) +
            list(driver_format_parameters["InputParams"]["EnergyStream"].keys())
        ))
        driver_format_parameters["y_cols"] = list(dict.fromkeys(
            list(driver_format_parameters["OutputParameters"]["Spreadsheet"].keys()) +
            list(driver_format_parameters["OutputParameters"]["MaterialStream"].keys()) +
            list(driver_format_parameters["OutputParameters"]["EnergyStream"].keys())
        ))
        
        # Update case parameters
        case.parameters = driver_format_parameters
        db.session.commit()
        
        return jsonify({"success": True, "message": "Parameters saved successfully"})
    except Exception as e:
        current_app.logger.error(f"Error saving parameters: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Failed to save parameters: {str(e)}"}), 500

import os
import json
import pandas as pd
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for, send_file
from api.database import db, Case, SimulationResult
from driver.Simulation.simulation_driver import SimulationDriver
import pythoncom
import tempfile

simulations_bp = Blueprint('simulations', __name__, url_prefix='/simulations')

@simulations_bp.route('/')
def index():
    # Get all cases
    cases = Case.query.order_by(Case.name).all()
    
    return render_template(
        'simulations/simulations_landing.html', 
        cases=cases
    )

@simulations_bp.route('/run')
@simulations_bp.route('/run/<int:case_id>')
def run_simulation(case_id=None):
    """Render the simulation run page for a case"""
    if case_id is None:
        # No case selected, render the case selection interface
        return render_template('simulations/run.html', case=None, active_page='cases')
    
    # Case is selected, get it and render the normal interface
    case = Case.query.get_or_404(case_id)
    return render_template('simulations/run.html', case=case, active_page='cases')

@simulations_bp.route('/results/<int:case_id>')
def simulation_results(case_id):
    """Render the simulation results page for a case"""
    case = Case.query.get_or_404(case_id)
    
    # Get latest result
    latest_result = SimulationResult.query.filter_by(case_id=case_id).order_by(SimulationResult.timestamp.desc()).first()
    
    # Get all results for history
    results_history = SimulationResult.query.filter_by(case_id=case_id).order_by(SimulationResult.timestamp.desc()).all()
    
    return render_template('simulations/results.html', 
                          case=case, 
                          latest_result=latest_result.data if latest_result else None,
                          results_history=results_history,
                          active_page='cases')

@simulations_bp.route('/api/run/<int:case_id>', methods=['POST'])
def api_run_simulation(case_id):
    """API endpoint to run a simulation for a case"""
    case = Case.query.get_or_404(case_id)
    
    # Check if simulation file exists
    if not case.simulation_file:
        return jsonify({"error": "No simulation file associated with this case"}), 400
    
    # Get input parameters from request
    data = request.json
    input_params = data.get('input_params', {})
    
    # Construct the full path to the simulation file
    sim_file_path = os.path.join(case.folder_path, 'HysysModel', case.simulation_file)
    if not os.path.exists(sim_file_path):
        return jsonify({"error": f"Simulation file not found at {sim_file_path}"}), 404
    
    try:
        # Initialize COM
        pythoncom.CoInitialize()

        # Initialize the simulation driver
        sim_driver = SimulationDriver('hysys', sim_file_path, case.parameters, resultindict=True)
        
        # Load the model
        sim_driver.load_model()
        
        # Run the simulation
        results = sim_driver.predict(data=input_params, flatten_components=False, include_inputs=True)
        
        # Don't close the driver here to keep the simulation open
        #sim_driver.close()
        
        return jsonify({"success": True, "results": results})
    except Exception as e:
        current_app.logger.error(f"Error running simulation: {str(e)}")
        return jsonify({"error": f"Failed to run simulation: {str(e)}"}), 500
    finally:
        # Always uninitialize COM
        pythoncom.CoUninitialize()

@simulations_bp.route('/api/close/<int:case_id>', methods=['POST'])
def api_close_simulation(case_id):
    """API endpoint to close a simulation for a case"""
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
        sim_driver = SimulationDriver('hysys', sim_file_path, case.parameters, resultindict=True)
        
        # Close the driver
        sim_driver.close()
        
        return jsonify({"success": True, "message": "Simulation closed successfully"})
    except Exception as e:
        current_app.logger.error(f"Error closing simulation: {str(e)}")
        return jsonify({"error": f"Failed to close simulation: {str(e)}"}), 500
    finally:
        # Always uninitialize COM
        pythoncom.CoUninitialize()

@simulations_bp.route('/api/save_results/<int:case_id>', methods=['POST'])
def api_save_results(case_id):
    """API endpoint to save simulation results"""
    case = Case.query.get_or_404(case_id)
    
    # Get results from request
    data = request.json
    results = data.get('results', {})
    name = data.get('name')
    simulation_type = data.get('simulation_type', 'Single Run')
    
    if not results:
        return jsonify({"error": "No results provided"}), 400
    
    try:
        # Create new simulation result
        new_result = SimulationResult(
            case_id=case.id,
            timestamp=datetime.now(),
            data=results,
            name=name,
            simulation_type=simulation_type
        )
        
        db.session.add(new_result)
        db.session.commit()
        
        return jsonify({"success": True, "result_id": new_result.id})
    except Exception as e:
        current_app.logger.error(f"Error saving results: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Failed to save results: {str(e)}"}), 500

@simulations_bp.route('/api/result/<int:result_id>')
def api_get_result(result_id):
    """API endpoint to get a specific simulation result"""
    result = SimulationResult.query.get_or_404(result_id)
    
    return jsonify({"success": True, "result": result.data})

@simulations_bp.route('/api/result/<int:result_id>', methods=['DELETE'])
def api_delete_result(result_id):
    """API endpoint to delete a simulation result"""
    result = SimulationResult.query.get_or_404(result_id)
    
    try:
        db.session.delete(result)
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Error deleting result: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Failed to delete result: {str(e)}"}), 500

@simulations_bp.route('/api/compare_results', methods=['POST'])
def api_compare_results():
    """API endpoint to get multiple results for comparison"""
    data = request.json
    result_ids = data.get('result_ids', [])
    
    if not result_ids:
        return jsonify({"error": "No result IDs provided"}), 400
    
    try:
        # Get all requested results
        results = []
        for result_id in result_ids:
            result = SimulationResult.query.get(result_id)
            if result:
                results.append(result.data)
        
        return jsonify({"success": True, "results": results})
    except Exception as e:
        current_app.logger.error(f"Error comparing results: {str(e)}")
        return jsonify({"error": f"Failed to compare results: {str(e)}"}), 500

@simulations_bp.route('/visualize/<int:case_id>')
def visualize_results(case_id):
    """Render the visualization page for simulation results"""
    case = Case.query.get_or_404(case_id)
    
    # Get results from query parameter
    results_json = request.args.get('results')
    results = json.loads(results_json) if results_json else None
    
    if not results:
        flash('No results provided for visualization', 'warning')
        return redirect(url_for('simulations.simulation_results', case_id=case_id))
    
    return render_template('simulations/visualize.html', 
                          case=case, 
                          results=results,
                          active_page='cases')

@simulations_bp.route('/api/result/<int:result_id>/update', methods=['POST'])
def api_update_result(result_id):
    """API endpoint to update a simulation result's metadata"""
    result = SimulationResult.query.get_or_404(result_id)
    
    # Get data from request
    data = request.json
    name = data.get('name')
    simulation_type = data.get('simulation_type')
    
    try:
        # Update result
        if name is not None:
            result.name = name
        if simulation_type is not None:
            result.simulation_type = simulation_type
        
        # Save changes
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "Result updated successfully",
            "result_id": result.id,
            "name": result.name,
            "simulation_type": result.simulation_type
        })
    except Exception as e:
        current_app.logger.error(f"Error updating result: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Failed to update result: {str(e)}"}), 500

@simulations_bp.route('/api/download/<int:result_id>')
def api_download_result(result_id):
    """API endpoint to download a simulation result as Excel"""
    result = SimulationResult.query.get_or_404(result_id)
    case = Case.query.get_or_404(result.case_id)
    
    try:
        import tempfile
        from flask import send_file
        
        # Create a list to store all rows for the DataFrame
        rows = []
        
        # Helper function to extract source info from parameter name
        def extract_source_info(param_name, param_type):
            # Try to find the parameter in the case configuration
            if case.parameters:
                # Check in input parameters
                if param_type == 'Input' and 'InputParams' in case.parameters:
                    # Check in Spreadsheet parameters
                    if 'Spreadsheet' in case.parameters['InputParams']:
                        for name, config in case.parameters['InputParams']['Spreadsheet'].items():
                            if name == param_name:
                                return 'Spreadsheet', config.get('SpreadsheetName', '')
                    
                    # Check in MaterialStream parameters
                    if 'MaterialStream' in case.parameters['InputParams']:
                        for name, config in case.parameters['InputParams']['MaterialStream'].items():
                            if name == param_name:
                                return 'MaterialStream', config.get('StreamName', '')
                    
                    # Check in EnergyStream parameters
                    if 'EnergyStream' in case.parameters['InputParams']:
                        for name, config in case.parameters['InputParams']['EnergyStream'].items():
                            if name == param_name:
                                return 'EnergyStream', config.get('StreamName', '')
                
                # Check in output parameters
                if param_type == 'Output' and 'OutputParameters' in case.parameters:
                    # Check in Spreadsheet parameters
                    if 'Spreadsheet' in case.parameters['OutputParameters']:
                        for name, config in case.parameters['OutputParameters']['Spreadsheet'].items():
                            if name == param_name:
                                return 'Spreadsheet', config.get('SpreadsheetName', '')
                    
                    # Check in MaterialStream parameters
                    if 'MaterialStream' in case.parameters['OutputParameters']:
                        for name, config in case.parameters['OutputParameters']['MaterialStream'].items():
                            if name == param_name:
                                return 'MaterialStream', config.get('StreamName', '')
                    
                    # Check in EnergyStream parameters
                    if 'EnergyStream' in case.parameters['OutputParameters']:
                        for name, config in case.parameters['OutputParameters']['EnergyStream'].items():
                            if name == param_name:
                                return 'EnergyStream', config.get('StreamName', '')
            
            # Try to infer from parameter name
            if '_' in param_name:
                parts = param_name.split('_')
                if len(parts) >= 2:
                    # First part might be the stream name
                    if any(x in parts[1].lower() for x in ['temp', 'temperature', 'press', 'pressure', 'flow', 'frac']):
                        return 'MaterialStream', parts[0]
            
            return 'Unknown', ''
        
        # Helper function to process component dictionaries
        def process_component_dict(param_name, param_dict, param_type):
            for comp_name, comp_value in param_dict.items():
                source_type, source_name = extract_source_info(param_name, param_type)
                
                if isinstance(comp_value, dict) and 'value' in comp_value:
                    rows.append({
                        'Parameter Type': param_type,
                        'Parameter Name': f"{param_name} - {comp_name}",
                        'Full Parameter Name': f"{param_name}_{comp_name}",
                        'Source Type': source_type,
                        'Source Name': source_name,
                        'Value': comp_value['value'],
                        'Unit': comp_value.get('uom', ''),
                        'Component': comp_name
                    })
                else:
                    rows.append({
                        'Parameter Type': param_type,
                        'Parameter Name': f"{param_name} - {comp_name}",
                        'Full Parameter Name': f"{param_name}_{comp_name}",
                        'Source Type': source_type,
                        'Source Name': source_name,
                        'Value': comp_value,
                        'Unit': '',
                        'Component': comp_name
                    })
        
        # Process input parameters
        if 'inputs' in result.data:
            for param_name, param_value in result.data['inputs'].items():
                # Get source information
                source_type, source_name = extract_source_info(param_name, 'Input')
                
                # Check if this is a component dictionary
                if isinstance(param_value, dict):
                    # Check if it's a value with UOM
                    if 'value' in param_value and 'uom' in param_value:
                        rows.append({
                            'Parameter Type': 'Input',
                            'Parameter Name': param_name,
                            'Full Parameter Name': param_name,
                            'Source Type': source_type,
                            'Source Name': source_name,
                            'Value': param_value['value'],
                            'Unit': param_value['uom'],
                            'Component': ''
                        })
                    # Check if it's a component dictionary
                    elif all(isinstance(k, str) and (isinstance(v, (dict, float, int)) or v is None) for k, v in param_value.items()):
                        # This is likely a component dictionary
                        process_component_dict(param_name, param_value, 'Input')
                    else:
                        # Some other dictionary, convert to string
                        rows.append({
                            'Parameter Type': 'Input',
                            'Parameter Name': param_name,
                            'Full Parameter Name': param_name,
                            'Source Type': source_type,
                            'Source Name': source_name,
                            'Value': str(param_value),
                            'Unit': '',
                            'Component': ''
                        })
                else:
                    # Simple value
                    rows.append({
                        'Parameter Type': 'Input',
                        'Parameter Name': param_name,
                        'Full Parameter Name': param_name,
                        'Source Type': source_type,
                        'Source Name': source_name,
                        'Value': param_value,
                        'Unit': '',
                        'Component': ''
                    })
        
        # Process output parameters
        if 'outputs' in result.data:
            for param_name, param_value in result.data['outputs'].items():
                # Get source information
                source_type, source_name = extract_source_info(param_name, 'Output')
                
                # Check if this is a component dictionary
                if isinstance(param_value, dict):
                    # Check if it's a value with UOM
                    if 'value' in param_value and 'uom' in param_value:
                        rows.append({
                            'Parameter Type': 'Output',
                            'Parameter Name': param_name,
                            'Full Parameter Name': param_name,
                            'Source Type': source_type,
                            'Source Name': source_name,
                            'Value': param_value['value'],
                            'Unit': param_value['uom'],
                            'Component': ''
                        })
                    # Check if it's a component dictionary
                    elif all(isinstance(k, str) and (isinstance(v, (dict, float, int)) or v is None) for k, v in param_value.items()):
                        # This is likely a component dictionary
                        process_component_dict(param_name, param_value, 'Output')
                    else:
                        # Some other dictionary, convert to string
                        rows.append({
                            'Parameter Type': 'Output',
                            'Parameter Name': param_name,
                            'Full Parameter Name': param_name,
                            'Source Type': source_type,
                            'Source Name': source_name,
                            'Value': str(param_value),
                            'Unit': '',
                            'Component': ''
                        })
                else:
                    # Simple value
                    rows.append({
                        'Parameter Type': 'Output',
                        'Parameter Name': param_name,
                        'Full Parameter Name': param_name,
                        'Source Type': source_type,
                        'Source Name': source_name,
                        'Value': param_value,
                        'Unit': '',
                        'Component': ''
                    })
        
        # Create DataFrame from rows
        df = pd.DataFrame(rows)
        
        # Create a temporary file to store the Excel
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            temp_path = tmp.name
        
        # Save DataFrame to Excel
        with pd.ExcelWriter(temp_path, engine='xlsxwriter') as writer:
            # Write the main data
            df.to_excel(writer, sheet_name='Simulation Results', index=False)
            
            # Format the Excel file
            workbook = writer.book
            worksheet = writer.sheets['Simulation Results']
            
            # Add formats
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#D7E4BC',
                'border': 1
            })
            
            # Write the headers with the format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                
            # Adjust column widths
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
        
        # Generate filename
        result_name = result.name or f"Result_{result_id}"
        safe_name = "".join([c if c.isalnum() or c in ['-', '_'] else '_' for c in result_name])
        filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Send the file
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading result: {str(e)}")
        return jsonify({"error": f"Failed to download result: {str(e)}"}), 500

@simulations_bp.route('/api/download_temp_result/<int:case_id>', methods=['POST'])
def api_download_temp_result(case_id):
    """API endpoint to download a temporary simulation result as Excel"""
    case = Case.query.get_or_404(case_id)
    
    try:
        # Get result data from request
        data = request.json
        result_data = data.get('results')
        
        if not result_data:
            return jsonify({"error": "No result data provided"}), 400
        
        # Create a list to store all rows for the DataFrame
        rows = []
        
        # Helper function to extract source info from parameter name
        def extract_source_info(param_name, param_type):
            # Try to find the parameter in the case configuration
            if case.parameters:
                # Check in input parameters
                if param_type == 'Input' and 'InputParams' in case.parameters:
                    # Check in Spreadsheet parameters
                    if 'Spreadsheet' in case.parameters['InputParams']:
                        for name, config in case.parameters['InputParams']['Spreadsheet'].items():
                            if name == param_name:
                                return 'Spreadsheet', config.get('SpreadsheetName', '')
                    
                    # Check in MaterialStream parameters
                    if 'MaterialStream' in case.parameters['InputParams']:
                        for name, config in case.parameters['InputParams']['MaterialStream'].items():
                            if name == param_name:
                                return 'MaterialStream', config.get('StreamName', '')
                    
                    # Check in EnergyStream parameters
                    if 'EnergyStream' in case.parameters['InputParams']:
                        for name, config in case.parameters['InputParams']['EnergyStream'].items():
                            if name == param_name:
                                return 'EnergyStream', config.get('StreamName', '')
                
                # Check in output parameters
                if param_type == 'Output' and 'OutputParameters' in case.parameters:
                    # Check in Spreadsheet parameters
                    if 'Spreadsheet' in case.parameters['OutputParameters']:
                        for name, config in case.parameters['OutputParameters']['Spreadsheet'].items():
                            if name == param_name:
                                return 'Spreadsheet', config.get('SpreadsheetName', '')
                    
                    # Check in MaterialStream parameters
                    if 'MaterialStream' in case.parameters['OutputParameters']:
                        for name, config in case.parameters['OutputParameters']['MaterialStream'].items():
                            if name == param_name:
                                return 'MaterialStream', config.get('StreamName', '')
                    
                    # Check in EnergyStream parameters
                    if 'EnergyStream' in case.parameters['OutputParameters']:
                        for name, config in case.parameters['OutputParameters']['EnergyStream'].items():
                            if name == param_name:
                                return 'EnergyStream', config.get('StreamName', '')
            
            # Try to infer from parameter name
            if '_' in param_name:
                parts = param_name.split('_')
                if len(parts) >= 2:
                    # First part might be the stream name
                    if any(x in parts[1].lower() for x in ['temp', 'temperature', 'press', 'pressure', 'flow', 'frac']):
                        return 'MaterialStream', parts[0]
            
            return 'Unknown', ''
        
        # Helper function to process component dictionaries
        def process_component_dict(param_name, param_dict, param_type):
            for comp_name, comp_value in param_dict.items():
                source_type, source_name = extract_source_info(param_name, param_type)
                
                if isinstance(comp_value, dict) and 'value' in comp_value:
                    rows.append({
                        'Parameter Type': param_type,
                        'Parameter Name': f"{param_name} - {comp_name}",
                        'Full Parameter Name': f"{param_name}_{comp_name}",
                        'Source Type': source_type,
                        'Source Name': source_name,
                        'Value': comp_value['value'],
                        'Unit': comp_value.get('uom', ''),
                        'Component': comp_name
                    })
                else:
                    rows.append({
                        'Parameter Type': param_type,
                        'Parameter Name': f"{param_name} - {comp_name}",
                        'Full Parameter Name': f"{param_name}_{comp_name}",
                        'Source Type': source_type,
                        'Source Name': source_name,
                        'Value': comp_value,
                        'Unit': '',
                        'Component': comp_name
                    })
        
        # Process input parameters
        if 'inputs' in result_data:
            for param_name, param_value in result_data['inputs'].items():
                # Get source information
                source_type, source_name = extract_source_info(param_name, 'Input')
                
                # Check if this is a component dictionary
                if isinstance(param_value, dict):
                    # Check if it's a value with UOM
                    if 'value' in param_value and 'uom' in param_value:
                        rows.append({
                            'Parameter Type': 'Input',
                            'Parameter Name': param_name,
                            'Full Parameter Name': param_name,
                            'Source Type': source_type,
                            'Source Name': source_name,
                            'Value': param_value['value'],
                            'Unit': param_value['uom'],
                            'Component': ''
                        })
                    # Check if it's a component dictionary
                    elif all(isinstance(k, str) and (isinstance(v, (dict, float, int)) or v is None) for k, v in param_value.items()):
                        # This is likely a component dictionary
                        process_component_dict(param_name, param_value, 'Input')
                    else:
                        # Some other dictionary, convert to string
                        rows.append({
                            'Parameter Type': 'Input',
                            'Parameter Name': param_name,
                            'Full Parameter Name': param_name,
                            'Source Type': source_type,
                            'Source Name': source_name,
                            'Value': str(param_value),
                            'Unit': '',
                            'Component': ''
                        })
                else:
                    # Simple value
                    rows.append({
                        'Parameter Type': 'Input',
                        'Parameter Name': param_name,
                        'Full Parameter Name': param_name,
                        'Source Type': source_type,
                        'Source Name': source_name,
                        'Value': param_value,
                        'Unit': '',
                        'Component': ''
                    })
        
        # Process output parameters
        if 'outputs' in result_data:
            for param_name, param_value in result_data['outputs'].items():
                # Get source information
                source_type, source_name = extract_source_info(param_name, 'Output')
                
                # Check if this is a component dictionary
                if isinstance(param_value, dict):
                    # Check if it's a value with UOM
                    if 'value' in param_value and 'uom' in param_value:
                        rows.append({
                            'Parameter Type': 'Output',
                            'Parameter Name': param_name,
                            'Full Parameter Name': param_name,
                            'Source Type': source_type,
                            'Source Name': source_name,
                            'Value': param_value['value'],
                            'Unit': param_value['uom'],
                            'Component': ''
                        })
                    # Check if it's a component dictionary
                    elif all(isinstance(k, str) and (isinstance(v, (dict, float, int)) or v is None) for k, v in param_value.items()):
                        # This is likely a component dictionary
                        process_component_dict(param_name, param_value, 'Output')
                    else:
                        # Some other dictionary, convert to string
                        rows.append({
                            'Parameter Type': 'Output',
                            'Parameter Name': param_name,
                            'Full Parameter Name': param_name,
                            'Source Type': source_type,
                            'Source Name': source_name,
                            'Value': str(param_value),
                            'Unit': '',
                            'Component': ''
                        })
                else:
                    # Simple value
                    rows.append({
                        'Parameter Type': 'Output',
                        'Parameter Name': param_name,
                        'Full Parameter Name': param_name,
                        'Source Type': source_type,
                        'Source Name': source_name,
                        'Value': param_value,
                        'Unit': '',
                        'Component': ''
                    })
        
        # Create DataFrame from rows
        df = pd.DataFrame(rows)
        
        # Create a temporary file to store the Excel
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            temp_path = tmp.name
        
        # Save DataFrame to Excel
        with pd.ExcelWriter(temp_path, engine='xlsxwriter') as writer:
            # Write the main data
            df.to_excel(writer, sheet_name='Simulation Results', index=False)
            
            # Format the Excel file
            workbook = writer.book
            worksheet = writer.sheets['Simulation Results']
            
            # Add formats
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#D7E4BC',
                'border': 1
            })
            
            # Write the headers with the format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                
            # Adjust column widths
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
        
        # Generate filename
        safe_name = f"Simulation_{case.name.replace(' ', '_')}"
        filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Send the file
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading result: {str(e)}")
        return jsonify({"error": f"Failed to download result: {str(e)}"}), 500
    
@simulations_bp.route('/batch_results/<int:result_id>')
def batch_simulation_results(result_id):
    """Render the batch simulation results page"""
    # Get the simulation result directly by ID
    result = SimulationResult.query.get_or_404(result_id)

    # Check if this is a batch result
    if result.simulation_type != "Batch Run":
        flash('Not a batch simulation result', 'danger')
        return redirect(url_for('cases.case_detail', case_id=result.case_id))
    
    # Get the case
    case = Case.query.get_or_404(result.case_id)
    
    # Get the results path from the data
    results_path = result.data.get('results_path')
    
    if not results_path or not os.path.exists(results_path):
        flash('Results file not found', 'danger')
        return redirect(url_for('cases.case_detail', case_id=case.id))
    
    try:
        # Read inputs and outputs from Excel
        inputs_df = pd.read_excel(results_path, sheet_name='Inputs', index_col='Sample ID')
        outputs_df = pd.read_excel(results_path, sheet_name='Outputs', index_col='Sample ID')
        
        # Add these lines to handle static inputs
        has_static_inputs = result.data.get('has_static_inputs', False)
        static_inputs = None
        
        if has_static_inputs:
            try:
                # Try to read from Excel first
                static_inputs_df = pd.read_excel(results_path, sheet_name='Static Inputs')
                static_inputs = static_inputs_df.to_dict(orient='records')
            except Exception:
                # If not in Excel, try from the result data
                static_inputs = result.data.get('static_inputs')

        # Read metadata
        metadata_df = pd.read_excel(results_path, sheet_name='Metadata')
        metadata = metadata_df.to_dict(orient='records')[0] if not metadata_df.empty else {}
        
        return render_template(
            'simulations/batch_results.html',
            result=result,
            case=case,
            metadata=metadata,
            inputs_count=len(inputs_df),
            outputs_count=len(outputs_df),
            has_static_inputs=has_static_inputs,
            static_inputs=static_inputs,
            completed=result.data.get('completed', 0),
            total=result.data.get('total_samples', 0),
            active_page='cases',
            referrer=request.referrer,
        )
    except Exception as e:
        current_app.logger.error(f"Error reading batch results: {str(e)}")
        flash(f"Error reading batch results: {str(e)}", 'danger')
        return redirect(url_for('cases.case_detail', case_id=case.id))

@simulations_bp.route('/api/batch/<int:result_id>/data')
def api_get_batch_data(result_id):
    """API endpoint to get batch simulation data for visualization and analysis"""
    try:
        # Get the result
        result = SimulationResult.query.get_or_404(result_id)
        
        # Check if this is a batch result
        if result.simulation_type != "Batch Run":
            return jsonify({"error": "Not a batch simulation result"}), 400
        
        # Get the results path from the data
        results_path = result.data.get('results_path')
        
        if not results_path or not os.path.exists(results_path):
            return jsonify({"error": "Results file not found"}), 404
        
        # Read inputs and outputs from Excel
        inputs_df = pd.read_excel(results_path, sheet_name='Inputs', index_col='Sample ID')
        outputs_df = pd.read_excel(results_path, sheet_name='Outputs', index_col='Sample ID')
        
        # Read metadata
        try:
            metadata_df = pd.read_excel(results_path, sheet_name='Metadata')
            # Convert to Python native types to ensure JSON serialization
            metadata = metadata_df.to_dict(orient='records')[0] if not metadata_df.empty else {}
            # Convert any NumPy types to Python native types
            metadata = {k: v.item() if hasattr(v, 'item') else v for k, v in metadata.items()}
        except Exception as e:
            current_app.logger.error(f"Error reading Metadata sheet: {str(e)}")
            metadata = {}
        
        # Add input and output parameter names to metadata
        metadata['input_params'] = list(inputs_df.columns)
        metadata['output_params'] = list(outputs_df.columns)
        
        # Combine inputs and outputs into a single result set
        results = []
        for i in range(len(inputs_df)):
            row_result = {}
            # Add input parameters
            for col in inputs_df.columns:
                value = inputs_df.iloc[i][col]
                # Convert NumPy types to Python native types
                if hasattr(value, 'item'):
                    value = value.item()
                row_result[col] = value
            
            # Add output parameters if available
            if i < len(outputs_df):
                for col in outputs_df.columns:
                    value = outputs_df.iloc[i][col]
                    # Convert NumPy types to Python native types
                    if hasattr(value, 'item'):
                        value = value.item()
                    row_result[col] = value
            
            results.append(row_result)
        
        # Return the combined data
        return jsonify({
            "metadata": metadata,
            "results": results,
            "total_samples": len(results),
            "completed": result.data.get('completed', 0) if hasattr(result.data.get('completed', 0), 'item') 
                         else result.data.get('completed', 0)
        })
    except Exception as e:
        current_app.logger.error(f"Error reading batch results: {str(e)}")
        return jsonify({"error": f"Failed to read batch results: {str(e)}"}), 500
import os
import json
from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename
from api.database import db, Case
from datetime import datetime
from driver.Simulation.simulation_driver import SimulationDriver

cases_bp = Blueprint('cases', __name__, url_prefix='/cases')

def allowed_file(filename):
    """Check if the file has an allowed extension"""
    ALLOWED_EXTENSIONS = {'hsc', 'hysys', 'bkp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# API endpoints
@cases_bp.route('/api/list', methods=['GET'])
def api_list_cases():
    """API endpoint to get all cases"""
    cases = Case.query.all()
    result = []
    
    for case in cases:
        result.append({
            'id': case.id,
            'name': case.name,
            'description': case.description,
            'driver_type': case.driver_type,
            'simulation_file': case.simulation_file,
            'created_at': case.created_at.isoformat(),
            'updated_at': case.updated_at.isoformat() if case.updated_at else None
        })
    
    return jsonify(result)

@cases_bp.route('/api/<int:case_id>', methods=['GET'])
def api_get_case(case_id):
    """API endpoint to get a specific case by ID"""
    case = Case.query.get_or_404(case_id)
    
    result = {
        'id': case.id,
        'name': case.name,
        'description': case.description,
        'driver_type': case.driver_type,
        'simulation_file': case.simulation_file,
        'parameters': case.parameters,
        'folder_path': case.folder_path,
        'created_at': case.created_at.isoformat(),
        'updated_at': case.updated_at.isoformat() if case.updated_at else None
    }
    
    return jsonify(result)

@cases_bp.route('/api/create', methods=['POST'])
def api_create_case():
    """API endpoint to create a new case"""
    data = request.form
    
    # Validate required fields
    if not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    
    # Create case folder structure
    case_folder = os.path.join(current_app.config['CASES_FOLDER'], secure_filename(data.get('name')))
    if not os.path.exists(case_folder):
        os.makedirs(case_folder)
        os.makedirs(os.path.join(case_folder, 'HysysModel'))
        os.makedirs(os.path.join(case_folder, 'Results'))
    
    # Handle file upload
    simulation_file = None
    if 'simulation_file' in request.files:
        file = request.files['simulation_file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(case_folder, 'HysysModel', filename)
            file.save(file_path)
            simulation_file = filename
    
    # Create new case
    new_case = Case(
        name=data.get('name'),
        description=data.get('description', ''),
        driver_type=data.get('driver_type', 'hysys'),
        simulation_file=simulation_file,
        folder_path=case_folder
    )
    
    db.session.add(new_case)
    db.session.commit()
    
    return jsonify({
        'id': new_case.id,
        'name': new_case.name,
        'message': 'Case created successfully'
    }), 201

@cases_bp.route('/api/<int:case_id>', methods=['PUT'])
def api_update_case(case_id):
    """API endpoint to update an existing case"""
    case = Case.query.get_or_404(case_id)
    data = request.form
    
    # Update basic info
    if data.get('name'):
        case.name = data.get('name')
    if data.get('description'):
        case.description = data.get('description')
    if data.get('driver_type'):
        case.driver_type = data.get('driver_type')
    
    # Handle file upload
    if 'simulation_file' in request.files and request.files['simulation_file'].filename:
        file = request.files['simulation_file']
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            hysys_model_folder = os.path.join(case.folder_path, 'HysysModel')
            if not os.path.exists(hysys_model_folder):
                os.makedirs(hysys_model_folder)
            
            file_path = os.path.join(hysys_model_folder, filename)
            file.save(file_path)
            case.simulation_file = filename
    
    # Update parameters if provided
    if data.get('parameters'):
        try:
            case.parameters = json.loads(data.get('parameters'))
        except Exception as e:
            return jsonify({'error': f'Invalid parameters format: {str(e)}'}), 400
    
    case.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'id': case.id,
        'name': case.name,
        'message': 'Case updated successfully'
    })

@cases_bp.route('/api/<int:case_id>', methods=['DELETE'])
def api_delete_case(case_id):
    """API endpoint to delete a case"""
    case = Case.query.get_or_404(case_id)
    
    # Optionally delete the case folder
    # import shutil
    # shutil.rmtree(case.folder_path)
    
    db.session.delete(case)
    db.session.commit()
    
    return jsonify({
        'message': f'Case {case.name} deleted successfully'
    })

# Web UI routes
@cases_bp.route('/')
@cases_bp.route('/list')
def list_cases():
    """Web UI route to list all cases"""
    cases = Case.query.all()
    return render_template('cases/list.html', cases=cases, active_page='cases')

@cases_bp.route('/new', methods=['GET', 'POST'])
def new_case():
    """Web UI route to create a new case"""
    if request.method == 'POST':
        # Handle form submission
        name = request.form.get('name')
        description = request.form.get('description', '')
        driver_type = request.form.get('driver_type', 'hysys')
        
        # Validate required fields
        if not name:
            flash('Name is required', 'danger')
            return render_template('cases/new.html', active_page='new_case')
        
        # Create case folder structure
        case_folder = os.path.join(current_app.config['CASES_FOLDER'], secure_filename(name))
        if not os.path.exists(case_folder):
            os.makedirs(case_folder)
            os.makedirs(os.path.join(case_folder, 'HysysModel'))
            os.makedirs(os.path.join(case_folder, 'Results'))
        
        # Handle file upload
        simulation_file = None
        if 'simulation_file' in request.files and request.files['simulation_file'].filename:
            file = request.files['simulation_file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(case_folder, 'HysysModel', filename)
                file.save(file_path)
                simulation_file = filename
            else:
                flash('Invalid file type. Allowed types are: .hsc, .hysys, .bkp', 'danger')
                return render_template('cases/new.html', active_page='new_case')
        
        # Create new case
        new_case = Case(
            name=name,
            description=description,
            driver_type=driver_type,
            simulation_file=simulation_file,
            folder_path=case_folder
        )
        
        db.session.add(new_case)
        db.session.commit()
        
        flash('Case created successfully!', 'success')
        return redirect(url_for('cases.case_detail', case_id=new_case.id))
    
    return render_template('cases/new.html', active_page='new_case')

@cases_bp.route('/<int:case_id>')
def case_detail(case_id):
    """Web UI route to view case details"""
    case = Case.query.get_or_404(case_id)
    return render_template('cases/detail.html', case=case, active_page='cases')

@cases_bp.route('/edit/<int:case_id>', methods=['GET', 'POST'])
def edit_case(case_id):
    """Web UI route to edit a case"""
    case = Case.query.get_or_404(case_id)
    
    if request.method == 'POST':
        # Update case details
        case.name = request.form.get('name')
        case.description = request.form.get('description', '')
        case.driver_type = request.form.get('driver_type', 'hysys')
        
        # Handle file upload if provided
        if 'simulation_file' in request.files and request.files['simulation_file'].filename:
            file = request.files['simulation_file']
            if allowed_file(file.filename):
                # Secure the filename
                filename = secure_filename(file.filename)
                
                # Save the file
                hysys_model_folder = os.path.join(case.folder_path, 'HysysModel')
                if not os.path.exists(hysys_model_folder):
                    os.makedirs(hysys_model_folder)
                
                file_path = os.path.join(hysys_model_folder, filename)
                file.save(file_path)
                
                # Update the case with the new file
                case.simulation_file = filename
            else:
                flash('Invalid file type. Allowed types are: .hsc, .hysys, .bkp', 'danger')
        
        # Process parameters if provided
        parameters_json = request.form.get('parametersJson')
        if parameters_json:
            try:
                # Convert flat parameter list to structured format compatible with simulation driver
                param_list = json.loads(parameters_json)
                
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
                for param in param_list:
                    param_type = param['parameterType']  # InputParams or OutputParameters
                    subtype = param['subtype']  # Spreadsheet, MaterialStream, or EnergyStream
                    
                    if subtype == 'Spreadsheet':
                        spreadsheet_name = param['spreadsheetName']
                        param_name = param['parameterName']
                        cell = param['cell']
                        uom = param.get('uom', '')
                        
                        # Create key in format expected by simulation driver
                        key = f"{spreadsheet_name}_{param_name}"
                        
                        # Add to driver format
                        driver_format_parameters[param_type]["Spreadsheet"][key] = {
                            "SpreadsheetName": spreadsheet_name,
                            "Cell": cell,
                            "UOM": uom
                        }
                        
                    elif subtype == 'MaterialStream':
                        stream_name = param['streamName']
                        param_name = param['parameterName']
                        param_property = param.get('propertyName', 'Property')
                        uom = param.get('uom', '')
                        
                        # Create parameter configuration
                        param_config = {
                            "StreamName": stream_name,
                            "ParameterType": param.get('parameterType', 'Property'),
                            "UOM": uom
                        }
                        
                        if param_config["ParameterType"] == 'Property':
                            param_config["PropertyName"] = param_property
                        elif param_config["ParameterType"] in ['MassFrac', 'MassFlow', 'MolarFlow']:
                            if param.get('components'):
                                param_config["GetComponents"] = param.get('components')
                            if param.get('scaleFactor'):
                                param_config["ScaleFactor"] = param.get('scaleFactor')
                        
                        # Add to driver format
                        driver_format_parameters[param_type]["MaterialStream"][param_name] = param_config
                        
                    elif subtype == 'EnergyStream':
                        stream_name = param['streamName']
                        param_name = param['parameterName']
                        property_name = param.get('propertyName', 'HeatFlow')
                        uom = param.get('uom', '')
                        
                        # Add to driver format
                        driver_format_parameters[param_type]["EnergyStream"][param_name] = {
                            "StreamName": stream_name,
                            "PropertyName": property_name,
                            "UOM": uom
                        }
                
                # Update case parameters
                case.parameters = driver_format_parameters
                
            except Exception as e:
                flash(f'Error processing parameters: {str(e)}', 'danger')
        
        # Save changes
        case.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash('Case updated successfully!', 'success')
        return redirect(url_for('cases.case_detail', case_id=case.id))
    
    return render_template('cases/edit.html', case=case, active_page='cases')

@cases_bp.route('/parameters/<int:case_id>', methods=['GET', 'POST'])
def configure_parameters(case_id):
    """Web UI route to configure case parameters"""
    case = Case.query.get_or_404(case_id)
    
    if request.method == 'POST':
        # Process the form submission to configure parameters
        # This will be handled by JavaScript and AJAX calls to the API
        flash('Parameters configured successfully!', 'success')
        return redirect(url_for('cases.case_detail', case_id=case.id))
    
    return render_template('cases/parameters/configure.html', case=case, active_page='cases')

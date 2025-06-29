from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

# Initialize SQLAlchemy
db = SQLAlchemy()

# Define models
class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    simulation_file = db.Column(db.String(255), nullable=True)
    folder_path = db.Column(db.String(255), nullable=True)
    parameters_json = db.Column(db.Text, nullable=True)
    driver_type = db.Column(db.String(50), default='hysys')  # Added driver_type field
    
    @property
    def parameters(self):
        if self.parameters_json:
            return json.loads(self.parameters_json)
        return {
            'InputParams': {
                'Spreadsheet': {},
                'MaterialStream': {},
                'EnergyStream': {}
            },
            'OutputParameters': {
                'Spreadsheet': {},
                'MaterialStream': {},
                'EnergyStream': {}
            }
        }
    
    @parameters.setter
    def parameters(self, value):
        self.parameters_json = json.dumps(value)
    
    def __repr__(self):
        return f'<Case {self.name}>'

class SimulationResult(db.Model):
    __tablename__ = 'simulation_results'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    data_json = db.Column(db.Text, nullable=False)  # JSON string with simulation results
    name = db.Column(db.String(100), nullable=True)  # Name of the simulation
    simulation_type = db.Column(db.String(50), default='Single Run')  # Type of simulation
    
    # Relationship with Case
    case = db.relationship('Case', backref=db.backref('simulation_results', lazy=True))
    
    @property
    def data(self):
        if self.data_json:
            return json.loads(self.data_json)
        return {}
    
    @data.setter
    def data(self, value):
        self.data_json = json.dumps(value)
    
    def __repr__(self):
        return f'<SimulationResult {self.id} for Case {self.case_id}>'



# Update Surrogate model to the database
class Surrogate(db.Model):
    __tablename__ = 'surrogate_models'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False)
    model_type = db.Column(db.String(50), nullable=False)  # 'random_forest', 'neural_network', etc.
    input_params = db.Column(db.JSON, nullable=False)  # List of input parameter names
    output_params = db.Column(db.JSON, nullable=False)  # List of output parameter names
    is_inverse_model = db.Column(db.Boolean, default=False)  # Flag for inverse models
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    model_path = db.Column(db.String(255), nullable=False)  # Path to the saved model file
    metrics_json = db.Column(db.Text)  # JSON string with metrics
    model_config_json = db.Column(db.Text)  # JSON string with model configuration
    
    # Relationship with Case
    case = db.relationship('Case', backref=db.backref('surrogate_models', lazy=True))
    
    @property
    def metrics(self):
        if self.metrics_json:
            return json.loads(self.metrics_json)
        return {}
    
    @metrics.setter
    def metrics(self, value):
        self.metrics_json = json.dumps(value)
    
    @property
    def model_config(self):
        if self.model_config_json:
            return json.loads(self.model_config_json)
        return {}
    
    @model_config.setter
    def model_config(self, value):
        self.model_config_json = json.dumps(value)
    
    def __repr__(self):
        return f'<Surrogate {self.name}>'

def init_db():
    db.create_all()

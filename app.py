from flask import Flask
from datetime import datetime
import json

from api.routes.parameters import parameters_bp
from api.routes.cases import cases_bp
from api.routes.simulations import simulations_bp
from api.routes.sampling import sampling_bp
from api.routes.surrogate import surrogate_bp
from api.routes.calibration import calibration_bp
from api.routes.analysis import analysis_bp
from api.routes.optimization import optimization_bp
from api.routes.explainability import explainability_bp

from api.database import db
from api.dashboard import dashboard_bp



import os

def create_app():
    app = Flask(__name__)
    # Define the path for storing case files
    #app.config['CASES_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Cases')
    # Configure the app
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_for_development')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hysys_simulation.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['CASES_FOLDER'] = 'Cases'
    
    # Initialize extensions
    db.init_app(app)

    @app.template_filter('strftime')
    def strftime_filter(format_string):
        return datetime.now().strftime(format_string)
    
    @app.template_filter('from_json')
    def from_json_filter(value):
        """Convert a JSON string to a Python object."""
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {}
    # Register blueprints
    app.register_blueprint(dashboard_bp)  # Register the dashboard blueprint

    app.register_blueprint(parameters_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(simulations_bp)
    app.register_blueprint(sampling_bp)
    app.register_blueprint(surrogate_bp)
    app.register_blueprint(optimization_bp)
    app.register_blueprint(explainability_bp)
    
    app.register_blueprint(calibration_bp)
    app.register_blueprint(analysis_bp)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)

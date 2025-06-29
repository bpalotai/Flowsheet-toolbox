from flask import Blueprint, render_template
from api.database import db, Case

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
def index():
    # Get counts from database
    case_count = Case.query.count()
    
    # For other models, we'll use 0 as placeholders since they don't exist yet
    simulation_count = 0  # Will be implemented when Simulation model is created
    surrogate_count = 0   # Will be implemented when SurrogateModel is created
    calibration_count = 0 # Will be implemented when Calibration model is created
    
    # Get recent cases (limit to 5)
    recent_cases = Case.query.order_by(Case.created_at.desc()).limit(5).all()
    
    return render_template('index.html', 
                          active_page='dashboard',
                          case_count=case_count,
                          simulation_count=simulation_count,
                          surrogate_count=surrogate_count,
                          calibration_count=calibration_count,
                          recent_cases=recent_cases)

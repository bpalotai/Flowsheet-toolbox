from flask import Blueprint, render_template, request
from api.database import db, Case


analysis_bp = Blueprint('analysis', __name__, url_prefix='/analysis')

@analysis_bp.route('/')
def analysis():
    # Get all cases
    cases = Case.query.all()
    
    # Get case_id from query parameter
    case_id = request.args.get('case_id', type=int)
    selected_case = None
    if case_id:
        selected_case = Case.query.get_or_404(case_id)
    
    return render_template('analysis/analysis.html', 
                          active_page='analysis',
                          cases=cases,
                          selected_case=selected_case)
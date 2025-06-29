import os
import json
import pandas as pd
import numpy as np
from flask import Blueprint, request, jsonify, render_template, current_app, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
from datetime import datetime

# Create blueprint
explainability_bp = Blueprint('explainability', __name__, url_prefix='/explainability')

@explainability_bp.route('/')
def explainability_index():
    """Render the explainability landing page"""
    return render_template('explainability/explainability_landing.html', active_page='explainability')
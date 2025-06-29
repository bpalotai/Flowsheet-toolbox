import os
import json
import pandas as pd
import numpy as np
from flask import Blueprint, request, jsonify, render_template, current_app, send_file, flash, redirect, url_for
from datetime import datetime
import tempfile
import joblib

import time

# Create blueprint
optimization_bp = Blueprint('optimization', __name__, url_prefix='/optimization')

@optimization_bp.route('/')
def optimization_index():
    """Render the optimization landing page"""
    return render_template('optimization/optimization_landing.html', active_page='optimization')
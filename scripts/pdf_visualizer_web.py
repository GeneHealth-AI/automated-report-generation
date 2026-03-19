#!/usr/bin/env python3
"""
Web-based PDF Report Visualizer for Precision Medicine Reports

Provides a Flask web service to generate PDF reports from JSON data.
"""

import os
import json
import tempfile
import logging
from datetime import datetime
from typing import Dict, Any

from flask import Flask, request, jsonify, send_file, render_template_string
from werkzeug.utils import secure_filename

# Import the PDF visualizer
from pdf_report_visualizer import PDFReportVisualizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'pdf_reports'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Set maximum file size (16MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# HTML template for the upload form
UPLOAD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Precision Medicine PDF Generator</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }
        h1 {
            color: #2C3E50;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input[type="text"], input[type="file"] {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        button {
            background-color: #2C3E50;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
        }
        button:hover {
            background-color: #34495E;
        }
        .api-section {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            margin-top: 30px;
        }
        pre {
            background-color: #f1f1f1;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
        }
    </style>
</head>
<body>
    <h1>Precision Medicine PDF Generator</h1>
    
    <form action="/upload" method="post" enctype="multipart/form-data">
        <div class="form-group">
            <label for="json_file">JSON Report File:</label>
            <input type="file" id="json_file" name="json_file" accept=".json" required>
        </div>
        
        <div class="form-group">
            <label for="patient_name">Patient Name:</label>
            <input type="text" id="patient_name" name="patient_name">
        </div>
        
        <div class="form-group">
            <label for="patient_id">Patient ID:</label>
            <input type="text" id="patient_id" name="patient_id">
        </div>
        
        <div class="form-group">
            <label for="provider">Provider Name:</label>
            <input type="text" id="provider" name="provider">
        </div>
        
        <div class="form-group">
            <label for="focus">Report Focus:</label>
            <input type="text" id="focus" name="focus">
        </div>
        
        <button type="submit">Generate PDF</button>
    </form>
    
    <div class="api-section">
        <h2>API Usage</h2>
        <p>You can also generate PDFs programmatically using the API:</p>
        
        <h3>POST /api/generate</h3>
        <p>Send a JSON payload with the report data:</p>
        <pre>
curl -X POST -H "Content-Type: application/json" -d @report.json http://localhost:5000/api/generate > report.pdf
        </pre>
        
        <h3>POST /api/generate-with-metadata</h3>
        <p>Send a JSON payload with report data and metadata:</p>
        <pre>
curl -X POST -H "Content-Type: application/json" -d '{
  "report_data": { ... },
  "metadata": {
    "patient_name": "John Doe",
    "patient_id": "12345",
    "provider": "Dr. Smith",
    "focus": "Cardiovascular Risk"
  }
}' http://localhost:5000/api/generate-with-metadata > report.pdf
        </pre>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Render the upload form."""
    return render_template_string(UPLOAD_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and generate PDF."""
    if 'json_file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['json_file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        # Save uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        try:
            # Load JSON data
            with open(file_path, 'r') as f:
                json_data = json.load(f)
            
            # Get form data
            report_info = {}
            if request.form.get('patient_name'):
                report_info["patient_name"] = request.form.get('patient_name')
            if request.form.get('patient_id'):
                report_info["patient_id"] = request.form.get('patient_id')
            if request.form.get('provider'):
                report_info["provider_name"] = request.form.get('provider')
            if request.form.get('focus'):
                report_info["focus"] = request.form.get('focus')
            
            # Generate PDF
            pdf_visualizer = PDFReportVisualizer(output_dir=OUTPUT_FOLDER)
            if report_info:
                pdf_visualizer.set_report_info(report_info)
            
            output_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            output_path = pdf_visualizer.generate_pdf_from_json(json_data, output_filename)
            
            # Return the PDF file
            return send_file(output_path, as_attachment=True)
            
        except Exception as e:
            logger.error(f"Error generating PDF: {str(e)}")
            return jsonify({"error": str(e)}), 500
        finally:
            # Clean up uploaded file
            if os.path.exists(file_path):
                os.remove(file_path)
    
    return jsonify({"error": "Unknown error"}), 500

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """API endpoint to generate PDF from JSON data."""
    try:
        # Get JSON data from request
        json_data = request.get_json()
        if not json_data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Generate PDF
        pdf_visualizer = PDFReportVisualizer(output_dir=tempfile.gettempdir())
        output_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = pdf_visualizer.generate_pdf_from_json(json_data, output_filename)
        
        # Return the PDF file
        return send_file(output_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-with-metadata', methods=['POST'])
def api_generate_with_metadata():
    """API endpoint to generate PDF from JSON data with metadata."""
    try:
        # Get JSON data from request
        request_data = request.get_json()
        if not request_data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Extract report data and metadata
        json_data = request_data.get("report_data", {})
        metadata = request_data.get("metadata", {})
        
        if not json_data:
            return jsonify({"error": "No report data provided"}), 400
        
        # Generate PDF
        pdf_visualizer = PDFReportVisualizer(output_dir=tempfile.gettempdir())
        
        # Set report info if provided
        report_info = {}
        if "patient_name" in metadata:
            report_info["patient_name"] = metadata["patient_name"]
        if "patient_id" in metadata:
            report_info["patient_id"] = metadata["patient_id"]
        if "provider" in metadata:
            report_info["provider_name"] = metadata["provider"]
        if "focus" in metadata:
            report_info["focus"] = metadata["focus"]
        
        if report_info:
            pdf_visualizer.set_report_info(report_info)
        
        output_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = pdf_visualizer.generate_pdf_from_json(json_data, output_filename)
        
        # Return the PDF file
        return send_file(output_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
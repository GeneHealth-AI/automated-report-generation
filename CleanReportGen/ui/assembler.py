import os
import re
import logging
from typing import List, Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime

logger = logging.getLogger(__name__)

class UIAssembler:
    """Assembles the final visual HTML report."""
    
    def __init__(self, template_dir: str, asset_dir: str):
        self.template_dir = template_dir
        self.asset_dir = asset_dir
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self._setup_filters()

    def _setup_filters(self):
        """Register custom Jinja2 filters."""
        def link_pmids(text):
            if not text or not isinstance(text, str): return text
            pattern = r'(?i)PMID[:\s]*(\d+)'
            replacement = r'<a href="https://pubmed.ncbi.nlm.nih.gov/\1/" target="_blank" class="pmid-link">PMID \1</a>'
            return re.sub(pattern, replacement, text)
        
        self.env.filters['link_pmids'] = link_pmids

    def render(self, report_data: Dict[str, Any]) -> str:
        """Render the complete report. Placeholder for a more complex main template."""
        # Load CSS
        css_path = os.path.join(self.asset_dir, "report.css")
        with open(css_path, 'r') as f:
            css_content = f.read()

        html_blocks = []
        # In a real scenario, we'd iterate through blocks and use their templates
        # For now, let's just show the structure logic
        main_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>GeneHealth Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700&display=swap" rel="stylesheet">
    <style>{css_content}</style>
</head>
<body>
    <aside class="sidebar">
        <div class="sidebar-logo">GeneHealth</div>
        <nav class="sidebar-nav">
            <!-- Nav links would go here -->
        </nav>
    </aside>
    <main class="main-content">
        <h1>Precision Medicine Report</h1>
        <div class="report-sections">
            <!-- Rendered blocks would go here -->
            <div class="report-block">
                <h2>Generated Report Data</h2>
                <pre>{json.dumps(report_data, indent=2)}</pre>
            </div>
        </div>
    </main>
</body>
</html>
"""
        return main_template

import json # Needed for helper pre rendering

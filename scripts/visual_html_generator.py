import os
import json
import logging
from typing import Any
from datetime import datetime
import re
from jinja2 import Environment, FileSystemLoader, select_autoescape
from report_blocks import ReportBlock

# Configure logger
logger = logging.getLogger(__name__)

def _create_fallback_block_html(block: ReportBlock) -> str:
    """
    Create a styled fallback HTML representation for a block when its template is unavailable.
    """
    title = getattr(block, 'title', block.block_type.value.replace('_', ' ').title())
    content = block.content
    
    # Format content nicely - if it's a dict, render it as key-value pairs
    content_html = ""
    if isinstance(content, dict):
        for key, value in content.items():
            if key == "raw_content":
                content_html += f'<div class="fallback-raw-text">{value}</div>'
                continue
                
            # Format key into readable title
            readable_key = key.replace('_', ' ').title()
            
            # Handle nested structures
            if isinstance(value, list):
                items_html = "".join(f"<li>{_format_item(item)}</li>" for item in value if item)
                content_html += f"""
                <div class="fallback-section">
                    <h3>{readable_key}</h3>
                    <ul class="fallback-list">{items_html}</ul>
                </div>
                """
            elif isinstance(value, dict):
                nested_html = _format_nested_dict(value)
                content_html += f"""
                <div class="fallback-section">
                    <h3>{readable_key}</h3>
                    {nested_html}
                </div>
                """
            elif value:
                content_html += f"""
                <div class="fallback-section">
                    <h3>{readable_key}</h3>
                    <p>{value}</p>
                </div>
                """
    elif isinstance(content, str):
        content_html = f"<div class='fallback-raw-text'>{content}</div>"
    else:
        content_html = f"<pre>{json.dumps(content, indent=2)}</pre>"
    
    return f"""
    <div class="report-block fallback-block" data-block-type="{block.block_type.value}">
        <style>
            .fallback-block {{
                font-family: 'Outfit', sans-serif;
                padding: 40px;
                color: #1a202c;
            }}
            .fallback-block h2 {{
                font-size: 1.5rem;
                font-weight: 700;
                color: #004d40;
                margin-bottom: 24px;
                padding-bottom: 16px;
                border-bottom: 1.5px solid #edf2f7;
            }}
            .fallback-section {{
                margin-bottom: 24px;
            }}
            .fallback-section h3 {{
                font-size: 1.15rem;
                font-weight: 700;
                color: #4a5568;
                margin-bottom: 12px;
                margin-top: 0;
            }}
            .fallback-section p {{
                color: #4a5568;
                line-height: 1.6;
                margin: 0;
            }}
            .fallback-list {{
                list-style: none;
                padding: 0;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 12px;
            }}
            .fallback-list li {{
                margin-bottom: 0;
            }}
            .fallback-card {{
                background: #f8fafb;
                border: 1px solid #edf2f7;
                border-radius: 16px;
                padding: 16px 20px;
                margin-bottom: 0;
                height: 100%;
            }}
            .fallback-card strong {{
                color: #004d40;
                font-size: 0.85rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                display: block;
                margin-bottom: 4px;
            }}
            .fallback-raw-text {{
                color: #4a5568;
                line-height: 1.6;
                white-space: pre-wrap;
            }}
        </style>
        <h2>{title}</h2>
        <div class="fallback-content">
            {content_html}
        </div>
    </div>
    """

def _format_item(item: Any) -> str:
    """Format a list item for fallback display."""
    if isinstance(item, dict):
        # Show key fields
        parts = []
        for k, v in item.items():
            if v and k not in ['genetic_basis']:  # Skip verbose fields
                readable_k = k.replace('_', ' ').title()
                parts.append(f"<strong>{readable_k}:</strong> {v}")
        return "<div class='fallback-card'>" + "<br>".join(parts) + "</div>"
    return str(item)

def _format_nested_dict(d: dict[str, Any]) -> str:
    """Format a nested dictionary for fallback display."""
    html = ""
    for k, v in d.items():
        readable_k = k.replace('_', ' ').title()
        if isinstance(v, list):
            items_html = "".join(f"<li>{_format_item(item)}</li>" for item in v)
            html += f"<p><strong>{readable_k}:</strong></p><ul class='fallback-list'>{items_html}</ul>"
        elif isinstance(v, dict):
            html += f"<p><strong>{readable_k}:</strong></p>{_format_nested_dict(v)}"
        elif v:
            html += f"<p><strong>{readable_k}:</strong> {v}</p>"
    return html

def _parse_block_content(content: Any, block_type_value: str) -> dict[str, Any]:
    """
    Parse and normalize block content, handling various input formats:
    - Markdown code-fenced JSON (```json ... ```)
    - Raw JSON strings
    - Already-parsed dictionaries
    - Nested structures where data is under a key matching the block type
    """
    # If already a dict, check for nested structure
    if isinstance(content, dict):
        # Check if content is nested under the block type key
        # e.g. {"lifestyle_recommendations": {...actual data...}}
        if block_type_value in content and isinstance(content[block_type_value], dict):
            return content[block_type_value]
        return content
    
    # If not a string, return as-is wrapped in a dict
    if not isinstance(content, str):
        return {"raw_content": content}
    
    # Clean string content
    content_str = content.strip()
    
    # Remove markdown code fences if present
    if content_str.startswith('```'):
        # Find the end of the first line (the language specifier line)
        first_newline = content_str.find('\n')
        if first_newline != -1:
            content_str = content_str[first_newline + 1:]
        # Remove closing fence
        if content_str.endswith('```'):
            content_str = content_str[:-3].rstrip()
    
    # Try to parse as JSON
    try:
        parsed = json.loads(content_str)
        if isinstance(parsed, dict):
            # Check for nested structure
            if block_type_value in parsed and isinstance(parsed[block_type_value], dict):
                return parsed[block_type_value]
            return parsed
        return {"raw_content": parsed}
    except json.JSONDecodeError:
        # Return as raw text
        return {"raw_content": content_str}


def generate_visual_html(blocks: list[ReportBlock], report_info: dict[str, Any] | None = None) -> str:
    """
    Generate a complete visual HTML report from a list of report blocks.
    """
    try:
        # Set up Jinja2 environment
        blocks_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'blocks')
        if not os.path.exists(blocks_dir):
            blocks_dir = 'blocks'
            
        env = Environment(
            loader=FileSystemLoader(blocks_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # Register custom filters
        def link_pmids(text):
            if not text or not isinstance(text, str):
                return text
            pattern = r'(?i)PMID[:\s]*(\d+)'
            replacement = r'<a href="https://pubmed.ncbi.nlm.nih.gov/\1/" target="_blank" class="pmid-link">PMID \1</a>'
            return re.sub(pattern, replacement, text)

        env.filters['link_pmids'] = link_pmids

        # Metadata for the report
        metadata = {
            "patient_name": report_info.get("patient_name", "") if report_info else "",
            "patient_id": report_info.get("member_id", "") if report_info else "",
            "provider_name": report_info.get("provider_name", "") if report_info else "",
            "date": datetime.now().strftime("%B %d, %Y"),
            "title": report_info.get("title", report_info.get("focus", "GeneHealth Report")) if report_info else "GeneHealth Report",
            "focus": report_info.get("focus", "GeneHealth Report") if report_info else "GeneHealth Report",
            "dashboard_url": report_info.get("dashboard_url", "https://www.genehealth.ai/dashboard") if report_info else "#",
            "reports_url": report_info.get("reports_url", "https://www.genehealth.ai/reports") if report_info else "#"
        }
        
        report_title = f"{metadata['title']} | {metadata['patient_name']}"

        # Sort blocks by order
        sorted_blocks = sorted(blocks, key=lambda x: x.order)

        # Main report template based on report_sample.html
        main_template = """
<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>{{ report_title }}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" />
        <link
            href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap"
            rel="stylesheet"
        />
        <style>
            :root {
                /* Brand Colors */
                --primary-blue: #1e40af;
                --primary-blue-hover: #1d4ed8;
                --primary-blue-light: #dbeafe;
                --info-blue: #2563eb;
                --accent-blue: #3b82f6;
                --warning-orange: #f97316;
                --success-green: #10b981;
                --success-green-dark: #004d40;
                --error-red: #ef4444;

                /* Backgrounds */
                --bg: #f8fafc;
                --sidebar-bg: #ffffff;
                --card-bg: #ffffff;

                /* Borders */
                --border: #c8d4de;
                --border-light: #e2e8f0;
                --border-lighter: #edf2f7;

                /* Text Colors - WCAG AA Compliant */
                --text-main: #1a202c;
                --text-heading: #0f172a;
                --text-muted: #4b5563;
                --text-light: #6b7280;
                --secondary-text: #475569;

                /* Risk & Evidence Visualization */
                --risk-high: #ef4444;
                --risk-med: #f97316;
                --risk-low: #10b981;
                --evidence-strong: #0369a1;
                --evidence-moderate: #0284c7;
                --evidence-emerging: #38bdf8;
                
                /* Layout */
                --sidebar-width: 280px;
                --content-max-width: 1000px;
                --content-max-width-wide: 1200px;

                /* Shadows */
                --card-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
                --card-shadow-hover: 0 8px 24px rgba(0, 0, 0, 0.12);
                --card-shadow-lifted: 0 12px 24px rgba(0, 0, 0, 0.04);

                /* Transitions */
                --transition: all 0.2s ease;
                --transition-slow: all 0.3s ease;
                --accordion-transition: max-height 0.3s ease-out, padding-top 0.3s ease-out,
                    padding-bottom 0.3s ease-out, opacity 0.3s ease-out;

                /* Spacing Scale */
                --space-xs: 0.5rem; /* 8px */
                --space-sm: 1rem; /* 16px */
                --space-md: 1.5rem; /* 24px */
                --space-lg: 2rem; /* 32px */
                --space-xl: 3rem; /* 48px */

                /* Typography Scale */
                --text-xs: 0.75rem; /* 12px */
                --text-sm: 0.875rem; /* 14px */
                --text-base: 1rem; /* 16px */
                --text-lg: 1.125rem; /* 18px */
                --text-xl: 1.25rem; /* 20px */
                --text-2xl: 1.5rem; /* 24px */
                --text-3xl: 1.75rem; /* 28px */
                --text-4xl: 2.25rem; /* 36px */

                /* Border Radius */
                --radius-sm: 8px;
                --radius-md: 12px;
                --radius-lg: 16px;
                --radius-xl: 24px;
                --radius-full: 9999px;

                /* Common Values */
                --gap-sm: 16px;
                --gap-md: 24px;
                --gap-lg: 32px;
                --padding-card: 32px;
                --padding-section: 48px;
                --font-weight-medium: 500;
                --font-weight-semibold: 600;
                --font-weight-bold: 700;
                --line-height-normal: 1.6;
                --line-height-loose: 1.7;
            }

            * {
                box-sizing: border-box;
            }

            /* Component: Risk Meter */
            .risk-meter-container {
                margin: 16px 0;
            }
            .risk-meter-labels {
                display: flex;
                justify-content: space-between;
                font-size: 0.7rem;
                font-weight: 700;
                text-transform: uppercase;
                color: var(--text-muted);
                margin-bottom: 6px;
            }
            .risk-meter-bar {
                height: 8px;
                background: var(--border-light);
                border-radius: 4px;
                position: relative;
                overflow: hidden;
            }
            .risk-meter-fill {
                height: 100%;
                border-radius: 4px;
                transition: width 1s ease-out;
            }
            .risk-fill-high { background: var(--risk-high); }
            .risk-fill-med { background: var(--risk-med); }
            .risk-fill-low { background: var(--risk-low); }

            .abs-risk-callout {
                background: var(--bg);
                padding: 12px 16px;
                border-radius: 12px;
                margin-top: 12px;
                display: flex;
                align-items: center;
                gap: 12px;
                border: 1px solid var(--border-light);
            }
            .abs-risk-value {
                font-size: 1.25rem;
                font-weight: 800;
                color: var(--text-heading);
            }
            .abs-risk-info {
                font-size: 0.8rem;
                color: var(--text-muted);
                line-height: 1.3;
            }

            /* Component: Evidence Strength */
            .evidence-meter {
                display: flex;
                gap: 4px;
                margin-top: 4px;
            }
            .evidence-dot {
                width: 12px;
                height: 4px;
                border-radius: 2px;
                background: var(--border-lighter);
            }
            .evidence-dot.active {
                background: var(--primary-blue);
            }
            .evidence-label {
                font-size: 0.65rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-left: 6px;
            }

            /* Shared Block Components */
            .block-section-heading {
                font-size: var(--text-lg);
                font-weight: var(--font-weight-bold);
                color: var(--text-heading);
                margin: var(--space-md) 0 var(--space-sm);
                display: flex;
                align-items: center;
                gap: 12px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .block-section-heading i {
                font-size: 0.9em;
                opacity: 0.8;
            }
            .block-footer-note {
                margin-top: var(--space-xl);
                background: var(--bg);
                border: 1px solid var(--border-light);
                padding: 1.25rem;
                border-radius: var(--radius-md);
                display: flex;
                gap: 1rem;
                font-size: var(--text-sm);
                color: var(--text-muted);
                align-items: flex-start;
            }
            .block-footer-note i {
                font-size: 1.25rem;
                margin-top: 2px;
                color: var(--text-light);
                flex-shrink: 0;
            }

            /* Dual-Usability Elements */
            .consumer-insight {
                background: #f0f9ff;
                border-left: 4px solid #0ea5e9;
                padding: 12px 16px;
                border-radius: 0 8px 8px 0;
                margin: 12px 0;
                font-size: 0.9rem;
                color: #0369a1;
            }
            .clinician-appendix {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                padding: 16px;
                border-radius: 12px;
                margin-top: 16px;
                font-size: 0.85rem;
            }
            .clinician-title {
                font-size: 0.75rem;
                font-weight: 700;
                text-transform: uppercase;
                color: #64748b;
                margin-bottom: 8px;
                display: flex;
                align-items: center;
                gap: 6px;
            }

            /* Print Styles */
            @media print {
                /* Hide navigation and interactive elements */
                .sidebar,
                .hamburger-btn,
                .mobile-overlay,
                .banner-actions,
                .edit-block-btn {
                    display: none !important;
                }

                /* Adjust main content for full width */
                .main-content {
                    margin-left: 0 !important;
                    max-width: none !important;
                    padding: 15px !important;
                    font-size: 12px !important;
                    line-height: 1.4 !important;
                }

                /* Reduce excessive spacing for print */
                .page-header {
                    margin-bottom: 20px !important;
                }

                .findings-header {
                    margin: 15px 0 !important;
                }

                .banner {
                    margin-bottom: 20px !important;
                    padding: 20px !important;
                }

                .dashboard-grid {
                    margin-bottom: 20px !important;
                    gap: 15px !important;
                }

                /* Expand all accordions for printing */
                .disclaimer-content,
                .accordion-content,
                .protein-accordion-item .accordion-content {
                    max-height: none !important;
                    opacity: 1 !important;
                    padding: var(--space-md) !important;
                    overflow: visible !important;
                }

                /* Hide accordion icons */
                .expand-icon,
                .accordion-icon {
                    display: none !important;
                }

                /* Optimize page breaks for better flow */
                .report-block {
                    page-break-after: auto;
                    break-after: auto;
                    margin-bottom: 1.5rem;
                }

                /* Avoid breaking inside important sections */
                .dashboard-grid,
                .banner {
                    page-break-inside: avoid;
                    break-inside: avoid;
                }

                /* Optimize colors for print */
                .banner {
                    background: #f8f9fa !important;
                    color: #000 !important;
                    border: 2px solid #dee2e6 !important;
                }

                /* Ensure text is readable in print */
                body, p, span, div, h1, h2, h3, h4, h5, h6 {
                    color: #000 !important;
                }
            }

            body {
                margin: 0;
                padding: 0;
                background-color: var(--bg);
                font-family: "Outfit", sans-serif;
                color: var(--text-main);
                display: flex;
                min-height: 100vh;
            }

            /* Sidebar Styling */
            .sidebar {
                width: var(--sidebar-width);
                background: var(--sidebar-bg);
                border-right: 1px solid var(--border);
                height: 100vh;
                position: fixed;
                left: 0;
                top: 0;
                display: flex;
                flex-direction: column;
                padding: 40px 0;
                z-index: 1000;
                transition: transform 0.3s ease;
            }

            .sidebar-logo {
                padding: 0 40px 48px;
                display: block;
            }

            .sidebar-logo .brand-text {
                font-weight: 700;
                font-size: 1.5rem;
                color: var(--primary-blue);
                letter-spacing: -0.02em;
            }

            .sidebar-nav {
                flex: 1;
                overflow-y: auto;
                padding: 0 24px;
            }

            .nav-category {
                margin-bottom: 32px;
            }

            .category-title {
                font-size: 0.75rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-muted);
                margin-bottom: 12px;
                padding-left: 16px;
            }

            .nav-link {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 14px 16px;
                border-radius: 12px;
                color: var(--secondary-text);
                text-decoration: none;
                font-weight: 500;
                transition: var(--transition);
                margin-bottom: 4px;
            }

            .nav-link i {
                width: 20px;
                text-align: center;
                font-size: 1.1rem;
                color: var(--text-muted);
                transition: var(--transition);
            }

            .nav-link:hover {
                background: rgba(30, 64, 175, 0.05);
                color: var(--primary-blue);
            }

            .nav-link.active {
                background: var(--primary-blue);
                color: white;
                box-shadow: 0 4px 12px rgba(30, 64, 175, 0.15);
            }

            .nav-link.active i {
                color: white;
            }

            /* Main Content */
            .main-content {
                margin-left: var(--sidebar-width);
                flex: 1;
                padding: 40px 56px;
                max-width: var(--content-max-width-wide);
                font-size: 15px;
                line-height: var(--line-height-loose);
            }

            /* Breadcrumbs */
            .breadcrumbs {
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 0.85rem;
                color: var(--text-muted);
                margin-bottom: 24px;
            }

            .breadcrumbs a {
                color: inherit;
                text-decoration: none;
            }

            .breadcrumbs i {
                font-size: 0.7rem;
            }

            .breadcrumbs span {
                color: var(--text-main);
                font-weight: 600;
            }

            /* Premium Banner */
            .banner {
                background: var(--primary-blue);
                background-image: radial-gradient(circle at top right, rgba(255, 255, 255, 0.05) 0%, transparent 70%);
                padding: var(--padding-section);
                border-radius: var(--radius-xl);
                color: white;
                margin-bottom: var(--padding-section);
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: relative;
                overflow: hidden;
            }

            .banner-text h1 {
                margin: 0 0 var(--space-sm);
                font-size: var(--text-4xl);
                font-weight: var(--font-weight-bold);
                letter-spacing: -0.03em;
            }

            .banner-text p {
                margin: 0;
                opacity: 0.85;
                font-size: var(--text-lg);
                max-width: 500px;
                line-height: var(--line-height-normal);
            }

            .banner-actions {
                display: flex;
                gap: var(--gap-sm);
                z-index: 1;
            }

            .btn-outline {
                padding: var(--space-sm) var(--space-md);
                border: 1.5px solid rgba(255, 255, 255, 0.3);
                border-radius: var(--radius-md);
                color: white;
                text-decoration: none;
                font-weight: var(--font-weight-semibold);
                font-size: var(--text-sm);
                transition: var(--transition);
                display: flex;
                align-items: center;
                gap: 10px;
                cursor: pointer;
                background: transparent;
            }

            .btn-outline:hover {
                background: rgba(255, 255, 255, 0.1);
                border-color: white;
            }

            /* Patient Info Card */
            .dashboard-grid {
                display: grid;
                grid-template-columns: 2fr 1fr;
                gap: var(--gap-lg);
                margin-bottom: var(--space-xl);
            }

            .patient-summary {
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: var(--radius-xl);
                padding: var(--padding-card);
                box-shadow: var(--card-shadow);
            }

            .summary-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--gap-lg);
                padding-bottom: var(--space-md);
                border-bottom: 1px solid var(--border);
            }

            .summary-header h3 {
                margin: 0;
                font-size: var(--text-xl);
                font-weight: var(--font-weight-bold);
            }

            .info-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: var(--gap-lg);
            }

            .info-item {
                display: flex;
                flex-direction: column;
                gap: var(--space-xs);
            }

            .info-label {
                font-size: var(--text-xs);
                font-weight: var(--font-weight-bold);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-muted);
            }

            .info-value {
                font-size: var(--text-lg);
                font-weight: var(--font-weight-semibold);
                color: var(--text-main);
            }

            /* Findings Header */
            .findings-header {
                margin-bottom: var(--gap-lg);
                margin-top: var(--space-xl);
            }

            .findings-header h2 {
                font-size: var(--text-3xl);
                font-weight: var(--font-weight-bold);
                margin-bottom: var(--space-xs);
            }

            .report-sections {
                display: flex;
                flex-direction: column;
                gap: 48px;
            }

            .section-anchor {
                scroll-margin-top: 40px;
            }

            .report-block {
                background: white;
                border: 2px solid var(--border);
                border-radius: 16px;
                overflow: hidden;
                box-shadow: var(--card-shadow);
                transition: var(--transition);
                padding: 32px;
            }

            .report-block:hover {
                box-shadow: 0 8px 30px rgba(0, 0, 0, 0.06);
            }

            /* Hamburger Menu */
            .hamburger-btn {
                display: none;
                position: fixed;
                top: 20px;
                left: 20px;
                z-index: 1100;
                background: var(--sidebar-bg);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 12px;
                cursor: pointer;
                box-shadow: var(--card-shadow);
                transition: var(--transition);
                width: 44px;
                height: 44px;
                align-items: center;
                justify-content: center;
            }

            .mobile-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0, 0, 0, 0.5);
                z-index: 999;
                opacity: 0;
                transition: opacity 0.3s ease;
                pointer-events: none;
            }

            .mobile-overlay.active {
                display: block;
                opacity: 1;
                pointer-events: auto;
            }

            footer {
                margin-top: 100px;
                padding: 60px 0;
                border-top: 1px solid var(--border);
                color: var(--text-muted);
                font-size: 0.9rem;
                text-align: center;
            }

            @media (max-width: 1024px) {
                .hamburger-btn { display: flex; }
                .sidebar { transform: translateX(-100%); }
                .sidebar.mobile-open { transform: translateX(0); }
                .main-content { margin-left: 0; padding: 80px 24px 32px; }
                .dashboard-grid { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <button class="hamburger-btn" id="hamburger-btn" aria-label="Toggle navigation menu">
            <i class="fas fa-bars"></i>
        </button>

        <div class="mobile-overlay" id="mobile-overlay"></div>

        <aside class="sidebar" id="sidebar">
            <div class="sidebar-logo">
                <span class="brand-text">GeneHealth</span>
            </div>
            <nav class="sidebar-nav">
                <div class="nav-category">
                    <div class="category-title">Your Summary</div>
                    {% for block in sorted_blocks if block.block_type.value in ['introduction', 'executive_summary'] %}
                    <a href="#section-{{ block.block_type.value }}" class="nav-link">
                        <i class="fas fa-{{ 'info-circle' if block.block_type.value == 'introduction' else 'clipboard-list' }}"></i>
                        {{ block.title }}
                    </a>
                    {% endfor %}
                </div>

                <div class="nav-category">
                    <div class="category-title">Your Action Plan</div>
                    {% for block in sorted_blocks if block.block_type.value in ['lifestyle_recommendations', 'monitoring_plan', 'clinical_implications'] %}
                    <a href="#section-{{ block.block_type.value }}" class="nav-link">
                        <i class="fas fa-{{ 'heartbeat' if block.block_type.value == 'lifestyle_recommendations' else 'calendar-check' if block.block_type.value == 'monitoring_plan' else 'stethoscope' }}"></i>
                        {{ block.title }}
                    </a>
                    {% endfor %}
                </div>

                <div class="nav-category">
                    <div class="category-title">Detailed Analysis</div>
                    {% for block in sorted_blocks if block.block_type.value in ['risk_assessment', 'mutation_profile', 'literature_evidence'] %}
                    <a href="#section-{{ block.block_type.value }}" class="nav-link">
                        <i class="fas fa-{{ 'exclamation-triangle' if block.block_type.value == 'risk_assessment' else 'dna' if block.block_type.value == 'mutation_profile' else 'book-medical' }}"></i>
                        {{ block.title }}
                    </a>
                    {% endfor %}
                </div>

                {% set additional_blocks = [] %}
                {% for block in sorted_blocks if block.block_type.value in ['research_opportunities', 'gwas_analysis', 'conclusion'] %}
                    {% if additional_blocks.append(block) %}{% endif %}
                {% endfor %}
                {% if additional_blocks %}
                <div class="nav-category">
                    <div class="category-title">Additional</div>
                    {% for block in additional_blocks %}
                    <a href="#section-{{ block.block_type.value }}" class="nav-link">
                        <i class="fas fa-{{ 'flask' if block.block_type.value == 'research_opportunities' else 'chart-bar' if block.block_type.value == 'gwas_analysis' else 'flag-checkered' }}"></i>
                        {{ block.title }}
                    </a>
                    {% endfor %}
                </div>
                {% endif %}
            </nav>
        </aside>

        <main class="main-content">
            <header class="page-header">
                <nav class="breadcrumbs" role="navigation" aria-label="Breadcrumb navigation">
                    <a href="{{ metadata.dashboard_url }}">Dashboard</a>
                    <i class="fas fa-chevron-right" aria-hidden="true"></i>
                    <a href="{{ metadata.reports_url }}">Reports</a>
                    <i class="fas fa-chevron-right" aria-hidden="true"></i>
                    <span aria-current="page">{{ metadata.title }}</span>
                </nav>

                <div class="banner">
                    <div class="banner-text">
                        <h1>{{ metadata.title }}</h1>
                        <p>Comprehensive evidence-based analysis of your genomic data for personalized health insights.</p>
                    </div>
                    <div class="banner-actions">
                        <button onclick="prepareForPrint()" class="btn-outline">
                            <i class="fas fa-file-pdf"></i>
                            <span>Print / Save PDF</span>
                        </button>
                    </div>
                </div>

                <div class="dashboard-grid">
                    <div class="patient-summary">
                        <div class="summary-header">
                            <h3>Patient Information</h3>
                            <span style="font-size: var(--text-sm); color: var(--text-muted)">{{ metadata.date }}</span>
                        </div>
                        <div class="info-grid">
                            <div class="info-item">
                                <span class="info-label">Full Name</span>
                                <span class="info-value">{{ metadata.patient_name or 'N/A' }}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Assessment Type</span>
                                <span class="info-value">{{ metadata.focus }}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Patient ID</span>
                                <span class="info-value">{{ metadata.patient_id or 'Not Provided' }}</span>
                            </div>
                            {% if metadata.provider_name %}
                            <div class="info-item">
                                <span class="info-label">Provider</span>
                                <span class="info-value">{{ metadata.provider_name }}</span>
                            </div>
                            {% endif %}

                        </div>
                    </div>

                    <div class="patient-summary" style="display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; border-style: dashed; background: transparent;">
                        <i class="fas fa-shield-alt fa-3x" style="color: var(--primary-blue); margin-bottom: var(--space-sm); opacity: 0.2"></i>
                        <p style="margin: 0; font-size: var(--text-sm); color: var(--text-muted); font-weight: 500">
                            Your data is secure.
                        </p>
                    </div>
                </div>
            </header>

            <div class="findings-header">
                <h2>Detailed Findings</h2>
            </div>

            <div class="report-sections">
                {% for block in sorted_blocks %}
                <div id="section-{{ block.block_type.value }}" class="section-anchor">
                    {{ rendered_blocks[sorted_blocks.index(block)] | safe }}
                </div>
                {% endfor %}
            </div>

            <footer>
                <div style="max-width: 800px; margin: 0 auto">
                    <p><strong>Clinical Notice:</strong> This report is for professional clinical evaluation. Genetic results should always be interpreted in the context of personal and family history.</p>
                    <p>&copy; 2026 GeneHealth-AI. All intellectual property rights reserved.</p>
                </div>
            </footer>
        </main>

        <script>
            // Scroll spy logic
            const sections = document.querySelectorAll(".section-anchor");
            const navLinks = document.querySelectorAll(".nav-link");

            window.addEventListener("scroll", () => {
                let current = "";
                sections.forEach((section) => {
                    const sectionTop = section.offsetTop;
                    if (window.pageYOffset >= sectionTop - 150) {
                        current = section.getAttribute("id").replace('section-', '');
                    }
                });

                navLinks.forEach((link) => {
                    link.classList.remove("active");
                    if (link.getAttribute("href") === `#section-${current}`) {
                        link.classList.add("active");
                    }
                });
            });

            // Mobile menu logic
            const hamburgerBtn = document.getElementById("hamburger-btn");
            const sidebar = document.getElementById("sidebar");
            const overlay = document.getElementById("mobile-overlay");

            function toggleMenu() {
                sidebar.classList.toggle("mobile-open");
                overlay.classList.toggle("active");
            }

            hamburgerBtn.addEventListener("click", toggleMenu);
            overlay.addEventListener("click", toggleMenu);

            document.querySelectorAll(".nav-link").forEach(link => {
                link.addEventListener("click", () => {
                    if (window.innerWidth <= 1024) toggleMenu();
                });
            });

            // Prepare for print function
            function prepareForPrint() {
                // Expand all accordion items
                document.querySelectorAll(".disclaimer-item, .protein-accordion-item, .accordion-item").forEach(item => {
                    item.classList.add("expanded");
                });
                
                // Set aria-expanded for accessibility
                document.querySelectorAll("[aria-expanded]").forEach(el => {
                    el.setAttribute("aria-expanded", "true");
                });

                // Small delay to ensure expansion before dialog
                setTimeout(() => {
                    window.print();
                }, 150);
            }
        </script>
    </body>
</html>
"""

        # Render each block
        rendered_blocks: list[str] = []
        for block in sorted_blocks:
            try:
                # Parse and normalize content
                block.content = _parse_block_content(block.content, block.block_type.value)
                
                # Derive template name from block.template or fallback to block_type.value
                template_name = block.template
                if not template_name or template_name.strip() == "":
                    # Fallback: derive from block_type, e.g., EXECUTIVE_SUMMARY -> executive_summary_block.html
                    template_name = f"{block.block_type.value}_block.html"
                elif not template_name.endswith('.html'):
                    # Append .html if missing
                    template_name = f"{template_name}.html"
                
                logger.debug(f"Attempting to render block {block.block_type.value} with template: {template_name}")
                
                # Check if template exists in loader
                try:
                    tmpl = env.get_template(template_name)
                    rendered = tmpl.render(block=block)
                    rendered_blocks.append(rendered)
                except Exception as template_err:
                    logger.warning(f"Failed to render template {template_name} for block {block.block_type}: {template_err}")
                    # Create a styled fallback for the block
                    fallback_html = _create_fallback_block_html(block)
                    rendered_blocks.append(fallback_html)
            except Exception as block_err:
                logger.error(f"Error processing block {block.block_type}: {block_err}")


        # Render final HTML
        final_tmpl = Environment(loader=None).from_string(main_template)
        
        return final_tmpl.render(
            report_title=report_title,
            metadata=metadata,
            sorted_blocks=sorted_blocks,
            rendered_blocks=rendered_blocks
        )

    except Exception as e:
        logger.error(f"Failed to generate visual HTML: {e}")
        return f"<html><body><h1>Error Generating Report</h1><p>{str(e)}</p></body></html>"

if __name__ == "__main__":
    # Test logic
    from report_blocks import BlockType
    test_blocks_example = [
        ReportBlock(
            block_type=BlockType.INTRODUCTION,
            title="Introduction",
            content={"overview": "Test overview", "approach": "Test approach", "scope": "Test scope"},
            template="introduction_block.html",
            order=1
        )
    ]
    html_result = generate_visual_html(test_blocks_example, {"patient_name": "Test User", "member_id": "123"})
    with open("testing_report.html", "w") as f_test:
        f_test.write(html_result)
    print("Test HTML generated as testing_report.html")

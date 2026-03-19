# Elegant PDF Generator for Precision Medicine Reports

A sophisticated PDF generator that creates professional precision medicine reports with comprehensive table of contents, elegant styling, and structured content parsing.

## 🌟 Features

### Professional Layout
- **Title Page**: Clean, professional title page with patient information
- **Table of Contents**: Comprehensive TOC with automatic page numbering
- **Section Numbering**: Automatic section and subsection numbering
- **Elegant Typography**: Professional color scheme and font styling

### Content Processing
- **JSON Parsing**: Handles complex nested JSON structures from report blocks
- **Block Templates**: Integrates with text block templates for formatting
- **Content Extraction**: Intelligently extracts and formats content from various data structures
- **Error Handling**: Graceful degradation when encountering parsing issues

### Medical Report Specific
- **Genetic Profile Analysis**: Detailed protein mutation analysis with clinical significance
- **Risk Assessment**: Highlighted risk conditions with associated proteins
- **Clinical Implications**: Treatment and monitoring recommendations with priority levels
- **Executive Summary**: Key findings and recommendations prominently displayed

## 📁 File Structure

```
elegant_pdf_generator.py     # Main PDF generator class
test_elegant_pdf.py         # Test script for multiple reports
demo_elegant_pdf.py         # Comprehensive demo with features
debug_elegant_pdf.py        # Debug utilities for troubleshooting
```

## 🚀 Quick Start

### Basic Usage

```python
from elegant_pdf_generator import ElegantPDFGenerator
import json

# Load your JSON report data
with open('report.json', 'r') as f:
    data = json.load(f)

# Generate elegant PDF
generator = ElegantPDFGenerator('output.pdf', data)
generator.generate_pdf()
```

### Command Line Demo

```bash
# Run the comprehensive demo
python demo_elegant_pdf.py

# Test with multiple reports
python test_elegant_pdf.py

# Debug specific issues
python debug_elegant_pdf.py
```

## 📊 JSON Report Structure

The generator expects JSON reports with the following structure:

```json
{
  "report_metadata": {
    "patient_name": "Patient Name",
    "patient_id": "ID123",
    "provider_name": "Healthcare Provider",
    "generated_at": "2025-07-29T...",
    "focus": "Report focus description",
    "total_blocks": 7
  },
  "blocks": {
    "introduction": {
      "title": "Introduction",
      "order": 1,
      "content": "```json\n{...}\n```"
    },
    "executive_summary": {
      "title": "Executive Summary", 
      "order": 2,
      "content": "```json\n{...}\n```"
    }
    // ... more blocks
  }
}
```

## 🎨 Styling Features

### Color Scheme
- **Primary**: #2C3E50 (Dark blue-gray)
- **Secondary**: #34495E (Medium blue-gray)
- **Accent**: #3498DB (Blue)
- **Highlight**: #ECF0F1 (Light gray background)
- **Priority Colors**: Red (high), Orange (medium), Green (low)

### Typography
- **Headers**: Helvetica-Bold with hierarchical sizing
- **Body Text**: Helvetica with justified alignment
- **Clinical Notes**: Helvetica-Oblique for emphasis
- **Tables**: Professional grid styling with alternating row colors

## 📋 Supported Block Types

### Core Sections
1. **Introduction**: Overview, methodology, scope, disclaimers
2. **Executive Summary**: Key findings, recommendations, risk highlights
3. **Genetic Profile**: Detailed protein analysis and mutations
4. **Risk Assessment**: High-risk conditions and associated proteins
5. **Clinical Implications**: Treatment and monitoring recommendations
6. **Literature Evidence**: Supporting research and studies
7. **Lifestyle Recommendations**: Personalized lifestyle guidance

### Content Processing
- **Nested JSON**: Handles multiple levels of JSON nesting
- **Markdown Extraction**: Extracts JSON from markdown code blocks
- **Clinical Tables**: Professional formatting for mutation data
- **Priority Systems**: Color-coded priority levels for recommendations

## 🔧 Technical Details

### Dependencies
```python
reportlab>=3.6.0
json (built-in)
re (built-in)
os (built-in)
datetime (built-in)
```

### Key Classes
- `ElegantPDFGenerator`: Main generator class
- `ElegantTOC`: Custom table of contents with styling
- Built-in error handling and content validation

### Performance
- Handles large JSON files (250KB+ content)
- Efficient memory usage with streaming content processing
- Optimized table generation for clinical data

## 📈 Generated Output Examples

The generator creates PDFs with:
- **File sizes**: 12KB - 117KB depending on content
- **Professional layout**: Multi-page reports with consistent styling
- **Navigation**: Clickable table of contents (in supported viewers)
- **Print-ready**: High-quality output suitable for clinical use

## 🛠️ Customization

### Styling Customization
```python
# Modify colors in _create_styles() method
styles.add(ParagraphStyle(
    name='CustomStyle',
    textColor=colors.HexColor('#YOUR_COLOR'),
    fontSize=12
))
```

### Content Processing
```python
# Add custom block processors
def _build_custom_section(self, block_data):
    # Your custom processing logic
    pass
```

## 🐛 Troubleshooting

### Common Issues
1. **JSON Parsing Errors**: Check for properly formatted JSON in block content
2. **Missing Content**: Verify block structure matches expected format
3. **Style Conflicts**: Ensure unique style names in customizations

### Debug Tools
```bash
# Use debug script for detailed analysis
python debug_elegant_pdf.py
```

## 📝 Example Output

Generated PDFs include:
- Professional title page with patient demographics
- Comprehensive table of contents with page numbers
- Structured sections with automatic numbering
- Clinical tables with mutation analysis
- Risk assessments with color-coded priorities
- Treatment recommendations with rationale
- Literature references and evidence levels

## 🤝 Integration

The elegant PDF generator integrates seamlessly with:
- JSON report generation systems
- Block-based template systems
- Clinical data processing pipelines
- Precision medicine workflows

## 📄 License

This elegant PDF generator is designed for precision medicine applications and clinical reporting systems.

---

*Generated elegant PDFs provide professional, comprehensive reports suitable for clinical use and patient communication.*
# GeneHealth CleanReportGen

Welcome to the modular version of the GeneHealth reporting system. This codebase has been refactored for clarity, maintainability, and ease of use.

## Architecture

The system is organized into the following modules:

- **`core/`**: Central business logic.
  - `coordinator.py`: Orchestrates the report generation lifecycle.
  - `processing.py`: Bioinformatics utilities for variant processing.
  - `classification.py`: Streamlined variant classification engine.
- **`engine/`**: LLM and RAG orchestration.
  - `generator.py`: Parallelized block generation via Gemini API.
  - `prompts.py`: Centralized LLM prompts.
  - `rag.py`: PubMed search and evidence retrieval.
- **`data/`**: Data models and storage logic.
  - `models.py`: Consolidated enums and dataclasses (ReportBlock, EnhancedVariant).
  - `storage.py`: S3 upload/download helpers.
- **`ui/`**: User interface components.
  - `assembler.py`: HTML report rendering using Jinja2.
  - `templates/`: Jinja2 HTML templates for report blocks.
  - `assets/`: Styling (report.css).
- **`utils/`**: Shared utilities.
  - `cache.py`: Variant description caching system.

## Getting Started

### Prerequisites

- Python 3.9+
- Gemini API Key (set as `GEMINI_API_KEY` in `.env`)
- AWS Credentials (if using S3 features)

### Basic Usage

To generate a report from a VCF file:

```bash
python3 main.py --vcf /path/to/variants.vcf --template /path/to/template.json --patient-name "John Doe"
```

## Advantages of the New Structure

1. **Modular**: Each component has a single responsibility.
2. **Parallelized**: Blocks are generated in parallel using thread pools.
3. **Robust RAG**: Dedicated PubMedRAG class for better research integration.
4. **Lean Models**: Consolidated data structures reduce complexity and memory usage.
5. **Modernized**: Uses the latest `google-generativeai` SDK and modern Python patterns.

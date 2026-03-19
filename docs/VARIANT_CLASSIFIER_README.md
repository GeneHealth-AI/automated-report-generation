# Variant Classification System

## Overview

The Variant Classification System provides the foundation for classifying genetic variants as either risk-increasing, protective, or neutral based on various data sources and evidence. This system is designed to support the enhanced genetic reporting feature that displays both risk and protective genetic factors.

## Features

- **Multi-source Evidence Integration**: Combines evidence from ClinVar, literature, population frequency data, and functional predictions
- **Configurable Classification Rules**: Customizable thresholds and weights for different evidence sources
- **Confidence Scoring**: Provides confidence levels (HIGH, MODERATE, LOW) for classifications
- **Flexible Configuration Management**: Support for loading and saving configuration from JSON files
- **Comprehensive Error Handling**: Graceful handling of missing or malformed data
- **Extensive Testing**: Full unit test coverage with various edge cases

## Core Components

### Enums

- **EffectDirection**: `RISK_INCREASING`, `PROTECTIVE`, `NEUTRAL`, `UNKNOWN`
- **ConfidenceLevel**: `HIGH`, `MODERATE`, `LOW`

### Classes

- **VariantClassifier**: Main classification engine
- **VariantClassification**: Result object containing classification details
- **ClassificationConfig**: Configuration management for thresholds and rules

## Usage

### Basic Usage

```python
from variant_classifier import VariantClassifier

# Initialize classifier with default configuration
classifier = VariantClassifier()

# Sample variant data
variant_data = {
    'rsid': 'rs334',
    'gene': 'HBB',
    'clinvar_significance': 'Pathogenic',
    'literature_evidence': {
        'risk_association': True,
        'protective_association': False
    },
    'population_frequency': {
        'frequency': 0.001,
        'associated_with_disease': True
    },
    'functional_impact': 'high'
}

# Classify the variant
result = classifier.classify_variant(variant_data)

print(f"Effect Direction: {result.effect_direction.value}")
print(f"Confidence Level: {result.confidence_level.value}")
print(f"Confidence Score: {result.confidence_score:.2f}")
print(f"Reasoning: {result.reasoning}")
```

### Configuration Management

```python
from variant_classifier import ClassificationConfig, VariantClassifier

# Load configuration from file
config = ClassificationConfig.load_from_file('config.json')
classifier = VariantClassifier(config)

# Create custom configuration
custom_config = ClassificationConfig(
    risk_thresholds={'clinvar_pathogenic': 0.9},
    protective_thresholds={'clinvar_benign': 0.9},
    confidence_weights={'clinvar': 0.5, 'literature': 0.3},
    evidence_source_priorities={'clinvar': 1, 'literature': 2},
    default_classification=EffectDirection.NEUTRAL
)

# Save configuration to file
custom_config.save_to_file('custom_config.json')
```

### Batch Classification

```python
# Classify multiple variants
variants = [variant1, variant2, variant3]
summary = classifier.get_classification_summary(variants)

print(f"Risk-increasing variants: {summary['risk_increasing']}")
print(f"Protective variants: {summary['protective']}")
print(f"Neutral variants: {summary['neutral']}")
print(f"Unknown variants: {summary['unknown']}")
```

## Configuration Format

The system uses JSON configuration files with the following structure:

```json
{
  "risk_thresholds": {
    "clinvar_pathogenic": 0.8,
    "literature_risk": 0.6,
    "population_frequency_rare_risk": 0.7
  },
  "protective_thresholds": {
    "clinvar_benign": 0.8,
    "literature_protective": 0.6,
    "population_frequency_common_protective": 0.7
  },
  "confidence_weights": {
    "clinvar": 0.4,
    "literature": 0.3,
    "population_data": 0.2,
    "functional_prediction": 0.1
  },
  "evidence_source_priorities": {
    "clinvar": 1,
    "literature": 2,
    "population_data": 3,
    "functional_prediction": 4
  },
  "default_classification": "unknown"
}
```

## Expected Variant Data Format

The classifier expects variant data in the following format:

```python
{
    'rsid': 'rs123456',                    # Variant identifier
    'gene': 'GENE_NAME',                   # Associated gene
    'clinvar_significance': 'Pathogenic',  # ClinVar classification
    'literature_evidence': {               # Literature-based evidence
        'risk_association': True,
        'protective_association': False
    },
    'population_frequency': {              # Population frequency data
        'frequency': 0.001,
        'associated_with_disease': True,
        'protective_effect': False
    },
    'functional_impact': 'high'            # Predicted functional impact
}
```

## Classification Logic

The system uses a weighted scoring approach:

1. **Evidence Extraction**: Extracts available evidence from variant data
2. **Effect Direction Determination**: Calculates risk and protective scores based on evidence
3. **Confidence Calculation**: Weights evidence sources according to configuration
4. **Final Classification**: Determines effect direction and confidence level

### ClinVar Classifications

- **Risk-increasing**: Pathogenic, Likely pathogenic
- **Protective**: Benign, Likely benign
- **Neutral/Unknown**: Uncertain significance, Conflicting interpretations

## Testing

Run the comprehensive test suite:

```bash
python -m pytest test_variant_classifier.py -v
```

## Demonstrations

- `demo_variant_classifier.py`: Basic classification examples
- `demo_config_management.py`: Configuration management examples

## Requirements Satisfied

This implementation satisfies the following requirements from the specification:

- **Requirement 1.1**: Categorizes variants as risk-increasing or protective
- **Requirement 5.1**: Configurable rules for determining risk vs protective effects
- **Requirement 5.2**: Allows updates to variant classifications without code changes

## Integration

This variant classification system is designed to integrate with the existing genetic reporting infrastructure and will be used by:

- Section management system (Task 2)
- Report block generators (Task 5)
- Data processing workflows (Task 7)
- PDF generation system (Task 8)

## Future Enhancements

- Integration with external databases (GWAS Catalog, PharmGKB)
- Machine learning-based classification models
- Real-time classification updates
- Advanced evidence weighting algorithms
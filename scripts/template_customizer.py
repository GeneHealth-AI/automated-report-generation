"""
Template Customization System for Risk/Protective Variant Reporting

This module provides comprehensive template customization capabilities including:
- Dynamic template generation based on conditions
- Risk/protective section customization
- Visual styling and layout options
- Template inheritance and composition
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import copy

from config_manager import ConfigManager, TemplateConfig


class SectionType(Enum):
    """Types of report sections"""
    INTRODUCTION = "introduction"
    EXECUTIVE_SUMMARY = "executive_summary"
    RISK_ASSESSMENT = "risk_assessment"
    PROTECTIVE_FACTORS = "protective_factors"
    MUTATION_PROFILE = "mutation_profile"
    CLINICAL_IMPLICATIONS = "clinical_implications"
    LITERATURE_EVIDENCE = "literature_evidence"
    LIFESTYLE_RECOMMENDATIONS = "lifestyle_recommendations"
    MONITORING_PLAN = "monitoring_plan"
    RESEARCH_OPPORTUNITIES = "research_opportunities"


class TemplateStyle(Enum):
    """Template visual styles"""
    PROFESSIONAL = "professional"
    CLINICAL = "clinical"
    PATIENT_FRIENDLY = "patient_friendly"
    RESEARCH = "research"
    COMPREHENSIVE = "comprehensive"


@dataclass
class SectionCustomization:
    """Customization options for individual report sections"""
    section_type: SectionType
    is_visible: bool
    title: Optional[str]
    subtitle: Optional[str]
    custom_content: Optional[str]
    max_items: Optional[int]
    sort_order: int
    styling: Dict[str, Any]
    conditional_display: Dict[str, Any]
    
    @classmethod
    def get_default_customization(cls, section_type: SectionType) -> 'SectionCustomization':
        """Get default customization for a section type"""
        defaults = {
            SectionType.INTRODUCTION: {
                'title': 'Introduction',
                'is_visible': True,
                'sort_order': 1,
                'styling': {'background_color': '#f8f9fa', 'border': 'none'}
            },
            SectionType.EXECUTIVE_SUMMARY: {
                'title': 'Executive Summary',
                'is_visible': True,
                'sort_order': 2,
                'max_items': 5,
                'styling': {'background_color': '#e3f2fd', 'border': '1px solid #2196f3'}
            },
            SectionType.RISK_ASSESSMENT: {
                'title': 'Risk Assessment',
                'is_visible': True,
                'sort_order': 3,
                'styling': {'background_color': '#ffebee', 'border': '1px solid #f44336'}
            },
            SectionType.PROTECTIVE_FACTORS: {
                'title': 'Protective Factors',
                'is_visible': True,
                'sort_order': 4,
                'styling': {'background_color': '#e8f5e8', 'border': '1px solid #4caf50'}
            },
            SectionType.MUTATION_PROFILE: {
                'title': 'Genetic Variant Profile',
                'is_visible': True,
                'sort_order': 5,
                'styling': {'background_color': '#fff3e0', 'border': '1px solid #ff9800'}
            },
            SectionType.CLINICAL_IMPLICATIONS: {
                'title': 'Clinical Implications',
                'is_visible': True,
                'sort_order': 6,
                'styling': {'background_color': '#f3e5f5', 'border': '1px solid #9c27b0'}
            },
            SectionType.LITERATURE_EVIDENCE: {
                'title': 'Literature Evidence',
                'is_visible': True,
                'sort_order': 7,
                'max_items': 10,
                'styling': {'background_color': '#e0f2f1', 'border': '1px solid #009688'}
            },
            SectionType.LIFESTYLE_RECOMMENDATIONS: {
                'title': 'Lifestyle Recommendations',
                'is_visible': True,
                'sort_order': 8,
                'styling': {'background_color': '#e8eaf6', 'border': '1px solid #3f51b5'}
            },
            SectionType.MONITORING_PLAN: {
                'title': 'Monitoring Plan',
                'is_visible': True,
                'sort_order': 9,
                'styling': {'background_color': '#fce4ec', 'border': '1px solid #e91e63'}
            },
            SectionType.RESEARCH_OPPORTUNITIES: {
                'title': 'Research Opportunities',
                'is_visible': False,
                'sort_order': 10,
                'styling': {'background_color': '#f1f8e9', 'border': '1px solid #8bc34a'}
            }
        }
        
        section_defaults = defaults.get(section_type, {})
        
        return cls(
            section_type=section_type,
            is_visible=section_defaults.get('is_visible', True),
            title=section_defaults.get('title', section_type.value.replace('_', ' ').title()),
            subtitle=None,
            custom_content=None,
            max_items=section_defaults.get('max_items'),
            sort_order=section_defaults.get('sort_order', 99),
            styling=section_defaults.get('styling', {}),
            conditional_display={}
        )


@dataclass
class RiskProtectiveCustomization:
    """Specific customization for risk/protective sections"""
    show_risk_section: bool
    show_protective_section: bool
    risk_section_title: str
    protective_section_title: str
    risk_styling: Dict[str, Any]
    protective_styling: Dict[str, Any]
    combined_display: bool
    risk_threshold_display: float
    protective_threshold_display: float
    confidence_indicator: bool
    
    @classmethod
    def get_default_customization(cls) -> 'RiskProtectiveCustomization':
        """Get default risk/protective customization"""
        return cls(
            show_risk_section=True,
            show_protective_section=True,
            risk_section_title="Risk-Increasing Factors",
            protective_section_title="Protective Factors",
            risk_styling={
                'color': '#d32f2f',
                'background_color': '#ffebee',
                'border_color': '#f44336',
                'icon': '⚠️'
            },
            protective_styling={
                'color': '#388e3c',
                'background_color': '#e8f5e8',
                'border_color': '#4caf50',
                'icon': '🛡️'
            },
            combined_display=False,
            risk_threshold_display=0.5,
            protective_threshold_display=0.5,
            confidence_indicator=True
        )


@dataclass
class CustomTemplate:
    """Complete custom template definition"""
    template_id: str
    name: str
    description: str
    category: str
    style: TemplateStyle
    sections: List[SectionCustomization]
    risk_protective_config: RiskProtectiveCustomization
    global_styling: Dict[str, Any]
    conditions: List[str]
    metadata: Dict[str, Any]
    
    def to_template_config(self) -> TemplateConfig:
        """Convert to TemplateConfig format"""
        # Convert sections to block configs
        block_configs = {}
        blocks = []
        
        # Sort sections by sort_order
        sorted_sections = sorted(self.sections, key=lambda x: x.sort_order)
        
        for section in sorted_sections:
            if section.is_visible:
                blocks.append(section.section_type.value)
                
                block_config = {
                    'is_visible': section.is_visible,
                    'title': section.title,
                    'styling': section.styling
                }
                
                if section.subtitle:
                    block_config['subtitle'] = section.subtitle
                if section.custom_content:
                    block_config['custom_content'] = section.custom_content
                if section.max_items:
                    block_config['max_items'] = section.max_items
                if section.conditional_display:
                    block_config['conditional_display'] = section.conditional_display
                
                block_configs[section.section_type.value] = block_config
        
        # Add risk/protective specific configurations
        if self.risk_protective_config:
            if 'risk_assessment' in block_configs:
                block_configs['risk_assessment'].update({
                    'show_risk_section': self.risk_protective_config.show_risk_section,
                    'risk_section_title': self.risk_protective_config.risk_section_title,
                    'risk_styling': self.risk_protective_config.risk_styling,
                    'risk_threshold_display': self.risk_protective_config.risk_threshold_display
                })
            
            if 'protective_factors' in block_configs:
                block_configs['protective_factors'].update({
                    'show_protective_section': self.risk_protective_config.show_protective_section,
                    'protective_section_title': self.risk_protective_config.protective_section_title,
                    'protective_styling': self.risk_protective_config.protective_styling,
                    'protective_threshold_display': self.risk_protective_config.protective_threshold_display
                })
        
        return TemplateConfig(
            template_id=self.template_id,
            name=self.name,
            category=self.category,
            focus=self.description,
            blocks=blocks,
            data_requirements={
                'required_genes': [],
                'optional_genes': [],
                'required_clinical_data': [],
                'optional_clinical_data': []
            },
            block_configs=block_configs,
            style=self.global_styling,
            metadata=self.metadata,
            permissions={
                'is_public': True,
                'shared_with': [],
                'editable_by': ['admin@precisionmedicine.org']
            }
        )


class TemplateCustomizer:
    """
    Main class for template customization and management
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the template customizer
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.logger = logging.getLogger(__name__)
    
    def create_custom_template(self, template_id: str, name: str, description: str,
                             category: str = "custom", style: TemplateStyle = TemplateStyle.PROFESSIONAL,
                             conditions: List[str] = None) -> CustomTemplate:
        """
        Create a new custom template
        
        Args:
            template_id: Unique template identifier
            name: Template name
            description: Template description
            category: Template category
            style: Visual style
            conditions: List of conditions this template is designed for
            
        Returns:
            CustomTemplate instance
        """
        # Create default sections
        sections = []
        for section_type in SectionType:
            sections.append(SectionCustomization.get_default_customization(section_type))
        
        # Create default risk/protective configuration
        risk_protective_config = RiskProtectiveCustomization.get_default_customization()
        
        # Create global styling based on style
        global_styling = self._get_style_config(style)
        
        custom_template = CustomTemplate(
            template_id=template_id,
            name=name,
            description=description,
            category=category,
            style=style,
            sections=sections,
            risk_protective_config=risk_protective_config,
            global_styling=global_styling,
            conditions=conditions or [],
            metadata={
                'created_date': '2025-01-01T00:00:00Z',
                'version': '1.0.0',
                'intended_audience': 'Healthcare providers',
                'evidence_level': 'Variable'
            }
        )
        
        return custom_template
    
    def customize_section(self, template: CustomTemplate, section_type: SectionType,
                         customizations: Dict[str, Any]) -> CustomTemplate:
        """
        Customize a specific section in a template
        
        Args:
            template: Template to customize
            section_type: Type of section to customize
            customizations: Dictionary of customization options
            
        Returns:
            Updated CustomTemplate
        """
        # Find the section to customize
        section_index = None
        for i, section in enumerate(template.sections):
            if section.section_type == section_type:
                section_index = i
                break
        
        if section_index is None:
            # Add new section if it doesn't exist
            section = SectionCustomization.get_default_customization(section_type)
            template.sections.append(section)
            section_index = len(template.sections) - 1
        
        # Apply customizations
        section = template.sections[section_index]
        
        if 'is_visible' in customizations:
            section.is_visible = customizations['is_visible']
        if 'title' in customizations:
            section.title = customizations['title']
        if 'subtitle' in customizations:
            section.subtitle = customizations['subtitle']
        if 'custom_content' in customizations:
            section.custom_content = customizations['custom_content']
        if 'max_items' in customizations:
            section.max_items = customizations['max_items']
        if 'sort_order' in customizations:
            section.sort_order = customizations['sort_order']
        if 'styling' in customizations:
            section.styling.update(customizations['styling'])
        if 'conditional_display' in customizations:
            section.conditional_display.update(customizations['conditional_display'])
        
        template.sections[section_index] = section
        return template
    
    def customize_risk_protective_sections(self, template: CustomTemplate,
                                         customizations: Dict[str, Any]) -> CustomTemplate:
        """
        Customize risk and protective sections specifically
        
        Args:
            template: Template to customize
            customizations: Risk/protective customization options
            
        Returns:
            Updated CustomTemplate
        """
        config = template.risk_protective_config
        
        if 'show_risk_section' in customizations:
            config.show_risk_section = customizations['show_risk_section']
        if 'show_protective_section' in customizations:
            config.show_protective_section = customizations['show_protective_section']
        if 'risk_section_title' in customizations:
            config.risk_section_title = customizations['risk_section_title']
        if 'protective_section_title' in customizations:
            config.protective_section_title = customizations['protective_section_title']
        if 'risk_styling' in customizations:
            config.risk_styling.update(customizations['risk_styling'])
        if 'protective_styling' in customizations:
            config.protective_styling.update(customizations['protective_styling'])
        if 'combined_display' in customizations:
            config.combined_display = customizations['combined_display']
        if 'risk_threshold_display' in customizations:
            config.risk_threshold_display = customizations['risk_threshold_display']
        if 'protective_threshold_display' in customizations:
            config.protective_threshold_display = customizations['protective_threshold_display']
        if 'confidence_indicator' in customizations:
            config.confidence_indicator = customizations['confidence_indicator']
        
        template.risk_protective_config = config
        return template
    
    def apply_condition_specific_customizations(self, template: CustomTemplate,
                                              condition: str) -> CustomTemplate:
        """
        Apply condition-specific customizations to a template
        
        Args:
            template: Template to customize
            condition: Condition name
            
        Returns:
            Customized template
        """
        condition_config = self.config_manager.get_condition_config(condition)
        if not condition_config:
            self.logger.warning(f"No condition-specific configuration found for {condition}")
            return template
        
        # Apply condition-specific styling
        condition_styling = self._get_condition_styling(condition)
        template.global_styling.update(condition_styling)
        
        # Customize sections based on condition
        if condition.lower() == 'adhd':
            template = self._apply_adhd_customizations(template)
        elif condition.lower() == 'cardiovascular_disease':
            template = self._apply_cardiovascular_customizations(template)
        elif condition.lower() == 'type_2_diabetes':
            template = self._apply_diabetes_customizations(template)
        
        return template
    
    def save_custom_template(self, template: CustomTemplate) -> bool:
        """
        Save a custom template to the configuration system
        
        Args:
            template: Custom template to save
            
        Returns:
            True if save successful, False otherwise
        """
        try:
            # Convert to TemplateConfig format
            template_config = template.to_template_config()
            
            # Save using config manager
            success = self.config_manager.update_template_config(
                template.template_id, template_config, "template_customizer"
            )
            
            if success:
                self.logger.info(f"Custom template {template.template_id} saved successfully")
            else:
                self.logger.error(f"Failed to save custom template {template.template_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error saving custom template: {str(e)}")
            return False
    
    def load_custom_template(self, template_id: str) -> Optional[CustomTemplate]:
        """
        Load a custom template from the configuration system
        
        Args:
            template_id: Template identifier
            
        Returns:
            CustomTemplate if found, None otherwise
        """
        try:
            template_config = self.config_manager.get_template_config(template_id)
            if not template_config:
                return None
            
            # Convert from TemplateConfig to CustomTemplate
            return self._convert_from_template_config(template_config)
            
        except Exception as e:
            self.logger.error(f"Error loading custom template: {str(e)}")
            return None
    
    def create_condition_specific_template(self, condition: str, base_template_id: str = None) -> CustomTemplate:
        """
        Create a template specifically customized for a condition
        
        Args:
            condition: Condition name
            base_template_id: Base template to start from (optional)
            
        Returns:
            Condition-specific CustomTemplate
        """
        # Create base template
        template_id = f"{condition.lower()}_risk_protective_template"
        # Handle special condition name formatting
        if condition.lower() == 'adhd':
            name = f"ADHD Risk and Protective Analysis"
        elif condition.lower() == 'cardiovascular_disease':
            name = f"Cardiovascular Disease Risk and Protective Analysis"
        elif condition.lower() == 'type_2_diabetes':
            name = f"Type 2 Diabetes Risk and Protective Analysis"
        else:
            name = f"{condition.replace('_', ' ').title()} Risk and Protective Analysis"
        description = f"Specialized template for {condition} risk and protective factor analysis"
        
        if base_template_id:
            base_template = self.load_custom_template(base_template_id)
            if base_template:
                template = copy.deepcopy(base_template)
                template.template_id = template_id
                template.name = name
                template.description = description
            else:
                template = self.create_custom_template(template_id, name, description)
        else:
            template = self.create_custom_template(template_id, name, description)
        
        # Apply condition-specific customizations
        template = self.apply_condition_specific_customizations(template, condition)
        template.conditions = [condition]
        
        return template
    
    # Helper methods
    def _get_style_config(self, style: TemplateStyle) -> Dict[str, Any]:
        """Get styling configuration for a template style"""
        style_configs = {
            TemplateStyle.PROFESSIONAL: {
                'color_scheme': 'blue_gray',
                'font_family': 'Arial, sans-serif',
                'font_size': '12px',
                'line_height': '1.6',
                'margin': '20px',
                'padding': '15px'
            },
            TemplateStyle.CLINICAL: {
                'color_scheme': 'medical_blue',
                'font_family': 'Times New Roman, serif',
                'font_size': '11px',
                'line_height': '1.5',
                'margin': '15px',
                'padding': '10px'
            },
            TemplateStyle.PATIENT_FRIENDLY: {
                'color_scheme': 'warm_colors',
                'font_family': 'Helvetica, sans-serif',
                'font_size': '14px',
                'line_height': '1.8',
                'margin': '25px',
                'padding': '20px'
            },
            TemplateStyle.RESEARCH: {
                'color_scheme': 'academic',
                'font_family': 'Georgia, serif',
                'font_size': '10px',
                'line_height': '1.4',
                'margin': '10px',
                'padding': '8px'
            },
            TemplateStyle.COMPREHENSIVE: {
                'color_scheme': 'multi_color',
                'font_family': 'Verdana, sans-serif',
                'font_size': '11px',
                'line_height': '1.7',
                'margin': '18px',
                'padding': '12px'
            }
        }
        
        return style_configs.get(style, style_configs[TemplateStyle.PROFESSIONAL])
    
    def _get_condition_styling(self, condition: str) -> Dict[str, Any]:
        """Get condition-specific styling"""
        condition_styles = {
            'adhd': {
                'primary_color': '#2196f3',
                'secondary_color': '#ff9800',
                'accent_color': '#4caf50'
            },
            'cardiovascular_disease': {
                'primary_color': '#f44336',
                'secondary_color': '#e91e63',
                'accent_color': '#9c27b0'
            },
            'type_2_diabetes': {
                'primary_color': '#ff5722',
                'secondary_color': '#795548',
                'accent_color': '#607d8b'
            }
        }
        
        return condition_styles.get(condition.lower(), {})
    
    def _apply_adhd_customizations(self, template: CustomTemplate) -> CustomTemplate:
        """Apply ADHD-specific customizations"""
        # Customize executive summary for ADHD
        template = self.customize_section(template, SectionType.EXECUTIVE_SUMMARY, {
            'max_items': 5,
            'custom_content': 'This report analyzes genetic factors associated with ADHD, including neurotransmitter pathway genes and pharmacogenomic considerations.'
        })
        
        # Customize clinical implications for ADHD
        template = self.customize_section(template, SectionType.CLINICAL_IMPLICATIONS, {
            'custom_content': 'Clinical implications focus on medication response, comorbidity risk, and treatment planning considerations.'
        })
        
        # Show research opportunities for ADHD
        template = self.customize_section(template, SectionType.RESEARCH_OPPORTUNITIES, {
            'is_visible': True,
            'sort_order': 9
        })
        
        return template
    
    def _apply_cardiovascular_customizations(self, template: CustomTemplate) -> CustomTemplate:
        """Apply cardiovascular disease-specific customizations"""
        # Emphasize risk assessment for cardiovascular disease
        template = self.customize_section(template, SectionType.RISK_ASSESSMENT, {
            'title': 'Cardiovascular Risk Assessment',
            'sort_order': 2  # Move up in priority
        })
        
        # Customize monitoring plan for cardiovascular disease
        template = self.customize_section(template, SectionType.MONITORING_PLAN, {
            'is_visible': True,
            'title': 'Cardiovascular Monitoring Plan',
            'custom_content': 'Regular monitoring of lipid levels, blood pressure, and cardiovascular risk markers.'
        })
        
        return template
    
    def _apply_diabetes_customizations(self, template: CustomTemplate) -> CustomTemplate:
        """Apply type 2 diabetes-specific customizations"""
        # Customize lifestyle recommendations for diabetes
        template = self.customize_section(template, SectionType.LIFESTYLE_RECOMMENDATIONS, {
            'title': 'Diabetes Management Recommendations',
            'sort_order': 3,  # Higher priority
            'custom_content': 'Personalized recommendations for diet, exercise, and glucose management based on genetic profile.'
        })
        
        # Customize monitoring plan for diabetes
        template = self.customize_section(template, SectionType.MONITORING_PLAN, {
            'is_visible': True,
            'title': 'Diabetes Monitoring Plan',
            'custom_content': 'Regular monitoring of glucose levels, HbA1c, and diabetes-related complications.'
        })
        
        return template
    
    def _convert_from_template_config(self, template_config: TemplateConfig) -> CustomTemplate:
        """Convert TemplateConfig to CustomTemplate"""
        # This is a simplified conversion - in practice, you might want more sophisticated mapping
        sections = []
        for block_name in template_config.blocks:
            try:
                section_type = SectionType(block_name)
                block_config = template_config.block_configs.get(block_name, {})
                
                section = SectionCustomization(
                    section_type=section_type,
                    is_visible=block_config.get('is_visible', True),
                    title=block_config.get('title', section_type.value.replace('_', ' ').title()),
                    subtitle=block_config.get('subtitle'),
                    custom_content=block_config.get('custom_content'),
                    max_items=block_config.get('max_items'),
                    sort_order=template_config.blocks.index(block_name),
                    styling=block_config.get('styling', {}),
                    conditional_display=block_config.get('conditional_display', {})
                )
                sections.append(section)
            except ValueError:
                # Skip unknown section types
                continue
        
        # Extract risk/protective configuration
        risk_protective_config = RiskProtectiveCustomization.get_default_customization()
        
        return CustomTemplate(
            template_id=template_config.template_id,
            name=template_config.name,
            description=template_config.focus,
            category=template_config.category,
            style=TemplateStyle.PROFESSIONAL,  # Default
            sections=sections,
            risk_protective_config=risk_protective_config,
            global_styling=template_config.style,
            conditions=[],
            metadata=template_config.metadata
        )
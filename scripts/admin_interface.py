"""
Admin Interface for Risk/Protective Variant Reporting Configuration Management

This module provides a comprehensive admin interface for updating classification parameters,
managing condition-specific rules, and customizing report templates.
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import getpass

from config_manager import (
    ConfigManager, ConditionSpecificConfig, TemplateConfig, AdminConfig,
    ConfigurationType
)
from variant_classifier import ClassificationConfig, EffectDirection


class AdminInterface:
    """
    Admin interface for configuration management
    """
    
    def __init__(self, config_dir: str = "configs"):
        """
        Initialize the admin interface
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_manager = ConfigManager(config_dir)
        self.logger = logging.getLogger(__name__)
        self.current_user = None
        self.session_active = False
    
    def authenticate(self, username: str, password: str = None) -> bool:
        """
        Authenticate user for admin access
        
        Args:
            username: Username for authentication
            password: Password (if None, will prompt)
            
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            admin_config = self.config_manager.admin_config
            
            # Check if user is in allowed users list
            if username not in admin_config.allowed_users:
                self.logger.warning(f"Authentication failed: User {username} not in allowed users")
                return False
            
            # For demo purposes, we'll use a simple authentication
            # In production, this should integrate with proper authentication system
            if password is None:
                password = getpass.getpass("Enter password: ")
            
            # Simple password check (in production, use proper password hashing)
            if password == "admin123":  # Demo password
                self.current_user = username
                self.session_active = True
                self.logger.info(f"User {username} authenticated successfully")
                return True
            else:
                self.logger.warning(f"Authentication failed: Invalid password for user {username}")
                return False
                
        except Exception as e:
            self.logger.error(f"Authentication error: {str(e)}")
            return False
    
    def logout(self):
        """Logout current user"""
        if self.current_user:
            self.logger.info(f"User {self.current_user} logged out")
        self.current_user = None
        self.session_active = False
    
    def _check_authentication(self) -> bool:
        """Check if user is authenticated"""
        if not self.session_active or not self.current_user:
            print("Error: Authentication required. Please login first.")
            return False
        return True
    
    # Classification Configuration Management
    def display_classification_config(self):
        """Display current classification configuration"""
        if not self._check_authentication():
            return
        
        config = self.config_manager.get_classification_config()
        
        print("\n=== Current Classification Configuration ===")
        print(f"Default Classification: {config.default_classification.value}")
        
        print("\nRisk Thresholds:")
        for key, value in config.risk_thresholds.items():
            print(f"  {key}: {value}")
        
        print("\nProtective Thresholds:")
        for key, value in config.protective_thresholds.items():
            print(f"  {key}: {value}")
        
        print("\nConfidence Weights:")
        for key, value in config.confidence_weights.items():
            print(f"  {key}: {value}")
        
        print("\nEvidence Source Priorities:")
        for key, value in config.evidence_source_priorities.items():
            print(f"  {key}: {value}")
    
    def update_classification_threshold(self, threshold_type: str, threshold_name: str, 
                                      new_value: float) -> bool:
        """
        Update a specific classification threshold
        
        Args:
            threshold_type: 'risk' or 'protective'
            threshold_name: Name of the threshold to update
            new_value: New threshold value (0.0-1.0)
            
        Returns:
            True if update successful, False otherwise
        """
        if not self._check_authentication():
            return False
        
        try:
            # Validate input
            if not (0.0 <= new_value <= 1.0):
                print(f"Error: Threshold value must be between 0.0 and 1.0")
                return False
            
            # Get current configuration
            config = self.config_manager.get_classification_config()
            
            # Update the appropriate threshold
            if threshold_type.lower() == 'risk':
                if threshold_name not in config.risk_thresholds:
                    print(f"Error: Risk threshold '{threshold_name}' not found")
                    return False
                config.risk_thresholds[threshold_name] = new_value
            elif threshold_type.lower() == 'protective':
                if threshold_name not in config.protective_thresholds:
                    print(f"Error: Protective threshold '{threshold_name}' not found")
                    return False
                config.protective_thresholds[threshold_name] = new_value
            else:
                print(f"Error: Invalid threshold type '{threshold_type}'. Use 'risk' or 'protective'")
                return False
            
            # Update configuration
            success = self.config_manager.update_classification_config(config, self.current_user)
            
            if success:
                print(f"Successfully updated {threshold_type} threshold '{threshold_name}' to {new_value}")
            else:
                print(f"Failed to update {threshold_type} threshold '{threshold_name}'")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error updating classification threshold: {str(e)}")
            print(f"Error updating threshold: {str(e)}")
            return False
    
    def update_confidence_weight(self, source: str, new_weight: float) -> bool:
        """
        Update confidence weight for an evidence source
        
        Args:
            source: Evidence source name
            new_weight: New weight value
            
        Returns:
            True if update successful, False otherwise
        """
        if not self._check_authentication():
            return False
        
        try:
            # Get current configuration
            config = self.config_manager.get_classification_config()
            
            if source not in config.confidence_weights:
                print(f"Error: Evidence source '{source}' not found")
                return False
            
            # Update weight
            config.confidence_weights[source] = new_weight
            
            # Normalize weights to sum to 1.0
            total_weight = sum(config.confidence_weights.values())
            if total_weight > 0:
                for key in config.confidence_weights:
                    config.confidence_weights[key] /= total_weight
            
            # Update configuration
            success = self.config_manager.update_classification_config(config, self.current_user)
            
            if success:
                print(f"Successfully updated confidence weight for '{source}' to {new_weight}")
                print("Note: All weights have been normalized to sum to 1.0")
                self.display_classification_config()
            else:
                print(f"Failed to update confidence weight for '{source}'")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error updating confidence weight: {str(e)}")
            print(f"Error updating confidence weight: {str(e)}")
            return False
    
    # Condition-Specific Configuration Management
    def list_condition_configs(self):
        """List all available condition configurations"""
        if not self._check_authentication():
            return
        
        conditions = self.config_manager.list_available_conditions()
        
        print("\n=== Available Condition Configurations ===")
        for i, condition in enumerate(conditions, 1):
            print(f"{i}. {condition}")
        
        if not conditions:
            print("No condition configurations found.")
    
    def display_condition_config(self, condition: str):
        """
        Display configuration for a specific condition
        
        Args:
            condition: Condition name
        """
        if not self._check_authentication():
            return
        
        config = self.config_manager.get_condition_config(condition)
        
        if not config:
            print(f"Error: Configuration for condition '{condition}' not found")
            return
        
        print(f"\n=== Configuration for {condition.upper()} ===")
        print(f"Default Classification: {config.default_classification.value}")
        
        print("\nRisk Thresholds:")
        for key, value in config.risk_thresholds.items():
            print(f"  {key}: {value}")
        
        print("\nProtective Thresholds:")
        for key, value in config.protective_thresholds.items():
            print(f"  {key}: {value}")
        
        print("\nConfidence Weights:")
        for key, value in config.confidence_weights.items():
            print(f"  {key}: {value}")
        
        print("\nSpecial Rules:")
        for key, value in config.special_rules.items():
            print(f"  {key}: {value}")
    
    def create_condition_config(self, condition_name: str) -> bool:
        """
        Create a new condition-specific configuration
        
        Args:
            condition_name: Name of the condition
            
        Returns:
            True if creation successful, False otherwise
        """
        if not self._check_authentication():
            return False
        
        try:
            # Check if condition already exists
            if self.config_manager.get_condition_config(condition_name):
                print(f"Error: Configuration for condition '{condition_name}' already exists")
                return False
            
            # Create new configuration based on default
            base_config = self.config_manager.get_classification_config()
            
            new_config = ConditionSpecificConfig(
                condition_name=condition_name.lower(),
                risk_thresholds=dict(base_config.risk_thresholds),
                protective_thresholds=dict(base_config.protective_thresholds),
                confidence_weights=dict(base_config.confidence_weights),
                evidence_source_priorities=dict(base_config.evidence_source_priorities),
                default_classification=base_config.default_classification,
                special_rules={}
            )
            
            # Update configuration
            success = self.config_manager.update_condition_config(
                condition_name, new_config, self.current_user
            )
            
            if success:
                print(f"Successfully created configuration for condition '{condition_name}'")
            else:
                print(f"Failed to create configuration for condition '{condition_name}'")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error creating condition configuration: {str(e)}")
            print(f"Error creating condition configuration: {str(e)}")
            return False
    
    def update_condition_threshold(self, condition: str, threshold_type: str, 
                                 threshold_name: str, new_value: float) -> bool:
        """
        Update a threshold for a specific condition
        
        Args:
            condition: Condition name
            threshold_type: 'risk' or 'protective'
            threshold_name: Name of the threshold
            new_value: New threshold value
            
        Returns:
            True if update successful, False otherwise
        """
        if not self._check_authentication():
            return False
        
        try:
            # Get current configuration
            config = self.config_manager.get_condition_config(condition)
            
            if not config:
                # If condition doesn't exist, create it first
                success = self.create_condition_config(condition)
                if not success:
                    print(f"Error: Could not create configuration for condition '{condition}'")
                    return False
                config = self.config_manager.get_condition_config(condition)
            
            # Create a copy of the configuration to avoid modifying the original object
            import copy
            config = copy.deepcopy(config)
            
            # Validate input
            if not (0.0 <= new_value <= 1.0):
                print(f"Error: Threshold value must be between 0.0 and 1.0")
                return False
            
            # Update the appropriate threshold
            if threshold_type.lower() == 'risk':
                if threshold_name not in config.risk_thresholds:
                    # Add the threshold if it doesn't exist
                    config.risk_thresholds[threshold_name] = new_value
                else:
                    config.risk_thresholds[threshold_name] = new_value
            elif threshold_type.lower() == 'protective':
                if threshold_name not in config.protective_thresholds:
                    # Add the threshold if it doesn't exist
                    config.protective_thresholds[threshold_name] = new_value
                else:
                    config.protective_thresholds[threshold_name] = new_value
            else:
                print(f"Error: Invalid threshold type '{threshold_type}'. Use 'risk' or 'protective'")
                return False
            
            # Update configuration
            success = self.config_manager.update_condition_config(condition, config, self.current_user)
            
            if success:
                print(f"Successfully updated {threshold_type} threshold '{threshold_name}' "
                      f"for condition '{condition}' to {new_value}")
            else:
                print(f"Failed to update threshold for condition '{condition}'")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error updating condition threshold: {str(e)}")
            print(f"Error updating condition threshold: {str(e)}")
            return False
    
    # Template Configuration Management
    def list_template_configs(self):
        """List all available template configurations"""
        if not self._check_authentication():
            return
        
        templates = self.config_manager.list_available_templates()
        
        print("\n=== Available Template Configurations ===")
        for i, template in enumerate(templates, 1):
            config = self.config_manager.get_template_config(template)
            print(f"{i}. {template} - {config.name if config else 'Unknown'}")
        
        if not templates:
            print("No template configurations found.")
    
    def display_template_config(self, template_id: str):
        """
        Display configuration for a specific template
        
        Args:
            template_id: Template identifier
        """
        if not self._check_authentication():
            return
        
        config = self.config_manager.get_template_config(template_id)
        
        if not config:
            print(f"Error: Template configuration '{template_id}' not found")
            return
        
        print(f"\n=== Template Configuration: {template_id} ===")
        print(f"Name: {config.name}")
        print(f"Category: {config.category}")
        print(f"Focus: {config.focus}")
        print(f"Blocks: {', '.join(config.blocks)}")
        
        print("\nBlock Configurations:")
        for block_name, block_config in config.block_configs.items():
            print(f"  {block_name}:")
            for key, value in block_config.items():
                print(f"    {key}: {value}")
        
        print(f"\nStyle: {config.style}")
        print(f"Permissions: {config.permissions}")
    
    def update_template_block_config(self, template_id: str, block_name: str, 
                                   config_key: str, new_value: Any) -> bool:
        """
        Update a block configuration in a template
        
        Args:
            template_id: Template identifier
            block_name: Name of the block to update
            config_key: Configuration key to update
            new_value: New value for the configuration
            
        Returns:
            True if update successful, False otherwise
        """
        if not self._check_authentication():
            return False
        
        try:
            # Get current template configuration
            config = self.config_manager.get_template_config(template_id)
            if not config:
                print(f"Error: Template configuration '{template_id}' not found")
                return False
            
            # Update block configuration
            if block_name not in config.block_configs:
                config.block_configs[block_name] = {}
            
            config.block_configs[block_name][config_key] = new_value
            
            # Update configuration
            success = self.config_manager.update_template_config(template_id, config, self.current_user)
            
            if success:
                print(f"Successfully updated {block_name}.{config_key} in template '{template_id}'")
            else:
                print(f"Failed to update template configuration")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error updating template block configuration: {str(e)}")
            print(f"Error updating template configuration: {str(e)}")
            return False
    
    # Interactive Menu System
    def run_interactive_menu(self):
        """Run interactive admin menu"""
        if not self.session_active:
            print("Please authenticate first.")
            username = input("Username: ")
            if not self.authenticate(username):
                print("Authentication failed.")
                return
        
        while self.session_active:
            self._display_main_menu()
            choice = input("\nEnter your choice: ").strip()
            
            if choice == '1':
                self._classification_config_menu()
            elif choice == '2':
                self._condition_config_menu()
            elif choice == '3':
                self._template_config_menu()
            elif choice == '4':
                self._view_audit_log()
            elif choice == '5':
                self.logout()
                print("Logged out successfully.")
                break
            elif choice.lower() == 'q':
                break
            else:
                print("Invalid choice. Please try again.")
    
    def _display_main_menu(self):
        """Display main admin menu"""
        print(f"\n=== Admin Interface - User: {self.current_user} ===")
        print("1. Classification Configuration Management")
        print("2. Condition-Specific Configuration Management")
        print("3. Template Configuration Management")
        print("4. View Audit Log")
        print("5. Logout")
        print("Q. Quit")
    
    def _classification_config_menu(self):
        """Classification configuration submenu"""
        while True:
            print("\n=== Classification Configuration Management ===")
            print("1. Display Current Configuration")
            print("2. Update Risk Threshold")
            print("3. Update Protective Threshold")
            print("4. Update Confidence Weight")
            print("5. Back to Main Menu")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == '1':
                self.display_classification_config()
            elif choice == '2':
                self._update_risk_threshold_interactive()
            elif choice == '3':
                self._update_protective_threshold_interactive()
            elif choice == '4':
                self._update_confidence_weight_interactive()
            elif choice == '5':
                break
            else:
                print("Invalid choice. Please try again.")
    
    def _condition_config_menu(self):
        """Condition configuration submenu"""
        while True:
            print("\n=== Condition-Specific Configuration Management ===")
            print("1. List Available Conditions")
            print("2. Display Condition Configuration")
            print("3. Create New Condition Configuration")
            print("4. Update Condition Threshold")
            print("5. Back to Main Menu")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == '1':
                self.list_condition_configs()
            elif choice == '2':
                condition = input("Enter condition name: ").strip()
                self.display_condition_config(condition)
            elif choice == '3':
                condition = input("Enter new condition name: ").strip()
                self.create_condition_config(condition)
            elif choice == '4':
                self._update_condition_threshold_interactive()
            elif choice == '5':
                break
            else:
                print("Invalid choice. Please try again.")
    
    def _template_config_menu(self):
        """Template configuration submenu"""
        while True:
            print("\n=== Template Configuration Management ===")
            print("1. List Available Templates")
            print("2. Display Template Configuration")
            print("3. Update Template Block Configuration")
            print("4. Back to Main Menu")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == '1':
                self.list_template_configs()
            elif choice == '2':
                template_id = input("Enter template ID: ").strip()
                self.display_template_config(template_id)
            elif choice == '3':
                self._update_template_block_interactive()
            elif choice == '4':
                break
            else:
                print("Invalid choice. Please try again.")
    
    def _update_risk_threshold_interactive(self):
        """Interactive risk threshold update"""
        config = self.config_manager.get_classification_config()
        
        print("\nAvailable Risk Thresholds:")
        thresholds = list(config.risk_thresholds.keys())
        for i, threshold in enumerate(thresholds, 1):
            print(f"{i}. {threshold}: {config.risk_thresholds[threshold]}")
        
        try:
            choice = int(input("Select threshold to update (number): ")) - 1
            if 0 <= choice < len(thresholds):
                threshold_name = thresholds[choice]
                new_value = float(input(f"Enter new value for {threshold_name} (0.0-1.0): "))
                self.update_classification_threshold('risk', threshold_name, new_value)
            else:
                print("Invalid selection.")
        except (ValueError, IndexError):
            print("Invalid input.")
    
    def _update_protective_threshold_interactive(self):
        """Interactive protective threshold update"""
        config = self.config_manager.get_classification_config()
        
        print("\nAvailable Protective Thresholds:")
        thresholds = list(config.protective_thresholds.keys())
        for i, threshold in enumerate(thresholds, 1):
            print(f"{i}. {threshold}: {config.protective_thresholds[threshold]}")
        
        try:
            choice = int(input("Select threshold to update (number): ")) - 1
            if 0 <= choice < len(thresholds):
                threshold_name = thresholds[choice]
                new_value = float(input(f"Enter new value for {threshold_name} (0.0-1.0): "))
                self.update_classification_threshold('protective', threshold_name, new_value)
            else:
                print("Invalid selection.")
        except (ValueError, IndexError):
            print("Invalid input.")
    
    def _update_confidence_weight_interactive(self):
        """Interactive confidence weight update"""
        config = self.config_manager.get_classification_config()
        
        print("\nAvailable Evidence Sources:")
        sources = list(config.confidence_weights.keys())
        for i, source in enumerate(sources, 1):
            print(f"{i}. {source}: {config.confidence_weights[source]}")
        
        try:
            choice = int(input("Select source to update (number): ")) - 1
            if 0 <= choice < len(sources):
                source_name = sources[choice]
                new_weight = float(input(f"Enter new weight for {source_name}: "))
                self.update_confidence_weight(source_name, new_weight)
            else:
                print("Invalid selection.")
        except (ValueError, IndexError):
            print("Invalid input.")
    
    def _update_condition_threshold_interactive(self):
        """Interactive condition threshold update"""
        conditions = self.config_manager.list_available_conditions()
        
        if not conditions:
            print("No condition configurations available.")
            return
        
        print("\nAvailable Conditions:")
        for i, condition in enumerate(conditions, 1):
            print(f"{i}. {condition}")
        
        try:
            choice = int(input("Select condition (number): ")) - 1
            if 0 <= choice < len(conditions):
                condition = conditions[choice]
                threshold_type = input("Enter threshold type (risk/protective): ").strip().lower()
                threshold_name = input("Enter threshold name: ").strip()
                new_value = float(input("Enter new value (0.0-1.0): "))
                
                self.update_condition_threshold(condition, threshold_type, threshold_name, new_value)
            else:
                print("Invalid selection.")
        except (ValueError, IndexError):
            print("Invalid input.")
    
    def _update_template_block_interactive(self):
        """Interactive template block configuration update"""
        templates = self.config_manager.list_available_templates()
        
        if not templates:
            print("No template configurations available.")
            return
        
        print("\nAvailable Templates:")
        for i, template in enumerate(templates, 1):
            config = self.config_manager.get_template_config(template)
            print(f"{i}. {template} - {config.name if config else 'Unknown'}")
        
        try:
            choice = int(input("Select template (number): ")) - 1
            if 0 <= choice < len(templates):
                template_id = templates[choice]
                block_name = input("Enter block name: ").strip()
                config_key = input("Enter configuration key: ").strip()
                new_value = input("Enter new value: ").strip()
                
                # Try to convert to appropriate type
                try:
                    if new_value.lower() in ['true', 'false']:
                        new_value = new_value.lower() == 'true'
                    elif new_value.isdigit():
                        new_value = int(new_value)
                    elif '.' in new_value and new_value.replace('.', '').isdigit():
                        new_value = float(new_value)
                except:
                    pass  # Keep as string
                
                self.update_template_block_config(template_id, block_name, config_key, new_value)
            else:
                print("Invalid selection.")
        except (ValueError, IndexError):
            print("Invalid input.")
    
    def _view_audit_log(self):
        """View audit log entries"""
        if not self._check_authentication():
            return
        
        try:
            audit_log_path = os.path.join(self.config_manager.config_dir, "audit_log.json")
            
            if not os.path.exists(audit_log_path):
                print("No audit log found.")
                return
            
            with open(audit_log_path, 'r') as f:
                audit_log = json.load(f)
            
            if not audit_log:
                print("Audit log is empty.")
                return
            
            print("\n=== Audit Log (Last 10 entries) ===")
            for entry in audit_log[-10:]:
                print(f"Timestamp: {entry['timestamp']}")
                print(f"User: {entry['user']}")
                print(f"Config Type: {entry['config_type']}")
                print("---")
                
        except Exception as e:
            self.logger.error(f"Error viewing audit log: {str(e)}")
            print(f"Error viewing audit log: {str(e)}")


def main():
    """Main function for running the admin interface"""
    print("=== Risk/Protective Variant Reporting - Admin Interface ===")
    
    admin = AdminInterface()
    
    # Authenticate user
    username = input("Username: ")
    if admin.authenticate(username):
        print(f"Welcome, {username}!")
        admin.run_interactive_menu()
    else:
        print("Authentication failed.")


if __name__ == '__main__':
    main()
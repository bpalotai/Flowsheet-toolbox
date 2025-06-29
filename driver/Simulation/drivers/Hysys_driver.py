import os
import win32com.client as win32
from xlsxwriter.utility import xl_cell_to_rowcol
import time
import pandas as pd
import numpy as np
import json
from driver.Simulation.simulation_interface import SimulationInterface
import pythoncom

class HysysSimulationDriver(SimulationInterface):
    def __init__(self, hy_filename, cols_mapping=None, resultindict=False):
        """
        Initialize the HYSYS simulation driver.
        
        Args:
            hy_filename (str): Path to the HYSYS file
            cols_mapping (dict, optional): Mapping of parameters for reading/writing
            resultindict (bool, optional): Whether to return results as dictionary
        """
        self.hy_filename = hy_filename
        self.cols_mapping = cols_mapping or {}
        self.HyApp = None
        self.HyCase = None
        self.HyFlowsheet = None
        self.HyOperations = None
        self.HySolver = None
        self.HyMaterialStreams = None
        self.HyEnergyStreams = None
        self.resultindict = resultindict
        
        # Initialize default output placeholders
        self.incaseofnooutput = {}
        self._initialize_output_placeholders()
        
    def _initialize_output_placeholders(self):
        """Initialize placeholders for all output parameters"""
        if not self.cols_mapping:
            return
            
        # Add spreadsheet outputs
        if 'Spreadsheet' in self.cols_mapping.get('OutputParameters', {}):
            for k in self.cols_mapping['OutputParameters']['Spreadsheet'].keys():
                self.incaseofnooutput[k] = None
        
        # Add material stream outputs
        if 'MaterialStream' in self.cols_mapping.get('OutputParameters', {}):
            for k, v in self.cols_mapping['OutputParameters']['MaterialStream'].items():
                stream_name = v['StreamName']
                param_type = v.get('ParameterType', 'Property')
                
                if param_type == 'Property':
                    self.incaseofnooutput[k] = None
                elif param_type == 'MassFrac':
                    get_components = v.get('GetComponents', [])
                    if get_components:
                        for comp_name in get_components:
                            self.incaseofnooutput[f"{k}_{comp_name}"] = None
                    else:
                        # Placeholder to be replaced when components are known
                        self.incaseofnooutput[f"{k}_placeholder"] = None
                elif param_type == 'MassFlow':
                    get_components = v.get('GetComponents', [])
                    if get_components:
                        for comp_name in get_components:
                            self.incaseofnooutput[f"{k}_{comp_name}"] = None
                    else:
                        # Placeholder to be replaced when components are known
                        self.incaseofnooutput[f"{k}_placeholder"] = None
                elif param_type == 'MolarFlow':
                    get_components = v.get('GetComponents', [])
                    if get_components:
                        for comp_name in get_components:
                            self.incaseofnooutput[f"{k}_{comp_name}"] = None
                    else:
                        # Placeholder to be replaced when components are known
                        self.incaseofnooutput[f"{k}_placeholder"] = None
        
        # Add energy stream outputs
        if 'EnergyStream' in self.cols_mapping.get('OutputParameters', {}):
            for k in self.cols_mapping['OutputParameters']['EnergyStream'].keys():
                self.incaseofnooutput[k] = None

    def load_model(self):
        """Load the HYSYS model and initialize connections"""
        hy_visible = True
        hyFilePath = os.path.abspath(self.hy_filename)

        try:
            pythoncom.CoInitialize()

            # Initialize Aspen Hysys application
            print(' # Connecting to the Aspen Hysys App ... ')
            self.HyApp = win32.Dispatch('HYSYS.Application')
            print(' # Loading HYSYS model ... :', hyFilePath)
            self.HyCase = self.HyApp.SimulationCases.Open(hyFilePath)
            self.HyCase.Visible = hy_visible
            HySysFile = self.HyCase.Title.Value
            print(' ')
            print('HySys File: ----------  ', HySysFile)
            
            # Main Aspen Hysys Document Objects
            self.HySolver = self.HyCase.Solver  # Access to Hysys Solver
            self.HyFlowsheet = self.HyCase.Flowsheet  # Access to main Flowsheet
            self.HyOperations = self.HyFlowsheet.Operations  # Access to the Unit Operations
            self.HyMaterialStreams = self.HyFlowsheet.MaterialStreams  # Access to the material streams
            self.HyEnergyStreams = self.HyFlowsheet.EnergyStreams  # Access to the energy streams

            # Update placeholders with actual component names
            self._update_component_placeholders()
            
            return print('Model loaded successfully!')
        except Exception as e:
            print(f"Error loading model: {str(e)}")
            if "com_error" in str(type(e)).lower():
                print("COM error detected. This might be due to Hysys not running properly.")
                print("Try restarting Hysys or checking the model file.")
            return False

    def _update_component_placeholders(self):
        """Update placeholders with actual component names from streams"""
        if not self.cols_mapping:
            return
            
        temp_dict = {}  # Create a new dictionary to avoid modifying during iteration
        
        for k, v in self.incaseofnooutput.items():
            if "_placeholder" in k:
                # This is a placeholder for component-specific parameters
                base_name = k.split("_placeholder")[0]
                
                # Find the corresponding stream in the output parameters
                stream_name = None
                param_type = None
                
                # Check in MaterialStream outputs
                if 'MaterialStream' in self.cols_mapping.get('OutputParameters', {}):
                    for output_name, output_config in self.cols_mapping['OutputParameters']['MaterialStream'].items():
                        if base_name == output_name:
                            stream_name = output_config['StreamName']
                            param_type = output_config.get('ParameterType')
                            break
                
                if stream_name and param_type:
                    try:
                        # Get component names from the stream
                        comp_names = self.HyFlowsheet.MaterialStreams.Item(stream_name).FluidPackage.Components.Names
                        
                        # Add each component
                        for comp_name in comp_names:
                            temp_dict[f"{base_name}_{comp_name}"] = None
                    except Exception as e:
                        print(f"Warning: Could not get components for stream {stream_name}: {str(e)}")
            else:
                # Keep other entries as they are
                temp_dict[k] = v
        
        # Replace the original dictionary with the updated one
        self.incaseofnooutput = temp_dict

    def explore(self):
        """
        Explore the HYSYS model to discover streams, spreadsheets, and their parameters.
        
        Returns:
            dict: Dictionary containing discovered model elements
        """
        if not self.HyCase:
            print("Error: Model not loaded. Call load_model() first.")
            return {}
            
        result = {
            "MaterialStreams": [],
            "EnergyStreams": [],
            "Spreadsheets": [],
            "UnitOperations": []
        }
        
        # Default UOMs for common properties
        default_uoms = {
            "Temperature": "C",
            "Pressure": "bar_g",
            "MassFlow": "kg/h",
            "MolarFlow": "kgmole/h",
            "HeatFlow": "kJ/h"
        }
        
        # Explore Material Streams
        try:
            for i in range(self.HyMaterialStreams.Count):
                stream = self.HyMaterialStreams.Item(i)
                
                # Get basic properties with values
                properties = []
                
                # Temperature
                try:
                    temp_value = stream.Temperature.GetValue(default_uoms["Temperature"])
                    properties.append({
                        "Name": "Temperature",
                        "Value": temp_value,
                        "UOM": default_uoms["Temperature"],  # Use default UOM
                        "CanModify": stream.Temperature.CanModify
                    })
                except Exception as e:
                    print(f"Error reading temperature for {stream.Name}: {str(e)}")
                
                # Pressure
                try:
                    pressure_value = stream.Pressure.GetValue(default_uoms["Pressure"])
                    properties.append({
                        "Name": "Pressure",
                        "Value": pressure_value,
                        "UOM": default_uoms["Pressure"],  # Use default UOM
                        "CanModify": stream.Pressure.CanModify
                    })
                except Exception as e:
                    print(f"Error reading pressure for {stream.Name}: {str(e)}")
                
                # Mass Flow
                try:
                    massflow_value = stream.MassFlow.GetValue(default_uoms["MassFlow"])
                    properties.append({
                        "Name": "MassFlow",
                        "Value": massflow_value,
                        "UOM": default_uoms["MassFlow"],  # Use default UOM
                        "CanModify": stream.MassFlow.CanModify
                    })
                except Exception as e:
                    print(f"Error reading mass flow for {stream.Name}: {str(e)}")
                
                # Molar Flow
                try:
                    molarflow_value = stream.MolarFlow.GetValue(default_uoms["MolarFlow"])
                    properties.append({
                        "Name": "MolarFlow",
                        "Value": molarflow_value,
                        "UOM": default_uoms["MolarFlow"],  # Use default UOM
                        "CanModify": stream.MolarFlow.CanModify
                    })
                except Exception as e:
                    print(f"Error reading molar flow for {stream.Name}: {str(e)}")
                
                # Vapor Fraction - try different approaches
                try:
                    vaporfrac_value = None
                    # Try direct access
                    try:
                        vaporfrac_value = stream.VaporFraction.Value
                        vap_can_modify = stream.VaporFraction.CanModify
                    except:
                        # Try as a property
                        try:
                            vaporfrac_value = stream.VaporFraction
                            vap_can_modify = stream.VaporFraction.CanModify
                        except:
                            # Try as a method
                            try:
                                vaporfrac_value = stream.VaporFraction()
                                vap_can_modify = stream.VaporFraction.CanModify
                            except:
                                pass
                    
                    if vaporfrac_value is not None:
                        properties.append({
                            "Name": "VaporFraction",
                            "Value": vaporfrac_value,
                            "UOM": "",  # No UOM for vapor fraction
                            "CanModify": vap_can_modify
                        })
                except Exception as e:
                    print(f"Error reading vapor fraction for {stream.Name}: {str(e)}")
                
                # Get component information
                components = []
                try:
                    comp_names = stream.FluidPackage.Components.Names
                    
                    # Mass fractions
                    try:
                        mass_fractions = stream.ComponentMassFractionValue
                        
                        # Mass flows
                        mass_flows = stream.ComponentMassFlowValue
                        
                        # Molar flows
                        molar_flows = stream.ComponentMolarFlowValue
                        
                        # Combine component information
                        for j, comp_name in enumerate(comp_names):
                            if j < len(mass_fractions) and j < len(mass_flows) and j < len(molar_flows):
                                comp_info = {
                                    "Name": comp_name,
                                    "MassFraction": mass_fractions[j],
                                    "MassFlow": mass_flows[j],
                                    "MassFlowUOM": default_uoms["MassFlow"],
                                    "MolarFlow": molar_flows[j],
                                    "MolarFlowUOM": default_uoms["MolarFlow"],
                                    
                                }
                                components.append(comp_info)
                    except Exception as e:
                        print(f"Error reading component values for {stream.Name}: {str(e)}")
                except Exception as e:
                    print(f"Error reading components for {stream.Name}: {str(e)}")
                
                stream_info = {
                    "Name": stream.Name,
                    "Properties": properties,
                    "Components": components,
                    "MassFractionCompCanModify": all(stream.ComponentMassFraction.CanModify),
                    "MassFlowCompCanModify": all(stream.ComponentMassFlow.CanModify),
                    "MolarFlowCompCanModify": all(stream.ComponentMolarFlow.CanModify)

                }
                result["MaterialStreams"].append(stream_info)
        except Exception as e:
            print(f"Error exploring material streams: {str(e)}")
        
        # Explore Energy Streams
        try:
            for i in range(self.HyEnergyStreams.Count):
                stream = self.HyEnergyStreams.Item(i)
                stream_info = {
                    "Name": stream.Name,
                    "Properties": []
                }
                
                # Energy Flow
                try:
                    energy_value = stream.HeatFlow.GetValue(default_uoms["HeatFlow"])
                    stream_info["Properties"].append({
                        "Name": "HeatFlow",
                        "Value": energy_value,
                        "UOM": default_uoms["HeatFlow"],  # Use default UOM
                        "CanModify": stream.HeatFlow.CanModify
                    })
                except Exception as e:
                    print(f"Error reading energy flow for {stream.Name}: {str(e)}")
                    
                result["EnergyStreams"].append(stream_info)
        except Exception as e:
            print(f"Error exploring energy streams: {str(e)}")
        
        # Explore Spreadsheets
        try:
            for i in range(self.HyOperations.Count):
                op = self.HyOperations.Item(i)
                try:
                    # Check if this is a spreadsheet by trying to access Cell method
                    cell = op.Cell(0, 0)
                    
                    sheet_info = {
                        "Name": op.Name,
                        "Cells": []
                    }
                    
                    # Sample some cells (first 10x10 grid)
                    for row in range(10):
                        for col in range(10):
                            try:
                                cell = op.Cell(col, row)
                                if cell.CellValue is not None:
                                    sheet_info["Cells"].append({
                                        "Row": row,
                                        "Column": col,
                                        "Address": self._get_excel_cell_address(row, col),
                                        "Value": cell.CellValue
                                    })
                            except:
                                pass
                    
                    result["Spreadsheets"].append(sheet_info)
                except:
                    # Not a spreadsheet, must be a unit operation
                    try:
                        op_info = {
                            "Name": op.Name,
                            "Type": "Unit Operation"  # Generic type
                        }
                        result["UnitOperations"].append(op_info)
                    except Exception as e:
                        print(f"Error processing operation {i}: {str(e)}")
        except Exception as e:
            print(f"Error exploring operations: {str(e)}")
        
        return result

    def _get_excel_cell_address(self, row, col):
        """Convert row and column indices to Excel-style cell address (e.g., A1, B2)"""
        col_str = ""
        col_num = col + 1  # Convert to 1-based indexing
        
        while col_num > 0:
            col_num, remainder = divmod(col_num - 1, 26)
            col_str = chr(65 + remainder) + col_str
            
        return f"{col_str}{row + 1}"  # Convert to 1-based indexing

    def sim_write(self, data=dict()):
        """
        Write input data to the HYSYS simulation.
        
        Args:
            data (dict): Dictionary containing input parameters and values
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.HySolver.CanSolve = False
            
            # Write spreadsheet data
            if 'Spreadsheet' in self.cols_mapping.get('InputParams', {}):
                for k, v in self.cols_mapping['InputParams']['Spreadsheet'].items():
                    if k in data:
                        try:
                            spreadsheet_name = v['SpreadsheetName']
                            cell = v['Cell']
                            (rows, cols) = xl_cell_to_rowcol(cell)
                            hycellin = self.HyOperations.Item(spreadsheet_name).Cell(cols, rows)
                            hycellin.CellValue = data[k]
                            print(f'Info: Wrote {k} to spreadsheet {spreadsheet_name} cell {cell}, value: {data[k]}')
                        except Exception as e:
                            print(f'Warning: Error writing to spreadsheet parameter {k}: {str(e)}')
                    else:
                        print(f'Info: Input parameter {k} not found in data - skipping')
            
            # Write material stream data
            if 'MaterialStream' in self.cols_mapping.get('InputParams', {}):
                for k, v in self.cols_mapping['InputParams']['MaterialStream'].items():
                    if k in data:
                        try:
                            stream_name = v['StreamName']
                            param_type = v.get('ParameterType', 'Property')
                            stream = self.HyMaterialStreams.Item(stream_name)
                            
                            if param_type == 'Property':
                                # Handle basic properties like temperature, pressure, etc.
                                property_name = v['PropertyName']
                                uom = v.get('UOM')
                                
                                # Use direct property access instead of SetValue
                                if property_name == "Temperature":
                                    if uom:
                                        stream.Temperature.SetValue(data[k], uom)
                                    else:
                                        stream.Temperature.Value = data[k]
                                        
                                elif property_name == "Pressure":
                                    if uom:
                                        stream.Pressure.SetValue(data[k], uom)
                                    else:
                                        stream.Pressure.Value = data[k]

                                elif property_name == "MassFlow":
                                    if uom:
                                        stream.MassFlow.SetValue(data[k], uom)
                                    else:
                                        stream.MassFlow.Value = data[k]

                                elif property_name == "MolarFlow":
                                    if uom:
                                        stream.MolarFlow.SetValue(data[k], uom)
                                    else:
                                        stream.MolarFlow.Value = data[k]
                                else:
                                    # Try generic approach
                                    try:
                                        prop = getattr(stream, property_name)
                                        prop.Value = data[k]
                                        print(f'Info: Wrote {k} to stream {stream_name} property {property_name}, value: {data[k]}')
                                    except Exception as e:
                                        print(f'Warning: Error writing to material stream parameter {k} using generic approach: {str(e)}')

                                print(f'Info: Wrote {k} to stream {stream_name} property {property_name}, value: {data[k]}')
                            elif param_type == 'MassFrac':
                                # Handle component mass fractions
                                comp_names = stream.FluidPackage.Components.Names
                                
                                # Create a list of mass fraction values in the same order as comp_names
                                mass_frac_values = []
                                
                                if isinstance(data[k], dict):
                                    # If input is a dictionary of component fractions
                                    for comp_name in comp_names:
                                        if comp_name in data[k]:
                                            mass_frac_values.append(data[k][comp_name])
                                        else:
                                            # Get current value if not specified
                                            current_values = stream.ComponentMassFractionValue
                                            current_idx = list(comp_names).index(comp_name) if comp_name in comp_names else -1
                                            if current_idx >= 0:
                                                mass_frac_values.append(current_values[current_idx])
                                            else:
                                                mass_frac_values.append(0)
                                else:
                                    # If input is a single value (for a specific component)
                                    comp_name = v.get('ComponentName')
                                    if comp_name:
                                        current_values = list(stream.ComponentMassFractionValue)
                                        comp_idx = list(comp_names).index(comp_name) if comp_name in comp_names else -1
                                        if comp_idx >= 0:
                                            current_values[comp_idx] = data[k]
                                            mass_frac_values = current_values
                                
                                # Set all component mass fractions at once
                                if mass_frac_values:
                                    stream.ComponentMassFractionValue = mass_frac_values
                                    print(f'Info: Wrote {k} mass fractions to stream {stream_name}')
                                
                            elif param_type == 'MassFlow':
                                # Handle component mass flows
                                comp_name = v.get('ComponentName')
                                if comp_name:
                                    # Set individual component mass flow
                                    stream.ComponentMassFlowValue[list(stream.FluidPackage.Components.Names).index(comp_name)] = data[k]
                                    print(f'Info: Wrote {k} mass flow to stream {stream_name} component {comp_name}, value: {data[k]}')
                                
                            elif param_type == 'MolarFlow':
                                # Handle component molar flows
                                comp_name = v.get('ComponentName')
                                if comp_name:
                                    # Set individual component molar flow
                                    stream.ComponentMolarFlowValue[list(stream.FluidPackage.Components.Names).index(comp_name)] = data[k]
                                    print(f'Info: Wrote {k} molar flow to stream {stream_name} component {comp_name}, value: {data[k]}')
                                
                        except Exception as e:
                            print(f'Warning: Error writing to material stream parameter {k}: {str(e)}')
                    else:
                        print(f'Info: Input parameter {k} not found in data - skipping')
            
            # Write energy stream data
            if 'EnergyStream' in self.cols_mapping.get('InputParams', {}):
                for k, v in self.cols_mapping['InputParams']['EnergyStream'].items():
                    if k in data:
                        try:
                            stream_name = v['StreamName']
                            property_name = v.get('PropertyName', 'HeatFlow')
                            uom = v.get('UOM')
                            
                            stream = self.HyEnergyStreams.Item(stream_name)
                            if property_name == "HeatFlow":
                                if uom:
                                    stream.HeatFlow.Value.SetValue(data[k], uom)
                                else:
                                    stream.HeatFlow.Value = data[k]
                            else:
                                # Try generic approach
                                setattr(stream, property_name, data[k])
                            
                            print(f'Info: Wrote {k} to energy stream {stream_name} property {property_name}, value: {data[k]}')
                        except Exception as e:
                            print(f'Warning: Error writing to energy stream parameter {k}: {str(e)}')
                    else:
                        print(f'Info: Input parameter {k} not found in data - skipping')
            
            return True
        except Exception as e:
            print(f'Error in sim_write: {str(e)}')
            if "com_error" in str(type(e)).lower():
                print("COM error detected. This might be due to Hysys not running properly.")
                print("Try restarting Hysys or checking the model file.")
            return False

    def sim_run(self, max_attempts=1000, delay=0.5):
        """
        Run the HYSYS simulation.
        
        Args:
            max_attempts (int): Maximum number of attempts to check if solver is still running
            delay (float): Delay between checks in seconds
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.HySolver.CanSolve = True
            xx = 0
            
            while self.HySolver.IsSolving and xx < max_attempts:
                xx += 1
                time.sleep(delay)  # Add a small delay to prevent tight loop
            
            if xx >= max_attempts:
                print("Warning: Solver did not complete within the expected time.")
                return False
            
            return True
        except Exception as e:
            print(f"Error during simulation run: {str(e)}")
            if "com_error" in str(type(e)).lower():
                print("COM error detected. This might be due to Hysys not running properly.")
                print("Try restarting Hysys or checking the model file.")
            return False

    def sim_read(self, include_inputs=False, flatten_components=True):
        """
        Read output data from the HYSYS simulation.
        
        Args:
            include_inputs (bool): Whether to include input parameters in the output
            flatten_components (bool): Whether to flatten component-specific parameters
                If True: "Parameter_Component": Value
                If False: "Parameter": {"Component": Value, ...}
            
        Returns:
            dict: Dictionary containing output parameters and values, organized by type
        """
        # Create a dictionary to store outputs with a nested structure
        result_dict = {
            "outputs": {},
            "inputs": {} if include_inputs else None
        }
        
        # For backward compatibility, we'll also maintain a flat structure
        output_dict = {}
        
        try:
            # Read spreadsheet outputs
            if 'Spreadsheet' in self.cols_mapping.get('OutputParameters', {}):
                for k, v in self.cols_mapping['OutputParameters']['Spreadsheet'].items():
                    try:
                        spreadsheet_name = v['SpreadsheetName']
                        cell = v['Cell']
                        uom = v.get('UOM', '')
                    
                        (rows, cols) = xl_cell_to_rowcol(cell)
                        hycellout = self.HyOperations.Item(spreadsheet_name).Cell(cols, rows)
                        
                        if uom and hasattr(hycellout, 'Variable'):
                            value = hycellout.Variable.GetValue(uom)
                        else:
                            value = hycellout.CellValue
                        
                        # Store in the nested structure with UOM
                        result_dict["outputs"][k] = {
                            "value": value,
                            "uom": uom
                        }
                        
                        # For backward compatibility, just store the value in the flat structure
                        output_dict[k] = value
                    except Exception as e:
                        print(f"Error reading spreadsheet output {k}: {str(e)}")
                        result_dict["outputs"][k] = {
                            "value": None,
                            "uom": v.get('UOM', '')
                        }
                        output_dict[k] = None

            # Read material stream outputs
            if 'MaterialStream' in self.cols_mapping.get('OutputParameters', {}):
                for k, v in self.cols_mapping['OutputParameters']['MaterialStream'].items():
                    try:
                        stream_name = v['StreamName']
                        param_type = v.get('ParameterType', 'Property')
                        uom = v.get('UOM', '')
                        
                        # Get the stream object
                        stream = self.HyMaterialStreams.Item(stream_name)
                        
                        if param_type == 'Property':
                            # Handle basic properties like temperature, pressure, etc.
                            property_name = v['PropertyName']
                            
                            try:
                                if property_name == "Temperature":
                                    if uom:
                                        value = stream.Temperature.GetValue(uom)
                                    else:
                                        value = stream.Temperature.Value
                                elif property_name == "Pressure":
                                    if uom:
                                        value = stream.Pressure.GetValue(uom)
                                    else:
                                        value = stream.Pressure.Value
                                elif property_name == "MassFlow":
                                    if uom:
                                        value = stream.MassFlow.GetValue(uom)
                                    else:
                                        value = stream.MassFlow.Value
                                elif property_name == "MolarFlow":
                                    if uom:
                                        value = stream.MolarFlow.GetValue(uom)
                                    else:
                                        value = stream.MolarFlow.Value
                                elif property_name == "VaporFraction":
                                    value = stream.VaporFraction.Value
                                    uom = ""  # No UOM for vapor fraction
                                else:
                                    # Try generic approach with direct property access
                                    prop = getattr(stream, property_name)
                                    value = prop.Value
                                
                                # Store in the nested structure with UOM
                                result_dict["outputs"][k] = {
                                    "value": value,
                                    "uom": uom
                                }
                                
                                # For backward compatibility, just store the value in the flat structure
                                output_dict[k] = value
                            except Exception as e:
                                print(f"Error reading {property_name} for stream {stream_name}: {str(e)}")
                                result_dict["outputs"][k] = {
                                    "value": None,
                                    "uom": uom
                                }
                                output_dict[k] = None
                        
                        elif param_type == 'MassFrac':
                            # Get component names directly
                            comp_names = stream.FluidPackage.Components.Names
                            
                            # Get mass fraction values directly
                            comp_values = stream.ComponentMassFractionValue
                            
                            # Create dictionary of component names and values
                            comp_dict = {comp_names[i]: comp_values[i] for i in range(len(comp_names))}
                            
                            # Get specific components or all components
                            get_components = v.get('GetComponents', [])
                            scale_factor = v.get('ScaleFactor', 1.0)  # For converting to percentage, etc.
                            
                            # Determine UOM based on scale factor
                            if scale_factor == 100.0:
                                comp_uom = "%"  # Percentage
                            elif scale_factor == 1.0:
                                comp_uom = "fraction"  # Fraction
                            else:
                                comp_uom = f"× {scale_factor}"  # Custom scale
                            
                            # Filter components if specified
                            if get_components:
                                comp_dict = {comp: comp_dict[comp] * scale_factor 
                                            for comp in get_components if comp in comp_dict}
                            else:
                                # Apply scale factor to all components
                                comp_dict = {comp: value * scale_factor for comp, value in comp_dict.items()}
                            
                            # Store results based on flatten_components flag
                            if flatten_components:
                                # Flatten: "Parameter_Component": Value
                                for comp_name, value in comp_dict.items():
                                    result_dict["outputs"][f"{k}_{comp_name}"] = {
                                        "value": value,
                                        "uom": comp_uom
                                    }
                                    output_dict[f"{k}_{comp_name}"] = value
                            else:
                                # Nested: "Parameter": {"Component": {"value": Value, "uom": UOM}, ...}
                                comp_dict_with_uom = {
                                    comp_name: {"value": value, "uom": comp_uom} 
                                    for comp_name, value in comp_dict.items()
                                }
                                result_dict["outputs"][k] = comp_dict_with_uom
                                output_dict[k] = comp_dict  # Keep original format for backward compatibility
                        
                        elif param_type in ['MassFlow', 'MolarFlow']:
                            # Get component names directly
                            comp_names = stream.FluidPackage.Components.Names
                            
                            # Get flow values directly
                            if param_type == 'MassFlow':
                                comp_values = stream.ComponentMassFlowValue
                                if not uom:
                                    uom = "kg/h"  # Default UOM for mass flow
                            else:  # MolarFlow
                                comp_values = stream.ComponentMolarFlowValue
                                if not uom:
                                    uom = "kgmole/h"  # Default UOM for molar flow
                            
                            # Create dictionary of component names and values
                            comp_dict = {comp_names[i]: comp_values[i] for i in range(len(comp_names))}
                            
                            # Get specific components or all components
                            get_components = v.get('GetComponents', [])
                            
                            # Filter components if specified
                            if get_components:
                                comp_dict = {comp: comp_dict[comp] for comp in get_components if comp in comp_dict}
                            
                            # Store results based on flatten_components flag
                            if flatten_components:
                                # Flatten: "Parameter_Component": Value
                                for comp_name, value in comp_dict.items():
                                    result_dict["outputs"][f"{k}_{comp_name}"] = {
                                        "value": value,
                                        "uom": uom
                                    }
                                    output_dict[f"{k}_{comp_name}"] = value
                            else:
                                # Nested: "Parameter": {"Component": {"value": Value, "uom": UOM}, ...}
                                comp_dict_with_uom = {
                                    comp_name: {"value": value, "uom": uom} 
                                    for comp_name, value in comp_dict.items()
                                }
                                result_dict["outputs"][k] = comp_dict_with_uom
                                output_dict[k] = comp_dict  # Keep original format for backward compatibility
                    
                    except Exception as e:
                        print(f"Error reading material stream output {k}: {str(e)}")
                        result_dict["outputs"][k] = {
                            "value": None,
                            "uom": v.get('UOM', '')
                        }
                        output_dict[k] = None

            # Read energy stream outputs
            if 'EnergyStream' in self.cols_mapping.get('OutputParameters', {}):
                for k, v in self.cols_mapping['OutputParameters']['EnergyStream'].items():
                    try:
                        stream_name = v['StreamName']
                        property_name = v.get('PropertyName', 'HeatFlow')
                        uom = v.get('UOM', '')
                        
                        stream = self.HyEnergyStreams.Item(stream_name)
                        
                        # Use direct property access
                        if property_name == "HeatFlow":
                            if uom:
                                value = stream.HeatFlow.GetValue(uom)
                            else:
                                value = stream.HeatFlow.Value
                        else:
                            # Try generic approach
                            prop = getattr(stream, property_name)
                            value = prop.Value
                        
                        # Store in the nested structure with UOM
                        result_dict["outputs"][k] = {
                            "value": value,
                            "uom": uom
                        }
                        
                        # For backward compatibility, just store the value in the flat structure
                        output_dict[k] = value
                    
                    except Exception as e:
                        print(f"Error reading energy stream output {k}: {str(e)}")
                        result_dict["outputs"][k] = {
                            "value": None,
                            "uom": v.get('UOM', '')
                        }
                        output_dict[k] = None
            
            # Optionally read input parameters as well
            if include_inputs:
                # Read spreadsheet inputs
                if 'Spreadsheet' in self.cols_mapping.get('InputParams', {}):
                    for k, v in self.cols_mapping['InputParams']['Spreadsheet'].items():
                        try:
                            spreadsheet_name = v['SpreadsheetName']
                            cell = v['Cell']
                            uom = v.get('UOM', '')
                            
                            (rows, cols) = xl_cell_to_rowcol(cell)
                            hycellin = self.HyOperations.Item(spreadsheet_name).Cell(cols, rows)
                            
                            value = hycellin.CellValue
                            
                            # Store in the nested structure with UOM
                            result_dict["inputs"][k] = {
                                "value": value,
                                "uom": uom
                            }
                            
                            # For backward compatibility, just store the value in the flat structure
                            output_dict[f"Input_{k}"] = value
                        except Exception as e:
                            print(f"Error reading spreadsheet input {k}: {str(e)}")
                            result_dict["inputs"][k] = {
                                "value": None,
                                "uom": v.get('UOM', '')
                            }
                            output_dict[f"Input_{k}"] = None
                
                # Read material stream inputs
                if 'MaterialStream' in self.cols_mapping.get('InputParams', {}):
                    for k, v in self.cols_mapping['InputParams']['MaterialStream'].items():
                        try:
                            stream_name = v['StreamName']
                            param_type = v.get('ParameterType', 'Property')
                            uom = v.get('UOM', '')
                            
                            # Get the stream object
                            stream = self.HyMaterialStreams.Item(stream_name)
                            
                            if param_type == 'Property':
                                # Handle basic properties
                                property_name = v['PropertyName']
                                
                                if property_name == "Temperature":
                                    if uom:
                                        value = stream.Temperature.GetValue(uom)
                                    else:
                                        value = stream.Temperature.Value
                                elif property_name == "Pressure":
                                    if uom:
                                        value = stream.Pressure.GetValue(uom)
                                    else:
                                        value = stream.Pressure.Value
                                elif property_name == "MassFlow":
                                    if uom:
                                        value = stream.MassFlow.GetValue(uom)
                                    else:
                                        value = stream.MassFlow.Value
                                elif property_name == "MolarFlow":
                                    if uom:
                                        value = stream.MolarFlow.GetValue(uom)
                                    else:
                                        value = stream.MolarFlow.Value
                                else:
                                    # Try generic approach
                                    value = getattr(stream, property_name).Value
                                
                                # Store in the nested structure with UOM
                                result_dict["inputs"][k] = {
                                    "value": value,
                                    "uom": uom
                                }
                                
                                # For backward compatibility, just store the value in the flat structure
                                output_dict[f"Input_{k}"] = value
                            
                            elif param_type in ['MassFrac', 'MassFlow', 'MolarFlow']:
                                # Get component names and values
                                comp_names = stream.FluidPackage.Components.Names
                                
                                if param_type == 'MassFrac':
                                    comp_values = stream.ComponentMassFractionValue
                                    scale_factor = v.get('ScaleFactor', 1.0)
                                    
                                    # Determine UOM based on scale factor
                                    if scale_factor == 100.0:
                                        comp_uom = "%"  # Percentage
                                    elif scale_factor == 1.0:
                                        comp_uom = "fraction"  # Fraction
                                    else:
                                        comp_uom = f"× {scale_factor}"  # Custom scale
                                elif param_type == 'MassFlow':
                                    comp_values = stream.ComponentMassFlowValue
                                    scale_factor = 1.0
                                    comp_uom = uom if uom else "kg/h"  # Default UOM for mass flow
                                else:  # MolarFlow
                                    comp_values = stream.ComponentMolarFlowValue
                                    scale_factor = 1.0
                                    comp_uom = uom if uom else "kgmole/h"  # Default UOM for molar flow
                                
                                # Create dictionary of component names and values
                                comp_dict = {comp_names[i]: comp_values[i] * scale_factor for i in range(len(comp_names))}
                                
                                # Store results based on flatten_components flag
                                if flatten_components:
                                    # Flatten: "Parameter_Component": Value
                                    for comp_name, value in comp_dict.items():
                                        result_dict["inputs"][f"{k}_{comp_name}"] = {
                                            "value": value,
                                            "uom": comp_uom
                                        }
                                        output_dict[f"Input_{k}_{comp_name}"] = value
                                else:
                                    # Nested: "Parameter": {"Component": {"value": Value, "uom": UOM}, ...}
                                    comp_dict_with_uom = {
                                        comp_name: {"value": value, "uom": comp_uom} 
                                        for comp_name, value in comp_dict.items()
                                    }
                                    result_dict["inputs"][k] = comp_dict_with_uom
                                    
                                    # For backward compatibility, still flatten in output_dict
                                    for comp_name, value in comp_dict.items():
                                        output_dict[f"Input_{k}_{comp_name}"] = value
                        
                        except Exception as e:
                            print(f"Error reading material stream input {k}: {str(e)}")
                            result_dict["inputs"][k] = {
                                "value": None,
                                "uom": v.get('UOM', '')
                            }
                            output_dict[f"Input_{k}"] = None
                
                # Read energy stream inputs
                if 'EnergyStream' in self.cols_mapping.get('InputParams', {}):
                    for k, v in self.cols_mapping['InputParams']['EnergyStream'].items():
                        try:
                            stream_name = v['StreamName']
                            property_name = v.get('PropertyName', 'HeatFlow')
                            uom = v.get('UOM', '')
                            
                            stream = self.HyEnergyStreams.Item(stream_name)
                            
                            if property_name == "HeatFlow":
                                if uom:
                                    value = stream.HeatFlow.GetValue(uom)
                                else:
                                    value = stream.HeatFlow.Value
                            else:
                                # Try generic approach
                                value = getattr(stream, property_name).Value
                            
                            # Store in the nested structure with UOM
                            result_dict["inputs"][k] = {
                                "value": value,
                                "uom": uom
                            }
                            
                            # For backward compatibility, just store the value in the flat structure
                            output_dict[f"Input_{k}"] = value
                        
                        except Exception as e:
                            print(f"Error reading energy stream input {k}: {str(e)}")
                            result_dict["inputs"][k] = {
                                "value": None,
                                "uom": v.get('UOM', '')
                            }
                            output_dict[f"Input_{k}"] = None

            # If resultindict is True, return the nested structure, otherwise return the flat structure
            if self.resultindict:
                return result_dict
            else:
                return output_dict
        
        except Exception as e:
            print(f"Error in sim_read: {str(e)}")
            if self.resultindict:
                return {"outputs": self.incaseofnooutput, "inputs": {} if include_inputs else None}
            else:
                return self.incaseofnooutput

    def predict(self, data=dict(), include_inputs=False, flatten_components=True):
        """
        Run a prediction with the HYSYS model.
        
        Args:
            data (dict): Dictionary containing input parameters and values
            include_inputs (bool): Whether to include input parameters in the output
            flatten_components (bool): Whether to flatten component-specific parameters
                
        Returns:
            dict: Dictionary containing output parameters and values
        """
        output = {}
        
        try:
            retd = self.sim_write(data)
            
            if retd:
                solved = self.sim_run()
                
                if solved:
                    try:
                        # Set resultindict temporarily based on what the user wants
                        original_resultindict = self.resultindict
                        
                        # Read the simulation results
                        output = self.sim_read(include_inputs=include_inputs, 
                                            flatten_components=flatten_components)
                        
                        # Restore the original resultindict setting
                        self.resultindict = original_resultindict
                    except Exception as e:
                        print(f'Read error!!! Model will be reloaded!!! {str(e)}')
                        self.close()
                        time.sleep(5)
                        self.load_model()
                        time.sleep(10)
                        if self.resultindict:
                            output = {"outputs": self.incaseofnooutput, "inputs": {} if include_inputs else None}
                        else:
                            output = self.incaseofnooutput
                else:
                    print("Simulation did not solve successfully. Using default output values.")
                    if self.resultindict:
                        output = {"outputs": self.incaseofnooutput, "inputs": {} if include_inputs else None}
                    else:
                        output = self.incaseofnooutput
            else:
                print("Failed to write inputs to simulation. Using default output values.")
                if self.resultindict:
                    output = {"outputs": self.incaseofnooutput, "inputs": {} if include_inputs else None}
                else:
                    output = self.incaseofnooutput
        except Exception as e:
            print(f"Error in predict: {str(e)}")
            if self.resultindict:
                output = {"outputs": self.incaseofnooutput, "inputs": {} if include_inputs else None}
            else:
                output = self.incaseofnooutput
        
        return output

    def convert_to_dataframe(self, sim_read_result):
        """
        Convert simulation read results to a pandas DataFrame with additional metadata columns.
        
        Args:
            sim_read_result (dict): The result from sim_read method
            
        Returns:
            pandas.DataFrame: DataFrame with columns for parameter type, source type, source name, parameter name, and value
        """
        # Create lists to store the data
        data_rows = []
        
        # Process each parameter in the simulation results
        for param_name, value in sim_read_result.items():
            # Default values
            param_type = "Unknown"
            source_type = "Unknown"
            source_name = "Unknown"
            uom = ""
            display_name = param_name
            
            # Determine if it's an input or output parameter
            is_input = param_name.startswith("Input_")
            if is_input:
                param_type = "Input"
                base_name = param_name[6:]  # Remove "Input_" prefix
            else:
                param_type = "Output"
                base_name = param_name
            
            # Extract component name if present
            component_name = None
            if "_" in base_name:
                parts = base_name.split("_", 1)
                if len(parts) > 1:
                    base_param = parts[0]
                    component_name = parts[1]
                    display_name = component_name
            else:
                base_param = base_name
            
            # Check parameter mappings to get metadata
            for mapping_type, mapping_dict in [
                ('Spreadsheet', 'Spreadsheet'),
                ('MaterialStream', 'MaterialStream'),
                ('EnergyStream', 'EnergyStream')
            ]:
                # Check in input parameters
                if is_input and mapping_dict in self.cols_mapping.get('InputParams', {}):
                    if base_param in self.cols_mapping['InputParams'][mapping_dict]:
                        config = self.cols_mapping['InputParams'][mapping_dict][base_param]
                        source_type = mapping_type
                        
                        if mapping_type == 'Spreadsheet':
                            source_name = config.get('SpreadsheetName', 'Unknown')
                            uom = config.get('UOM', '')
                        else:  # Stream types
                            source_name = config.get('StreamName', 'Unknown')
                            uom = config.get('UOM', '')
                            
                            # For component-specific parameters
                            if component_name and config.get('ParameterType') in ['MassFrac', 'MassFlow', 'MolarFlow']:
                                display_name = f"{config.get('ParameterType')} of {component_name}"
                
                # Check in output parameters
                elif not is_input and mapping_dict in self.cols_mapping.get('OutputParameters', {}):
                    if base_param in self.cols_mapping['OutputParameters'][mapping_dict]:
                        config = self.cols_mapping['OutputParameters'][mapping_dict][base_param]
                        source_type = mapping_type
                        
                        if mapping_type == 'Spreadsheet':
                            source_name = config.get('SpreadsheetName', 'Unknown')
                            uom = config.get('UOM', '')
                        else:  # Stream types
                            source_name = config.get('StreamName', 'Unknown')
                            uom = config.get('UOM', '')
                            
                            # For component-specific parameters
                            if component_name and config.get('ParameterType') in ['MassFrac', 'MassFlow', 'MolarFlow']:
                                display_name = f"{config.get('ParameterType')} of {component_name}"
            
            # Add the parameter to the data rows
            data_rows.append({
                'Parameter Type': param_type,
                'Parameter Name': display_name,
                'Full Parameter Name': param_name,
                'Source Type': source_type,
                'Source Name': source_name,
                'Value': value,
                'Unit': uom,
                'Component': component_name
            })
        
        # Create DataFrame
        if data_rows:
            df = pd.DataFrame(data_rows)
            return df
        else:
            return pd.DataFrame()

    def save_mapping(self, filename):
        """
        Save the current parameter mapping to a JSON file.
        
        Args:
            filename (str): Path to save the mapping file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(filename, 'w') as f:
                json.dump(self.cols_mapping, f, indent=4)
            print(f"Mapping saved to {filename}")
            return True
        except Exception as e:
            print(f"Error saving mapping: {str(e)}")
            return False
    
    def load_mapping(self, filename):
        """
        Load parameter mapping from a JSON file.
        
        Args:
            filename (str): Path to the mapping file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(filename, 'r') as f:
                self.cols_mapping = json.load(f)
            
            # Reinitialize output placeholders with the new mapping
            self.incaseofnooutput = {}
            self._initialize_output_placeholders()
            
            print(f"Mapping loaded from {filename}")
            return True
        except Exception as e:
            print(f"Error loading mapping: {str(e)}")
            return False

    def close(self):
        """
        Close the Hysys case and application.
        """
        try:
            # First close the case
            if self.HyCase:
                self.HyCase.Close()
            
            # Then quit the application
            if self.HyApp:
                self.HyApp.Quit()
                
            print("Hysys application closed successfully.")
        except Exception as e:
            print(f"Error closing Hysys application: {str(e)}")
        
        # Set references to None to help with garbage collection
        self.HyCase = None
        self.HyApp = None
        self.HyFlowsheet = None
        self.HyOperations = None
        self.HySolver = None
        self.HyMaterialStreams = None
        self.HyEnergyStreams = None
        try:
            pythoncom.CoUninitialize()
        except:
            pass


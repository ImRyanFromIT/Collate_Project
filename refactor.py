#!/usr/bin/env python3
import json
import sys
import os
import pandas as pd
from functools import lru_cache
from datetime import datetime, timedelta
import argparse
import glob
import re

def load_config():
    """Load configuration from config.json"""
    with open('config.json', 'r') as f:
        return json.load(f)

CONFIG = load_config()

class SimpleCache:
    def __init__(self, ttl_seconds=3600):
        self._cache = {}
        self._ttl = timedelta(seconds=ttl_seconds)
    
    def get(self, key):
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._ttl:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key, value):
        self._cache[key] = (value, datetime.now())
    
    def clear(self):
        self._cache.clear()

cache = SimpleCache(ttl_seconds=CONFIG['cache']['ttl_seconds'])

def parse_ticket(ticket_file_path):
    """
    Extract hostnames from local .txt ticket file.
    Input: Path to .txt file containing ticket description
    Returns: {"hostnames": ["hostname1", "hostname2", ...]}
    """
    try:
        with open(ticket_file_path, 'r', encoding='utf-8') as f:
            description = f.read()
        
        if not description.strip():
            return {"hostnames": []}
        
        pattern = r'Server:\s*([^\s\n]+)'  # Match "Server: hostname"
        hostnames = re.findall(pattern, description, re.IGNORECASE)
        
        # Clean and deduplicate hostnames
        hostnames = [hostname.strip() for hostname in hostnames if hostname.strip()]
        unique_hostnames = list(dict.fromkeys(hostnames)) 
        
        return {"hostnames": unique_hostnames}
    
    except FileNotFoundError:
        return {"hostnames": [], "error": f"Ticket file not found: {ticket_file_path}"}
    except Exception as e:
        return {"hostnames": [], "error": str(e)}

def get_support_group(hostname, use_cache=True):
    """
    Find support group for a hostname from CSV file.
    Uses configurable column mappings from config.json
    Returns: {"hostname": str, "support_group": str|None, "found": bool}
    """
    if use_cache and CONFIG['cache']['enabled']:
        cached_result = cache.get(f"support_group:{hostname}")
        if cached_result is not None:
            return cached_result
    
    try:
        csv_file_path = CONFIG['csv_files']['assets_csv']
        hostname_col = CONFIG['csv_columns']['assets_csv']['hostname_column']
        support_group_col = CONFIG['csv_columns']['assets_csv']['support_group_column']
        
        df = pd.read_csv(csv_file_path)
        
        # Validate column indices
        max_col_needed = max(hostname_col, support_group_col)
        if len(df.columns) <= max_col_needed:
            return {"hostname": hostname, "support_group": None, "found": False, 
                   "error": f"CSV file needs at least {max_col_needed + 1} columns, found {len(df.columns)}."}
        
        # Case-insensitive hostname lookup
        hostname_upper = hostname.strip().upper()
        hostname_match = df[df.iloc[:, hostname_col].str.strip().str.upper() == hostname_upper]
        
        if not hostname_match.empty:
            support_group = hostname_match.iloc[0, support_group_col] if pd.notna(hostname_match.iloc[0, support_group_col]) else None
            result = {"hostname": hostname, "support_group": support_group, "found": True}
            
            if CONFIG['cache']['enabled']:
                cache.set(f"support_group:{hostname}", result)
            return result
        
        result = {"hostname": hostname, "support_group": None, "found": False}
        if CONFIG['cache']['enabled']:
            cache.set(f"support_group:{hostname}", result)
        return result
        
    except FileNotFoundError:
        return {"hostname": hostname, "support_group": None, "found": False, "error": f"CSV file not found: {CONFIG['csv_files']['assets_csv']}"}
    except KeyError as e:
        return {"hostname": hostname, "support_group": None, "found": False, "error": f"Configuration missing: {str(e)}"}
    except Exception as e:
        return {"hostname": hostname, "support_group": None, "found": False, "error": str(e)}

def get_app_owners(support_group, use_cache=True):
    """
    Find app owners for a support group from CSV file.
    Uses configurable column mappings from config.json
    Returns: {"support_group": str, "contacts": {...}, "found": bool}
    """
    if use_cache and CONFIG['cache']['enabled']:
        cached_result = cache.get(f"app_owners:{support_group}")
        if cached_result is not None:
            return cached_result
    
    try:
        csv_file_path = CONFIG['csv_files']['email_distros_csv']
        support_group_col = CONFIG['csv_columns']['email_distros_csv']['support_group_column']
        email_distros_col = CONFIG['csv_columns']['email_distros_csv']['email_distros_column']
        individual_contacts_col = CONFIG['csv_columns']['email_distros_csv']['individual_contacts_column']
        notes_col = CONFIG['csv_columns']['email_distros_csv']['notes_column']
        
        df = pd.read_csv(csv_file_path)
        
        # Validate column indices
        max_col_needed = max(support_group_col, email_distros_col, individual_contacts_col, notes_col)
        if len(df.columns) <= max_col_needed:
            return {"support_group": support_group, "contacts": {}, "found": False, 
                   "error": f"CSV file needs at least {max_col_needed + 1} columns, found {len(df.columns)}."}
        
        # Case-insensitive support group lookup
        support_group_upper = support_group.strip().upper()
        group_match = df[df.iloc[:, support_group_col].str.strip().str.upper() == support_group_upper]
        
        if not group_match.empty:
            result = {
                "support_group": support_group,
                "contacts": {
                    "app_owner": group_match.iloc[0, support_group_col] if pd.notna(group_match.iloc[0, support_group_col]) else None,
                    "email_distros": group_match.iloc[0, email_distros_col] if pd.notna(group_match.iloc[0, email_distros_col]) else None,
                    "individual_contacts": group_match.iloc[0, individual_contacts_col] if pd.notna(group_match.iloc[0, individual_contacts_col]) else None,
                    "notes": group_match.iloc[0, notes_col] if pd.notna(group_match.iloc[0, notes_col]) else None
                },
                "found": True
            }
            
            if CONFIG['cache']['enabled']:
                cache.set(f"app_owners:{support_group}", result)
            return result
        
        result = {"support_group": support_group, "contacts": {}, "found": False}
        if CONFIG['cache']['enabled']:
            cache.set(f"app_owners:{support_group}", result)
        return result
        
    except FileNotFoundError:
        return {"support_group": support_group, "contacts": {}, "found": False, "error": f"CSV file not found: {CONFIG['csv_files']['email_distros_csv']}"}
    except KeyError as e:
        return {"support_group": support_group, "contacts": {}, "found": False, "error": f"Configuration missing: {str(e)}"}
    except Exception as e:
        return {"support_group": support_group, "contacts": {}, "found": False, "error": str(e)}

def process_tickets(file_inputs, is_batch=False):
    """
    Process single ticket file or multiple files/patterns and group by support teams.
    
    Args:
        file_inputs: str (single file path) or list (file patterns for batch processing)
        is_batch: bool indicating whether this is batch processing
        
    Returns:
        dict: Processing results with hostnames grouped by support teams
    """
    # Normalize input to list format
    if isinstance(file_inputs, str):
        file_patterns = [file_inputs]
    else:
        file_patterns = file_inputs
    
    # Collect hostnames from all files
    all_hostnames = []
    processed_files = []
    file_errors = []
    
    for pattern in file_patterns:
        # For single file mode, treat pattern as direct file path
        if not is_batch:
            files = [pattern]
        else:
            files = glob.glob(pattern)
        
        for file_path in files:
            try:
                parse_result = parse_ticket(file_path)
                hostnames = parse_result.get('hostnames', [])
                
                all_hostnames.extend(hostnames)  # Extend even if empty - more concise
                processed_files.append(file_path)
                
                if 'error' in parse_result:
                    file_errors.append(f"{file_path}: {parse_result['error']}")
                    
            except Exception as e:
                file_errors.append(f"{file_path}: {str(e)}")
    
    # For batch processing, deduplicate hostnames
    if is_batch:
        unique_hostnames = list(dict.fromkeys(all_hostnames))
    else:
        unique_hostnames = all_hostnames
    
    # Handle no hostnames found
    if not unique_hostnames:
        result = {
            "status": "success",
            "message": "No hostnames found in ticket" + ("s" if is_batch else ""),
            "results": {},
            "errors": {
                "hostnames_not_found": []
            }
        }
        
        # Add batch-specific fields
        if is_batch:
            result["files_processed"] = processed_files
            result["errors"]["file_errors"] = file_errors
        else:
            # For single file, include parse errors in main errors
            if file_errors:
                result["errors"] = file_errors[0].split(": ", 1)[1] if file_errors else {}
        
        return result
    
    # Group hostnames by support group
    groups = {}
    not_found = []
    
    for hostname in unique_hostnames:
        support_info = get_support_group(hostname)
        
        if not support_info['found']:
            not_found.append(hostname)
            continue
        
        support_group = support_info['support_group']
        
        # Get app owners/contacts (only lookup once per support group)
        if support_group not in groups:
            owner_info = get_app_owners(support_group)
            groups[support_group] = {
                "hostnames": [],
                "support_group_name": support_group,
                "contacts": owner_info.get('contacts', {}) if owner_info['found'] else {},
                "contact_lookup_successful": owner_info['found']
            }
        
        groups[support_group]["hostnames"].append(hostname)
    
    # Build result structure
    result = {
        "status": "success",
        "summary": {
            "total_hostnames": len(unique_hostnames),
            "grouped_into": len(groups),
            "not_found": len(not_found)
        },
        "results": groups,
        "errors": {
            "hostnames_not_found": not_found
        }
    }
    
    # Add batch-specific fields
    if is_batch:
        result["summary"]["files_processed"] = len(processed_files)
        result["files_processed"] = processed_files
        result["errors"]["file_errors"] = file_errors
    
    return result

def format_results(results):
    """Format results for display"""
    output = []
    
    output.append("\n=== TICKET PROCESSING RESULTS ===\n")
    
    if 'summary' in results:
        if 'files_processed' in results['summary']:
            output.append(f"Files Processed: {results['summary']['files_processed']}")
        output.append(f"Total Hostnames: {results['summary']['total_hostnames']}")
        output.append(f"Support Groups: {results['summary']['grouped_into']}")
        output.append(f"Not Found: {results['summary']['not_found']}\n")
    
    if 'files_processed' in results:
        output.append("Processed Files:")
        for file_path in results['files_processed']:
            output.append(f"  - {file_path}")
        output.append("")
    
    if results.get('results'):
        for group_name, group_data in results['results'].items():
            output.append(f"\n[{group_name}]")
            output.append(f"Hostnames: {', '.join(group_data['hostnames'])}")
            
            contacts = group_data.get('contacts', {})
            if contacts:
                if contacts.get('email_distros'):
                    output.append(f"Email: {contacts['email_distros']}")
                if contacts.get('individual_contacts'):
                    output.append(f"Contacts: {contacts['individual_contacts']}")
                if contacts.get('notes'):
                    output.append(f"Notes: {contacts['notes']}")
            else:
                output.append("Contact information not found")
    
    if results.get('errors', {}).get('hostnames_not_found'):
        output.append(f"\nHostnames not found: {', '.join(results['errors']['hostnames_not_found'])}")
    
    if results.get('errors', {}).get('file_errors'):
        output.append(f"\nFile errors:")
        for error in results['errors']['file_errors']:
            output.append(f"  - {error}")
    
    return '\n'.join(output)

def main():
    parser = argparse.ArgumentParser(description='Refactored Ticket Processing System - CSV Based')
    parser.add_argument('--ticket', type=str, help='Process a single ticket file (.txt)')
    parser.add_argument('--batch', nargs='+', help='Process multiple ticket files')
    parser.add_argument('--lookup', type=str, help='Look up support group for a hostname')
    parser.add_argument('--contacts', type=str, help='Look up contacts for a support group')
    parser.add_argument('--clear-cache', action='store_true', help='Clear the cache')
    
    args = parser.parse_args()
    
    if args.clear_cache:
        cache.clear()
        print("Cache cleared.")
        return
    
    if args.lookup:
        result = get_support_group(args.lookup)
        if result['found']:
            print(f"Hostname: {result['hostname']}")
            print(f"Support Group: {result['support_group']}")
        else:
            print(f"Hostname '{args.lookup}' not found")
            if 'error' in result:
                print(f"Error: {result['error']}")
        return
    
    if args.contacts:
        result = get_app_owners(args.contacts)
        if result['found']:
            print(f"Support Group: {result['support_group']}")
            contacts = result.get('contacts', {})
            if contacts.get('email_distros'):
                print(f"Email: {contacts['email_distros']}")
            if contacts.get('individual_contacts'):
                print(f"Contacts: {contacts['individual_contacts']}")
            if contacts.get('notes'):
                print(f"Notes: {contacts['notes']}")
        else:
            print(f"Support group '{args.contacts}' not found")
            if 'error' in result:
                print(f"Error: {result['error']}")
        return
    
    if args.ticket:
        try:
            results = process_tickets(args.ticket, is_batch=False)
            print(format_results(results))
        except Exception as e:
            print(f"Error processing ticket: {str(e)}")
            sys.exit(1)
        return
    
    if args.batch:
        try:
            results = process_tickets(args.batch, is_batch=True)
            print(format_results(results))
        except Exception as e:
            print(f"Error processing batch: {str(e)}")
            sys.exit(1)
        return
    
    parser.print_help()

if __name__ == "__main__":
    main()
